# -*- coding: UTF-8 -*-
"""
农业与流水线生产结算服务测试
============================
- 农业生产结算服务（agriculture_service）：药田与温室的效率计算、结算结果、提示选项与关闭绘制时的行为。
- 流水线生产结算服务（assembly_service）：流水线效率计算、原料不足与满仓异常，以及跨日生产扩展模块后的床位与仓容更新。
- Tk 提示回调（tk_ui.callbacks）：以配置文本宽度通过 WaitDraw 绘制农业与流水线结算提示。
"""

from unittest import mock

from Script.Config import game_config, normal_config
from Script.Core import get_text
from Script.Design import basement, game_time
from Script.Kernel import core
from Script.Modules.domains import achievement, maintenance, medical
from Script.Modules.domains import production, warehouse
from Script.Modules.gameplay_resolution import achievement_service
from Script.Modules.gameplay_resolution import agriculture_service
from Script.Modules.gameplay_resolution import assembly_service
from Script.Modules.gameplay_resolution import ui_hooks, working
from Script.System.Medical_System import medical_core
from Script.UI.Moudle import draw
from tests import chara_abilities as ca
from tests import kernel_data
from tests.fast.base import FastTestCase
from Script.Modules.domains import chara_life

_ = get_text._
""" 文本翻译函数 """
AGRICULTURE = 47
""" 能力编号 47（农业技能） """
MAKING = 48
""" 能力编号 48（制造技能） """
HERB = 11
""" 资源编号 11（普通药材） """
SPICE = 16
""" 资源编号 16（香料） """
PILL = 21
""" 资源编号 21（常规药物） """
BED_FORMULA = 17
""" 生产配方编号 17（成品为资源 54） """
STORE_FORMULA = 18
""" 生产配方编号 18（成品为资源 55） """
SHELL = 13
""" 资源编号 13（工业材料） """
CHIP = 22
""" 资源编号 22（感染抑制剂小样） """
BED_MODULE = 54
""" 资源编号 54（住院病房扩展模块） """
STORE_MODULE = 55
""" 资源编号 55（仓储空间扩展模块） """


