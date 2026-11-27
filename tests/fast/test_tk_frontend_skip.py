"""
`TkFrontend` 跳过模式集成测试：在子进程中以假渲染器验证右键跳过、
游戏侧跳过同步、预排清除、清屏边界与重连保持跳过行为。
"""

from tests.fast.base import FastTestCase
from tests.fast.tk_frontend_child import drive, rows


class TkFrontendSkipTest(FastTestCase):
    """
    通过假渲染器子进程验证 `TkFrontend` 键鼠跳过、游戏侧跳过同步、
    预排清除、清屏阻隔与重连继承跳过开关行为的测试类。
    """

    def test_right_click_releases_and_skips_until_prompt_or_sync(self) -> None:
        """断言右键可解除当前暂停并跳过后续超屏暂停，遇到 `Choose`、`InputText` 或 `SyncPanel` 后恢复按块暂停。"""
        clears = {
            "choose": [["choose"], ["tick"], ["enter"]],
            "input": [["input"], ["tick"], ["enter"]],
            "sync": [["sync"]],
        }
        for name, clear in clears.items():
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
                self.assertEqual(held["screen"][-2:], ["c", "d"])
                self.assertEqual(skipped["hold"], "none")
                self.assertEqual(skipped["screen"][-2:], ["g", "h"])
                self.assertEqual(cleared["hold"], "unit")
                self.assertEqual(cleared["hidden"], ["k", "l"])

    def test_game_skip_lets_screens_through_until_cleared(self) -> None:
        """
        断言收到 `SkipPauses(True)` 后多屏输出不暂停，
        收到 `SkipPauses(False)`、`Choose`、`InputText` 或 `SyncPanel` 后恢复按块暂停。
        """
        clears = {
            "skip off": [["skip", False]],
            "choose": [["choose"], ["tick"], ["enter"]],
            "input": [["input"], ["tick"], ["enter"]],
            "sync": [["sync"]],
        }
        for name, clear in clears.items():
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

    def test_game_skip_behind_a_hold_releases_it(self) -> None:
        """断言排在暂停之后的 `SkipPauses(True)` 会直接解除当前暂停并继续显示后续行。"""
        [look] = drive(
            [
                rows("a", "b"),
                rows("c", "d"),
                ["skip", True],
                rows("e", "f"),
                rows("g", "h"),
                ["tick"],
                ["look"],
            ]
        )
        self.assertEqual(look["hold"], "none")
        self.assertEqual(look["screen"][-2:], ["g", "h"])

    def test_queued_right_click_ends_with_sync_or_skip_off(self) -> None:
        """
        断言无请求时右键预排的跳过在收到 `SyncPanel` 或 `SkipPauses(False)` 后清除，
        后续 `Pause` 正常就绪且不自动提交跳过应答。
        """
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

    def test_game_skip_after_a_clear_waits_for_the_click(self) -> None:
        """
        断言位于 `Clear("screen")` 之后的 `SkipPauses(True)` 不提前解除当前暂停，
        点击后才清屏显示后续行并开启跳过。
        """
        held, released = drive(
            [
                rows("a", "b"),
                rows("c", "d"),
                ["clear"],
                ["skip", True],
                rows("e", "f"),
                ["tick"],
                ["look"],
                ["click"],
                ["tick"],
                ["look"],
            ]
        )
        self.assertEqual(held["hold"], "unit")
        self.assertEqual(held["hidden"], ["c", "d"])
        self.assertEqual(released["hold"], "none")
        self.assertEqual(released["screen"], ["e", "f"])
        self.assertTrue(released["skip"])

    def test_reattach_keeps_an_active_game_skip(self) -> None:
        """
        断言附着快照带有开启态 `skip_pauses` 时前端保持跳过模式，
        后续多屏输出不触发暂停并滚至末尾。
        """
        [look] = drive(
            [
                rows("a", "b"),
                rows("c", "d"),
                rows("e", "f"),
                ["tick"],
                ["look"],
            ],
            skip=True,
        )
        self.assertTrue(look["skip"])
        self.assertEqual(look["hold"], "none")
        self.assertEqual(look["screen"], ["d", "e", "f"])
