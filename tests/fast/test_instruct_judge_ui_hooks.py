"""
指令实行值界面回调测试
======================
- ConfirmHookTest：确认提问回调的登记、顺序与返回值约定。
- TkConfirmTest：经 Tk 回调绘制确认提问的顺序与玩家选择结果。
- CalculationNoticeTest：实行值计算文本与合意获得文本的提示派发。
- AskJudgeTest：选择指令时经确认回调派发提问与早返回。
- ImportBoundaryTest：指令实行值模块与 ui_hooks 的导入边界及无界面加载。
"""

import json
import subprocess
import sys
from unittest import mock

from Script.Config import normal_config
from Script.Core import flow_handle, get_text
from Script.Design import instuct_judege
from Script.Kernel import core
from Script.Modules.domains import abilities, modes
from Script.Modules.gameplay_resolution import ui_hooks, working
from Script.Modules.tk_ui import callbacks
from Script.UI.Moudle import draw
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT, banned_imports
from tests.fast.test_ejaculation_services import imports_in

TARGET = 1
""" 测试使用的目标角色编号（1）。 """
NAME = "测试干员"
""" 测试使用的目标角色名称。 """
SOURCES = (
    "Script/Design/instuct_judege.py",
    "Script/Modules/gameplay_resolution/ui_hooks.py",
)
""" 接受导入边界检查的两个模块仓库相对路径元组。 """
CLEAN_RUN = """
import json, sys
from Script.Modules.gameplay_resolution import ui_hooks
asked = []
ui_hooks.on_confirm(lambda text: asked.append(text) or False)
answer = ui_hooks.emit_confirm("问")
loaded = sorted(
    name
    for name in sys.modules
    if name.split(".")[0] in ("tkinter", "_tkinter")
    or name == "Script.UI"
    or name.startswith("Script.UI.")
)
print(json.dumps({"asked": asked, "answer": answer, "loaded": loaded}))
"""
""" 子进程脚本源码：只导入 ui_hooks 并派发一次确认提问，以 JSON 输出提问记录、返回值与已加载的界面模块。 """

type Drawn = tuple[str, object, object, object]
""" 一次绘制的记录元组类型，依次为绘制类名、文本、宽度，以及按钮的响应文本或文本的样式名。 """

_ = get_text._


class DrawCase(FastTestCase):
    """接管 Script.UI.Moudle.draw 中带 draw 属性的类与 flow_handle.askfor_all 的测试基类。"""

    def setUp(self) -> None:
        """
        初始化玩家与目标角色，打开工作集与 debug 模式，
        并接管 draw 模块中带 draw 属性的绘制类与 flow_handle.askfor_all。
        """
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(TARGET, NAME)
        self.enterContext(working.based_on(core.state()))
        modes.set_debug(True)
        self.drawn: list[Drawn] = []
        for cls in vars(draw).values():
            if isinstance(cls, type) and hasattr(cls, "draw"):
                self.enterContext(
                    mock.patch.object(
                        cls, "draw", autospec=True, side_effect=self.keep
                    )
                )
        self.ask = self.enterContext(
            mock.patch.object(
                flow_handle, "askfor_all", side_effect=AssertionError
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
                getattr(now, "return_text", getattr(now, "style", None)),
            )
        )


class ConfirmHookTest(FastTestCase):
    """确认提问回调的登记、派发顺序与返回值测试。"""

    def setUp(self) -> None:
        """将 ui_hooks._confirms 暂时替换为空列表。"""
        super().setUp()
        self.enterContext(mock.patch.object(ui_hooks, "_confirms", []))

    def test_unregistered_confirm_is_true(self) -> None:
        """验证未登记回调时 ui_hooks.emit_confirm 返回 True。"""
        self.assertIs(ui_hooks.emit_confirm("问"), True)

    def test_registered_answer_is_returned(self) -> None:
        """验证 on_confirm 原样返回传入回调，并验证 emit_confirm 转发提问文本且返回回调的布尔答复。"""
        confirm = mock.Mock(return_value=True)
        self.assertIs(ui_hooks.on_confirm(confirm), confirm)
        self.assertIs(ui_hooks.emit_confirm("问"), True)
        confirm.return_value = False
        self.assertIs(ui_hooks.emit_confirm("再问"), False)
        self.assertEqual(
            confirm.call_args_list, [mock.call("问"), mock.call("再问")]
        )

    def test_callbacks_run_in_order_until_refused(self) -> None:
        """
        验证多个回调按登记顺序收到提问，遇到首个返回假值的回调时返回 False 并停止调用后续回调，
        全部返回真值时依次执行全部回调并返回 True。
        """
        calls = mock.Mock()
        calls.first.return_value = True
        calls.second.return_value = False
        calls.third.return_value = True
        for fn in (calls.first, calls.second, calls.third):
            ui_hooks.on_confirm(fn)
        self.assertIs(ui_hooks.emit_confirm("问"), False)
        self.assertEqual(
            calls.mock_calls, [mock.call.first("问"), mock.call.second("问")]
        )
        calls.reset_mock()
        calls.second.return_value = True
        self.assertIs(ui_hooks.emit_confirm("问"), True)
        self.assertEqual(
            calls.mock_calls,
            [
                mock.call.first("问"),
                mock.call.second("问"),
                mock.call.third("问"),
            ],
        )