class ProductionCase(FastTestCase):
    """生产结算服务测试基类，准备测试世界、工作集缓冲区与成就通知桩。"""

    def setUp(self) -> None:
        """初始化玩家角色与工作集缓冲区，检查开局时刻前提并打桩成就结算通知。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.enterContext(working.based_on(core.state()))
        self.hour = game_time.now().hour
        self.assertGreaterEqual(self.hour, 4, "前提：开局时刻不早于 4 点")
        self.settled = self.enterContext(
            mock.patch.object(
                achievement_service, "settle_and_notify", return_value=[]
            )
        )

    def staff(self, kind: str, levels: dict[int, int], skill: int) -> None:
        """
        按等级映射创建干员、设置其工作类型与技能等级，并写入指定产线的工人名单。
        Keyword arguments:
        kind -- str，产线类型键名（herb_garden、green_house 或 assembly）
        levels -- dict[int, int]，角色编号到技能等级的映射
        skill -- int，要设置的能力编号
        Return arguments:
        None -- 无返回值
        """
        for cid, level in levels.items():
            self.world.chara(cid, f"干员{cid}")
            kernel_data.put(
                chara_life.work_type.set, cid, production.KINDS[kind]
            )
            ca.ability(cid)[skill] = level
        production.set_workers(kind, list(levels))


class NoticeCase(ProductionCase):
    """带提示记录器的生产结算测试基类，拦截 ui_hooks 提示回调以检验发出的提示。"""

    def setUp(self) -> None:
        """在基类初始化后将 ui_hooks 提示回调列表替换为本用例的提示记录器。"""
        super().setUp()
        self.notices: list[tuple[str, bool, str | None, bool]] = []
        self.enterContext(
            mock.patch.object(ui_hooks, "_notices", [self.notice])
        )

    def notice(
        self, text: str, *, wait: bool, style: str | None, use_text_width: bool
    ) -> None:
        """
        记录单条结算提示文本及其显示选项。
        Keyword arguments:
        text -- str，提示文本
        wait -- bool，是否等待玩家确认
        style -- str | None，文本样式名
        use_text_width -- bool，是否按配置文本宽度排版
        Return arguments:
        None -- 无返回值
        """
        self.notices.append((text, wait, style, use_text_width))

    def shown(self) -> list[str]:
        """
        断言已记录至少一条提示且均使用 wait=True、style=None 与 use_text_width=True，并返回提示文本列表。
        Return arguments:
        list[str] -- 按记录顺序排列的提示文本列表
        """
        options = {notice[1:] for notice in self.notices}
        self.assertEqual(options, {(True, None, True)})
        return [notice[0] for notice in self.notices]


class AgricultureServiceTest(NoticeCase):
    """农业生产结算服务（agriculture_service）的效率计算与结算测试。"""

    def test_efficiency_counts_main_and_sub_planters(self) -> None:
        """验证药田与温室的效率计算正确计入主副种植员、排除他线主种植员并在主位空缺时生效。"""
        production.open_lines("herb_garden", [0, 1])
        production.open_lines("green_house", [0])
        self.staff("herb_garden", {1: 4, 2: 2, 3: 10}, AGRICULTURE)
        self.staff("green_house", {4: 4, 5: 2}, AGRICULTURE)
        production.appoint("herb_garden", 0, 1)
        production.appoint("herb_garden", 1, 3)
        production.appoint("green_house", 0, 4)
        courtyard = basement.calc_facility_efficiency(16)
        garden = basement.calc_facility_efficiency(41)
        efficiency = agriculture_service.calculate_agriculture_line_efficiency
        _text, herb = efficiency(0, 0)
        self.assertAlmostEqual(herb, 1.185 * (courtyard + garden - 1))
        _text, house = efficiency(0, 1)
        self.assertAlmostEqual(house, 1.185 * courtyard)
        _text, vacant = efficiency(5, 1)
        self.assertAlmostEqual(vacant, 1.025 * courtyard)

    def test_settle_fills_both_fields_and_notifies(self) -> None:
        """验证同时结算药田与温室时的设备故障文案、满仓截断异常、提示发出、库存与时刻更新及种植成就通知。"""
        production.set_line("herb_garden", 0, product=HERB)
        production.set_line("green_house", 0, product=SPICE)
        maintenance.set_damage("疗养庭院", 2)
        warehouse.set(SPICE, warehouse.capacity() - 3)
        efficiency = agriculture_service.calculate_agriculture_line_efficiency
        herb_num = int(10 * efficiency(0, 0)[1])
        spice_num = int(10 * efficiency(0, 1)[1])
        spice_name = game_config.config_resouce[SPICE].name
        herb_text = (
            _("\n今日药田共生产了{0}个{1}").format(
                herb_num, game_config.config_resouce[HERB].name
            )
            + _("，由于设备故障，生产效率下降{0}%").format(4)
            + "\n"
        )
        spice_text = (
            _("\n今日温室共生产了{0}个{1}").format(spice_num, spice_name)
            + _("，由于设备故障，生产效率下降{0}%").format(4)
            + _("，由于仓库容量不足，{0}已达上限数量{1}").format(
                spice_name, warehouse.capacity()
            )
            + "\n"
        )
        un_normal, text = agriculture_service.settle_agriculture_line()
        self.assertTrue(un_normal)
        self.assertEqual(
            text, "\n" + _("○疗养庭院结算：\n") + herb_text + spice_text
        )
        self.assertEqual(self.shown(), [herb_text, spice_text])
        self.assertEqual(warehouse.amount(HERB), herb_num)
        self.assertEqual(warehouse.amount(SPICE), warehouse.capacity())
        self.assertEqual(achievement.get("harvest_count"), herb_num + spice_num)
        hour = game_time.now().hour
        self.assertEqual(production.lines("herb_garden")[0]["hour"], hour)
        self.assertEqual(production.lines("green_house")[0]["hour"], hour)
        self.settled.assert_called_once_with(_("种植"))

    def test_settle_without_drawing_emits_nothing(self) -> None:
        """验证 draw_flag=False 时不带抬头且不发出提示，但仍完成入库并通知种植成就结算。"""
        production.set_line("herb_garden", 0, product=HERB)
        un_normal, text = agriculture_service.settle_agriculture_line(
            draw_flag=False
        )
        self.assertFalse(un_normal)
        self.assertNotIn(_("○疗养庭院结算：\n"), text)
        self.assertEqual(self.notices, [])
        self.assertGreater(warehouse.amount(HERB), 0)
        self.settled.assert_called_once_with(_("种植"))


class AssemblyServiceTest(NoticeCase):
    """流水线生产结算服务（assembly_service）的效率计算与结算测试。"""

    def test_efficiency_counts_main_and_sub_workers(self) -> None:
        """验证流水线效率计算正确计入主副工人、排除他线主工人，且对不存在的产线返回零效率。"""
        production.open_lines("assembly", [0, 1])
        self.staff("assembly", {1: 4, 2: 2, 3: 10}, MAKING)
        production.appoint("assembly", 0, 1)
        production.appoint("assembly", 1, 3)
        workshop = basement.calc_facility_efficiency(12)
        efficiency = assembly_service.calculate_assembly_line_efficiency
        self.assertAlmostEqual(efficiency(0)[1], workshop * 100 + 18.5)
        self.assertAlmostEqual(efficiency(1)[1], workshop * 100 + 42.5)
        self.assertEqual(efficiency(7), (_("无此生产线"), 0.0))

    def test_shortage_is_abnormal(self) -> None:
        """验证原料不足时返回异常标记与缺料文案、按可产上限消耗原料并更新结算时刻，且关闭绘制时不发提示。"""
        production.set_line("assembly", 0, hour=self.hour - 4)
        warehouse.set(HERB, 25)
        un_normal, text = assembly_service.settle_assembly_line(draw_flag=False)
        self.assertTrue(un_normal)
        self.assertIn(
            _("由于原料不足，最大可以生产{0}个，实际").format(2), text
        )
        self.assertEqual(warehouse.amount(HERB), 5)
        self.assertEqual(warehouse.amount(PILL), 2)
        self.assertEqual(self.notices, [])
        self.assertEqual(production.lines("assembly")[0]["hour"], self.hour)
        self.settled.assert_called_once_with(_("生产"))

    def test_full_warehouse_is_abnormal(self) -> None:
        """验证成品超出仓容时返回异常标记与满仓文案、按上限截断库存并正常扣料，且关闭绘制时不发提示。"""
        production.set_line("assembly", 0, hour=self.hour - 4)
        warehouse.set(HERB, 1000)
        warehouse.set(PILL, warehouse.capacity() - 1)
        un_normal, text = assembly_service.settle_assembly_line(draw_flag=False)
        self.assertTrue(un_normal)
        self.assertIn(
            _("，由于仓库容量不足，{0}已达上限数量{1}").format(
                game_config.config_resouce[PILL].name, warehouse.capacity()
            ),
            text,
        )
        self.assertEqual(warehouse.amount(HERB), 1000 - 40)
        self.assertEqual(warehouse.amount(PILL), warehouse.capacity())
        self.assertEqual(self.notices, [])
        self.settled.assert_called_once_with(_("生产"))

    def test_new_day_modules_raise_beds_and_storage(self) -> None:
        """验证跨日生产住院病房与仓储空间扩展模块时更新库存、床位上限、额外仓容模块数与四条结算提示。"""
        production.open_lines("assembly", [0, 1])
        production.set_line("assembly", 0, product=BED_FORMULA, hour=23)
        production.set_line("assembly", 1, product=STORE_FORMULA, hour=23)
        made = self.hour + 1
        warehouse.set_all({SHELL: 2000, PILL: 100, CHIP: 100})
        un_normal, text = assembly_service.settle_assembly_line(newdayflag=True)
        self.assertFalse(un_normal)
        shown = self.shown()
        self.assertEqual(text, "\n" + _("○制造加工部结算：\n") + "".join(shown))
        self.assertEqual(len(shown), 4)
        self.assertEqual(
            shown[2:],
            [
                _(
                    "○由于生产了{0}个住院病房扩展模块，罗德岛住院部床位数量提升了{1}个！\n"
                ).format(made, 3 * made),
                _(
                    "○由于生产了{0}个仓储空间扩展模块，罗德岛仓库容量提升了{1}！\n"
                ).format(made, 200 * made),
            ],
        )
        self.assertEqual(warehouse.amount(SHELL), 2000 - 150 * made)
        self.assertEqual(warehouse.amount(BED_MODULE), made)
        self.assertEqual(warehouse.amount(STORE_MODULE), made)
        self.assertEqual(medical.state().bed_modules, made)
        self.assertEqual(
            medical.state().bed_limit,
            medical_core._calculate_medical_bed_limit(),
        )
        self.assertEqual(warehouse.extra_modules(), made)
        self.assertEqual(achievement.get("production_count"), 2 * made)
        self.settled.assert_called_once_with(_("生产"))


class TkProductionNoticeTest(ProductionCase):
    """Tk 提示回调（tk_ui.callbacks.draw_notice）绘制生产结算提示的测试。"""

    def test_tk_draws_each_notice_at_text_width(self) -> None:
        """
        验证沿用启动阶段登记的提示回调且不替换提示回调列表时，
        农业与流水线两条结算提示均按配置文本宽度与默认样式通过 WaitDraw 绘制。
        """
        waited = self.enterContext(
            mock.patch.object(draw.WaitDraw, "draw", autospec=True)
        )
        production.set_line("herb_garden", 0, product=HERB)
        production.set_line("assembly", 0, hour=self.hour - 1)
        warehouse.set(HERB, 100)
        _flag, farm = agriculture_service.settle_agriculture_line()
        _flag, plant = assembly_service.settle_assembly_line()
        width = normal_config.config_normal.text_width
        header = "\n" + _("○疗养庭院结算：\n")
        self.assertEqual(
            [
                (type(now).__name__, now.width, now.style, now.text)
                for (now,), _kw in waited.call_args_list
            ],
            [
                ("WaitDraw", width, "standard", farm.removeprefix(header)),
                ("WaitDraw", width, "standard", plant.removeprefix("\n")),
            ],
        )
