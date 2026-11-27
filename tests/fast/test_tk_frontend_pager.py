"""
`TkFrontend` 分页集成测试：在子进程中以假渲染器验证超屏暂停、
逐屏翻页、按键与按钮响应、满积压退出与附着重放行为。
"""

from tests.fast.base import FastTestCase
from tests.fast.tk_frontend_child import drive, rows


class TkFrontendPagerTest(FastTestCase):
    """
    通过假渲染器子进程验证 `TkFrontend` 分页暂停、逐屏翻页、
    应答推进、按钮点击、满积压退出与重连投影行为的测试类。
    """

    def test_output_that_fits_reaches_the_prompt(self) -> None:
        """断言未超视口的输出直接到达后续 `Choose` 请求并完成输入门控就绪。"""
        [look] = drive(
            [rows("a"), rows("b"), rows("c"), ["choose"], ["tick"], ["look"]]
        )
        self.assertEqual(look["hold"], "none")
        self.assertEqual(look["screen"], ["a", "b", "c"])
        self.assertEqual(look["request"], "Choose")
        self.assertTrue(look["armed"])

    def test_overflowing_chunk_waits_hidden_until_click(self) -> None:
        """断言超屏输出块整体隐藏并阻断后续 `Choose` 请求，左键点击后显现该块并交付请求且不提交多余应答。"""
        held, released = drive(
            [
                rows("a", "b"),
                rows("c", "d"),
                ["choose"],
                ["tick"],
                ["look"],
                ["click"],
                ["tick"],
                ["look"],
            ]
        )
        self.assertEqual(held["hold"], "unit")
        self.assertEqual(held["screen"], ["a", "b"])
        self.assertEqual(held["hidden"], ["c", "d"])
        self.assertIsNone(held["request"])
        self.assertEqual(released["hold"], "none")
        self.assertEqual(released["screen"][-2:], ["c", "d"])
        self.assertEqual(released["request"], "Choose")
        self.assertEqual(released["sent"], [])

    def test_oversize_chunk_pages_one_screen_at_a_time(self) -> None:
        """断言单块超过视口的输出按整屏依次停在 "page" 状态，且不在暂停时隐藏文本。"""
        names = [f"r{index}" for index in range(8)]
        looks = drive(
            [
                rows(*names),
                ["tick"],
                ["look"],
                ["click"],
                ["tick"],
                ["look"],
                ["click"],
                ["tick"],
                ["look"],
            ]
        )
        self.assertEqual(
            [look["hold"] for look in looks], ["page", "page", "none"]
        )
        self.assertEqual(looks[0]["screen"], names[0:3])
        self.assertEqual(looks[1]["screen"], names[3:6])
        self.assertEqual(looks[2]["screen"][-2:], names[6:8])
        self.assertEqual(looks[0]["hidden"], [])

    def test_accepted_answer_starts_a_fresh_screen(self) -> None:
        """断言端口接受应答后锚点推进使后续一屏内容不暂停，应答被拒绝时锚点不动从而触发 "unit" 暂停。"""
        steps = [
            rows("a", "b", "c"),
            ["pause"],
            ["tick"],
            ["click"],
            rows("d", "e", "f"),
            ["tick"],
            ["look"],
        ]
        [accepted] = drive(steps)
        self.assertEqual(accepted["sent"], ["Continue"])
        self.assertEqual(accepted["hold"], "none")
        self.assertEqual(accepted["screen"], ["d", "e", "f"])
        [rejected] = drive(steps, accept=False)
        self.assertEqual(rejected["sent"], ["Continue"])
        self.assertEqual(rejected["hold"], "unit")
        self.assertEqual(rejected["hidden"], ["d", "e", "f"])

    def test_empty_chunk_after_a_full_screen_does_not_hold(self) -> None:
        """断言满屏之后收到空文本渲染块仍保持 "none" 状态。"""
        [look] = drive([rows("a", "b", "c"), ["text", ""], ["tick"], ["look"]])
        self.assertEqual(look["hold"], "none")
        self.assertEqual(look["screen"], ["a", "b", "c"])

    def test_enter_releases_a_hold(self) -> None:
        """断言按下回车键可解除当前分页暂停并显现隐藏输出块。"""
        [look] = drive(
            [rows("a", "b"), rows("c", "d"), ["tick"], ["enter"], ["look"]]
        )
        self.assertEqual(look["hold"], "none")
        self.assertEqual(look["screen"][-2:], ["c", "d"])

    def test_exit_behind_a_hold_closes_at_once(self) -> None:
        """断言暂停期间同批或后续批次收到的 `Exit` 事件会立即关闭窗口。"""
        cases = {
            "same batch": [rows("a", "b"), rows("c", "d"), ["exit"]],
            "later batch": [rows("a", "b"), rows("c", "d"), ["tick"], ["exit"]],
        }
        for name, steps in cases.items():
            with self.subTest(name):
                [look] = drive([*steps, ["tick"], ["look"]])
                self.assertTrue(look["closed"])

    def test_unmapped_window_never_holds(self) -> None:
        """断言视口高度为 0 时大段输出保持 "none" 状态。"""
        [look] = drive([rows(*"abcdefgh"), ["tick"], ["look"]], viewport=0)
        self.assertEqual(look["hold"], "none")

    def test_reattach_counts_only_new_output(self) -> None:
        """断言附着阶段回放的投影文本不计入未读高度，后续单行输出保持 "none" 状态。"""
        [look] = drive(
            [rows("x"), ["tick"], ["look"]],
            projection=(rows(*"abcdef"),),
        )
        self.assertEqual(look["hold"], "none")
        self.assertEqual(look["screen"], ["e", "f", "x"])

    def test_button_press_during_hold_only_releases(self) -> None:
        """
        断言暂停期间点击按钮仅解除暂停且不写入输入框或提交应答，
        待 `Choose` 就绪后再点击按钮才提交 `SubmitChoice:1`。
        """
        held, armed = drive(
            [
                rows("a", "b"),
                rows("c", "d"),
                ["choose"],
                ["tick"],
                ["press", "1"],
                ["tick"],
                ["look"],
                ["press", "1"],
                ["look"],
            ]
        )
        self.assertEqual(held["hold"], "none")
        self.assertEqual(held["order"], "")
        self.assertEqual(held["sent"], [])
        self.assertTrue(held["armed"])
        self.assertEqual(armed["sent"], ["SubmitChoice:1"])

    def test_exit_behind_a_full_backlog_closes(self) -> None:
        """
        断言暂停期间本地积压队列在 `DRAIN_BATCH` 处停止拉取并保持窗口打开，
        随后排入 `Exit` 时单轮泵送即可关闭窗口。
        """
        many = [rows(f"r{index}") for index in range(300)]
        full, closed = drive(
            [rows("a", "b"), rows("c", "d"), ["tick"], *many, ["tick", 5]]
            + [["look"], ["exit"], ["tick"], ["look"]]
        )
        self.assertEqual(full["hold"], "unit")
        self.assertEqual(full["backlog"], full["limit"])
        self.assertFalse(full["closed"])
        self.assertTrue(closed["closed"])

    def test_reattach_leaves_the_view_at_the_end(self) -> None:
        """断言附着回放超屏投影后不暂停且不隐藏文本，并将视图停在末尾行。"""
        [look] = drive(
            [["look"]],
            projection=(rows("a", "b"), rows("c", "d"), rows("e", "f")),
        )
        self.assertEqual(look["hold"], "none")
        self.assertEqual(look["hidden"], [])
        self.assertEqual(look["screen"], ["d", "e", "f"])
