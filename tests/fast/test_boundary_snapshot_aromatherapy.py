"""
香薰疗愈边界快照与查询测试
==========================
- 值对象（SnapshotValueTest）：验证快照与行动计划数据类的字段校验、不可变性与槽位约束。
- 状态快照（AromatherapySnapshotTest）：验证剩余次数、对象、资源筛选、解锁原因与确认条件。
- 行动计划（AromatherapyPlanTest）：验证 8 种配方的动作映射、库存不足拒绝与未知配方拒绝。
- 面板集成（AromatherapyPanelTest）：验证面板绘制快照、选配方、确认执行与完整按键流程。
- 导入边界（SnapshotImportBoundaryTest）：验证 boundary_snapshot.py 仅绝对导入标准库。
"""

import ast
import dataclasses
import sys
from pathlib import Path
from unittest import mock

from Script.Config import game_config
from Script.Core import constant, flow_handle
from Script.Kernel import core
from Script.Modules.domains import flags, identity, tallies, warehouse
from Script.Modules.gameplay_resolution import aromatherapy_query, working
from Script.Modules.tk_ui import player_pick
from Script.Protocol import boundary_snapshot as bs
from Script.UI.Moudle import draw
from Script.UI.Panel import aromatherapy_panel
from tests import chara_abilities as ca
from tests import kernel_data
from tests.chara_activity import aim
from tests.fast.base import FastTestCase

NPC = 1
""" 测试用调香对象角色编号（1）。 """
SPICE = 16
""" 香料的资源编号（16）。 """
ESSENCE = 41
""" 浓缩香精的资源编号（41）。 """
DRAWN = (draw.NormalDraw, draw.TitleLineDraw, draw.LineDraw, draw.CenterButton)
""" 面板测试中统一拦截绘制调用的界面绘制类元组。 """


class _Screen:
    """无界面测试用的屏幕记录器，记录绘制内容并按预设按键驱动选项回调。"""

    def __init__(self) -> None:
        """初始化按键队列、绘制记录列表与按钮索引字典。"""
        self.presses: list[str] = []
        self.drawn: list[tuple[str, str, str, str | None]] = []
        self.buttons: dict[str, draw.CenterButton] = {}

    def record(self, obj: object) -> None:
        """记录单次绘制对象的类名、文本、样式与返回键，并登记 CenterButton 实例。"""
        text = getattr(obj, "text", getattr(obj, "title", ""))
        style = getattr(obj, "style", getattr(obj, "normal_style", ""))
        key = getattr(obj, "return_text", None)
        if isinstance(obj, draw.CenterButton):
            self.buttons[obj.return_text] = obj
        self.drawn.append((type(obj).__name__, str(text), str(style), key))

    def askfor_all(self, return_list: list[str], *args: object) -> str:
        """按预设按键匹配按钮并触发其绑定回调，清空按钮表后返回对应键值。"""
        label = self.presses.pop(0)
        key = next(
            k
            for k in return_list
            if k in self.buttons and label in self.buttons[k].text
        )
        button = self.buttons[key]
        self.buttons.clear()
        if button.cmd_func is not None:
            given = button.args
            button.cmd_func(*(given if isinstance(given, tuple) else (given,)))
        return key

    def texts(self, kind: str) -> list[str]:
        """筛选并返回指定绘制类名的文本列表。"""
        return [text for name, text, _style, _key in self.drawn if name == kind]


def _option(
    recipe_id: int,
    reasons: tuple[str, ...] = (),
    ingredients: tuple[bs.RecipeIngredient, ...] = (),
) -> bs.AromatherapyRecipeOption:
    """构造带默认名称与介绍的测试用配方选项对象。"""
    name, info = f"配方{recipe_id}", f"介绍{recipe_id}"
    return bs.AromatherapyRecipeOption(
        recipe_id, name, info, not reasons, reasons, ingredients
    )


def _snapshot(
    can_confirm: bool, recipes: tuple[bs.AromatherapyRecipeOption, ...] = ()
) -> bs.AromatherapySnapshot:
    """构造指定确认状态与配方列表的测试用香薰快照对象。"""
    stock = (
        bs.ResourceStockItem(SPICE, "香料", 7),
        bs.ResourceStockItem(43, "高级香水", 1),
    )
    meta = bs.SnapshotMeta(5, "aromatherapy")
    return bs.AromatherapySnapshot(
        meta,
        4,
        NPC,
        "某干员",
        "某配方",
        stock,
        2,
        "某选中",
        can_confirm,
        recipes,
    )


