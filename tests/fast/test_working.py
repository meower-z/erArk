# -*- coding: UTF-8 -*-
"""
工作集（gameplay_resolution.working）的测试，用玩具插件（tests/fast/kernel_toys.py）
====================================================================================
- 事件里写两次、中间读：读到自己的写入，这一步每个 (角色, 键) 只交给内核一个效果。
- 一开始没有的键 put 两次：只有一个 old 为 None 的 StateChange，内核接受。
- 只有处理函数经缓冲区的写入让触发函数变为不成立：写入在这一步套用，不报 EventStillTrue。
- 干员选行动时写入报错。结算出错的一步写下的东西不留到下一步。
- 选择里的写入（含 forget）随行动走，行动开始时生效。只有写入、没有草稿的玩家选择也定下 Edit。
- based_on 里读得到自己的写入，套用效果后的状态有它。
- 角色离开花名册再回来，数据还在。forget 丢掉 roster.offstage 里的一项。
"""

from collections.abc import Mapping
from typing import Any, cast
from unittest import mock

from Script.Kernel import core
from Script.Modules.gameplay_resolution import edits, working
from Script.Modules.tk_ui import player_pick
from tests.fast.kernel_toys import KernelTestCase, Toy, flag, game


def _add(old: core.JSON, op: str, operand: core.JSON) -> core.JSON:
    assert op == "add" and isinstance(old, int) and isinstance(operand, int)
    return old + operand


