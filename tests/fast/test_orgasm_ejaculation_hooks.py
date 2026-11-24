"""
高潮与射精结算界面回调测试
==========================
- EjaculationHookTest：忍耐询问与射精面板单槽位回调的登记、覆盖与返回值约定。
- TkEjaculationPanelTest：正常启动流程登记 Tk 回调及两类回调的委托与绘制顺序。
- OrgasmJudgeTest：玩家射精时 orgasm_judge 对两类回调的派发。
- EdgeNoticeTest：寸止判定结果经提示回调派发。
- ClimaxPanelTest：玩家 P 部位绝顶时 base_chara_climix_common_settle 派发射精面板。
- ImportBoundaryTest：两个结算模块与射精服务的导入边界及不加载射精面板。
"""

import json
import subprocess
import sys
from unittest import mock

from Script.Config import normal_config
from Script.Core import game_type, get_text
from Script.Kernel import core
from Script.Modules.domains import abilities, activity, h_meters, h_state
from Script.Modules.gameplay_resolution import ejaculation_service, ui_hooks
from Script.Modules.gameplay_resolution import working
from Script.Modules.tk_ui import callbacks
from Script.Settle import common_default, orgasm_settle
from Script.UI.Moudle import draw
from Script.UI.Panel import ejaculation_panel
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT, banned_imports

TARGET = 1
""" 测试使用的目标角色编号（1）。 """
NAME = "测试干员"
""" 测试使用的目标角色名称。 """
SOURCES = (
    "Script/Modules/gameplay_resolution/ejaculation_service.py",
    "Script/Settle/orgasm_settle.py",
    "Script/Settle/common_default.py",
)
""" 需通过后端界面边界检查的三个模块仓库相对路径元组。 """
STARTUP_CHECK = """
import json, sys
from Script.Config import normal_config
normal_config.init_normal_config()
from Script.Modules.gameplay_resolution import ejaculation_service
before = [
    ejaculation_service._endure_panel is not None,
    ejaculation_service._ejaculation_panel is not None,
    "Script.Modules.tk_ui.callbacks" in sys.modules,
]
from Script.Kernel import core
from Script.Modules import load_order
core.load(load_order.LOAD_ORDER)
endure = ejaculation_service._endure_panel
panel = ejaculation_service._ejaculation_panel
print(json.dumps({
    "before": before,
    "endure": None if endure is None else [endure.__module__, endure.__name__],
    "panel": None if panel is None else [panel.__module__, panel.__name__],
}))
"""
""" 子进程脚本源码：不直接导入 callbacks，经正常启动加载顺序完成内核装载并输出两类回调的登记结果。 """
CLEAN_RUN = """
import json, sys
from Script.Config import normal_config
normal_config.init_normal_config()
from Script.Modules.gameplay_resolution import ejaculation_service
shown = []
ejaculation_service.on_endure_panel(lambda: False)
ejaculation_service.on_endure_panel(lambda: True)
ejaculation_service.on_ejaculation_panel(lambda: shown.append("first"))
ejaculation_service.on_ejaculation_panel(lambda: shown.append("panel"))
endured = ejaculation_service.emit_endure_panel()
ejaculation_service.emit_ejaculation_panel()
from Script.Settle import common_default, orgasm_settle
loaded = sorted(
    name
    for name in sys.modules
    if name.split(".")[0] in ("tkinter", "_tkinter")
    or name == "Script.UI.Panel.ejaculation_panel"
)
print(json.dumps({"endured": endured, "shown": shown, "loaded": loaded}))
"""
""" 子进程脚本源码：登记两类回调并各派发一次，再导入两个结算模块，以 JSON 输出派发结果与已加载的射精面板或 Tk 模块。 """

type Drawn = tuple[str, object, object, object]
""" 一次绘制的记录元组类型，依次为绘制类名、文本、宽度与样式名。 """

_ = get_text._


