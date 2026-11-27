"""
射精与精液污浊服务测试
======================
- 精液污浊与流动（semen_dirty_service）：验证部位污浊累计、扣减保底、缺位跳过、穿着服装污浊与满溢流动记录。
- 通用射精与忍耐（ejaculation_service）：验证忍耐掷骰、额外精液优先扣减与无精液返回。
- 射精总流程（ejaculation_flow）：验证目标部位、避孕套、体外无壳卵、无精液与关闭回调五个分支及成就调用。
- Tk 回调与模块边界：验证 load_order 登记后的六步绘制顺序、调用方导入服务，以及射精面板的定义边界。
"""

import ast
import inspect
from importlib.util import resolve_name
from types import ModuleType
from unittest import mock

from Script.Config import game_config, normal_config
from Script.Core import get_text
from Script.Design import attr_calculation, handle_premise
from Script.Kernel import core
from Script.Modules import load_order
from Script.Modules.domains import action_info, activity, dirty, first_record
from Script.Modules.domains import h_meters, h_state, identity, tallies
from Script.Modules.domains import wardrobe
from Script.Modules.gameplay_resolution import achievement_service
from Script.Modules.gameplay_resolution import ejaculation_service
from Script.Modules.gameplay_resolution import locker_service
from Script.Modules.gameplay_resolution import semen_dirty_service, working
from Script.Settle import default as settle_default
from Script.Settle import realtime_settle
from Script.System.Cooking_System import cooking
from Script.System.Item_System import condom_handle
from Script.System.Pregnancy_System import soft_egg_handle
from Script.UI.Moudle import draw
from Script.UI.Panel import ejaculation_panel
from tests import chara_abilities as ca
from tests.fast.base import FastTestCase

TARGET = 1
""" 测试使用的目标角色编号（1）。 """
MOUTH = 2
""" 测试使用的身体部位编号（部位 2）。 """
SHOT = ("射精文本", 120)
""" 射精总流程测试替身返回的固定文本与射精量元组。 """
PANEL = "Script.UI.Panel.ejaculation_panel"
""" 射精面板模块的完整导入路径字符串。 """
MOVED = frozenset(
    {
        "judge_endure_ejaculation",
        "common_ejaculation",
        "update_semen_dirty",
        "calculate_semen_flow",
        "ejaculation_flow",
    }
)
""" 由射精与精液污浊服务提供的五个函数名集合。 """
CALLERS = (
    settle_default,
    realtime_settle,
    cooking,
    condom_handle,
    locker_service,
)
""" 依赖射精或精液污浊服务的五个调用方模块元组。 """
FLOW_TYPES = {"B": 0, "C": 1, "E": 2}
""" 精液流动配置前缀字母到目标类型编号的映射表。 """


