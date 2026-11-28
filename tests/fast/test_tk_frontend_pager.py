"""`TkFrontend` 分页停顿快速测试，验证停顿提示、映射前等待、请求批次不移视图、溢出翻页、背压与重连。"""

from tests.fast.base import FastTestCase
from tests.fast.tk_frontend_child import drive, rows


class TkFrontendPagerTest(FastTestCase):
    """验证 `TkFrontend` 与 `Pager` 协同处理分页停顿、背压与重连流程的测试类。"""

    def test_output_that_fits_reaches_the_prompt(self) -> None:
        """断言未超出视口的输出不停顿且不显示停顿提示，直接推进到就绪的 `Choose` 请求。"""
        [look] = drive(
            [rows("a"), rows("b"), rows("c"), ["choose"], ["tick"], ["look"]]
        )
        self.assertEqual(look["hold"], "none")
        self.assertEqual(look["screen"], ["a", "b", "c"])
        self.assertEqual(look["request"], "Choose")
        self.assertTrue(look["armed"])
        self.assertFalse(look["cue"])

    def test_overflowing_chunk_waits_hidden_until_click(self) -> None:
        """断言前端隐藏溢出块、开启停顿提示并暂缓请求，左键后关闭提示、显现该块并到达 `Choose` 且不提交应答。"""
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
        self.assertTrue(held["cue"])
        self.assertEqual(released["hold"], "none")
        self.assertFalse(released["cue"])
        self.assertEqual(released["screen"][-2:], ["c", "d"])
        self.assertEqual(released["request"], "Choose")
        self.assertEqual(released["sent"], [])

    def test_oversize_chunk_pages_one_screen_at_a_time(self) -> None:
        """断言前端对超高单块不隐藏而逐页停顿并开启停顿提示，两次左键点击后翻完并关闭提示与停顿。"""
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
        self.assertEqual([look["cue"] for look in looks], [True, True, False])
        self.assertEqual(looks[0]["screen"], names[0:3])
        self.assertEqual(looks[1]["screen"], names[3:6])
        self.assertEqual(looks[2]["screen"][-2:], names[6:8])
        self.assertEqual(looks[0]["hidden"], [])

    def test_accepted_answer_starts_a_fresh_screen(self) -> None:
        """断言应答被端口接受后以新屏幕重新计算未读高度，被拒绝时保留旧锚点并对后续输出触发停顿。"""
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
        """断言满屏输出后紧跟空文本块不触发分页停顿，当前画面保持不变。"""
        [look] = drive([rows("a", "b", "c"), ["text", ""], ["tick"], ["look"]])
        self.assertEqual(look["hold"], "none")
        self.assertEqual(look["screen"], ["a", "b", "c"])

    def test_enter_releases_a_hold(self) -> None:
        """断言在分页停顿期间按下回车键会解除停顿并显示先前隐藏的输出块。"""
        [look] = drive(
            [rows("a", "b"), rows("c", "d"), ["tick"], ["enter"], ["look"]]
        )
        self.assertEqual(look["hold"], "none")
        self.assertEqual(look["screen"][-2:], ["c", "d"])

    def test_exit_behind_a_hold_closes_at_once(self) -> None:
        """断言无论 `Exit` 与触发停顿的输出同批还是后批到达，窗口都会立即关闭。"""
        cases = {
            "same batch": [rows("a", "b"), rows("c", "d"), ["exit"]],
            "later batch": [rows("a", "b"), rows("c", "d"), ["tick"], ["exit"]],
        }
        for name, steps in cases.items():
            with self.subTest(name):
                [look] = drive([*steps, ["tick"], ["look"]])
                self.assertTrue(look["closed"])

    def test_startup_output_waits_for_a_mapped_view(self) -> None:
        """断言视口为 0 时前端不拉取事件且遇 `Exit` 仍关闭窗口，视口可用后首轮事件泵即对启动输出分页。"""
        steps = [rows(*"abcdefgh"), ["choose"], ["tick"], ["look"]]
        unmapped, mapped = drive(
            [*steps, ["map", 30], ["step"], ["look"]], viewport=0
        )
        self.assertEqual((unmapped["queued"], unmapped["views"]), (2, []))
        self.assertIsNone(unmapped["request"])
        self.assertEqual(mapped["hold"], "page")
        self.assertEqual(mapped["screen"], ["a", "b", "c"])
        self.assertIsNone(mapped["request"])
        [closed] = drive([rows("a"), ["exit"], ["tick"], ["look"]], viewport=0)
        self.assertTrue(closed["closed"])

    def test_batches_without_output_keep_the_scrollback_view(self) -> None:
        """断言上翻回看旧输出时，跳过开关、面板同步与输入请求批次不移动视图，新输出批次则滚回末尾。"""
        batches = {
            "skip": ([["skip", True]], ["a", "b", "c"]),
            "choose": ([["choose"]], ["a", "b", "c"]),
            "input": ([["input"]], ["a", "b", "c"]),
            "pause": ([["pause"]], ["a", "b", "c"]),
            "sync": ([["sync"]], ["a", "b", "c"]),
            "output": ([rows("x")], ["e", "f", "x"]),
        }
        for name, (batch, screen) in batches.items():
            with self.subTest(name):
                steps = [["tick"], ["scrollup"], *batch, ["tick"], ["look"]]
                [look] = drive(steps, projection=(rows(*"abcdef"),))
                self.assertEqual(look["screen"], screen)

    def test_reattach_counts_only_new_output(self) -> None:
        """断言重连回放的旧输出计为已读，仅对重连后新到达的输出计算是否停顿。"""
        [look] = drive(
            [rows("x"), ["tick"], ["look"]],
            projection=(rows(*"abcdef"),),
        )
        self.assertEqual(look["hold"], "none")
        self.assertEqual(look["screen"], ["e", "f", "x"])

    def test_button_press_during_hold_only_releases(self) -> None:
        """断言停顿期间点击输出按钮只解除停顿而不写入输入框或提交，就绪后再点击才发送选择应答。"""
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

    def test_button_press_before_a_prompt_leaves_the_input_empty(self) -> None:
        """断言尚无就绪输入请求时点击输出按钮既不写入输入框也不发送应答。"""
        [look] = drive([rows("a"), ["tick"], ["press", "1"], ["look"]])
        self.assertEqual(look["order"], "")
        self.assertEqual(look["sent"], [])

    def test_hold_leaves_later_events_in_the_port(self) -> None:
        """断言分页停顿期间后续事件保留在端口队列中不被拉取，左键释放后再继续消费并到达 `Choose`。"""
        later = [["text", ""] for _ in range(5)]
        held, released = drive(
            [rows("a", "b"), rows("c", "d"), ["tick"], *later, ["choose"]]
            + [["tick", 5], ["look"], ["click"], ["tick"], ["look"]]
        )
        self.assertEqual(held["hold"], "unit")
        self.assertEqual(held["queued"], 6)
        self.assertIsNone(held["request"])
        self.assertEqual(released["queued"], 0)
        self.assertEqual(released["request"], "Choose")

    def test_exit_queued_behind_a_hold_closes(self) -> None:
        """断言停顿后端口内排有多条输出与末尾 `Exit` 时，窗口直接关闭而其余排队事件留在端口中。"""
        later = [rows(f"r{index}") for index in range(5)]
        [look] = drive(
            [rows("a", "b"), rows("c", "d"), ["tick"], *later, ["exit"]]
            + [["tick"], ["look"]]
        )
        self.assertTrue(look["closed"])
        self.assertEqual(look["queued"], 6)

    def test_reattach_leaves_the_view_at_the_end(self) -> None:
        """断言重连回放多段输出时不测高且各块起点无未读，首轮事件泵后无停顿与隐藏并同步一次文末视图。"""
        [look] = drive(
            [["tick"], ["look"]],
            projection=(rows("a", "b"), rows("c", "d"), rows("e", "f")),
        )
        self.assertEqual(look["hold"], "none")
        self.assertEqual(look["hidden"], [])
        self.assertEqual(look["screen"], ["d", "e", "f"])
        self.assertEqual(look["fits"], 0)
        self.assertEqual(look["unread_at_unit"], [0, 0, 0])
        self.assertEqual(look["views"], ["end"])

    def test_each_batch_moves_the_view_once(self) -> None:
        """断言单次事件泵处理多块输出时仅同步一次视图，未停顿时滚至末尾，停顿时对齐锚点。"""
        cases = {
            "unheld": ([rows("a"), rows("b"), rows("c")], ["end"]),
            "held": ([rows("a", "b"), rows("c", "d")], ["pin"]),
        }
        for name, (chunks, views) in cases.items():
            with self.subTest(name):
                _, look = drive([["look"], *chunks, ["tick"], ["look"]])
                self.assertEqual(look["views"], views)
