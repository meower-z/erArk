"""
模态选项提示槽测试
==================
- AskTest：测试 modal_hooks 的处理函数登记、替换、转发与结果校验。
- UiFreeTest：测试在拦截界面与 Script.Design 的无界面子进程中运行 modal_hooks。
"""

from unittest import mock

from Script.Modules.gameplay_resolution import modal_hooks
from Script.Protocol.modal_prompts import (
    ChoiceOption,
    ChoicePrompt,
    ChoiceResult,
)
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import BLOCKED, run_ui_free

PROMPT = ChoicePrompt(
    "pick", (ChoiceOption("a", "甲"), ChoiceOption("b", "乙")), "问"
)
""" 测试使用的双选项 ChoicePrompt 样例。 """
UI_FREE_RUN = """
from Script.Modules.gameplay_resolution import modal_hooks
from Script.Protocol.modal_prompts import ChoiceOption, ChoicePrompt, ChoiceResult
seen = []
def answer(prompt):
    seen.append(prompt.text)
    return ChoiceResult(prompt.prompt_id, "b")
modal_hooks.on_choice(answer)
prompt = ChoicePrompt("pick", (ChoiceOption("a", "甲"), ChoiceOption("b", "乙")), "问")
payload["picked"] = modal_hooks.ask(prompt).selected_option_id
payload["seen"] = seen
"""
""" 无界面子进程代码片段：导入 modal_hooks，登记处理函数并发起一次提问，通过 payload 回传所选标识与收到的提问文本。 """


class AskTest(FastTestCase):
    """测试 modal_hooks.on_choice 与 modal_hooks.ask 的登记、替换及结果校验行为。"""

    def setUp(self) -> None:
        """将 modal_hooks._ask 暂时替换为 None，保证每项测试从空槽开始。"""
        super().setUp()
        self.enterContext(mock.patch.object(modal_hooks, "_ask", None))

    def test_unregistered_ask_raises(self) -> None:
        """验证未登记处理函数时调用 modal_hooks.ask 抛出 RuntimeError。"""
        with self.assertRaises(RuntimeError):
            modal_hooks.ask(PROMPT)

    def test_ask_returns_handler_result(self) -> None:
        """验证 on_choice 原样返回处理函数，ask 仅以传入提示调用该函数一次并原样返回其结果。"""
        handler = mock.Mock(return_value=ChoiceResult("pick", "b"))
        self.assertIs(modal_hooks.on_choice(handler), handler)
        self.assertEqual(modal_hooks.ask(PROMPT), ChoiceResult("pick", "b"))
        handler.assert_called_once_with(PROMPT)

    def test_later_handler_replaces_earlier(self) -> None:
        """验证后登记的处理函数覆盖先前的登记，调用 ask 时不触发先前的处理函数。"""
        first = mock.Mock(return_value=ChoiceResult("pick", "a"))
        second = mock.Mock(return_value=ChoiceResult("pick", "b"))
        modal_hooks.on_choice(first)
        modal_hooks.on_choice(second)
        self.assertEqual(modal_hooks.ask(PROMPT).selected_option_id, "b")
        first.assert_not_called()

    def test_rejects_result_for_another_prompt(self) -> None:
        """验证处理函数返回不匹配的 prompt_id 时，modal_hooks.ask 抛出 ValueError。"""
        modal_hooks.on_choice(lambda prompt: ChoiceResult("other", "a"))
        with self.assertRaises(ValueError):
            modal_hooks.ask(PROMPT)

    def test_rejects_option_not_offered(self) -> None:
        """验证处理函数返回不在 prompt.options 中的选项标识时，modal_hooks.ask 抛出 ValueError。"""
        modal_hooks.on_choice(lambda prompt: ChoiceResult("pick", "c"))
        with self.assertRaises(ValueError):
            modal_hooks.ask(PROMPT)


class UiFreeTest(FastTestCase):
    """测试 modal_hooks 在无界面且拦截 Script.Design 的子进程中独立运行。"""

    def test_asks_without_ui_or_design(self) -> None:
        """验证拦截默认界面根模块与 Script.Design 后，子进程可经 modal_hooks 完成提问且不触发或加载任何受拦截模块。"""
        child = run_ui_free(UI_FREE_RUN, blocked=BLOCKED | {"Script.Design"})
        self.assertEqual(child.payload, {"picked": "b", "seen": ["问"]})
        self.assertEqual((child.attempted, child.loaded), ([], []))
