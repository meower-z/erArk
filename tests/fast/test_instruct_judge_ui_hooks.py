"""
指令实行值界面回调测试
======================
- ConfirmHookTest：测试 emit_confirm 未登记处理函数时的异常、提示构造与返回值映射。
- TkConfirmTest：测试经 Tk 确认渲染函数绘制提问的顺序与玩家选择结果。
- CalculationNoticeTest：测试实行值计算文本与合意获得文本的提示派发。
- AskJudgeTest：测试 ask_judge 经 emit_confirm 派发确认提问与早返回。
- ImportBoundaryTest：测试在无界面子进程中导入 modal_hooks 与 ui_hooks 并派发确认提问。
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
from Script.Modules.gameplay_resolution import modal_hooks, ui_hooks, working
from Script.Modules.tk_ui import callbacks
from Script.Protocol.modal_prompts import (
    ChoiceOption,
    ChoicePrompt,
    ChoiceResult,
)
from Script.UI.Moudle import draw
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT

TARGET = 1
""" 测试使用的目标角色编号（1）。 """
NAME = "测试干员"
""" 测试使用的目标角色名称。 """
CLEAN_RUN = """
import json, sys
from Script.Modules.gameplay_resolution import modal_hooks, ui_hooks
from Script.Protocol.modal_prompts import ChoiceResult
asked = []
def back(prompt):
    asked.append([prompt.prompt_id, prompt.text, [[o.option_id, o.label] for o in prompt.options]])
    return ChoiceResult(prompt.prompt_id, "back")
modal_hooks.on_choice(back)
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
"""
子进程脚本源码：导入 modal_hooks 与 ui_hooks，登记选择处理函数并调用 emit_confirm，
以 JSON 输出提问记录、返回值与已加载的界面模块。
"""

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
    """测试 ui_hooks.emit_confirm 在 modal_hooks 槽上的异常处理、提示构造与返回值映射。"""

    def setUp(self) -> None:
        """将 modal_hooks._ask 暂时替换为 None，保证每项测试从空槽开始。"""
        super().setUp()
        self.enterContext(mock.patch.object(modal_hooks, "_ask", None))

    def test_unregistered_confirm_raises(self) -> None:
        """验证 modal_hooks 未登记处理函数时，调用 ui_hooks.emit_confirm 抛出 RuntimeError。"""
        with self.assertRaises(RuntimeError):
            ui_hooks.emit_confirm("问")

    def test_confirm_asks_one_prompt(self) -> None:
        """
        验证登记处理函数后，emit_confirm 按序构造 instruct_confirm 提示，
        并将 confirm 与 back 结果映射为 True 与 False。
        """
        answers = iter(["confirm", "back"])
        prompts: list[ChoicePrompt] = []

        def answer(prompt: ChoicePrompt) -> ChoiceResult:
            """
            记录收到的 ChoicePrompt 并按预设顺序返回对应的 ChoiceResult。
            Keyword arguments:
            prompt -- ChoicePrompt，emit_confirm 传入的确认选项提示
            Return arguments:
            ChoiceResult -- 使用下一个预设选项标识构造的选择结果
            """
            prompts.append(prompt)
            return ChoiceResult(prompt.prompt_id, next(answers))

        modal_hooks.on_choice(answer)
        self.assertIs(ui_hooks.emit_confirm("问"), True)
        self.assertIs(ui_hooks.emit_confirm("再问"), False)
        options = (
            ChoiceOption("confirm", _("确定")),
            ChoiceOption("back", _("返回")),
        )
        self.assertEqual(
            prompts,
            [
                ChoicePrompt("instruct_confirm", options, "问"),
                ChoicePrompt("instruct_confirm", options, "再问"),
            ],
        )


class TkConfirmTest(DrawCase):
    """测试经已登记的 Tk 确认渲染函数执行确认提问时的绘制顺序与玩家选择结果。"""

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

    def test_emit_confirm_draws_through_tk(self) -> None:
        """
        验证调用 ui_hooks.emit_confirm 经已登记的 Tk 渲染函数按预期顺序绘制，
        并在选择[确定]与[返回]时分别返回 True 与 False。
        """
        self.ask.side_effect = [_("确定"), _("返回")]
        self.assertIs(ui_hooks.emit_confirm(self.text), True)
        self.assertIs(ui_hooks.emit_confirm(self.text), False)
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
        """将 modal_hooks._ask 暂时替换为返回 self.answer 对应 ChoiceResult 的模拟处理函数 self.confirm。"""
        super().setUp()
        self.answer = "confirm"
        self.confirm = mock.Mock(
            side_effect=lambda prompt: ChoiceResult(
                prompt.prompt_id, self.answer
            )
        )
        self.enterContext(mock.patch.object(modal_hooks, "_ask", self.confirm))

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
        self.answer = "back"
        self.assertIs(instuct_judege.ask_judge(0, TARGET, _("亲吻")), False)
        self.assertEqual(
            [call.args[0].text for call in self.confirm.call_args_list],
            [text, text],
        )
        self.assertEqual(self.drawn, [])
        self.ask.assert_not_called()


class ImportBoundaryTest(FastTestCase):
    """ui_hooks 的无界面子进程加载与确认提问派发测试。"""

    def test_ui_hooks_loads_without_ui(self) -> None:
        """
        验证独立子进程导入 modal_hooks 与 ui_hooks 即可登记处理函数并派发确认提问，
        且不加载 Script.UI、tkinter 或 _tkinter。
        """
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
            report,
            {
                "asked": [
                    [
                        "instruct_confirm",
                        "问",
                        [["confirm", _("确定")], ["back", _("返回")]],
                    ]
                ],
                "answer": False,
                "loaded": [],
            },
        )