class SnapshotValueTest(FastTestCase):
    """验证边界快照与命令计划数据类的字段校验与不可变约束。"""

    def test_meta_checks_clock_and_panel(self) -> None:
        """验证 SnapshotMeta 拒绝非整型、布尔或负值 clock 以及非字符串或空 panel。"""
        self.assertEqual(bs.SnapshotMeta(0, "aromatherapy").clock, 0)
        for clock in (True, False, 1.0, "3", None):
            with self.subTest(clock=clock):
                self.assertRaises(TypeError, bs.SnapshotMeta, clock, "x")
        self.assertRaises(ValueError, bs.SnapshotMeta, -1, "x")
        self.assertRaises(TypeError, bs.SnapshotMeta, 0, None)
        self.assertRaises(ValueError, bs.SnapshotMeta, 0, "")

    def test_outcome_checks_flag_and_reason(self) -> None:
        """验证 CommandOutcome 默认空原因码，并拒绝非布尔 accepted 与非字符串 reason。"""
        self.assertEqual(bs.CommandOutcome(True), bs.CommandOutcome(True, ""))
        for accepted in (1, 0, None, "yes"):
            with self.subTest(accepted=accepted):
                self.assertRaises(TypeError, bs.CommandOutcome, accepted)
        for reason in (None, 3):
            with self.subTest(reason=reason):
                self.assertRaises(TypeError, bs.CommandOutcome, False, reason)

    def test_plan_fields_follow_outcome(self) -> None:
        """验证 AromatherapyActionPlan 在受理时要求三项行动字段齐全、拒绝时三者均为 None。"""
        yes, no = bs.CommandOutcome(True), bs.CommandOutcome(False, "short")
        plan = bs.AromatherapyActionPlan
        self.assertEqual(plan(yes, "b", 1, 2).recipe_id, 2)
        self.assertIsNone(plan(no).behavior_id)
        for fields in ((None, 1, 2), ("b", None, 2), ("b", 1, None), ()):
            with self.subTest(accepted=fields):
                self.assertRaises(ValueError, plan, yes, *fields)
        for fields in (("b",), (None, 1), (None, None, 2)):
            with self.subTest(rejected=fields):
                self.assertRaises(ValueError, plan, no, *fields)

    def test_values_are_frozen(self) -> None:
        """验证边界值对象拒绝属性写入且不生成实例 __dict__。"""
        values = (
            bs.SnapshotMeta(0, "aromatherapy"),
            bs.CommandOutcome(False),
            bs.AromatherapyActionPlan(bs.CommandOutcome(False)),
            _snapshot(True, (_option(1),)),
        )
        for value in values:
            with self.subTest(type(value).__name__):
                first = dataclasses.fields(value)[0].name
                with self.assertRaises(dataclasses.FrozenInstanceError):
                    setattr(value, first, None)
                self.assertFalse(hasattr(value, "__dict__"))


