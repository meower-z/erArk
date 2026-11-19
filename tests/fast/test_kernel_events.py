# -*- coding: UTF-8 -*-
"""
内核的事件：触发函数交回数据，处理函数收到这份数据，用玩具插件（tests/fast/kernel_toys.py）
========================================

- 不看角色的触发函数成立一次，处理函数收到它交回的数据；交回 None 的从不结算；交回 False 抛 RuntimeError。
- 结算后触发函数仍交回同样的数据抛 EventStillTrue，GameState 不变。
- 两个同时成立的事件各结算一次，一步一个（先后不保证，不检查）。
"""

from typing import Any

from Script.Kernel import core
from tests.fast.kernel_toys import KernelTestCase, Toy, flag, game


class EventTest(KernelTestCase):
    """触发函数与处理函数"""

    def test_world_trigger_fires_once_with_its_data(self) -> None:
        """全局键 due 记着一个分钟数：触发函数交回它，处理函数收到它并清掉 due，此后不再结算"""
        toy = Toy()
        got: list[Any] = []

        def due(state: core.GameState) -> Any:
            return core.value(state, None, "due")

        @toy.event("Due", due)
        def settle(minute: int) -> core.Effects:
            got.append(minute)
            return (core.StateChange(None, "due", minute, None),)

        state = game(0, {"a": 9, "b": 9})
        self.start(
            core.GameState(state.clock, state.characters, {"due": 25}), toy
        )
        for _ in range(4):
            core.step()
        self.assertEqual(got, [25])
        self.assertIsNone(core.value(core.state(), None, "due"))

    def test_none_never_fires(self) -> None:
        """触发函数一直交回 None：处理函数从不运行，时间照常流逝"""
        toy = Toy()
        fired: list[Any] = []

        @toy.event("Never", lambda state: None)
        def never(data: Any) -> core.Effects:
            fired.append(data)
            return ()

        self.start(game(0, {"a": 3}), toy)
        for _ in range(6):
            core.step()
        self.assertEqual(fired, [])
        self.assertGreater(core.state().clock, 0)

    def test_false_raises(self) -> None:
        """触发函数交回 False（不是 None）：RuntimeError，GameState 不变"""
        toy = Toy()

        @toy.event("Bool", lambda state: False)
        def boolean(data: Any) -> core.Effects:
            return ()

        self.start(game(0, {"a": 9}), toy)
        before = core.state()
        with self.assertRaisesRegex(RuntimeError, "returned False"):
            core.step()
        self.assertIs(core.state(), before)

    def test_event_still_true_raises(self) -> None:
        """结算后触发函数仍交回同样的角色键：EventStillTrue，GameState 不变"""
        toy = Toy()

        @toy.event("Stuck", flag("stuck"))
        def stuck(who: str) -> core.Effects:
            return ()

        self.start(game(0, {"a": 9}, {"a": {"stuck": True}}), toy)
        before = core.state()
        with self.assertRaises(core.EventStillTrue):
            core.step()
        self.assertIs(core.state(), before)

    def test_simultaneous_events_both_settle(self) -> None:
        """First 与 Second 对 a 同时成立：两步里各结算一次，第三步时间流逝"""
        toy = Toy()
        fired: list[str] = []
        for name in ("First", "Second"):

            def body(who: str, name: str = name) -> core.Effects:
                fired.append(name)
                return (core.StateChange(who, name, True, False),)

            toy.event(name, flag(name))(body)
        on = {"First": True, "Second": True}
        self.start(game(0, {"a": 9}, {"a": on}), toy)
        core.step()
        core.step()
        self.assertEqual(sorted(fired), ["First", "Second"])
        self.assertEqual(core.state().clock, 0)
        core.step()
        self.assertEqual(len(fired), 2)
        self.assertEqual(core.state().clock, 9)
