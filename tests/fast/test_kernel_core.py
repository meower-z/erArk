# -*- coding: UTF-8 -*-
"""
内核的测试：step、state 与 reset_state，用玩具插件（tests/fast/kernel_toys.py）
========================================

- 一次 step() 只结算一个事件、一次选行动加开始、或一次时间流逝；core.run 就是不停地 step()。
  选行动或结算里再调用 step() 抛 RuntimeError；结算出错时这一步什么也不改。
- state() 在条件、事件、选行动、行动开始、时间流逝（时钟还是旧的）、规则、Notice 的端口与 ApplyEffects 的钩子里，
  都是这一步开始时的同一个对象。
- reset_state：两步之间换掉 GameState，Reset 钩子跑一次；选行动里调用时这次选择中止，越过插件的 except Exception，
  不开始行动，下一步在新 GameState 上选；结算里（事件、行动开始、时间流逝、规则、Reset 钩子）抛 RuntimeError。
- Reset 的输入钩子里 state() 与 game_time.now() 已是新 GameState 与它的时钟，why 冻结后交给钩子；
  新 GameState 不合格、钩子改了时钟或钩子抛错时，抛错且 state() 不变。
"""

from collections.abc import Callable
from dataclasses import replace
from types import MappingProxyType
from typing import Any

from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.save_load import kernel_state
from tests.fast.kernel_toys import KernelTestCase, Toy, flag, game


class StopRun(Exception):
    """玩具插件结束 core.run 用的异常"""


class StepTest(KernelTestCase):
    """step() 与 run()"""

    def toy_world(self, trace: list[tuple[str, ...]]) -> Toy:
        """
        玩具世界：a 身上带 ring 时事件 Ring 成立并摘掉它；选行动给出 3 分钟的 Work；时间流逝记下终点
        Keyword arguments:
        trace -- 记下每次结算的列表
        Return arguments:
        Toy -- 玩具插件
        """
        toy = Toy()

        @toy.action("Work")
        def work(act: core.Action) -> core.Effects:
            trace.append(("start", act.who))
            return ()

        @toy.event("Ring", flag("ring"))
        def ring(who: str) -> core.Effects:
            trace.append(("event", who))
            return (core.StateChange(who, "ring", True, False),)

        @toy.input_hook(core.pick_next_action)
        def pick(who: str) -> core.Intercept[core.Action]:
            trace.append(("pick", who))
            return core.Intercept(core.new_action(work, who, 3))

        @toy.output_hook(core.time_elapse)
        def elapse(result: tuple[int, core.Effects]) -> Any:
            trace.append(("elapse", str(result[0])))
            if result[0] >= 6:
                raise StopRun
            return result

        return toy

    def test_each_step_settles_one_thing(self) -> None:
        """事件、a 选行动并开始、b 选行动并开始、时间流逝，各占一步"""
        trace: list[tuple[str, ...]] = []
        self.start(
            game(0, {"a": 0, "b": 0}, {"a": {"ring": True}}),
            self.toy_world(trace),
        )
        steps = []
        for _ in range(4):
            mark = len(trace)
            core.step()
            steps.append(trace[mark:])
        self.assertEqual(
            steps,
            [
                [("event", "a")],
                [("pick", "a"), ("start", "a")],
                [("pick", "b"), ("start", "b")],
                [("elapse", "3")],
            ],
        )
        self.assertEqual(core.state().clock, 3)

    def test_run_is_steps_forever(self) -> None:
        """core.run 的结算顺序与逐次调用 step() 的相同"""
        trace: list[tuple[str, ...]] = []
        toy = self.toy_world(trace)
        start = game(0, {"a": 0, "b": 0}, {"a": {"ring": True}})
        self.start(start, toy)
        with self.assertRaises(StopRun):
            while True:
                core.step()
        stepped = list(trace)
        trace.clear()
        with self.assertRaises(StopRun):
            core.run(start, (toy.module,))
        self.assertEqual(trace, stepped)
        self.assertEqual(stepped[-1], ("elapse", "6"))

    def test_step_inside_a_settlement_raises(self) -> None:
        """选行动、行动开始与事件里调用 step() 都抛 RuntimeError，GameState 不变"""
        toy = Toy()

        @toy.action("Nest")
        def nest(act: core.Action) -> core.Effects:
            core.step()
            return ()

        @toy.input_hook(core.pick_next_action)
        def pick(who: str) -> core.Intercept[core.Action]:
            if core.value(core.state(), who, "pick") is True:
                core.step()
            return core.Intercept(core.new_action(nest, who, 1))

        @toy.event("Nest", flag("nest"))
        def nest_event(who: str) -> core.Effects:
            core.step()
            return ()

        for state in (
            game(0, {"a": 0}, {"a": {"pick": True}}),
            game(0, {"a": 0}),
            game(0, {"a": 5}, {"a": {"nest": True}}),
        ):
            self.start(state, toy)
            before = core.state()
            with self.assertRaisesRegex(RuntimeError, "inside a step"):
                core.step()
            self.assertIs(core.state(), before)

    def test_raising_start_leaves_the_state(self) -> None:
        """行动开始时抛错：这一步之前的 GameState 原样留着，下一步照常"""
        toy = Toy()
        fail = [True]

        @toy.action("Fragile")
        def fragile(act: core.Action) -> core.Effects:
            if fail[0]:
                raise ValueError("broken start")
            return (core.StateChange(act.who, "done", None, True),)

        @toy.input_hook(core.pick_next_action)
        def pick(who: str) -> core.Intercept[core.Action]:
            return core.Intercept(core.new_action(fragile, who, 2))

        self.start(game(0, {"a": 0}), toy)
        before = core.state()
        with self.assertRaises(ValueError):
            core.step()
        self.assertIs(core.state(), before)
        fail[0] = False
        core.step()
        after = core.state().characters["a"]
        self.assertEqual(after.action.action_id, fragile.name)
        self.assertIs(after.data["done"], True)


