# -*- coding: UTF-8 -*-
"""
交易服务与基地每日结算测试
==========================
- 交易服务（trade_service）：资源类型去重、交易员倍率与上下限、供需与价格约束、交易截断、自动交易返回值及每日供需波动。
- 基地每日结算（daily_base_service）：香薰疗愈次数随疗养庭院等级刷新，以及定期体检抽选与周期清空。
- 基地跨日提示（basement.update_base_resouce_newday）：有自动交易成交时绘制一条贸易部结算提示，无成交时不绘制。
"""

import sys
from unittest import mock

from Script.Config import game_config
from Script.Core import get_text
from Script.Design import basement
from Script.Kernel import core
from Script.Modules.domains import action_info, economy, facility
from Script.Modules.domains import physical_exam, tallies, warehouse
from Script.Modules.domains import work
from Script.Modules.gameplay_resolution import agriculture_service
from Script.Modules.gameplay_resolution import assembly_service
from Script.Modules.gameplay_resolution import daily_base_service
from Script.Modules.gameplay_resolution import prison_service
from Script.Modules.gameplay_resolution import trade_service, working
from Script.UI.Moudle import draw
from tests import chara_abilities as ca
from tests.fast.base import FastTestCase

COURTYARD = 16
""" 疗养庭院设施编号 """
TALK = 40
""" 话术技能能力编号 """
SELL_LINE = "  · 自动卖出{0} x {1}，单价{2}，总计{3}"
""" 自动卖出成交明细的格式化模板 """
BUY_LINE = "  · 自动买入{0} x {1}，单价{2}，总计{3}"
""" 自动买入成交明细的格式化模板 """
VISITOR_PANEL = "Script.UI.Panel.invite_visitor_panel"
""" 访客面板模块的完整导入路径 """


def _plain_resource() -> int:
    """从配置中选取一个可买卖且价格不低于 100 的普通资源编号"""
    for rid, data in game_config.config_resouce.items():
        if (
            rid not in (0, 1)
            and data.price >= 100
            and data.cant_buy == 0
            and data.type not in {"无", "货币", get_text._("特产")}
        ):
            return rid
    raise AssertionError("配置里没有可以买卖的普通资源")


