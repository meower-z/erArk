# -*- coding: UTF-8 -*-
"""
内核的测试：角色的加入与移除、事件的先后、选行动交回的东西，用玩具插件（tests/fast/kernel_toys.py）
========================================

- AddCharacter 加入的角色带一个此刻结束的 Idle，下一步在同一时刻选行动，数据冻结成只读；重复加入、
  Interrupt 或移除不在场的角色抛 RuntimeError。事件移除自己或别的条件成立的角色不抛 KeyError。
- 事件每一步一个，按登记的先后、再按角色的先后；结算后条件仍成立抛 EventStillTrue。
- 选行动只交回自己的 Action；选行动里造出又丢掉的效果抛 DroppedChanges；行动数据只能是 JSON。
"""

from types import MappingProxyType
from typing import Any

from Script.Kernel import core
from tests.fast.kernel_toys import KernelTestCase, Toy, flag, game


class RosterTest(KernelTestCase):
    """角色的加入与移除"""

    def test_added_character_picks_at_the_same_clock(self) -> None:
        """事件在 30 分加入 c：下一步在 30 分为 c 选行动；再加一次 c 抛 RuntimeError"""
        toy = Toy()
        picked: list[tuple[str, int]] = []

        @toy.event("Arrive", flag("bring"))
        def arrive(who: str) -> core.Effects:
            return (
                core.StateChange(who, "bring", True, False),
                core.AddCharacter("c", {"from": who}),
            )

        @toy.input_hook(core.pick_next_action)
        def pick(who: str) -> tuple[str]:
            picked.append((who, core.state().clock))
            return (who,)

        self.start(game(30, {"a": 50}, {"a": {"bring": True}}), toy)
        core.step()
        added = core.state().characters["c"]
        self.assertEqual(added.data, {"from": "a"})
        self.assertIsInstance(added.data, MappingProxyType)
        core.step()
        self.assertEqual(picked, [("c", 30)])
        self.assertEqual(core.state().characters["c"].action.start, 30)
        with self.assertRaisesRegex(RuntimeError, "already in the game"):
            core.preview(core.state(), (core.AddCharacter("c"),))

    def test_removal_in_an_event_scan(self) -> None:
        """a 的事件移除 a 自己，b 的事件移除条件同样成立的 c：都不抛 KeyError，被移除的角色不再结算"""
        toy = Toy()
        fired: list[tuple[str, str]] = []

        @toy.event("Leave", flag("leave"))
        def leave(who: str) -> core.Effects:
            fired.append(("Leave", who))
            if who == "b":
                return (
                    core.StateChange(who, "leave", True, False),
                    core.RemoveCharacter("c"),
                )
            return (core.RemoveCharacter(who),)

        self.start(
            game(
                0,
                {"a": 9, "b": 9, "c": 9},
                {
                    "a": {"leave": True},
                    "b": {"leave": False},
                    "c": {"leave": True},
                },
            ),
            toy,
        )
        core.step()
        self.assertEqual(tuple(core.state().characters), ("b", "c"))
        core.reset_state(
            game(
                0,
                {"b": 9, "c": 9},
                {"b": {"leave": True}, "c": {"leave": True}},
            )
        )
        core.step()
        self.assertEqual(tuple(core.state().characters), ("b",))
        self.assertEqual(fired, [("Leave", "a"), ("Leave", "b")])

    def test_unknown_character(self) -> None:
        """Interrupt 或移除不在场的角色抛 RuntimeError"""
        state = game(0, {"a": 9})
        for effect in (core.Interrupt("x"), core.RemoveCharacter("x")):
            with (
                self.subTest(effect),
                self.assertRaisesRegex(RuntimeError, "is not in the game"),
            ):
                core.preview(state, (effect,))

    def test_one_event_per_step_in_order(self) -> None:
        """两个事件对 a、b 都成立：每一步一个，先按事件登记的先后，再按角色的先后"""
        toy = Toy()
        fired: list[tuple[str, str]] = []
        for name in ("First", "Second"):

            def body(who: str, name: str = name) -> core.Effects:
                fired.append((name, who))
                return (core.StateChange(who, name, True, False),)

            toy.event(name, flag(name))(body)
        on = {"First": True, "Second": True}
        self.start(game(0, {"a": 9, "b": 9}, {"a": on, "b": on}), toy)
        for count in range(1, 5):
            core.step()
            self.assertEqual(len(fired), count)
        self.assertEqual(
            fired,
            [("First", "a"), ("First", "b"), ("Second", "a"), ("Second", "b")],
        )

    def test_event_still_true_raises(self) -> None:
        """事件结算后自己的条件仍成立：EventStillTrue，GameState 不变"""
        toy = Toy()

        @toy.event("Stuck", flag("stuck"))
        def stuck(who: str) -> core.Effects:
            return ()

        self.start(game(0, {"a": 9}, {"a": {"stuck": True}}), toy)
        before = core.state()
        with self.assertRaises(core.EventStillTrue):
            core.step()
        self.assertIs(core.state(), before)


class PickTest(KernelTestCase):
    """选行动交回的东西"""

    def picking(self, answer: Any) -> Toy:
        """
        选行动交回 answer(行动) 的玩具插件
        Keyword arguments:
        answer -- 由 Work 行动算出选行动交回值的函数
        Return arguments:
        Toy -- 玩具插件
        """
        toy = Toy()

        @toy.action("Work")
        def work(act: core.Action) -> core.Effects:
            return ()

        @toy.input_hook(core.pick_next_action)
        def pick(who: str) -> core.Intercept[Any]:
            return core.Intercept(answer(work, who))

        return toy

    def test_pick_returns_only_an_action(self) -> None:
        """交回 (Action, ()) 或别的角色的 Action 抛 RuntimeError；交回自己的 Action 照常开始"""
        answers = (
            lambda work, who: (core.new_action(work, who, 1), ()),
            lambda work, who: core.new_action(work, "b", 1),
        )
        for answer in answers:
            self.start(game(0, {"a": 0, "b": 9}), self.picking(answer))
            before = core.state()
            with self.assertRaisesRegex(RuntimeError, "pick returned"):
                core.step()
            self.assertIs(core.state(), before)
        good = self.picking(lambda work, who: core.new_action(work, who, 4))
        self.start(game(0, {"a": 0}), good)
        core.step()
        self.assertEqual(core.state().characters["a"].action.duration, 4)

    def test_effects_dropped_in_a_pick_raise(self) -> None:
        """选行动里调用交回效果的导出调用、又丢掉效果：DroppedChanges，GameState 不变"""
        toy = Toy()

        @toy.own
        def mark(who: str) -> core.Effects:
            return (core.StateChange(who, "x", None, 1),)

        marker = core.export(toy.name("Mark"))(mark)

        @toy.input_hook(core.pick_next_action)
        def pick(who: str) -> tuple[str]:
            marker(who)
            return (who,)

        self.start(game(0, {"a": 0}), toy)
        before = core.state()
        with self.assertRaises(core.DroppedChanges):
            core.step()
        self.assertIs(core.state(), before)

    def test_action_data_must_be_json(self) -> None:
        """行动数据里有函数或非字符串的键：行动开始抛 TypeError，GameState 不变"""
        for data in ({"call": print}, {1: "one"}, ({"deep": [object()]},)):
            with self.subTest(data):
                toy = self.picking(
                    lambda work, who, data=data: core.new_action(
                        work, who, 1, data
                    )
                )
                self.start(game(0, {"a": 0}), toy)
                before = core.state()
                with self.assertRaisesRegex(TypeError, "JSON"):
                    core.step()
                self.assertIs(core.state(), before)