class TkConfirmTest(DrawCase):
    """经已登记 Tk 回调执行确认提问的绘制顺序与玩家选择测试。"""

    def setUp(self) -> None:
        """为目标角色设置初吻素质，并准备亲吻指令对应的预期提问文本。"""
        super().setUp()
        abilities.talent(TARGET)[4] = 1
        self.text = (
            _("\n\n 是否要夺走{0}的初吻？").format(NAME)
            + _(" (对方的态度：")
            + _("接受)\n")
        )

    def expected(self) -> list[Drawn]:
        """
        构造确认提问预期的六步绘制记录序列。
        Return arguments:
        list[Drawn] -- 依次为提问文本、两次换行、[确定]与[返回]两个按钮及一次换行的绘制记录
        """
        half = int(normal_config.config_normal.text_width / 2)
        return [
            ("WaitDraw", self.text, 0, "standard"),
            ("NormalDraw", "\n", 1, "standard"),
            ("NormalDraw", "\n", 1, "standard"),
            ("CenterButton", _("[确定]"), half, _("确定")),
            ("CenterButton", _("[返回]"), half, _("返回")),
            ("NormalDraw", "\n", 1, "standard"),
        ]

    def test_tk_callback_registered(self) -> None:
        """验证测试世界载入后 callbacks.draw_confirm 已登记到 ui_hooks._confirms。"""
        self.assertIn(callbacks.draw_confirm, ui_hooks._confirms)

    def test_confirm_draws_and_returns_true(self) -> None:
        """验证玩家选择[确定]时 ask_judge 按预期顺序绘制提问与按钮、以两按钮响应文本调用 askfor_all 并返回 True。"""
        self.ask.side_effect = None
        self.ask.return_value = _("确定")
        self.assertIs(instuct_judege.ask_judge(0, TARGET, _("亲吻")), True)
        self.assertEqual(self.drawn, self.expected())
        self.ask.assert_called_once_with([_("确定"), _("返回")])

    def test_back_returns_false(self) -> None:
        """验证玩家选择[返回]时 ask_judge 按预期顺序绘制提问与按钮、以两按钮响应文本调用 askfor_all 并返回 False。"""
        self.ask.side_effect = None
        self.ask.return_value = _("返回")
        self.assertIs(instuct_judege.ask_judge(0, TARGET, _("亲吻")), False)
        self.assertEqual(self.drawn, self.expected())
        self.ask.assert_called_once_with([_("确定"), _("返回")])

    def test_callback_answers_directly(self) -> None:
        """验证直接调用 callbacks.draw_confirm 按同一顺序绘制，并在选择[确定]或[返回]时分别返回 True 或 False。"""
        self.ask.side_effect = [_("确定"), _("返回")]
        self.assertIs(callbacks.draw_confirm(self.text), True)
        self.assertIs(callbacks.draw_confirm(self.text), False)
        self.assertEqual(self.drawn, self.expected() * 2)