def imports_in(source: str, package: str) -> set[str]:
    """
    解析源码语法树，收集导入模块名与成员完整路径，并按包名解析相对导入。
    Keyword arguments:
    source -- str，待解析的 Python 源码字符串
    package -- str，用于解析相对导入的所属包名
    Return arguments:
    set[str] -- 源码导入语句中提取出的模块名与成员完整路径集合
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = resolve_name("." * node.level + (node.module or ""), package)
            found.add(base)
            found.update(f"{base}.{alias.name}" for alias in node.names)
    return found


def imported_modules(module: ModuleType) -> set[str]:
    """
    读取模块源码与所属包名并交由 imports_in 提取导入模块与成员路径。
    Keyword arguments:
    module -- ModuleType，待检查的模块对象
    Return arguments:
    set[str] -- 源码导入语句中提取出的模块名与成员完整路径集合
    """
    return imports_in(inspect.getsource(module), module.__package__ or "")


class SemenDirtyServiceTest(FastTestCase):
    """精液污浊与流动服务（semen_dirty_service）的单元测试。"""

    def setUp(self) -> None:
        """创建玩家与测试目标角色并打开基于当前状态的工作集上下文。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(TARGET, "测试干员")
        self.enterContext(working.based_on(core.state()))

    def test_body_shot_adds_semen_and_records_position(self) -> None:
        """验证向目标部位 2 写入 500ml 精液会更新污浊量、等级、累计总量、射精部位、插入状态与初体验记录。"""
        semen_dirty_service.update_semen_dirty(TARGET, MOUTH, 0, 500)
        part = dirty.view(TARGET).body_semen[MOUTH]
        level = attr_calculation.get_semen_now_level(500, MOUTH, 0)
        self.assertEqual((part[1], part[2], part[3]), (500, level, 500))
        self.assertEqual(h_state.get(TARGET, "shoot_position_body"), MOUTH)
        self.assertEqual(h_state.get(TARGET, "insert_position"), -1)
        self.assertEqual(h_state.get(0, "current_sex_position"), -1)
        self.assertTrue(first_record.has_shoot_body(TARGET, MOUTH))

    def test_drain_keeps_total_and_shoot_position(self) -> None:
        """验证扣减精液时当前量下限为 0，累计总量与射精部位保持不变。"""
        before = h_state.get(TARGET, "shoot_position_body")
        update = semen_dirty_service.update_semen_dirty
        update(TARGET, MOUTH, 0, 300, update_shoot_position_flag=False)
        update(TARGET, MOUTH, 0, -500, update_shoot_position_flag=False)
        part = dirty.view(TARGET).body_semen[MOUTH]
        self.assertEqual((part[1], part[3]), (0, 300))
        self.assertEqual(h_state.get(TARGET, "shoot_position_body"), before)

    def test_absent_part_and_bare_cloth_stay_clean(self) -> None:
        """验证目标缺少素质 113 时的部位 12 以及未穿戴服装类型的精液量均保持为 0。"""
        ca.talent(TARGET)[113] = 0
        semen_dirty_service.update_semen_dirty(TARGET, 12, 0, 100)
        self.assertEqual(dirty.view(TARGET).body_semen[12][1], 0)
        worn = wardrobe.of(TARGET).cloth_wear
        bare = min(cid for cid in worn if not worn[cid])
        semen_dirty_service.update_semen_dirty(TARGET, bare, 1, 100)
        self.assertEqual(dirty.view(TARGET).cloth_semen[bare][1], 0)

    def test_worn_cloth_gets_semen(self) -> None:
        """验证向目标已穿戴的服装类型写入精液会更新服装污浊量与服装射精部位。"""
        worn = wardrobe.of(TARGET).cloth_wear
        cloth = min(cid for cid in worn if worn[cid])
        semen_dirty_service.update_semen_dirty(TARGET, cloth, 1, 100)
        self.assertEqual(dirty.view(TARGET).cloth_semen[cloth][1], 100)
        self.assertEqual(h_state.get(TARGET, "shoot_position_cloth"), cloth)

    def test_overflow_follows_full_flow_table(self) -> None:
        """验证部位 2 精液溢出时按满溢流动表为目标追加流动记录，且角色 0 不生成流动记录。"""
        over = 1000
        amount = game_config.config_body_part[MOUTH].max_volume + over
        semen_dirty_service.update_semen_dirty(
            TARGET, MOUTH, 0, amount, update_shoot_position_flag=False
        )
        semen_dirty_service.calculate_semen_flow(TARGET, MOUTH, 0, amount)
        expected = [
            {
                "type": FLOW_TYPES[flow[0]],
                "id": int(flow[1:].split("-")[0]),
                "remaining_volume": max(
                    1, over * int(flow[1:].split("-")[1]) // 100
                ),
            }
            for flow in game_config.config_body_part_full_flow[MOUTH]
        ]
        self.assertTrue(expected)
        self.assertEqual(
            dirty.view(TARGET).semen_flow,
            [{"source": {"type": 0, "id": MOUTH}, "targets": expected}],
        )
        semen_dirty_service.calculate_semen_flow(0, MOUTH, 0, amount)
        self.assertEqual(dirty.view(0).semen_flow, [])


