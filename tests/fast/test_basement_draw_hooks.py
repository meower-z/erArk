"""
基地结算提示经 ui_hooks 发出的测试
==================================
- 提示发出与绘制（BasementNoticeTest）：验证 basement 经 ui_hooks.emit_notice
  发出的提示参数与 Tk 回调绘制结果。
"""

from unittest import mock

from Script.Config import normal_config
from Script.Core import get_text
from Script.Design import basement
from Script.Kernel import core
from Script.Modules.domains import fridge, power_supply, tallies, warehouse
from Script.Modules.domains import official
from Script.Modules.gameplay_resolution import agriculture_service
from Script.Modules.gameplay_resolution import assembly_service
from Script.Modules.gameplay_resolution import daily_base_service
from Script.Modules.gameplay_resolution import prison_service, trade_service
from Script.Modules.gameplay_resolution import ui_hooks, visitor_service
from Script.Modules.gameplay_resolution import working
from Script.Settle import power_settle
from Script.System.Cooking_System import cooking
from Script.System.Medical_System import medical_service
from Script.UI.Moudle import draw
from tests.fast.base import FastTestCase

TODO_SETTING = 5
"""normal_config.system_setting.draw_setting 中待办事项提示的开关索引（5）。"""
NEW_DAY_STEPS = (
    (basement, "update_work_people"),
    (basement, "settle_office_work"),
    (basement, "settle_semen"),
    (basement, "settle_milk"),
    (basement, "settle_pink_certificate"),
    (medical_service, "settle_medical_department"),
    (agriculture_service, "settle_agriculture_line"),
    (assembly_service, "settle_assembly_line"),
    (visitor_service, "settle_visitor_arrivals_and_departures"),
    (daily_base_service, "settle_aromatherapy_sessions"),
    (daily_base_service, "settle_health_check"),
    (cooking, "init_food_shop_data"),
    (prison_service, "settle_prisoners"),
)
"""
测试贸易结算提示时打桩跳过的 (模块, 属性名) 配对元组，
使 update_base_resouce_newday 仅执行贸易部结算分支。
"""

type Notice = tuple[str, bool, str | None, bool]
"""一条提示的参数元组类型，依次为 text、wait、style 与 use_text_width。"""

_ = get_text._


