"""`TkFrontend` 跳过开关快速测试，验证右键与后端 `SkipPauses` 事件如何开启、保持与清除跳过状态。"""

from tests.fast.base import FastTestCase
from tests.fast.tk_frontend_child import drive, rows

CLEARS = {
    "choose": [["choose"], ["tick"], ["enter"]],
    "input": [["input"], ["tick"], ["enter"]],
    "sync": [["sync"]],
    "skip off": [["skip", False]],
}
"""各类清除跳过开关的步骤序列映射，包含 `Choose`、`InputText`、`SyncPanel` 与 `SkipPauses(False)`。"""


class TkFrontendSkipTest(FastTestCase):
    """验证 `TkFrontend` 统一跳过开关在右键、后端事件与重连场景下行为正确的测试类。"""

    def test_right_click_releases_and_skips_until_cleared(self) -> None:
        """断言停顿期间右键释放当前停顿并开启跳过，直至遇到四类清除事件之一后重新触发分页停顿。"""
        for name, clear in CLEARS.items():
            with self.subTest(name):
                held, skipped, cleared = drive(
                    [
                        rows("a", "b"),
                        rows("c", "d"),
                        ["tick"],
                        ["rclick"],
                        ["look"],
                        rows("e", "f"),
                        rows("g", "h"),
                        ["tick"],
                        ["look"],
                        *clear,
                        rows("i", "j"),
                        rows("k", "l"),
                        ["tick"],
                        ["look"],
                    ]
                )
                self.assertEqual(held["hold"], "none")
                self.assertTrue(held["skip"])
                self.assertEqual(held["screen"][-2:], ["c", "d"])
                self.assertEqual(skipped["hold"], "none")
                self.assertEqual(skipped["screen"][-2:], ["g", "h"])
                self.assertFalse(cleared["skip"])
                self.assertEqual(cleared["hold"], "unit")
                self.assertEqual(cleared["hidden"], ["k", "l"])

    def test_game_skip_lets_screens_through_until_cleared(self) -> None:
        """断言后端发出 `SkipPauses(True)` 后多屏输出连续通过不停顿，直至四类清除事件之一关闭跳过。"""
        for name, clear in CLEARS.items():
            with self.subTest(name):
                skipped, cleared = drive(
                    [
                        ["skip", True],
                        rows("a", "b"),
                        rows("c", "d"),
                        rows("e", "f"),
                        ["tick"],
                        ["look"],
                        *clear,
                        rows("i", "j"),
                        rows("k", "l"),
                        ["tick"],
                        ["look"],
                    ]
                )
                self.assertEqual(skipped["hold"], "none")
                self.assertEqual(skipped["screen"], ["d", "e", "f"])
                self.assertEqual(cleared["hold"], "unit")
                self.assertEqual(cleared["hidden"], ["k", "l"])

    def test_game_skip_behind_a_hold_waits_for_the_click(self) -> None:
        """断言排在分页停顿之后的 `SkipPauses(True)` 需等玩家点击继续后才按流顺序生效。"""
        held, released = drive(
            [
                rows("a", "b"),
                rows("c", "d"),
                ["skip", True],
                rows("e", "f"),
                rows("g", "h"),
                ["tick"],
                ["look"],
                ["click"],
                ["tick"],
                ["look"],
            ]
        )
        self.assertEqual(held["hold"], "unit")
        self.assertFalse(held["skip"])
        self.assertEqual(held["hidden"], ["c", "d"])
        self.assertEqual(released["hold"], "none")
        self.assertTrue(released["skip"])
        self.assertEqual(released["screen"], ["f", "g", "h"])

    def test_idle_right_click_ends_with_sync_or_skip_off(self) -> None:
        """断言空闲期右键开启的跳过在遇到 `SyncPanel` 或 `SkipPauses(False)` 后清除，随后的 `Pause` 正常等待玩家。"""
        for name, clear in {
            "sync": ["sync"],
            "skip off": ["skip", False],
        }.items():
            with self.subTest(name):
                [look] = drive(
                    [["rclick"], clear, ["pause"], ["tick"], ["look"]]
                )
                self.assertFalse(look["skip"])
                self.assertEqual(look["request"], "Pause")
                self.assertTrue(look["armed"])
                self.assertEqual(look["sent"], [])

    def test_idle_right_click_skips_the_next_pause_and_stays_on(self) -> None:
        """断言空闲期右键开启的跳过会在投递 `Pause` 的同一次事件泵内直接返回带跳过的 `Continue`，且跳过保持开启。"""
        answered, look = drive(
            [
                ["rclick"],
                ["pause"],
                ["step"],
                ["look"],
                rows("a", "b"),
                rows("c", "d"),
                ["tick"],
                ["look"],
            ]
        )
        self.assertEqual(answered["sent"], ["Continue:skip"])
        self.assertEqual(look["sent"], ["Continue:skip"])
        self.assertTrue(look["skip"])
        self.assertEqual(look["hold"], "none")
        self.assertIsNone(look["request"])

    def test_right_click_before_arming_skips_the_pause(self) -> None:
        """断言对已投递但尚未就绪的 `Pause` 右键后，就绪步骤会以带跳过的 `Continue` 应答且门控保持未就绪。"""
        [look] = drive([["pause"], ["step"], ["rclick"], ["tick"], ["look"]])
        self.assertEqual(look["sent"], ["Continue:skip"])
        self.assertFalse(look["armed"])

    def test_right_click_on_a_choice_keeps_skip_off(self) -> None:
        """断言当前挂起请求为 `Choose` 且未处于停顿时，右键不开启跳过开关。"""
        [look] = drive([["choose"], ["tick"], ["rclick"], ["look"]])
        self.assertFalse(look["skip"])

    def test_reattach_restores_the_game_skip(self) -> None:
        """断言重连回放包含 `SyncPanel` 后仍按附着快照的 `skip_pauses` 设置跳过开关，并据此决定后续输出是否停顿。"""
        for skip, hold in ((True, "none"), (False, "unit")):
            with self.subTest(skip=skip):
                [look] = drive(
                    [rows("a", "b"), rows("c", "d"), ["tick"], ["look"]],
                    projection=(["sync"],),
                    skip=skip,
                )
                self.assertEqual(look["skip"], skip)
                self.assertEqual(look["hold"], hold)