class SnapshotTest(KernelTestCase):
    """结算各处读到的 state()"""

    def test_state_is_the_step_boundary(self) -> None:
        """每一步里各处读到的 state() 都是这一步开始时的对象"""
        toy = Toy()
        seen: list[tuple[str, core.GameState]] = []
        clocks: list[tuple[int, int, int]] = []

        def look(where: str) -> None:
            seen.append((where, core.state()))

        @toy.own
        def heard(text: str) -> None:
            look("notice")

        port = core.hook_only(toy.name("Heard"))(heard)

        @toy.rule("count")
        def count(state: core.GameState, change: core.Change) -> core.GameState:
            look("rule")
            old = core.value(state, change.who, change.key) or 0
            assert isinstance(old, int) and isinstance(change.operand, int)
            return core.with_value(
                state, change.who, change.key, old + change.operand
            )

        key = toy.name("count")

        @toy.action("Work")
        def work(act: core.Action) -> core.Effects:
            look("start")
            return (
                core.Change(act.who, key, "add", 1),
                core.Notice(port, ("worked",)),
            )

        def ringing(state: core.GameState) -> str | None:
            look("condition")
            return flag("ring")(state)

        @toy.event("Ring", ringing)
        def ring(who: str) -> core.Effects:
            look("event")
            return (
                core.StateChange(who, "ring", True, False),
                core.Change(who, key, "add", 1),
            )

        @toy.input_hook(core.pick_next_action)
        def pick(who: str) -> core.Intercept[core.Action]:
            look("pick")
            return core.Intercept(core.new_action(work, who, 2))

        @toy.input_hook(core.time_elapse)
        def elapse(start: int, end: int) -> tuple[int, int]:
            look("elapse")
            clocks.append((core.state().clock, start, end))
            return (start, end)

        @toy.input_hook(core.apply_effects)
        def applying(effects: core.Effects) -> tuple[core.Effects]:
            look("apply")
            return (effects,)

        self.start(game(0, {"a": 0}, {"a": {"ring": True}}), toy)
        places: set[str] = set()
        for _ in range(3):
            seen.clear()
            boundary = core.state()
            core.step()
            self.assertIsNot(core.state(), boundary, "这一步改了 GameState")
            for where, state in seen:
                self.assertIs(state, boundary, where)
                places.add(where)
        self.assertEqual(clocks, [(0, 0, 2)], "时间流逝里 state() 还是旧的时钟")
        self.assertEqual(
            places,
            {
                "condition",
                "event",
                "rule",
                "notice",
                "apply",
                "pick",
                "start",
                "elapse",
            },
        )


