# -*- coding: UTF-8 -*-
"""
行动的结束函数（core.action_end）与事件、收尾的循环上限
======================================================

- 登记了结束函数的行动用完时间后，内核在这一分钟的事件之后、选行动之前运行它一次，交给它结束时的行动；
  之后角色拿着 0 分钟的 kernel.Idle，下一步选行动。被打断的行动在打断的那一分钟收尾。
- 没有结束函数的 0 分钟行动不收尾：同一分钟里先结算事件，再由角色接着选。有结束函数的 0 分钟行动照样收尾。
- 事件与收尾之间互相触发超过 core.CYCLE_LIMIT 步时抛出 core.EventCycle。
- 移除角色与 reset_state 不运行结束函数；重复登记或给没有登记的行动登记结束函数时报错。
- 插件在 kernel.EndAction 上的输入钩子看到每一次收尾。
"""

from collections.abc import Callable

from Script.Kernel import core
from tests.fast.kernel_toys import KernelTestCase, Toy, flag, game

type Log = list[tuple[str, str, int]]


class ActionEndTest(KernelTestCase):
    """结束函数在一步里的位置与次数"""

    def toy_world(
        self, minutes: int, *, with_end: bool = True, on_start: str = ""
    ) -> tuple[Toy, Log, list[core.Action]]:
        """
        玩具世界：A 第一次选 minutes 分钟的 Work，之后选 60 分钟的 Rest；B 的 Idle 到第 99 分钟。
        事件 Flagged 在角色数据 flag 为真时成立并清掉它，事件 Leave 在 leave 为真时移除角色。
        Work 的结束函数把 flag 设为真（with_end 为假时 Work 没有结束函数）；on_start 为数据键时 Work 开始时把它设为真
        Keyword arguments:
        minutes -- Work 的分钟数
        with_end -- Work 是否登记结束函数
        on_start -- Work 开始时设为真的数据键，空时不设
        Return arguments:
        tuple -- (插件, 日志, 结束函数收到的行动)
        """
        toy = Toy()
        log: Log = []
        ended: list[core.Action] = []

        @toy.action("Work")
        def work(act: core.Action) -> core.Effects:
            log.append(("start", act.who, core.instant()[0]))
            if on_start:
                return (core.StateChange(act.who, on_start, None, True),)
            return ()

        @toy.action("Rest")
        def rest(act: core.Action) -> core.Effects:
            return ()

        if with_end:

            def end(act: core.Action) -> core.Effects:
                log.append(("end", act.who, core.instant()[0]))
                ended.append(act)
                return (core.StateChange(act.who, "flag", None, True),)

            core.action_end(work)(toy.own(end))

        @toy.event("Flagged", flag("flag"))
        def flagged(who: str) -> core.Effects:
            log.append(("event", who, core.instant()[0]))
            return (core.StateChange(who, "flag", True, None),)

        @toy.event("Leave", flag("leave"))
        def leave(who: str) -> core.Effects:
            log.append(("leave", who, core.instant()[0]))
            return (core.RemoveCharacter(who),)

        picks = iter([work])

        @toy.input_hook(core.pick_next_action)
        def pick(who: str) -> core.Intercept[core.Action]:
            log.append(("pick", who, core.instant()[0]))
            kind = next(picks, rest)
            length = minutes if kind is work else 60
            return core.Intercept(core.new_action(kind, who, length))

        self.start(game(10, {"A": 10, "B": 99}), toy)
        return toy, log, ended

    def run_until(self, log: Log, entries: int) -> None:
        """走到日志有 entries 条为止（最多 50 步）"""
        for _ in range(50):
            if len(log) >= entries:
                return
            core.step()

    def test_k1_end_runs_once_after_events_before_pick(self) -> None:
        """3 分钟的 Work 在第 13 分钟收尾一次，收尾使事件成立，事件先于下一次选；之后角色拿着 0 分钟的 Idle"""
        _, log, ended = self.toy_world(3)
        self.run_until(log, 5)
        self.assertEqual(
            log[:5],
            [
                ("pick", "A", 10),
                ("start", "A", 10),
                ("end", "A", 13),
                ("event", "A", 13),
                ("pick", "A", 13),
            ],
        )
        self.assertEqual(len(ended), 1)
        self.assertEqual((ended[0].start, ended[0].duration), (10, 3))

    def test_k1_closed_character_holds_zero_minute_idle(self) -> None:
        """收尾那一步之后，角色的行动是从这一分钟开始的 0 分钟 kernel.Idle"""
        self.toy_world(3)
        core.step()
        core.step()
        core.step()
        act = core.state().characters["A"].action
        self.assertEqual(
            (act.action_id, act.start, act.duration), (core.idle.name, 13, 0)
        )

    def test_k2_interrupted_action_ends_at_interrupt(self) -> None:
        """第 11 分钟打断 3 分钟的 Work：收尾在第 11 分钟，收到的行动 duration 为 1"""
        toy, log, ended = self.toy_world(3)
        core.step()

        @toy.input_hook(core.time_elapse)
        def stop(
            begin: int, end: int
        ) -> core.Intercept[tuple[int, core.Effects]]:
            return core.Intercept((11, (core.Interrupt("A"),)))

        core.step()
        core.step()
        self.assertEqual(log[2], ("end", "A", 11))
        self.assertEqual(ended[0].duration, 1)

    def test_k3_zero_minute_kind_without_end_goes_to_pick(self) -> None:
        """没有结束函数的 0 分钟 Work 在第 10 分钟开始并使事件成立：事件与再选都在第 10 分钟，不收尾，时钟不动"""
        _, log, ended = self.toy_world(0, with_end=False, on_start="flag")
        instants = []
        for _ in range(3):
            instants.append(core.instant())
            core.step()
        self.assertEqual(
            log,
            [
                ("pick", "A", 10),
                ("start", "A", 10),
                ("event", "A", 10),
                ("pick", "A", 10),
            ],
        )
        self.assertEqual(instants, [(10, 0), (10, 1), (10, 2)])
        self.assertEqual(ended, [])
        self.assertEqual(core.state().clock, 10)

    def test_k4_zero_minute_kind_with_end_wraps_up(self) -> None:
        """有结束函数的 0 分钟 Work 在第 10 分钟收尾"""
        _, log, ended = self.toy_world(0)
        self.run_until(log, 3)
        self.assertEqual(log[2], ("end", "A", 10))
        self.assertEqual(len(ended), 1)

    def test_k6_reset_state_runs_no_end(self) -> None:
        """Work 进行中时 reset_state 换入第 20 分钟（Work 已过结束的分钟）：换入时不运行结束函数"""
        _, log, ended = self.toy_world(3)
        core.step()
        old = core.state()
        core.reset_state(core.GameState(20, old.characters, old.data))
        self.assertEqual(ended, [])

    def test_k6_removed_character_runs_no_end(self) -> None:
        """Work 开始时设 leave，事件 Leave 移除 A：之后时间走过 Work 的结束分钟，A 的结束函数从不运行"""
        _, log, ended = self.toy_world(3, on_start="leave")
        for _ in range(4):
            core.step()
        self.assertIn(("leave", "A", 10), log)
        self.assertNotIn("A", core.state().characters)
        self.assertGreater(core.state().clock, 13)
        self.assertEqual(ended, [])