class TradeServiceTest(FastTestCase):
    """资源交易服务（trade_service）的倍率、价格、成交截断与自动交易测试"""

    def setUp(self) -> None:
        """创建博士与主副交易员角色，打开工作集上下文并准备测试资源与仓容"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "主交易员")
        self.world.chara(2, "副交易员")
        self.enterContext(working.based_on(core.state()))
        self.rid = _plain_resource()
        self.data = game_config.config_resouce[self.rid]
        warehouse.set_extra_modules(5000)

    def hire_traders(self, main_talk: int, sub_talk: int) -> None:
        """
        将角色 1 与 2 设为交易员，任命角色 1 为当前测试资源类型的主交易员并设置两人的话术等级。
        Keyword arguments:
        main_talk -- int，主交易员的话术能力等级
        sub_talk -- int，副交易员的话术能力等级
        Return arguments:
        None -- 直接写入岗位名册、主交易员与能力状态
        """
        work.set_rosters({economy.TRADER_WORK: [1, 2]})
        economy.set_main_trader(self.data.type, 1)
        ca.ability(1)[TALK] = main_talk
        ca.ability(2)[TALK] = sub_talk

    def test_resource_types_are_unique(self) -> None:
        """验证资源类型列表无重复且与除编号 0 外全部配置资源的类型集合一致"""
        types = trade_service.get_trade_resource_types()
        self.assertEqual(len(types), len(set(types)))
        expected = {
            data.type
            for rid, data in game_config.config_resouce.items()
            if rid != 0
        }
        self.assertEqual(set(types), expected)

    def test_trader_bonus_and_limits(self) -> None:
        """验证无交易员、常规话术加成以及高话术下买入 0.5 下限与卖出 2.0 上限的乘数计算"""
        self.assertEqual(
            trade_service.calculate_trade_multiplier(self.rid, True),
            (1, 0.0, 0.0),
        )
        self.hire_traders(10, 20)
        buy, main, sub = trade_service.calculate_trade_multiplier(
            self.rid, True
        )
        self.assertAlmostEqual(main, 0.05)
        self.assertAlmostEqual(sub, 0.02)
        self.assertAlmostEqual(buy, 0.93)
        sell, _main, _sub = trade_service.calculate_trade_multiplier(
            self.rid, False
        )
        self.assertAlmostEqual(sell, 1.07)
        self.hire_traders(200, 20)
        self.assertEqual(
            trade_service.calculate_trade_multiplier(self.rid, True)[0], 0.5
        )
        self.assertEqual(
            trade_service.calculate_trade_multiplier(self.rid, False)[0], 2.0
        )

    def test_price_follows_supply_and_keeps_buy_above_sell(self) -> None:
        """验证买卖价格随供需系数变化，并在高交易员加成下保持买入价不低于卖出价"""
        price = self.data.price
        self.assertEqual(
            trade_service.get_resouce_price(self.rid, True),
            (int(1.1 * price), 0.0),
        )
        self.assertEqual(
            trade_service.get_resouce_price(self.rid, False),
            (int(0.9 * price), 0.0),
        )
        economy.set_supply_demand({self.rid: 2.0})
        self.assertEqual(
            trade_service.get_resouce_price(self.rid, True)[0],
            int(2.2 * price),
        )
        self.hire_traders(200, 0)
        buy = trade_service.get_resouce_price(self.rid, True)[0]
        sell = trade_service.get_resouce_price(self.rid, False)[0]
        self.assertGreaterEqual(buy, sell)
        self.assertEqual(sell, int(2.2 * price * 0.5))

    def test_trade_caps_by_money_and_stock(self) -> None:
        """验证 perform_trade 按龙门币与库存截断买卖数量、对无效请求返回 None 并累加今日成交量"""
        buy_price = trade_service.get_resouce_price(self.rid, True)[0]
        warehouse.set(1, buy_price * 7)
        warehouse.set(self.rid, 0)
        self.assertEqual(
            trade_service.perform_trade(self.rid, 50, True),
            {"quantity": 7, "price": buy_price, "total_price": buy_price * 7},
        )
        self.assertEqual(warehouse.amount(1), 0)
        self.assertEqual(warehouse.amount(self.rid), 7)
        self.assertIsNone(trade_service.perform_trade(self.rid, 5, True))
        sold = trade_service.perform_trade(self.rid, 50, False)
        assert sold is not None
        self.assertEqual(sold["quantity"], 7)
        self.assertEqual(warehouse.amount(self.rid), 0)
        self.assertIsNone(trade_service.perform_trade(self.rid, 5, False))
        self.assertIsNone(trade_service.perform_trade(self.rid, 0, True))
        self.assertEqual(economy.traded_today()[self.rid], 14)

    def auto_line(self, line: str, quantity: int, money_moved: int) -> str:
        """
        按给定的成交数量与资金变动拼出预期的自动交易明细文本。
        Keyword arguments:
        line -- str，自动卖出或自动买入明细模板
        quantity -- int，成交数量
        money_moved -- int，成交对应的龙门币变动额
        Return arguments:
        str -- 格式化后的预期明细行文本
        """
        price = money_moved // quantity
        return get_text._(line).format(
            get_text._(self.data.name), quantity, price, price * quantity
        )

    def test_auto_trade_returns_lines_without_drawing(self) -> None:
        """验证自动交易无交易员时返回空列表，有交易员时完成买卖并返回明细且不调用 WaitDraw.draw"""
        warehouse.set(1, 10**9)
        warehouse.set(self.rid, 30)
        economy.set_auto_trade(
            self.rid,
            {
                **economy.DEFAULT_AUTO_TRADE,
                "sell_on": True,
                "sell_stock": 10,
                "sell_price_percent": 1,
            },
        )
        self.assertEqual(trade_service.auto_trade_resources(), [])
        self.assertEqual(warehouse.amount(self.rid), 30)
        self.hire_traders(0, 0)
        with mock.patch.object(draw.WaitDraw, "draw") as drawn:
            lines = trade_service.auto_trade_resources()
        drawn.assert_not_called()
        self.assertEqual(warehouse.amount(self.rid), 10)
        gained = warehouse.amount(1) - 10**9
        self.assertEqual(lines, [self.auto_line(SELL_LINE, 20, gained)])
        economy.set_auto_trade(
            self.rid,
            {
                **economy.DEFAULT_AUTO_TRADE,
                "buy_on": True,
                "buy_stock": 40,
                "buy_price_percent": 300,
            },
        )
        before = warehouse.amount(1)
        lines = trade_service.auto_trade_resources()
        self.assertEqual(warehouse.amount(self.rid), 40)
        spent = before - warehouse.amount(1)
        self.assertEqual(lines, [self.auto_line(BUY_LINE, 30, spent)])

    def test_daily_fluctuation_returns_auto_trade_lines(self) -> None:
        """验证每日供需波动后触发自动交易并返回成交明细，同时更新库存与今日成交量"""
        warehouse.set(1, 0)
        warehouse.set(self.rid, 25)
        self.hire_traders(0, 0)
        economy.set_auto_trade(
            self.rid,
            {
                **economy.DEFAULT_AUTO_TRADE,
                "sell_on": True,
                "sell_stock": 5,
                "sell_price_percent": 1,
            },
        )
        lines = trade_service.daily_supply_demand_fluctuation()
        self.assertEqual(warehouse.amount(self.rid), 5)
        self.assertEqual(
            lines, [self.auto_line(SELL_LINE, 20, warehouse.amount(1))]
        )
        self.assertEqual(economy.traded_today()[self.rid], 20)


class DailyBaseServiceTest(FastTestCase):
    """基地每日结算服务（daily_base_service）的香薰次数与定期体检结算测试"""

    def setUp(self) -> None:
        """创建博士与三名测试干员并打开基于当前状态的工作集上下文"""
        super().setUp()
        self.world.chara(0, "博士")
        for cid in (1, 2, 3):
            self.world.chara(cid, f"干员{cid}")
        self.enterContext(working.based_on(core.state()))

    def test_aromatherapy_sessions_follow_courtyard_level(self) -> None:
        """验证疗养庭院 0、3、4、5 级下香薰疗愈次数分别刷新为 1、1、2、3 次"""
        for level, sessions in ((0, 1), (3, 1), (4, 2), (5, 3)):
            facility.set_level(COURTYARD, level)
            daily_base_service.settle_aromatherapy_sessions()
            self.assertEqual(tallies.get(tallies.AROMATHERAPY), sessions)

    def exam_day(self, periodic: int, extra: int) -> None:
        """
        配置体检日程开关与人数参数，并准备待检干员 1、2 与已检干员 3 的初始状态。
        Keyword arguments:
        periodic -- int，定期体检开关设置值（0 关闭，1 开启）
        extra -- int，每日体检人数设置值（实际人数为该值加 1）
        Return arguments:
        None -- 直接写入体检设置、名单与干员今日体检时段
        """
        physical_exam.set_settings(
            {2: periodic, 3: 3, 4: 2, 5: 1, 6: extra, 7: 0}
        )
        physical_exam.add(physical_exam.CHOSEN, 1)
        physical_exam.add(physical_exam.CHOSEN, 2)
        physical_exam.finish(3, {"done"})
        action_info.set(3, "health_check_today", 2)

    def check_slots(self) -> dict[int, int]:
        """读取三名测试干员当前的今日体检时段映射"""
        return {
            cid: action_info.get(cid, "health_check_today") for cid in (1, 2, 3)
        }

    def test_health_check_day_picks_every_listed_operator(self) -> None:
        """验证体检日人数上限覆盖名单时为两名在列干员分配时段 1 或 2，清零未在列干员并清空今日与周期记录"""
        self.exam_day(1, 1)
        daily_base_service.settle_health_check()
        slots = self.check_slots()
        self.assertIn(slots[1], (1, 2))
        self.assertIn(slots[2], (1, 2))
        self.assertEqual(slots[3], 0)
        self.assertEqual(physical_exam.checks(physical_exam.TODAY), {})
        self.assertEqual(physical_exam.ids(physical_exam.EXAMINED), set())

    def test_health_check_day_samples_daily_count(self) -> None:
        """验证体检日每日人数为 1 时仅从两名在列干员中抽选一人并分配时段 1 或 2"""
        self.exam_day(1, 0)
        daily_base_service.settle_health_check()
        slots = self.check_slots()
        picked = [cid for cid in (1, 2) if slots[cid] != 0]
        self.assertEqual(len(picked), 1)
        self.assertIn(slots[picked[0]], (1, 2))
        self.assertEqual(slots[3], 0)

    def test_periodic_check_off_clears_only_today(self) -> None:
        """验证关闭定期体检时仅清空今日体检记录，保留本周期已体检名单与干员时段"""
        self.exam_day(0, 1)
        daily_base_service.settle_health_check()
        self.assertEqual(physical_exam.checks(physical_exam.TODAY), {})
        self.assertEqual(physical_exam.ids(physical_exam.EXAMINED), {3})
        self.assertEqual(self.check_slots(), {1: 0, 2: 0, 3: 2})


class NewDayTradeNoticeTest(FastTestCase):
    """基地每日结算（basement.update_base_resouce_newday）绘制贸易部结算提示的测试"""

    def setUp(self) -> None:
        """创建博士角色、打开工作集上下文并关闭定期体检开关"""
        super().setUp()
        self.world.chara(0, "博士")
        self.enterContext(working.based_on(core.state()))
        physical_exam.set_settings({2: 0})

    def notices(self, lines: list[str]) -> list[str]:
        """
        运行每日基地结算，断言囚犯结算桩被调用一次，并收集贸易部结算的 WaitDraw 绘制文本。
        Keyword arguments:
        lines -- list[str]，模拟 daily_supply_demand_fluctuation 返回的成交明细行列表
        Return arguments:
        list[str] -- 所有包含「○贸易部结算：」抬头的 WaitDraw 绘制文本列表
        """
        self.assertNotIn(VISITOR_PANEL, sys.modules)
        sys.modules[VISITOR_PANEL] = mock.MagicMock()
        self.addCleanup(sys.modules.pop, VISITOR_PANEL)
        with (
            mock.patch.object(agriculture_service, "settle_agriculture_line"),
            mock.patch.object(assembly_service, "settle_assembly_line"),
            mock.patch.object(prison_service, "settle_prisoners") as settled,
            mock.patch.object(
                trade_service,
                "daily_supply_demand_fluctuation",
                return_value=lines,
            ),
            mock.patch.object(draw.WaitDraw, "draw", autospec=True) as drawn,
        ):
            basement.update_base_resouce_newday()
        settled.assert_called_once_with()
        header = get_text._("○贸易部结算：\n")
        texts = [call.args[0].text for call in drawn.call_args_list]
        return [text for text in texts if header in text]

    def test_trade_lines_draw_one_notice(self) -> None:
        """验证返回两条自动交易明细时绘制一条包含抬头与全部明细的贸易部结算提示"""
        lines = ["  · 甲", "  · 乙"]
        header = get_text._("○贸易部结算：\n")
        self.assertEqual(
            self.notices(lines), ["\n" + header + "  · 甲\n  · 乙\n"]
        )

    def test_no_trade_lines_draw_no_notice(self) -> None:
        """验证自动交易明细为空时不绘制贸易部结算提示"""
        self.assertEqual(self.notices([]), [])