class ResetTest(KernelTestCase):
    """reset_state 的三种时机"""

    def test_reset_between_steps(self) -> None:
        """两步之间换掉 GameState：Reset 钩子跑一次，下一步为新 GameState 里的角色选行动"""
        toy = Toy()
        resets: list[core.GameState] = []
        picked: list[tuple[str, int]] = []

        @toy.input_hook(core.reset)
        def on_reset(
            new: core.GameState, why: core.Data
        ) -> tuple[core.GameState, core.Data]:
            resets.append(new)
            return (new, why)

        @toy.input_hook(core.pick_next_action)
        def pick(who: str) -> tuple[str]:
            picked.append((who, core.state().clock))
            return (who,)

        self.start(game(0, {"a": 0}), toy)
        core.step()
        resets.clear()
        new = game(40, {"b": 40})
        core.reset_state(new)
        self.assertEqual(resets, [new])
        self.assertEqual(core.state(), new)
        core.step()
        self.assertEqual(picked, [("a", 0), ("b", 40)])

    def test_reset_in_a_pick_aborts_it(self) -> None:
        """选行动里 reset_state：插件的 except Exception 拦不住，行动不开始，下一步在新 GameState 上选"""
        toy = Toy()
        started: list[str] = []
        picked: list[tuple[str, int]] = []
        new = game(90, {"b": 90})

        @toy.action("Work")
        def work(act: core.Action) -> core.Effects:
            started.append(act.who)
            return ()

        @toy.input_hook(core.pick_next_action)
        def pick(who: str) -> core.Intercept[core.Action]:
            picked.append((who, core.state().clock))
            if who == "a":
                try:
                    core.reset_state(new)
                except Exception:
                    started.append("swallowed")
            return core.Intercept(core.new_action(work, who, 5))

        self.start(game(0, {"a": 0}), toy)
        core.step()
        self.assertEqual(started, [])
        self.assertEqual(core.state(), new)
        core.step()
        self.assertEqual(picked, [("a", 0), ("b", 90)])
        self.assertEqual(started, ["b"])
        self.assertEqual(core.state().characters["b"].action.start, 90)

    def test_reset_mid_settlement_raises(self) -> None:
        """事件、行动开始、时间流逝、规则里 reset_state 都抛 RuntimeError，GameState 不变"""
        cases: list[tuple[str, Callable[[Toy], core.GameState]]] = [
            ("event", self.reset_in_event),
            ("start", self.reset_in_start),
            ("elapse", self.reset_in_elapse),
            ("rule", self.reset_in_rule),
        ]
        for where, build in cases:
            with self.subTest(where):
                toy = Toy()
                self.start(build(toy), toy)
                before = core.state()
                with self.assertRaisesRegex(
                    RuntimeError, "forbidden during settlement"
                ):
                    core.step()
                self.assertIs(core.state(), before)

    def test_reset_inside_a_reset_hook_raises(self) -> None:
        """Reset 钩子里再 reset_state 抛 RuntimeError，GameState 不变"""
        toy = Toy()

        @toy.input_hook(core.reset)
        def again(
            new: core.GameState, why: core.Data
        ) -> tuple[core.GameState, core.Data]:
            if new.clock == 1:
                self.call_reset()
            return (new, why)

        self.start(game(0, {"a": 0}), toy)
        before = core.state()
        with self.assertRaisesRegex(
            RuntimeError, "forbidden during settlement"
        ):
            core.reset_state(game(1, {"a": 1}))
        self.assertIs(core.state(), before)
        core.step()

    def call_reset(self) -> None:
        """结算里换掉 GameState"""
        core.reset_state(game(7, {"z": 7}))

    def reset_in_event(self, toy: Toy) -> core.GameState:
        """
        事件 Hit 的结算里 reset_state
        Keyword arguments:
        toy -- 玩具插件
        Return arguments:
        GameState -- 起始 GameState
        """

        @toy.event("Hit", lambda state: True)
        def hit(_due: bool) -> core.Effects:
            self.call_reset()
            return ()

        return game(0, {"a": 5})

    def reset_in_start(self, toy: Toy) -> core.GameState:
        """
        行动开始里 reset_state
        Keyword arguments:
        toy -- 玩具插件
        Return arguments:
        GameState -- 起始 GameState
        """

        @toy.action("Work")
        def work(act: core.Action) -> core.Effects:
            self.call_reset()
            return ()

        @toy.input_hook(core.pick_next_action)
        def pick(who: str) -> core.Intercept[core.Action]:
            return core.Intercept(core.new_action(work, who, 1))

        return game(0, {"a": 0})

    def reset_in_elapse(self, toy: Toy) -> core.GameState:
        """
        时间流逝的钩子里 reset_state
        Keyword arguments:
        toy -- 玩具插件
        Return arguments:
        GameState -- 起始 GameState
        """

        @toy.input_hook(core.time_elapse)
        def elapse(start: int, end: int) -> tuple[int, int]:
            self.call_reset()
            return (start, end)

        return game(0, {"a": 5})

    def reset_in_rule(self, toy: Toy) -> core.GameState:
        """
        规则里 reset_state（事件交回这个键的 Change）
        Keyword arguments:
        toy -- 玩具插件
        Return arguments:
        GameState -- 起始 GameState
        """

        @toy.rule("k")
        def k_rule(
            state: core.GameState, change: core.Change
        ) -> core.GameState:
            self.call_reset()
            return state

        key = toy.name("k")

        @toy.event("Touch", flag("t"))
        def touch(who: str) -> core.Effects:
            return (
                core.StateChange(who, "t", True, False),
                core.Change(who, key, "set", 1),
            )

        return game(0, {"a": 5}, {"a": {"t": True}})