class CalculationNoticeTest(DrawCase):
    """calculation_instuct_judege 的实行值计算文本与合意获得文本提示派发测试。"""

    def setUp(self) -> None:
        """将 ui_hooks._notices 暂时替换为只含 self.record 的列表，用于记录派发出的提示参数。"""
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

    def assert_calculation(self, text: str, judge: float) -> None:
        """
        断言派发的计算文本以基础实行值需求开头，并以 debug 修正与总实行值结尾。
        Keyword arguments:
        text -- str，派发的计算文本
        judge -- float，calculation_instuct_judege 返回的总实行值
        """
        self.assertTrue(text.startswith(_("需要基础实行值至少为")), text)
        self.assertTrue(
            text.endswith(_("+debug模式(+99999)") + f" = {judge}\n"), text
        )

    def test_both_notices_wait(self) -> None:
        """验证首次获得亲吻合意时写入合意素质、先后派发计算文本与合意获得文本两条等待提示，且不触发直接绘制。"""
        result = instuct_judege.calculation_instuct_judege(0, TARGET, _("亲吻"))
        self.assertEqual(result[0], 1)
        self.assertEqual(abilities.talent(TARGET)[11], 1)
        self.assertEqual(len(self.notices), 2)
        self.assert_calculation(self.notices[0][0], result[1])
        self.assertEqual(self.notices[0][1:], (True, None, False))
        self.assertEqual(
            self.notices[1],
            (_("\n 获得了{0}的【亲吻合意】\n").format(NAME), True, None, False),
        )
        self.assertEqual(self.drawn, [])

    def test_no_agreement_text_when_owned(self) -> None:
        """验证目标角色已有亲吻合意时只派发一条计算文本提示。"""
        abilities.talent(TARGET)[11] = 1
        result = instuct_judege.calculation_instuct_judege(0, TARGET, _("亲吻"))
        self.assertEqual(len(self.notices), 1)
        self.assert_calculation(self.notices[0][0], result[1])

    def test_not_draw_flag_is_silent(self) -> None:
        """验证 not_draw_flag 为真时不派发提示，也不写入合意素质。"""
        instuct_judege.calculation_instuct_judege(
            0, TARGET, _("亲吻"), not_draw_flag=True
        )
        self.assertEqual(self.notices, [])
        self.assertEqual(abilities.talent(TARGET)[11], 0)

    def test_visitor_type_is_silent(self) -> None:
        """验证访客类判定（need_type 为 V）通过时不派发提示。"""
        result = instuct_judege.calculation_instuct_judege(
            0, TARGET, _("访客留下")
        )
        self.assertEqual(result[0], 1)
        self.assertEqual(self.notices, [])

    def test_tk_notices_draw_wait_text(self) -> None:
        """
        验证经 callbacks.draw_notice 派发时，计算文本与合意获得文本各绘制为一个宽度为 0、样式为 standard 的 WaitDraw。
        """
        ui_hooks._notices[:] = [callbacks.draw_notice]
        instuct_judege.calculation_instuct_judege(0, TARGET, _("亲吻"))
        self.assertEqual(
            [name for name, *_rest in self.drawn], ["WaitDraw", "WaitDraw"]
        )
        self.assertEqual(
            [rest for _name, _text, *rest in self.drawn],
            [[0, "standard"], [0, "standard"]],
        )
        self.assertEqual(
            self.drawn[1][1], _("\n 获得了{0}的【亲吻合意】\n").format(NAME)
        )


class AskJudgeTest(DrawCase):
    """ask_judge 经 ui_hooks.emit_confirm 派发确认提问与早返回的测试。"""

    def setUp(self) -> None:
        """将 ui_hooks._confirms 暂时替换为只含模拟回调 self.confirm 的列表。"""
        super().setUp()
        self.confirm = mock.Mock(return_value=True)
        self.enterContext(
            mock.patch.object(ui_hooks, "_confirms", [self.confirm])
        )

    def test_player_target_skips_question(self) -> None:
        """验证目标角色为玩家时 ask_judge 返回 True，且不调用确认回调也不触发绘制。"""
        abilities.talent(0)[4] = 1
        self.assertIs(instuct_judege.ask_judge(0, 0, _("亲吻")), True)
        self.confirm.assert_not_called()
        self.assertEqual(self.drawn, [])

    def test_empty_question_skips_confirm(self) -> None:
        """验证无提问文本时 ask_judge 返回 True，且不调用确认回调也不触发绘制。"""
        self.assertIs(instuct_judege.ask_judge(0, TARGET, _("亲吻")), True)
        self.confirm.assert_not_called()
        self.assertEqual(self.drawn, [])

    def test_question_forwards_answer(self) -> None:
        """
        验证存在提问文本时 ask_judge 将文本传给 emit_confirm 并原样返回 True 或 False，且不触发直接绘制或 askfor_all。
        """
        abilities.talent(TARGET)[4] = 1
        text = (
            _("\n\n 是否要夺走{0}的初吻？").format(NAME)
            + _(" (对方的态度：")
            + _("接受)\n")
        )
        self.assertIs(instuct_judege.ask_judge(0, TARGET, _("亲吻")), True)
        self.confirm.return_value = False
        self.assertIs(instuct_judege.ask_judge(0, TARGET, _("亲吻")), False)
        self.assertEqual(
            self.confirm.call_args_list, [mock.call(text), mock.call(text)]
        )
        self.assertEqual(self.drawn, [])
        self.ask.assert_not_called()


class ImportBoundaryTest(FastTestCase):
    """指令实行值模块与 ui_hooks 的导入边界及无界面加载测试。"""

    def test_sources_import_no_ui(self) -> None:
        """
        验证 SOURCES 中两个模块通过 banned_imports 检查，
        且 Script/Design/instuct_judege.py 不导入 Script.Core.flow_handle。
        """
        for path in SOURCES:
            with self.subTest(path=path):
                self.assertEqual(
                    banned_imports((ROOT / path).read_bytes(), path), []
                )
        source = (ROOT / SOURCES[0]).read_text(encoding="utf-8")
        self.assertNotIn(
            "Script.Core.flow_handle", imports_in(source, "Script.Design")
        )

    def test_ui_hooks_loads_without_ui(self) -> None:
        """验证独立子进程只导入 ui_hooks 即可登记并派发确认提问，且不加载 Script.UI、tkinter 或 _tkinter。"""
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
            report, {"asked": ["问"], "answer": False, "loaded": []}
        )