class CommonEjaculationTest(FastTestCase):
    """忍耐判定与通用射精结算（ejaculation_service）的单元测试。"""

    def setUp(self) -> None:
        """创建玩家角色、关闭射精加倍前提并固定随机系数为 1.0。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.enterContext(working.based_on(core.state()))
        activity.set_target(0, 0)
        action_info.set(0, "day_first_shoot_semen", False)
        for name in (
            "handle_self_semen_energy_agent",
            "handle_aromatherapy_flag_7",
            "handle_pl_semen_tmp_ge_max",
            "handle_self_semen_thick_1",
        ):
            self.enterContext(
                mock.patch.object(handle_premise, name, return_value=0)
            )
        self.enterContext(mock.patch("random.uniform", return_value=1.0))

    def test_judge_endure_compares_roll_with_rate(self) -> None:
        """验证 judge_endure_ejaculation 以 randint(1, 100) 的结果与忍耐几率比较并返回布尔值。"""
        with mock.patch("random.randint", return_value=60) as roll:
            self.assertTrue(ejaculation_service.judge_endure_ejaculation(60))
            self.assertFalse(ejaculation_service.judge_endure_ejaculation(59))
        roll.assert_called_with(1, 100)

    def test_shot_spends_extra_semen_first(self) -> None:
        """验证常规射精先扣减额外精液再扣减基础精液，并更新射精计数、全局精液统计与污浊标记。"""
        h_meters.set(0, semen=1000, extra_semen=4)
        level = h_state.orgasm_level(0, 3)
        before = tallies.get(tallies.SEMEN)
        amount = game_config.config_semen_shoot_amount[0].base_semen_amount
        text, shot = ejaculation_service.common_ejaculation()
        self.assertEqual(shot, amount)
        self.assertEqual(
            text,
            get_text._("射精，射出了") + str(amount) + get_text._("ml精液"),
        )
        self.assertEqual(
            (h_meters.of(0)["semen"], h_meters.of(0)["extra_semen"]),
            (1000 - (amount - 4), 0),
        )
        self.assertEqual(tallies.get(tallies.SEMEN), before + amount)
        self.assertEqual(h_state.orgasm_level(0, 3), level + 1)
        self.assertEqual(h_state.get(0, "just_shoot"), 1)
        self.assertTrue(dirty.view(0).penis_dirty_dict["semen"])

    def test_no_semen_left_shoots_nothing(self) -> None:
        """验证无剩余精液时返回 0 射精量与对应文本，且不改动全局精液统计与 just_shoot。"""
        h_meters.set(0, semen=0, extra_semen=0)
        before = tallies.get(tallies.SEMEN)
        self.assertEqual(
            ejaculation_service.common_ejaculation(),
            (get_text._("只流出了些许前列腺液，已经射不出精液了"), 0),
        )
        self.assertEqual(tallies.get(tallies.SEMEN), before)
        self.assertEqual(h_state.get(0, "just_shoot"), 0)


class EjaculationFlowTest(FastTestCase):
    """射精总流程（ejaculation_flow）各分支与回调派发的单元测试。"""

    def setUp(self) -> None:
        """准备测试角色并替身化射精文本回调、通用射精结算与成就结算接口。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(TARGET, "测试干员")
        self.enterContext(working.based_on(core.state()))
        self.banners: list[str] = []
        self.enterContext(
            mock.patch.object(
                ejaculation_service, "_banners", [self.banners.append]
            )
        )
        self.shot = self.enterContext(
            mock.patch.object(
                ejaculation_service, "common_ejaculation", return_value=SHOT
            )
        )
        self.judge = self.enterContext(
            mock.patch.object(
                achievement_service, "get_achievement_judge_by_value"
            )
        )
        self.settle = self.enterContext(
            mock.patch.object(achievement_service, "settle_and_notify")
        )

    def assert_settled(self) -> None:
        """断言本次流程各调用一次成就 1201 数值判定与射精类成就结算。"""
        self.judge.assert_called_once_with(1201, 1)
        self.settle.assert_called_once_with(get_text._("射精"))

    def test_shot_on_target_body_part(self) -> None:
        """验证向目标部位 2 射精会发送组合文本、写入部位污浊与射精量并更新射精部位。"""
        ejaculation_service.ejaculation_flow(MOUTH, 0, TARGET)
        self.assertEqual(
            self.banners,
            [
                get_text._("在{0}的{1}{2}").format(
                    identity.of(TARGET).name,
                    game_config.config_body_part[MOUTH].name,
                    SHOT[0],
                )
            ],
        )
        self.assertEqual(dirty.view(TARGET).body_semen[MOUTH][1], SHOT[1])
        self.assertEqual(h_state.get(0, "shoot_semen_amount"), SHOT[1])
        self.assertEqual(h_meters.shoot_position(), MOUTH)
        self.assert_settled()

    def test_condom_keeps_the_semen(self) -> None:
        """验证佩戴穿戴道具 13 时记录避孕套统计、入库用过的避孕套、卸下道具且目标部位保持为 0。"""
        h_state.set_body_item(0, 13, True)
        count = h_state.get(0, "condom_count")
        with mock.patch.object(condom_handle, "add_used_condom") as used:
            ejaculation_service.ejaculation_flow(MOUTH, 0, TARGET)
        used.assert_called_once_with(SHOT[1])
        self.assertEqual(
            h_state.get(0, "condom_count"),
            [count[0] + 1, count[1] + SHOT[1]],
        )
        self.assertFalse(h_state.body_item_on(0, 13))
        self.assertEqual(self.banners, [get_text._("在避孕套里") + SHOT[0]])
        self.assertEqual(dirty.view(TARGET).body_semen[MOUTH][1], 0)
        self.assert_settled()

    def test_soft_egg_takes_the_semen(self) -> None:
        """验证指定体外无壳卵编号时精液全部加到该卵、发送卵文本且目标部位保持为 0。"""
        with (
            mock.patch.object(soft_egg_handle, "add_semen_to_soft_egg") as add,
            mock.patch.object(
                soft_egg_handle, "get_soft_egg_name", return_value="卵"
            ),
        ):
            ejaculation_service.ejaculation_flow(-1, 0, soft_egg_id=3)
        add.assert_called_once_with(3, SHOT[1])
        self.assertEqual(
            self.banners, [get_text._("在{0}上{1}").format("卵", SHOT[0])]
        )
        self.assertEqual(dirty.view(TARGET).body_semen[MOUTH][1], 0)
        self.assert_settled()

    def test_empty_shot_shows_player_text(self) -> None:
        """验证射精量为 0 时发送含玩家名的文本且不增加射精量与目标污浊。"""
        self.shot.return_value = ("没有精液", 0)
        ejaculation_service.ejaculation_flow(MOUTH, 0, TARGET)
        self.assertEqual(self.banners, [identity.of(0).name + "没有精液"])
        self.assertEqual(h_state.get(0, "shoot_semen_amount"), 0)
        self.assertEqual(dirty.view(TARGET).body_semen[MOUTH][1], 0)
        self.assert_settled()

    def test_draw_flag_off_emits_no_banner(self) -> None:
        """验证 draw_flag 为 False 时不触发射精文本回调，但仍写入目标部位污浊并结算成就。"""
        ejaculation_service.ejaculation_flow(MOUTH, 0, TARGET, draw_flag=False)
        self.assertEqual(self.banners, [])
        self.assertEqual(dirty.view(TARGET).body_semen[MOUTH][1], SHOT[1])
        self.assert_settled()