class EndRegistrationTest(KernelTestCase):
    """登记结束函数的检查与 kernel.EndAction 钩子"""

    def test_k7_unregistered_or_second_end_raises(self) -> None:
        """没有登记的行动、已有结束函数的行动，再登记结束函数都报错"""
        toy = Toy()

        @toy.action("Work")
        def work(act: core.Action) -> core.Effects:
            return ()

        end: Callable[[core.Action], core.Effects] = toy.own(lambda act: ())
        core.action_end(work)(end)
        with self.assertRaises(RuntimeError):
            core.action_end(work)(end)
        with self.assertRaises(RuntimeError):
            core.action_end(core.Start(toy.name("Nothing")))(end)

    def test_k8_plugin_hook_sees_every_end(self) -> None:
        """插件在 kernel.EndAction 上的输入钩子看到 A 与 B 的两次收尾"""
        toy = Toy()
        plugin = Toy()
        seen: list[str] = []

        @toy.action("Work")
        def work(act: core.Action) -> core.Effects:
            return ()

        @toy.action("Rest")
        def rest(act: core.Action) -> core.Effects:
            return ()

        core.action_end(work)(toy.own(lambda act: ()))

        @toy.input_hook(core.pick_next_action)
        def pick(who: str) -> core.Intercept[core.Action]:
            if (
                core.state().characters[who].action.action_id == core.idle.name
                and core.state().clock == 10
            ):
                return core.Intercept(core.new_action(work, who, 2))
            return core.Intercept(core.new_action(rest, who, 60))

        @plugin.input_hook(core.end_action)
        def spy(act: core.Action) -> tuple[core.Action]:
            seen.append(act.who)
            return (act,)

        core.load((toy.module, plugin.module))
        core.reset_state(game(10, {"A": 10, "B": 10}))
        for _ in range(8):
            core.step()
        self.assertEqual(seen, ["A", "B"])


class EventCycleTest(KernelTestCase):
    """事件互相触发的上限"""

    def test_k5_two_events_feeding_each_other_raise(self) -> None:
        """事件 Ping 设 pong、Pong 设 ping：超过 CYCLE_LIMIT 步后抛出 core.EventCycle"""
        toy = Toy()

        @toy.event("Ping", flag("ping"))
        def ping(who: str) -> core.Effects:
            return (
                core.StateChange(who, "ping", True, None),
                core.StateChange(who, "pong", None, True),
            )

        @toy.event("Pong", flag("pong"))
        def pong(who: str) -> core.Effects:
            return (
                core.StateChange(who, "pong", True, None),
                core.StateChange(who, "ping", None, True),
            )

        self.start(game(10, {"A": 99}, {"A": {"ping": True}}), toy)
        with self.assertRaises(core.EventCycle):
            for _ in range(core.CYCLE_LIMIT + 2):
                core.step()
