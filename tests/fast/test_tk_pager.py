"""`Pager` 分页状态机单元测试，验证高度边界判定、重复结算、停顿释放、右键跳过与后端事件对跳过开关的影响。"""

from Script.Frontend.Tk.pager import Fit, Pager
from Script.Protocol import (
    Choose,
    Clear,
    InputText,
    Pause,
    RenderChunk,
    SkipPauses,
    SyncPanel,
)
from tests.fast.base import FastTestCase

PAUSE = Pause("s", 1, 1, 1)
"""测试用的暂停输入请求样本。"""
CHOOSE = Choose("s", 2, 1, 2, ("1",))
"""测试用的选项输入请求样本。"""
TEXT = InputText("s", 3, 1, 3, 8)
"""测试用的文本输入请求样本。"""


class PagerTest(FastTestCase):
    """验证 `Pager` 停顿判定、释放计数及跳过开关转换规则的测试类。"""

    def test_hold_starts_one_pixel_past_the_viewport(self) -> None:
        """断言高度未超视口或视口非正时不停顿，超出 1 像素即按块前高度进入 `"unit"` 或 `"page"` 停顿。"""
        cases = [
            (Fit(300, 200, 300), "none"),
            (Fit(0, 0, 300), "none"),
            (Fit(300, 300, 300), "none"),
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

    def test_settle_replaces_the_previous_hold(self) -> None:
        """断言再次调用 `settle` 会以新的高度判定结果覆盖先前的停顿状态。"""
        pager = Pager()
        pager.settle(Fit(900, 0, 300))
        self.assertEqual(pager.settle(Fit(200, 0, 300)), "none")
        self.assertEqual(pager.hold, "none")

    def test_release_reports_the_hold_it_ends(self) -> None:
        """断言 `release` 返回释放前的停顿状态，并仅在结束实际停顿时将 `turns` 计数加一。"""
        pager = Pager()
        self.assertEqual(pager.release(), "none")
        self.assertEqual(pager.turns, 0)
        for turn, fit, hold in (
            (1, Fit(900, 0, 300), "page"),
            (2, Fit(900, 9, 300), "unit"),
        ):
            pager.settle(fit)
            self.assertEqual(pager.release(), hold)
            self.assertEqual(pager.hold, "none")
            self.assertEqual(pager.turns, turn)

    def test_right_click_skips_outside_choice_and_text(self) -> None:
        """断言空闲、暂停或处于分页停顿时右键开启跳过开关，未停顿时的 `Choose` 与 `InputText` 请求保持关闭。"""
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

    def test_events_turn_skip_on_and_off(self) -> None:
        """
        断言 `SkipPauses(False)`、`SyncPanel`、`Choose` 与 `InputText` 关闭跳过，
        `SkipPauses(True)` 开启跳过后其他事件保持开启。
        """
        off = {
            "skip off": SkipPauses("s", 4, False),
            "sync": SyncPanel("s", 4, 1, "settle"),
            "choose": CHOOSE,
            "text": TEXT,
        }
        for name, event in off.items():
            with self.subTest(name):
                pager = Pager()
                pager.right_click(None)
                pager.observe(event)
                self.assertFalse(pager.skip)
        pager = Pager()
        pager.observe(SkipPauses("s", 5, True))
        for event in (PAUSE, Clear("s", 6, "screen"), RenderChunk("s", 7, ())):
            pager.observe(event)
            self.assertTrue(pager.skip)