class TkBannerTest(FastTestCase):
    """经 load_order 登记 Tk 射精文本回调后的六步绘制测试。"""

    def setUp(self) -> None:
        """载入启动顺序以登记 Tk 回调，准备测试角色并拦截绘制类的 draw 调用。"""
        super().setUp()
        core.load(load_order.LOAD_ORDER)
        self.world.chara(0, "博士")
        self.world.chara(TARGET, "测试干员")
        self.enterContext(working.based_on(core.state()))
        self.enterContext(
            mock.patch.object(
                ejaculation_service, "common_ejaculation", return_value=SHOT
            )
        )
        for name in ("get_achievement_judge_by_value", "settle_and_notify"):
            self.enterContext(mock.patch.object(achievement_service, name))
        self.drawn: list[tuple[str, str, float, str]] = []
        for cls in (draw.NormalDraw, draw.WaitDraw, draw.LineDraw):
            self.enterContext(
                mock.patch.object(
                    cls, "draw", autospec=True, side_effect=self.keep
                )
            )

    def keep(self, now: draw.NormalDraw | draw.LineDraw) -> None:
        """
        记录被拦截绘制对象的类名、文本、宽度与样式。
        Keyword arguments:
        now -- draw.NormalDraw | draw.LineDraw，被调用 draw 的绘制对象
        Return arguments:
        None -- 无返回值
        """
        self.drawn.append((type(now).__name__, now.text, now.width, now.style))

    def test_banner_draws_six_steps(self) -> None:
        """验证射精流程触发 Tk 回调后按序输出换行、分隔线、换行、semen 样式 WaitDraw 与两次换行。"""
        ejaculation_service.ejaculation_flow(MOUTH, 0, TARGET)
        width = normal_config.config_normal.text_width
        text = get_text._("在{0}的{1}{2}").format(
            identity.of(TARGET).name,
            game_config.config_body_part[MOUTH].name,
            SHOT[0],
        )
        feed = ("NormalDraw", "\n", 1, draw.NormalDraw().style)
        self.assertEqual(
            self.drawn,
            [
                feed,
                ("LineDraw", "-", width, draw.LineDraw("-", width).style),
                feed,
                ("WaitDraw", text, width, "semen"),
                feed,
                feed,
            ],
        )


class ModuleBoundaryTest(FastTestCase):
    """调用方与射精面板模块边界的语法树测试。"""

    def test_callers_import_services(self) -> None:
        """验证五个调用方模块均导入射精或精液污浊服务。"""
        for module in CALLERS:
            imports = imported_modules(module)
            self.assertTrue(
                {
                    ejaculation_service.__name__,
                    semen_dirty_service.__name__,
                }
                & imports,
                module.__name__,
            )

    def test_relative_import_of_panel_is_caught(self) -> None:
        """验证 imports_in 能按所属包名解析函数内对射精面板的相对导入并检出面板路径。"""
        source = "def f():\n    from ..UI.Panel import ejaculation_panel\n"
        package = settle_default.__package__ or ""
        self.assertIn(PANEL, imports_in(source, package))

    def test_panel_keeps_only_panel_code(self) -> None:
        """
        验证射精面板顶层只定义 show_endure_ejaculation_panel 与 Ejaculation_Panel，
        且任意作用域不绑定五个服务函数名。
        """
        tree = ast.parse(inspect.getsource(ejaculation_panel))
        defined = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.ClassDef))
        }
        self.assertEqual(
            defined, {"show_endure_ejaculation_panel", "Ejaculation_Panel"}
        )
        bound = {
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        assigned = {
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
        }
        self.assertFalse(MOVED & (bound | assigned))