class _AromatherapyWorld(FastTestCase):
    """香薰查询与面板测试基类，准备玩家、干员角色及状态配置辅助方法。"""

    def setUp(self) -> None:
        """创建角色 0 与测试干员 NPC，并将玩家交互目标指向 NPC。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(NPC, "干员")
        aim(0, NPC)

    def given(
        self,
        sex: int = 0,
        level: int = 0,
        sessions: int = 1,
        treated: int = 0,
        stock: dict[int, int] | None = None,
    ) -> None:
        """设置测试干员性别、玩家农业技能等级、剩余次数、今日已调香标记与仓库库存。"""
        kernel_data.put(identity.update, NPC, sex=sex)
        ca.ability(0)[47] = level
        kernel_data.put(tallies.set, tallies.AROMATHERAPY, sessions)
        kernel_data.put(flags.set, NPC, aromatherapy=treated)
        for rid, amount in (stock or {}).items():
            kernel_data.put(warehouse.set, rid, amount)

    def snapshot(self, selected: int = 0) -> bs.AromatherapySnapshot:
        """在当前内核状态工作集中调用 build_aromatherapy_snapshot 生成快照。"""
        with working.based_on(core.state()):
            return aromatherapy_query.build_aromatherapy_snapshot(selected)

    def plan(self, recipe_id: int) -> bs.AromatherapyActionPlan:
        """在当前内核状态工作集中调用 plan_aromatherapy_action 生成行动计划。"""
        with working.based_on(core.state()):
            return aromatherapy_query.plan_aromatherapy_action(recipe_id)

    def options(self) -> dict[int, bs.AromatherapyRecipeOption]:
        """从当前快照提取按配方编号索引的配方选项字典。"""
        return {option.recipe_id: option for option in self.snapshot().recipes}


class AromatherapySnapshotTest(_AromatherapyWorld):
    """验证 build_aromatherapy_snapshot 读取游戏状态并计算快照字段的正确性。"""

    def test_sessions_target_and_treated_label(self) -> None:
        """验证快照元数据、剩余次数、目标角色信息及今日已调香配方名的读取结果。"""
        self.given(sessions=2)
        snapshot = self.snapshot()
        meta = bs.SnapshotMeta(core.state().clock, "aromatherapy")
        self.assertEqual(snapshot.meta, meta)
        self.assertEqual(snapshot.remaining_today, 2)
        target = (snapshot.target_cid, snapshot.target_name)
        self.assertEqual(target, (NPC, "干员"))
        self.assertIsNone(snapshot.target_today_recipe_name)
        self.given(treated=3)
        self.assertEqual(
            self.snapshot().target_today_recipe_name,
            game_config.config_aromatherapy_recipes[3].name,
        )

    def test_resources_keep_spice_and_perfumes(self) -> None:
        """验证库存筛选按顺序保留香料与四类香水资源并排除资源 1。"""
        self.given(stock={SPICE: 7, ESSENCE: 2, 1: 5})
        rows = [
            (item.resource_id, item.name, item.amount)
            for item in self.snapshot().resources
        ]
        names = ["香料", "浓缩香精", "普通香水", "高级香水", "药用香水"]
        ids, amounts = [16, 41, 42, 43, 44], [7, 2, 0, 0, 0]
        self.assertEqual(rows, list(zip(ids, names, amounts, strict=True)))

    def test_level_and_sex_lock_recipes(self) -> None:
        """验证农业技能等级不足与对象性别不符时配方的未解锁原因及 unlocked 状态。"""
        female, male = ("(仅限女性调香对象)",), ("(仅限男性调香对象)",)
        expected = {
            (1, 2): {
                2: (),
                4: ("(需要[农业技能]等级>=4)",),
                8: ("(需要[农业技能]等级>=6)",),
            },
            (1, 6): {2: (), 4: (), 8: (), 6: (), 7: male},
            (0, 6): {3: female, 5: female, 6: female, 7: ()},
        }
        for (sex, level), reasons in expected.items():
            self.given(sex=sex, level=level)
            options = self.options()
            for recipe_id, wanted in reasons.items():
                with self.subTest(sex=sex, level=level, recipe=recipe_id):
                    self.assertEqual(options[recipe_id].lock_reasons, wanted)
                    self.assertEqual(options[recipe_id].unlocked, not wanted)

    def test_recipes_list_both_reasons_and_ingredients(self) -> None:
        """验证配方列表覆盖编号 1 至 8、配方 3 的双项锁定原因及配方 2 与 6 的材料消耗。"""
        self.given(sex=0, level=0)
        options = self.options()
        self.assertEqual(list(options), [1, 2, 3, 4, 5, 6, 7, 8])
        self.assertEqual(
            options[3].lock_reasons,
            ("(需要[农业技能]等级>=4)", "(仅限女性调香对象)"),
        )
        spice = bs.RecipeIngredient(SPICE, "香料", 5)
        essence = bs.RecipeIngredient(ESSENCE, "浓缩香精", 1)
        self.assertEqual(options[2].ingredients, (spice, essence))
        spice = bs.RecipeIngredient(SPICE, "香料", 20)
        self.assertEqual(options[6].ingredients, (spice,))

    def test_confirm_needs_recipe_session_and_untreated_target(self) -> None:
        """验证 can_confirm 组合真值表以及未选与选中配方时的名称展示。"""
        for selected, sessions, treated in (
            (s, n, t) for s in (0, 2) for n in (0, 1) for t in (0, 3)
        ):
            self.given(sessions=sessions, treated=treated)
            snapshot = self.snapshot(selected)
            with self.subTest(selected=selected, sessions=sessions, t=treated):
                wanted = selected == 2 and sessions == 1 and treated == 0
                self.assertEqual(snapshot.can_confirm, wanted)
                self.assertEqual(snapshot.selected_recipe_id, selected)
        self.assertEqual(self.snapshot(0).selected_recipe_name, "无")
        self.assertEqual(self.snapshot(2).selected_recipe_name, "迷梦香精")


class AromatherapyPlanTest(_AromatherapyWorld):
    """验证 plan_aromatherapy_action 的配方映射与拒绝分支。"""

    def test_each_recipe_plans_its_action(self) -> None:
        """验证库存充足时配方 1 至 8 均生成对应的行为编号与角色状态常量计划。"""
        self.given(stock={SPICE: 100, ESSENCE: 10, 43: 10})
        for recipe_id in range(1, 9):
            behavior = getattr(constant.Behavior, f"AROMATHERAPY_{recipe_id}")
            status = constant.CharacterStatus
            state = getattr(status, f"STATUS_AROMATHERAPY_{recipe_id}")
            wanted = bs.AromatherapyActionPlan(
                bs.CommandOutcome(True), behavior, state, recipe_id
            )
            with self.subTest(recipe=recipe_id):
                self.assertEqual(self.plan(recipe_id), wanted)

    def test_short_stock_rejects(self) -> None:
        """验证库存刚好满足时受理配方 1，材料不足时以 insufficient_resources 拒绝配方 2 与 6。"""
        self.given(stock={SPICE: 5, ESSENCE: 0})
        self.assertTrue(self.plan(1).outcome.accepted)
        reason = bs.CommandOutcome(False, "insufficient_resources")
        short = bs.AromatherapyActionPlan(reason)
        self.assertEqual(self.plan(2), short)
        self.assertEqual(self.plan(6), short)

    def test_unknown_recipe_rejects(self) -> None:
        """验证编号 0 与 99 等未登记配方以 unknown_recipe 被拒绝。"""
        self.given(stock={SPICE: 100})
        reason = bs.CommandOutcome(False, "unknown_recipe")
        unknown = bs.AromatherapyActionPlan(reason)
        self.assertEqual(self.plan(0), unknown)
        self.assertEqual(self.plan(99), unknown)


class AromatherapyPanelTest(_AromatherapyWorld):
    """打桩绘制与输入接口，验证香薰疗愈面板的展示与行动触发逻辑。"""

    def setUp(self) -> None:
        """拦截界面绘制与 askfor_all 调用，打开工作集并初始化香薰面板实例。"""
        super().setUp()
        self.screen = _Screen()
        record = self.screen.record
        for cls in (*DRAWN, draw.LeftButton):
            patch = mock.patch.object(
                cls, "draw", autospec=True, side_effect=record
            )
            self.enterContext(patch)
        ask = mock.patch.object(
            flow_handle, "askfor_all", self.screen.askfor_all
        )
        self.enterContext(ask)
        self.enterContext(working.based_on(core.state()))
        self.panel = aromatherapy_panel.Aromatherapy_Panel(100)

    def patch_query(self, name: str, value: object) -> mock.MagicMock:
        """将 aromatherapy_query 中指定名称的对象打桩为固定返回值。"""
        patch = mock.patch.object(aromatherapy_query, name, return_value=value)
        return self.enterContext(patch)

    def test_draw_renders_query_snapshot(self) -> None:
        """验证 draw() 按查询快照输出信息行，并依据 can_confirm 控制 [确定] 按钮显示。"""
        for can_confirm, buttons in (
            (True, [" [001]选择配方 ", "[确定]", "[返回]"]),
            (False, [" [001]选择配方 ", "[返回]"]),
        ):
            with self.subTest(can_confirm=can_confirm):
                self.screen.presses[:] = ["返回"]
                self.screen.drawn.clear()
                self.panel.now_choice_recipe_id = 2
                with mock.patch.object(
                    aromatherapy_query,
                    "build_aromatherapy_snapshot",
                    return_value=_snapshot(can_confirm),
                ) as built:
                    self.panel.draw()
                built.assert_called_once_with(2)
                self.assertEqual(
                    [t for t in self.screen.texts("NormalDraw") if t != "\n"],
                    [
                        "\n  今日剩余调香次数    ：  4次",
                        "\n  当前调香对象        ：  某干员(今日已调香-某配方)",
                        "\n  当前调香资源        ：  香料：7  高级香水：1",
                        "\n  当前选择的调香配方  ：  某选中",
                    ],
                )
                self.assertEqual(self.screen.texts("CenterButton"), buttons)

    def test_select_recipe_renders_options(self) -> None:
        """验证 select_recipe() 区分绘制已解锁按钮、消耗行与灰显锁定项，并在点击后更新所选配方。"""
        self.screen.presses[:] = ["[002]"]
        ingredients = (
            bs.RecipeIngredient(SPICE, "香料", 5),
            bs.RecipeIngredient(ESSENCE, "浓缩香精", 1),
        )
        recipes = (_option(2, (), ingredients), _option(7, ("(甲)", "(乙)")))
        built = self.patch_query(
            "build_aromatherapy_snapshot", _snapshot(False, recipes)
        )
        self.panel.select_recipe()
        built.assert_called_once_with(0)
        self.assertEqual(self.panel.now_choice_recipe_id, 2)
        for row in (
            ("LeftButton", "[002]配方2：介绍2", "standard", "\n2"),
            (
                "NormalDraw",
                "     调香消耗：  香料：5  浓缩香精：1",
                "standard",
                None,
            ),
            ("NormalDraw", "[007]配方7(甲)(乙)：介绍7", "deep_gray", None),
        ):
            self.assertIn(row, self.screen.drawn)

    def test_run_chooses_planned_action(self) -> None:
        """验证 run_aromatherapy() 在计划被拒时不触发选择，受理时将计划参数传给 player_pick.choose。"""
        self.panel.now_choice_recipe_id = 3
        rejected = bs.AromatherapyActionPlan(bs.CommandOutcome(False, "x"))
        planned = self.patch_query("plan_aromatherapy_action", rejected)
        self.assertIsNone(self.panel.run_aromatherapy())
        planned.return_value = bs.AromatherapyActionPlan(
            bs.CommandOutcome(True), "aromatherapy_3", 193, 3
        )
        with self.assertRaises(player_pick.Chosen) as chosen:
            self.panel.run_aromatherapy()
        planned.assert_called_with(3)
        self.assertEqual(
            chosen.exception.action.action_data,
            {
                "behavior_id": "aromatherapy_3",
                "minutes": 60,
                "state": 193,
                "args": {"recipe_id": 3},
            },
        )

    def test_confirm_picks_selected_recipe(self) -> None:
        """验证按选择配方、选中配方 2 并确认的完整流程会触发对应的调香行动选择。"""
        self.given(sex=1, level=2, sessions=1, stock={SPICE: 5, ESSENCE: 1})
        self.screen.presses[:] = ["选择配方", "[002]", "确定"]
        with self.assertRaises(player_pick.Chosen) as chosen:
            self.panel.draw()
        action = chosen.exception.action
        self.assertEqual(action.action_id, "gameplay_resolution.aromatherapy")
        self.assertEqual(
            action.action_data,
            {
                "behavior_id": constant.Behavior.AROMATHERAPY_2,
                "minutes": 60,
                "state": constant.CharacterStatus.STATUS_AROMATHERAPY_2,
                "args": {"recipe_id": 2},
            },
        )


class SnapshotImportBoundaryTest(FastTestCase):
    """检查 Script/Protocol/boundary_snapshot.py 模块导入边界的测试类。"""

    def test_snapshot_module_imports_stdlib_only(self) -> None:
        """验证 Script/Protocol/boundary_snapshot.py 仅使用绝对导入且全部来自标准库。"""
        root = Path(__file__).resolve().parents[2]
        source = (root / "Script/Protocol/boundary_snapshot.py").read_bytes()
        imported: list[tuple[int, str]] = []
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.extend((0, alias.name) for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append((node.level, node.module or ""))
        self.assertTrue(imported)
        outside = [
            (level, name)
            for level, name in imported
            if level or name.split(".")[0] not in sys.stdlib_module_names
        ]
        self.assertEqual(outside, [])
