"""
纯状态分页器 `Pager` 单元测试：验证视口高度边界、跳过标记、
右键条件与解除暂停计数规则。
"""

from Script.Frontend.Tk.pager import Fit, Pager
from Script.Protocol import Choose, InputText, Pause
from tests.fast.base import FastTestCase

PAUSE = Pause("s", 1, 1, 1)
"""测试用的暂停输入请求样本。"""
CHOOSE = Choose("s", 2, 1, 2, ("1",))
"""测试用的选项输入请求样本。"""
TEXT = InputText("s", 3, 1, 3, 8)
"""测试用的最大长度为 8 的文本输入请求样本。"""


class PagerTest(FastTestCase):
    """
    验证纯状态 `Pager` 在高度边界、跳过标记、右键条件
    与解除暂停计数场景下行为正确的测试类。
    """

    def test_hold_starts_one_pixel_past_the_viewport(self) -> None:
        """断言未读高度超过视口 1 像素即按 `before_unit` 进入 "unit" 或 "page" 暂停，未超视口或视口非正时为 "none"。"""
        cases = [
            (Fit(300, 200, 300), "none"),
            (Fit(0, 0, 300), "none"),
            (Fit(301, 200, 300), "unit"),
            (Fit(301, 0, 300), "page"),
            (Fit(301, -40, 300), "page"),
            (Fit(900, 200, 0), "none"),
            (Fit(900, 200, -4), "none"),
        ]
        for fit, hold in cases:
            with self.subTest(fit=fit):
                pager = Pager()
                self.assertEqual(pager.settle(fit), hold)
                self.assertEqual(pager.hold, hold)

    def test_skip_lasts_until_a_prompt_or_sync(self) -> None:
        """
        断言无请求右键后 `Pause` 保持 `skip` 开启，
        收到 `Choose`、`InputText` 或调用 `synced()` 后关闭 `skip`。
        """
        for clear in ("choose", "text", "sync"):
            with self.subTest(clear):
                pager = Pager()
                pager.right_click(None)
                pager.asked(PAUSE)
                self.assertTrue(pager.skip)
                if clear == "sync":
                    pager.synced()
                else:
                    pager.asked(CHOOSE if clear == "choose" else TEXT)
                self.assertFalse(pager.skip)

    def test_right_click_skips_only_outside_choice_and_text(self) -> None:
        """断言未暂停时右键仅在无请求或 `Pause` 下开启跳过，已处于暂停时即使挂起 `Choose` 也开启跳过。"""
        cases = [(None, True), (PAUSE, True), (CHOOSE, False), (TEXT, False)]
        for request, skip in cases:
            with self.subTest(request=type(request).__name__):
                pager = Pager()
                pager.right_click(request)
                self.assertEqual(pager.skip, skip)
        pager = Pager()
        pager.settle(Fit(900, 200, 300))
        pager.right_click(CHOOSE)
        self.assertTrue(pager.skip)

    def test_release_reports_the_hold_it_ends(self) -> None:
        """
        断言未暂停时调用 `release()` 返回 "none" 且 `turns` 保持 0，
        每次解除有效暂停均返回原状态、归零 `hold` 并使 `turns` 递增。
        """
        pager = Pager()
        self.assertEqual(pager.release(), "none")
        self.assertEqual(pager.turns, 0)
        for turn in (1, 2):
            pager.settle(Fit(900, 0, 300))
            self.assertEqual(pager.release(), "page")
            self.assertEqual(pager.hold, "none")
            self.assertEqual(pager.turns, turn)