class WorkingTest(KernelTestCase):
    """working 的读写与搬动"""

    def setUp(self) -> None:
        """每个测试登记自己的键：plain 只能 put，count 由规则拥有。缓存里有角色 1、2、3"""
        super().setUp()
        self.enterContext(mock.patch.dict(working._keys))
        self.enterContext(
            mock.patch.dict(
                self.cache.character_data, {1: None, 2: None, 3: None}
            )
        )
        self.toy = Toy()
        self.plain = self.toy.name("plain")
        self.count = self.toy.name("count")
        working.register(self.plain, None)
        working.register(self.count, 0, _add)
        count = self.count

        @self.toy.rule("count")
        def apply_count(
            game: core.GameState, change: core.Change
        ) -> core.GameState:
            old = core.value(game, change.who, count)
            ops = cast(tuple[core.JSON, ...], change.operand)
            new = working.fold_all(count, old, ops)
            return core.with_value(game, change.who, count, new)

        self.applied: list[core.Effects] = []
        self.spy = Toy()

        @self.spy.input_hook(core.apply_effects)
        def seen(effects: core.Effects) -> tuple[core.Effects]:
            self.applied.append(effects)
            return (effects,)

    def run_world(self, state: core.GameState) -> None:
        """
        载入 spy（最里层，看到 flush 之后的效果）、working 与玩具插件，从 state 开始
        Keyword arguments:
        state -- 起始 GameState
        """
        core.load((self.spy.module, working, self.toy.module))
        core.reset_state(state)

    def test_handler_reads_its_writes_and_applies_one_effect(self) -> None:
        """事件里 put 两次、change 两次，中间读到自己的写入。这一步每个键只有一个效果"""
        reads: list[core.JSON] = []

        @self.toy.event("Go", flag("go"))
        def go(who: str) -> core.Effects:
            working.put(who, self.plain, 1)
            reads.append(working.get(who, self.plain))
            working.put(who, self.plain, 2)
            working.change(who, self.count, "add", 3)
            reads.append(working.get(who, self.count))
            working.change(who, self.count, "add", 4)
            return (core.StateChange(who, "go", True, False),)

        self.run_world(game(0, {"1": 9}, {"1": {"go": True}}))
        core.step()
        self.assertEqual(reads, [1, 3])
        mine = [
            e
            for e in self.applied[-1]
            if isinstance(e, core.StateChange | core.Change)
            and e.key in (self.plain, self.count)
        ]
        self.assertEqual(len(mine), 2)
        self.assertEqual(core.value(core.state(), "1", self.plain), 2)
        self.assertEqual(core.value(core.state(), "1", self.count), 7)

    def test_two_puts_on_an_absent_key(self) -> None:
        """一开始没有的键 put 两次：只有一个从 None 出发的 StateChange，内核接受"""

        @self.toy.event("Go", flag("go"))
        def go(who: str) -> core.Effects:
            working.put(None, self.plain, {"a": 1})
            working.put(None, self.plain, {"a": 2})
            return (core.StateChange(who, "go", True, False),)

        self.run_world(game(0, {"1": 9}, {"1": {"go": True}}))
        core.step()
        mine = [
            e
            for e in self.applied[-1]
            if isinstance(e, core.StateChange) and e.key == self.plain
        ]
        self.assertEqual(
            mine, [core.StateChange(None, self.plain, None, {"a": 2})]
        )
        self.assertEqual(core.value(core.state(), None, self.plain), {"a": 2})

    def test_trigger_cleared_only_by_a_buffered_write(self) -> None:
        """触发函数读给它的状态。只有处理函数经缓冲区的写入让它变为不成立，这一步结算完不报 EventStillTrue"""
        count = self.count

        def due(state: core.GameState) -> str | None:
            return "1" if working.get("1", count, state) == 0 else None

        @self.toy.event("Fill", due)
        def fill(who: str) -> core.Effects:
            working.change(who, count, "add", 1)
            return ()

        self.run_world(game(0, {"1": 9}))
        core.step()
        self.assertEqual(core.value(core.state(), "1", count), 1)

    def test_write_in_an_npc_pick_raises(self) -> None:
        """干员选行动时写入报 RuntimeError，状态不变"""

        @self.toy.input_hook(core.pick_next_action)
        def pick(who: str) -> tuple[str]:
            working.put(who, self.plain, 1)
            return (who,)

        self.run_world(game(0, {"1": 0}))
        before = core.state()
        with self.assertRaisesRegex(RuntimeError, "outside a step"):
            core.step()
        self.assertIs(core.state(), before)

    def test_failed_step_leaves_nothing(self) -> None:
        """事件写入后抛错，下一步不带上这些写入"""
        fail = [True]

        @self.toy.event("Go", flag("go"))
        def go(who: str) -> core.Effects:
            if fail[0]:
                working.put(who, self.plain, "stale")
                raise ValueError("broken")
            working.change(who, self.count, "add", 1)
            return (core.StateChange(who, "go", True, False),)

        self.run_world(game(0, {"1": 9}, {"1": {"go": True}}))
        with self.assertRaises(ValueError):
            core.step()
        fail[0] = False
        core.step()
        self.assertIsNone(core.value(core.state(), "1", self.plain))
        self.assertEqual(core.value(core.state(), "1", self.count), 1)

    def test_pick_writes_ride_the_action(self) -> None:
        """选择里的写入关闭时交回，行动开始时 replay，套用后生效。整值替换的旧值不符时 replay 报错"""
        carried: list[tuple[core.JSON, ...]] = []

        @self.toy.action("Work")
        def work(act: core.Action) -> core.Effects:
            data = cast(Mapping[str, Any], act.action_data)
            working.replay(data["effects"])
            return ()

        @self.toy.input_hook(core.pick_next_action)
        def pick(who: str) -> core.Intercept[core.Action]:
            buffer = working.open_pick()
            working.put(who, self.plain, 5)
            working.change(who, self.count, "add", 2)
            self_read = working.get(who, self.plain)
            effects = working.close_pick(buffer)
            carried.append(effects)
            assert self_read == 5
            data = {"effects": effects}
            return core.Intercept(core.new_action(work, who, 3, data))

        self.run_world(game(0, {"1": 0}))
        core.step()
        self.assertEqual(core.value(core.state(), "1", self.plain), 5)
        self.assertEqual(core.value(core.state(), "1", self.count), 2)
        stale = core.with_value(core.state(), "1", self.plain, 6)
        with (
            working.based_on(stale),
            self.assertRaisesRegex(RuntimeError, "does not follow"),
        ):
            working.replay(carried[0])

    def test_forget_in_a_pick_rides_the_action(self) -> None:
        """选择里 forget 的角色随交回的写入走，行动开始时 replay，roster.offstage 里这个角色的一项随之丢掉"""

        @self.toy.action("Work")
        def work(act: core.Action) -> core.Effects:
            working.replay(cast(Mapping[str, Any], act.action_data)["effects"])
            return ()

        @self.toy.input_hook(core.pick_next_action)
        def pick(who: str) -> core.Intercept[core.Action]:
            buffer = working.open_pick()
            working.forget(3)
            data = {"effects": working.close_pick(buffer)}
            return core.Intercept(core.new_action(work, who, 3, data))

        start = game(0, {"1": 0})
        with working.based_on(start) as buffer:
            working.put("3", self.plain, "parked")
            effects = buffer.effects()
        self.run_world(core.preview(start, effects))
        core.step()
        offstage = core.value(core.state(), None, working.OFFSTAGE)
        self.assertEqual(dict(cast(Mapping[str, Any], offstage)), {})

    def test_pick_with_only_effects_commits_an_edit(self) -> None:
        """玩家选择里只写了 GameState 数据：草稿关闭时定下一个草稿为空、带这些写入的 Edit"""
        self.run_world(game(0, {"0": 9}))
        with (
            self.assertRaises(player_pick.Chosen) as chosen,
            player_pick.picking(),
            player_pick.drafting("test"),
        ):
            working.put(None, self.plain, 1)
        act = chosen.exception.action
        self.assertEqual(act.action_id, edits.EDIT)
        data = cast(Mapping[str, Any], act.action_data)
        self.assertEqual(data["draft"], ())
        self.assertEqual(
            data["effects"],
            ({"who": None, "key": self.plain, "old": None, "new": 1},),
        )

    def test_based_on_reads_its_writes(self) -> None:
        """based_on 里读到自己的写入。effects() 套用后的状态有它，不在花名册里的角色的写入在 roster.offstage 里"""
        start = game(0, {"1": 9})
        with working.based_on(start) as buffer:
            working.change("1", self.count, "add", 2)
            working.put("2", self.plain, "parked")
            self.assertEqual(working.get("1", self.count), 2)
            self.assertEqual(working.get("2", self.plain), "parked")
            effects = buffer.effects()
        self.run_world(start)
        after = core.preview(start, effects)
        self.assertEqual(core.value(after, "1", self.count), 2)
        self.assertEqual(working.get("2", self.plain, after), "parked")

    def test_data_follows_the_roster(self) -> None:
        """角色 2 离开花名册，数据进 roster.offstage，回来时数据跟着回来。forget 丢掉角色 3 停放的数据"""

        @self.toy.event("Leave", flag("leave"))
        def leave(who: str) -> core.Effects:
            return (
                core.StateChange(who, "leave", True, False),
                core.RemoveCharacter(who),
            )

        @self.toy.event("Back", lambda g: "2" if g.data.get("back") else None)
        def back(who: str) -> core.Effects:
            working.forget(3)
            return (
                core.StateChange(None, "back", True, False),
                core.AddCharacter(who),
            )

        start = game(0, {"1": 9, "2": 9}, {"2": {"leave": True}})
        with working.based_on(start) as buffer:
            working.put("2", self.plain, "kept")
            working.put("3", self.plain, "parked")
            effects = buffer.effects()
        self.run_world(core.preview(start, effects))
        core.step()
        self.assertNotIn("2", core.state().characters)
        self.assertEqual(working.get("2", self.plain, core.state()), "kept")
        core.reset_state(core.with_value(core.state(), None, "back", True))
        core.step()
        self.assertEqual(core.value(core.state(), "2", self.plain), "kept")
        offstage = core.value(core.state(), None, working.OFFSTAGE)
        self.assertEqual(dict(cast(Mapping[str, Any], offstage)), {})
