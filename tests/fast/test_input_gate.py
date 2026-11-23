"""`InputGate` 输入门控单元测试：验证右键预排跳过、聚焦判定、不可跳过暂停处理及各类请求的提交应答规则。"""

from Script.Frontend.Tk.gate import InputGate
from Script.Protocol import (
    Choose,
    Continue,
    InputText,
    Pause,
    SubmitChoice,
    SubmitText,
)
from tests.fast.base import FastTestCase

EPOCH = 1
"""测试用例使用的固定控制器代次编号。"""
PAUSE = Pause("s", 1, EPOCH, 7)
"""测试用的可跳过暂停请求样本。"""
LOCKED = Pause("s", 2, EPOCH, 8, skippable=False)
"""测试用的不可跳过暂停请求样本。"""
CHOOSE = Choose("s", 3, EPOCH, 9, ("1", "2"))
"""测试用的选项输入请求样本。"""
TEXT = InputText("s", 4, EPOCH, 10, 8)
"""测试用的最大长度为 8 且不允许空串的文本输入请求样本。"""


class InputGateTest(FastTestCase):
    """验证 `InputGate` 在跳过预排、输入框聚焦与应答构造场景下行为正确的测试类。"""

    def test_right_click_before_arming_skips_the_pending_pause(self) -> None:
        """断言就绪前右键会在 `arm()` 时对挂起的可跳过暂停返回跳过应答，接受后清除预排并不跳过下一次暂停。"""
        gate = InputGate(EPOCH)
        self.assertIsNone(gate.offer(PAUSE))
        gate.right_click()
        answer = gate.arm()
        self.assertEqual(answer, Continue(EPOCH, 7, skip_pauses=True))
        self.assertFalse(gate.armed)
        assert answer is not None
        gate.accepted(answer)
        self.assertFalse(gate.skip_requested)
        self.assertIsNone(gate.offer(PAUSE))

    def test_right_click_during_choice_or_text_queues_no_skip(self) -> None:
        """断言在 `Choose` 或 `InputText` 请求期间右键不会预排跳过，且 `continue_pause` 返回 `None`。"""
        for request in (CHOOSE, TEXT):
            with self.subTest(type(request).__name__):
                gate = InputGate(EPOCH)
                gate.offer(request)
                self.assertIsNone(gate.arm())
                gate.right_click()
                self.assertFalse(gate.skip_requested)
                self.assertIsNone(gate.continue_pause(True))

    def test_arming_focuses_choice_and_text_prompts(self) -> None:
        """断言门控就绪后 `Choose` 与 `InputText` 请求需要聚焦输入框，`Pause` 不需要聚焦。"""
        expected = {PAUSE: False, CHOOSE: True, TEXT: True}
        for request, focus in expected.items():
            with self.subTest(type(request).__name__):
                gate = InputGate(EPOCH)
                gate.offer(request)
                gate.arm()
                self.assertTrue(gate.armed)
                self.assertEqual(gate.wants_focus(), focus)

    def test_queued_skip_waits_for_a_skippable_pause(self) -> None:
        """断言预排的跳过会越过不可跳过暂停并留待下一个可跳过暂停生效，遇到 `Choose` 请求时被清除。"""
        gate = InputGate(EPOCH)
        gate.right_click()
        self.assertIsNone(gate.offer(LOCKED))
        self.assertIsNone(gate.arm())
        self.assertEqual(gate.continue_pause(False), Continue(EPOCH, 8))
        skip = gate.offer(PAUSE)
        self.assertEqual(skip, Continue(EPOCH, 7, skip_pauses=True))
        gate.offer(CHOOSE)
        self.assertFalse(gate.skip_requested)

    def test_submit_answers_by_request_kind(self) -> None:
        """断言未就绪时提交返回 `None`，就绪后按 `Pause`、`Choose`、`InputText` 规则返回应答或拒绝并解除就绪。"""
        cases = [
            (PAUSE, "", Continue(EPOCH, 7)),
            (PAUSE, "x", None),
            (CHOOSE, "2", SubmitChoice(EPOCH, 9, "2", "button")),
            (TEXT, "", None),
            (TEXT, "123456789", None),
            (TEXT, "abc", SubmitText(EPOCH, 10, "abc")),
        ]
        for request, text, expected in cases:
            with self.subTest(f"{type(request).__name__} {text!r}"):
                gate = InputGate(EPOCH)
                gate.offer(request)
                self.assertIsNone(gate.submit(text, "button"))
                gate.arm()
                self.assertEqual(gate.submit(text, "button"), expected)
                self.assertFalse(gate.armed)