class DrawCase(FastTestCase):
    """初始化玩家与目标角色，并接管射精面板与 draw 模块中各绘制类 draw 方法的测试基类。"""

    def setUp(self) -> None:
        """初始化玩家与目标角色，打开工作集，并把射精面板与各绘制类的 draw 调用记录到 self.drawn。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(TARGET, NAME)
        self.enterContext(working.based_on(core.state()))
        self.drawn: list[Drawn] = []
        classes = [ejaculation_panel.Ejaculation_Panel]
        classes += [
            cls
            for cls in vars(draw).values()
            if isinstance(cls, type) and hasattr(cls, "draw")
        ]
        for cls in classes:
            self.enterContext(
                mock.patch.object(
                    cls, "draw", autospec=True, side_effect=self.keep
                )
            )

    def keep(self, now: object) -> None:
        """
        记录一次被调用 draw 方法的绘制对象信息到 self.drawn。
        Keyword arguments:
        now -- object，被调用 draw 方法的绘制对象实例
        """
        self.drawn.append(
            (
                type(now).__name__,
                getattr(now, "text", None),
                getattr(now, "width", None),
                getattr(now, "style", None),
            )
        )

    def panel_drawn(self) -> list[Drawn]:
        """
        构造射精面板预期的两步绘制记录。
        Return arguments:
        list[Drawn] -- 按配置文本宽度绘制的射精面板与同宽分隔线
        """
        width = normal_config.config_normal.text_width
        return [
            ("Ejaculation_Panel", None, width, None),
            ("LineDraw", "-", width, "standard"),
        ]


class EjaculationHookTest(FastTestCase):
    """忍耐询问与射精面板单槽位回调的登记、覆盖与返回值测试。"""

    def setUp(self) -> None:
        """将两类回调槽位暂时重置为 None，并在结束后恢复原值。"""
        super().setUp()
        self.enterContext(
            mock.patch.object(ejaculation_service, "_endure_panel", None)
        )
        self.enterContext(
            mock.patch.object(ejaculation_service, "_ejaculation_panel", None)
        )

    def test_unregistered_hooks(self) -> None:
        """验证未登记回调时 emit_endure_panel 返回 False，emit_ejaculation_panel 不执行操作。"""
        self.assertIs(ejaculation_service.emit_endure_panel(), False)
        self.assertIsNone(ejaculation_service.emit_ejaculation_panel())

    def test_endure_answer_is_returned(self) -> None:
        """验证 on_endure_panel 原样返回传入回调，emit_endure_panel 返回回调的 True 或 False。"""
        endure = mock.Mock(return_value=True)
        self.assertIs(ejaculation_service.on_endure_panel(endure), endure)
        self.assertIs(ejaculation_service.emit_endure_panel(), True)
        endure.return_value = False
        self.assertIs(ejaculation_service.emit_endure_panel(), False)
        self.assertEqual(endure.call_args_list, [mock.call(), mock.call()])

    def test_endure_replaces_previous_handler(self) -> None:
        """验证后登记的忍耐询问回调覆盖先前的回调，派发时只调用最新登记的回调。"""
        calls = mock.Mock()
        calls.first.return_value = True
        calls.second.return_value = False
        ejaculation_service.on_endure_panel(calls.first)
        ejaculation_service.on_endure_panel(calls.second)
        self.assertIs(ejaculation_service.emit_endure_panel(), False)
        self.assertEqual(calls.mock_calls, [mock.call.second()])

    def test_panel_replaces_previous_handler(self) -> None:
        """验证 on_ejaculation_panel 原样返回回调且后登记者覆盖先登记者，派发时只调用最新回调一次。"""
        calls = mock.Mock()
        self.assertIs(
            ejaculation_service.on_ejaculation_panel(calls.first), calls.first
        )
        self.assertIs(
            ejaculation_service.on_ejaculation_panel(calls.second), calls.second
        )
        ejaculation_service.emit_ejaculation_panel()
        self.assertEqual(calls.mock_calls, [mock.call.second()])


class TkEjaculationPanelTest(DrawCase):
    """正常启动登记与 Tk 回调对忍耐询问、射精面板的委托与绘制顺序测试。"""

    def test_startup_registers_tk_callbacks(self) -> None:
        """验证独立子进程在不直接导入 callbacks 时，执行正常启动加载顺序后会登记两个 Tk 回调。"""
        result = subprocess.run(
            [sys.executable, "-c", STARTUP_CHECK],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        report = json.loads(result.stdout.splitlines()[-1])
        self.assertEqual(
            report,
            {
                "before": [False, False, False],
                "endure": [
                    "Script.Modules.tk_ui.callbacks",
                    "draw_endure_ejaculation_panel",
                ],
                "panel": [
                    "Script.Modules.tk_ui.callbacks",
                    "draw_ejaculation_panel",
                ],
            },
        )

    def test_endure_callback_returns_panel_answer(self) -> None:
        """验证 draw_endure_ejaculation_panel 无参调用 show_endure_ejaculation_panel 并原样返回 True 或 False。"""
        show = self.enterContext(
            mock.patch.object(
                ejaculation_panel,
                "show_endure_ejaculation_panel",
                side_effect=[True, False],
            )
        )
        self.assertIs(callbacks.draw_endure_ejaculation_panel(), True)
        self.assertIs(callbacks.draw_endure_ejaculation_panel(), False)
        self.assertEqual(show.call_args_list, [mock.call(), mock.call()])

    def test_panel_callback_draws_panel_then_line(self) -> None:
        """验证 draw_ejaculation_panel 先按配置文本宽度绘制射精面板，再绘制同宽分隔线。"""
        callbacks.draw_ejaculation_panel()
        self.assertEqual(self.drawn, self.panel_drawn())


class OrgasmJudgeTest(DrawCase):
    """玩家射精槽满时 orgasm_judge 对忍耐询问与射精面板回调的派发测试。"""

    def setUp(self) -> None:
        """
        将玩家射精槽设为已满、精液量设为 100，
        并把两类回调槽位替换为模拟忍耐回调与射精面板记录回调。
        """
        super().setUp()
        h_meters.set(0, eja=1000, eja_max=1000, semen=100, extra_semen=0)
        self.endure = mock.Mock(return_value=False)
        self.panels = mock.Mock()
        self.enterContext(
            mock.patch.object(ejaculation_service, "_endure_panel", self.endure)
        )
        self.enterContext(
            mock.patch.object(
                ejaculation_service, "_ejaculation_panel", self.panels
            )
        )
        self.change = game_type.CharacterStatusChange()

    def test_endured_skips_panel(self) -> None:
        """验证忍耐回调返回 True 时 orgasm_judge 直接返回，不登记射精二段行为也不派发射精面板。"""
        self.endure.return_value = True
        orgasm_settle.orgasm_judge(0, self.change)
        self.endure.assert_called_once_with()
        self.panels.assert_not_called()
        self.assertEqual(activity.second_behavior(0, "p_orgasm_small"), 0)
        self.assertEqual(self.drawn, [])

    def test_not_endured_shows_panel(self) -> None:
        """验证忍耐回调返回 False 时登记 p_orgasm_small、清空射精槽并派发一次射精面板。"""
        orgasm_settle.orgasm_judge(0, self.change)
        self.endure.assert_called_once_with()
        self.panels.assert_called_once_with()
        self.assertEqual(activity.second_behavior(0, "p_orgasm_small"), 1)
        self.assertEqual(h_meters.of(0)["eja"], 0)
        self.assertEqual(self.drawn, [])

    def test_skip_endure_shows_panel(self) -> None:
        """验证 skip_undure 为真时不调用忍耐回调，按忍住次数登记 p_orgasm_strong 并派发一次射精面板。"""
        h_state.set(0, endure_not_shot_count=4)
        orgasm_settle.orgasm_judge(0, self.change, skip_undure=True)
        self.endure.assert_not_called()
        self.panels.assert_called_once_with()
        self.assertEqual(activity.second_behavior(0, "p_orgasm_strong"), 1)

    def test_no_semen_skips_both_hooks(self) -> None:
        """验证玩家精液合计不超过 2ml 时登记 p_no_semen_climax，且不调用两类回调。"""
        h_meters.set(0, semen=2, extra_semen=0)
        orgasm_settle.orgasm_judge(0, self.change)
        self.endure.assert_not_called()
        self.panels.assert_not_called()
        self.assertEqual(activity.second_behavior(0, "p_no_semen_climax"), 1)

    def test_tk_callbacks_draw_panel(self) -> None:
        """验证经已登记 Tk 回调结算一次未忍住的射精时，依次绘制射精面板与同宽分隔线。"""
        self.enterContext(
            mock.patch.object(
                ejaculation_service,
                "_endure_panel",
                callbacks.draw_endure_ejaculation_panel,
            )
        )
        self.enterContext(
            mock.patch.object(
                ejaculation_service,
                "_ejaculation_panel",
                callbacks.draw_ejaculation_panel,
            )
        )
        self.enterContext(
            mock.patch.object(
                ejaculation_panel,
                "show_endure_ejaculation_panel",
                return_value=False,
            )
        )
        orgasm_settle.orgasm_judge(0, self.change)
        self.assertEqual(self.drawn, self.panel_drawn())


class EdgeNoticeTest(DrawCase):
    """judge_orgasm_edge_success 的寸止结果提示派发测试。"""

    def setUp(self) -> None:
        """将 ui_hooks._notices 暂时替换为只含 self.record 的列表。"""
        super().setUp()
        self.notices: list[tuple[str, bool, str | None, bool]] = []
        self.enterContext(
            mock.patch.object(ui_hooks, "_notices", [self.record])
        )

    def record(
        self, text: str, *, wait: bool, style: str | None, use_text_width: bool
    ) -> None:
        """
        将一次经 ui_hooks.emit_notice 派发的提示参数元组追加到 self.notices。
        Keyword arguments:
        text -- str，提示文本
        wait -- bool，是否等待玩家确认
        style -- str | None，文本样式名
        use_text_width -- bool，是否按配置文本宽度排版
        """
        self.notices.append((text, wait, style, use_text_width))

    def judge(self, level: int, roll: float = 0.5) -> bool:
        """
        以玩家寸止技巧等级 level 与随机数 roll 对一个部位的一次寸止计数进行判定。
        Keyword arguments:
        level -- int，玩家能力 30 的等级
        roll -- float，random.uniform 的返回值
        Return arguments:
        bool -- judge_orgasm_edge_success 的结果
        """
        abilities.ability(0)[30] = level
        with mock.patch.object(orgasm_settle.random, "uniform") as uniform:
            uniform.return_value = roll
            return orgasm_settle.judge_orgasm_edge_success(TARGET, {4: 1})

    def test_success_notice(self) -> None:
        """验证技巧余量大于 2 时判定成功，并派发一条不等待、默认样式与宽度的成功提示。"""
        self.assertIs(self.judge(2), True)
        text = "\n" + _("成功寸止了{0}的绝顶\n").format(NAME)
        self.assertEqual(self.notices, [(text, False, None, False)])
        self.assertEqual(self.drawn, [])

    def test_near_limit_notice(self) -> None:
        """验证技巧余量在 0 到 2 之间时判定成功，并派发接近极限的提示。"""
        self.assertIs(self.judge(1), True)
        text = "\n" + _(
            "成功寸止了{0}的绝顶，但差不多也到了能控制住的极限了，还是尽快释放出来比较好\n"
        ).format(NAME)
        self.assertEqual(self.notices, [(text, False, None, False)])

    def test_fail_and_over_limit_notices(self) -> None:
        """验证技巧不足时随机数低于失败率则判定失败，否则判定成功，两种结果各派发对应提示。"""
        self.assertIs(self.judge(0, roll=0.0), False)
        self.assertIs(self.judge(0, roll=0.99), True)
        self.assertEqual(
            [text for text, *_rest in self.notices],
            [
                "\n" + _("尝试寸止{0}的绝顶，但失败了\n").format(NAME),
                "\n"
                + _(
                    "成功寸止了{0}的绝顶，但已经超过了能控制住的极限，随时都可能释放出来\n"
                ).format(NAME),
            ],
        )

    def test_tk_notice_draws_normal_text(self) -> None:
        """验证经 callbacks.draw_notice 派发时，成功提示绘制为一个宽度为 0、样式为 standard 的 NormalDraw。"""
        ui_hooks._notices[:] = [callbacks.draw_notice]
        self.judge(2)
        text = "\n" + _("成功寸止了{0}的绝顶\n").format(NAME)
        self.assertEqual(self.drawn, [("NormalDraw", text, 0, "standard")])


class ClimaxPanelTest(DrawCase):
    """base_chara_climix_common_settle 在玩家 P 部位绝顶时的射精面板派发测试。"""

    def setUp(self) -> None:
        """将玩家射精槽设为 500，并把射精面板回调槽位替换为记录回调。"""
        super().setUp()
        h_meters.set(0, eja=500)
        self.panels = mock.Mock()
        self.enterContext(
            mock.patch.object(
                ejaculation_service, "_ejaculation_panel", self.panels
            )
        )

    def test_penis_climax_shows_panel(self) -> None:
        """验证玩家 P 部位（part_id 为 3）绝顶时清空射精槽并派发一次射精面板。"""
        common_default.base_chara_climix_common_settle(0, part_id=3)
        self.panels.assert_called_once_with()
        self.assertEqual(h_meters.of(0)["eja"], 0)
        self.assertEqual(self.drawn, [])

    def test_npc_penis_part_is_ignored(self) -> None:
        """验证非玩家角色的 P 部位绝顶直接返回，不派发射精面板。"""
        common_default.base_chara_climix_common_settle(TARGET, part_id=3)
        self.panels.assert_not_called()

    def test_tk_callback_draws_panel(self) -> None:
        """验证经已登记 Tk 回调结算玩家 P 部位绝顶时，依次绘制射精面板与同宽分隔线。"""
        self.enterContext(
            mock.patch.object(
                ejaculation_service,
                "_ejaculation_panel",
                callbacks.draw_ejaculation_panel,
            )
        )
        common_default.base_chara_climix_common_settle(0, part_id=3)
        self.assertEqual(self.drawn, self.panel_drawn())


class ImportBoundaryTest(FastTestCase):
    """两个结算模块与射精服务的导入边界及不加载射精面板测试。"""

    def test_sources_import_no_ui(self) -> None:
        """验证两个结算模块与射精服务均通过 banned_imports 检查。"""
        for path in SOURCES:
            with self.subTest(path=path):
                self.assertEqual(
                    banned_imports((ROOT / path).read_bytes(), path), []
                )

    def test_settles_load_without_panel(self) -> None:
        """验证独立子进程中两类单槽位回调按约定派发，且导入两个结算模块后不加载射精面板模块与 Tk 模块。"""
        result = subprocess.run(
            [sys.executable, "-c", CLEAN_RUN],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        report = json.loads(result.stdout.splitlines()[-1])
        self.assertEqual(
            report, {"endured": True, "shown": ["panel"], "loaded": []}
        )