class BasementNoticeTest(FastTestCase):
    """Script/Design/basement.py 八处提示的 ui_hooks 派发参数与 Tk 回调绘制测试。"""

    def setUp(self) -> None:
        """
        创建玩家角色并打开内核工作集。
        在已登记的提示回调旁追加 record 回调，并拦截 NormalDraw 与 WaitDraw 的 draw 方法。
        """
        super().setUp()
        self.world.chara(0, "博士")
        self.enterContext(working.based_on(core.state()))
        self.notices: list[Notice] = []
        self.enterContext(
            mock.patch.object(
                ui_hooks, "_notices", [*ui_hooks._notices, self.record]
            )
        )
        self.drawn: list[tuple[str, float, str, str]] = []
        for cls in (draw.NormalDraw, draw.WaitDraw):
            self.enterContext(
                mock.patch.object(
                    cls, "draw", autospec=True, side_effect=self.keep
                )
            )

    def record(
        self, text: str, *, wait: bool, style: str | None, use_text_width: bool
    ) -> None:
        """
        记录一条经 ui_hooks.emit_notice 派发的提示参数。
        Keyword arguments:
        text -- str，提示文本
        wait -- bool，是否等待玩家确认
        style -- str | None，文本样式名，为 None 时使用默认样式
        use_text_width -- bool，是否按配置文本宽度排版
        Return arguments:
        None -- 无返回值
        """
        self.notices.append((text, wait, style, use_text_width))

    def keep(self, now: draw.NormalDraw) -> None:
        """
        记录被拦截绘制对象的类名、宽度、样式与文本。
        Keyword arguments:
        now -- draw.NormalDraw，调用 draw 方法的绘制对象实例
        Return arguments:
        None -- 无返回值
        """
        self.drawn.append((type(now).__name__, now.width, now.style, now.text))

    def assert_notice(self, *expected: Notice) -> None:
        """
        依次核对 Tk 回调绘出的绘制对象列表与 ui_hooks 记录的提示参数列表。
        Keyword arguments:
        expected -- Notice，按顺序预期的提示参数元组
        Return arguments:
        None -- 无返回值
        """
        width = normal_config.config_normal.text_width
        self.assertEqual(
            self.drawn,
            [
                (
                    "WaitDraw" if wait else "NormalDraw",
                    width if use_text_width else 0,
                    style or draw.NormalDraw.style,
                    text,
                )
                for text, wait, style, use_text_width in expected
            ],
        )
        self.assertEqual(self.notices, list(expected))

    def test_trade_notice_keeps_default_width(self) -> None:
        """
        打桩其余每日结算步骤后，贸易波动返回空列表时 update_base_resouce_newday 不发出提示。
        贸易波动返回两条记录时，函数发出一条默认宽度的等待型贸易部结算提示。
        """
        for module, attr in NEW_DAY_STEPS:
            self.enterContext(mock.patch.object(module, attr))
        trade = self.enterContext(
            mock.patch.object(trade_service, "daily_supply_demand_fluctuation")
        )
        trade.return_value = []
        basement.update_base_resouce_newday()
        self.assert_notice()
        trade.return_value = ["  · 甲", "  · 乙"]
        basement.update_base_resouce_newday()
        self.assert_notice(
            (
                "\n" + _("○贸易部结算：\n") + "  · 甲\n  · 乙\n",
                True,
                None,
                False,
            )
        )

    def test_milk_notices(self) -> None:
        """
        冰箱存入 30ml 母乳时，settle_milk 按文本宽度发出一条等待型转化提示。
        再存入等同仓库容量的母乳时，settle_milk 将鲜母乳库存截断至上限，
        并按文本宽度依次发出转化与超限两条等待型提示。
        """
        capacity = warehouse.capacity()
        fridge.add(fridge.MILK, 0, 30)
        basement.settle_milk()
        convert = _("\n今日共有{0}ml母乳未使用，已全部转化为【鲜母乳】\n")
        self.assert_notice((convert.format(30), True, None, True))
        self.drawn.clear()
        self.notices.clear()
        fridge.add(fridge.MILK, 0, capacity)
        basement.settle_milk()
        self.assertEqual(warehouse.amount(31), capacity)
        self.assert_notice(
            (convert.format(capacity), True, None, True),
            (
                _("\n由于仓库容量不足，【鲜母乳】已达上限数量{0}\n").format(
                    capacity
                ),
                True,
                None,
                True,
            ),
        )

    def test_semen_notices(self) -> None:
        """
        当日精液计数为 40ml 时，settle_semen 按文本宽度发出一条等待型转化提示。
        矿石病药材库存已达上限后再结算 40ml 时，settle_semen 将该库存截断至上限，
        并按文本宽度依次发出转化与超限两条等待型提示。
        """
        capacity = warehouse.capacity()
        convert = _("\n今日共射出{0}ml精液，已全部转化为【矿石病药材】\n")
        tallies.set(tallies.SEMEN, 40)
        basement.settle_semen()
        self.assert_notice((convert.format(40), True, None, True))
        self.drawn.clear()
        self.notices.clear()
        warehouse.set(12, capacity)
        tallies.set(tallies.SEMEN, 40)
        basement.settle_semen()
        self.assertEqual(warehouse.amount(12), capacity)
        self.assert_notice(
            (convert.format(40), True, None, True),
            (
                _("\n由于仓库容量不足，【矿石病药材】已达上限数量{0}\n").format(
                    capacity
                ),
                True,
                None,
                True,
            ),
        )

    def test_office_work_notice(self) -> None:
        """
        打桩动力结算返回 (0.0, "") 且待处理公务量为 10**6 时，
        settle_office_work 按文本宽度发出一条包含 1000000.0 与 50% 的等待型公务结算提示。
        """
        self.enterContext(
            mock.patch.object(
                power_settle, "settle_power_system", return_value=(0.0, "")
            )
        )
        official.set_office_work(10**6)
        basement.settle_office_work()
        self.assert_notice(
            (
                _("\n今日剩余待处理公务量为{0:.1f}，").format(10**6)
                + _("且各区块设施运行基本正常，")
                + _("因此今日罗德岛的各设施的总效率为{0}%\n").format(50),
                True,
                None,
                True,
            )
        )

    def test_pink_certificate_notice(self) -> None:
        """
        总好感度为 250 且陷落凭证分别为 0 与 30 时，
        settle_pink_certificate 按文本宽度发出等待型提示，且仅在陷落凭证为 30 时附带陷落行。
        """
        head = _("\n今日全角色总好感度上升为：{0}，折合为 {1} 粉红凭证\n")
        for fallen, tail in (
            (0, ""),
            (30, _("本周全陷落角色提供的粉红凭证为：{0}\n").format(30)),
        ):
            with self.subTest(fallen=fallen):
                self.drawn.clear()
                self.notices.clear()
                tallies.set(tallies.FAVORABILITY, 250)
                tallies.set(tallies.FALLEN, fallen)
                basement.settle_pink_certificate()
                self.assert_notice(
                    (head.format(250, 2) + tail, True, None, True)
                )

    def test_todo_notice(self) -> None:
        """
        打桩供电为 0.0、耗电为 10.0 且其余待办项为空时，待办开关为 0 则 draw_todo 不发出提示。
        待办开关设为 1 时，draw_todo 按文本宽度发出一条 gold_enrod 样式的等待型供电不足提示。
        """
        for name, value in (
            ("power_generation", 0.0),
            ("power_consumption", 10.0),
        ):
            self.enterContext(
                mock.patch.object(power_supply, name, return_value=value)
            )
        for service, name in (
            (assembly_service, "settle_assembly_line"),
            (agriculture_service, "settle_agriculture_line"),
        ):
            self.enterContext(
                mock.patch.object(service, name, return_value=(False, ""))
            )
        self.enterContext(
            mock.patch.object(
                visitor_service, "get_today_departing_visitors", return_value=[]
            )
        )
        setting = normal_config.system_setting.draw_setting
        self.enterContext(mock.patch.dict(setting, {TODO_SETTING: 0}))
        basement.draw_todo()
        self.assert_notice()
        setting[TODO_SETTING] = 1
        basement.draw_todo()
        self.assert_notice(
            (
                "\n" + _("  当前供电不足，可能影响基地正常运转\n"),
                True,
                "gold_enrod",
                True,
            )
        )