class ResetHookTest(KernelTestCase):
    """Reset 钩子看到的状态与 why，以及新 GameState 的检查"""

    def test_hook_reads_incoming_clock(self) -> None:
        """输入钩子里 state() 是新 GameState，game_time.now() 是它的时钟"""
        toy = Toy()
        seen: list[tuple[int, int]] = []

        @toy.input_hook(core.reset)
        def look(
            new: core.GameState, why: core.Data
        ) -> tuple[core.GameState, core.Data]:
            seen.append(
                (core.state().clock, game_time.minutes(game_time.now()))
            )
            return (new, why)

        first = kernel_state.first_clock()
        self.start(game(first, {"a": first}), toy)
        seen.clear()
        clock = first + 600
        core.reset_state(game(clock, {"b": clock}))
        self.assertEqual(seen, [(clock, clock)])

    def test_why_reaches_hooks_frozen(self) -> None:
        """why 冻结成只读的 JSON 交给输入钩子"""
        toy = Toy()
        got: list[core.Data] = []

        @toy.input_hook(core.reset)
        def keep(
            new: core.GameState, why: core.Data
        ) -> tuple[core.GameState, core.Data]:
            got.append(why)
            return (new, why)

        self.start(game(0, {"a": 0}), toy)
        why: core.Data = {
            "cause": "load",
            "save": "3",
            "inherit": {"keys": (1, 2)},
        }
        core.reset_state(game(5, {"a": 5}), why)
        self.assertEqual(got[-1]["cause"], "load")
        self.assertEqual(got[-1]["inherit"], {"keys": (1, 2)})
        self.assertIsInstance(got[-1], MappingProxyType)
        with self.assertRaises(TypeError):
            not_json: Any = object()
            core.reset_state(game(5, {"a": 5}), {"cause": not_json})

    def test_bad_state_raises_and_keeps_state(self) -> None:
        """不合格的新 GameState 或钩子返回的 GameState 抛 RuntimeError，state() 不变"""
        idle = core.Action("a", core.idle.name, None, 0, 0)
        half: Any = 0.5
        bad: list[tuple[str, core.GameState]] = [
            ("clock", replace(game(0, {"a": 0}), clock=half)),
            ("who", self.with_action(replace(idle, who="b"))),
            ("unregistered", self.with_action(replace(idle, action_id="x"))),
            ("start", self.with_action(replace(idle, start=half))),
            ("negative", self.with_action(replace(idle, duration=-1))),
        ]
        self.start(game(0, {"a": 0}), Toy())
        before = core.state()
        for name, state in bad:
            with self.subTest(name), self.assertRaises(RuntimeError):
                core.reset_state(state)
            self.assertIs(core.state(), before)
        for name, state in bad:
            with self.subTest("hook " + name):
                toy = Toy()

                @toy.input_hook(core.reset)
                def swap(
                    new: core.GameState,
                    why: core.Data,
                    out: core.GameState = state,
                ) -> tuple[core.GameState, core.Data]:
                    return (out, why)

                core.load((toy.module,))
                kept = core.state()
                with self.assertRaises(RuntimeError):
                    core.reset_state(game(0, {"a": 0}))
                self.assertIs(core.state(), kept)

    def test_clock_change_raises(self) -> None:
        """钩子改了时钟抛 RuntimeError，state() 不变"""
        toy = Toy()

        @toy.input_hook(core.reset)
        def later(
            new: core.GameState, why: core.Data
        ) -> tuple[core.GameState, core.Data]:
            return (replace(new, clock=new.clock + 1), why)

        self.start(game(0, {"a": 0}), Toy())
        before = core.state()
        core.load((toy.module,))
        with self.assertRaisesRegex(RuntimeError, "changed the clock"):
            core.reset_state(game(10, {"a": 10}))
        self.assertIs(core.state(), before)

    def test_raising_hook_keeps_state(self) -> None:
        """钩子抛错时 state() 与它的时钟都回到调用前"""
        toy = Toy()

        @toy.input_hook(core.reset)
        def boom(
            new: core.GameState, why: core.Data
        ) -> tuple[core.GameState, core.Data]:
            raise ValueError("boom")

        self.start(game(0, {"a": 0}), Toy())
        before = core.state()
        core.load((toy.module,))
        with self.assertRaisesRegex(ValueError, "boom"):
            core.reset_state(game(10, {"a": 10}))
        self.assertIs(core.state(), before)
        self.assertEqual(core.instant()[0], 0)

    def with_action(self, act: core.Action) -> core.GameState:
        """
        只有角色 a 的 GameState，时钟 0，a 的行动是 act
        Keyword arguments:
        act -- a 的行动
        Return arguments:
        GameState -- 新的 GameState
        """
        character = core.Character(act, MappingProxyType({}))
        return core.GameState(
            0, MappingProxyType({"a": character}), MappingProxyType({})
        )
