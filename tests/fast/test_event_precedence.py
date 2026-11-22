# -*- coding: UTF-8 -*-
"""
事件之间的先后写在触发函数里：前提不成立时，触发函数交回 None
================================================================
内核不保证同时成立的事件谁先结算，所以要等另一个事件的事件在自己的触发函数里写明前提。
每个用例造一个让事件成立的现场，先让它要等的事件成立（触发交回 None），再让那个事件已结算（触发交回数据）。
- NewDay 等 Tick 把每个角色结算到此刻（ticked 等于时钟）。
- 别的事件等这一分钟的 Tick 与 NewDay（time_hooks.clock_settled）。
- PlayerSpent、HEnd、GroupExit 等 ArtsBreak（time_hooks.arts_settled）。
- HEnd、GroupExit、HLeftBehind 等玩家力竭（PlayerSpent）。
- StopFollowing 等同一干员的 BecomeTired。
- HLeftBehind 等同一干员力竭的收场（events.tired_case）。
另有一例：BecomeTired 与 PlayerSpent 的触发函数从交给它们的 GameState 读体力，不读同一步里还没套用的写入。
"""

import datetime
from collections.abc import Callable
from types import MappingProxyType
from typing import cast
from unittest import mock

from Script.Design import attr_calculation, character_behavior, game_time
from Script.Design import handle_premise
from Script.Kernel import core
from Script.Modules.domains import activity, flags, modes, needs
from Script.Modules.gameplay_resolution import actions, events, time_hooks
from Script.Modules.gameplay_resolution import working
from Script.Settle import realtime_settle
from tests.fast.base import FastTestCase
from tests import kernel_data
from tests.chara_activity import aim

type Trigger = Callable[[core.GameState], object]

MIDNIGHT = (
    game_time.day(game_time.minutes(datetime.datetime(2019, 3, 1))) + 1
) * game_time.MINUTES_PER_DAY
""" 一个 0 点的时钟 """
NOON = MIDNIGHT + 12 * 60
""" 同一天中午的时钟 """


def state(clock: int, ticked: int, settled_day: int) -> core.GameState:
    """
    玩家与干员1各做一个 10 小时的 Behavior 的 GameState。两人的 body.needs 与 activity 的十个键取调用时内核状态里的值
    Keyword arguments:
    clock -- 时钟
    ticked -- 上一次 Tick 结算到的时钟
    settled_day -- 已跑过新一天结算的游戏日
    Return arguments:
    GameState -- 新的 GameState
    """
    characters = {
        who: core.Character(
            core.Action(who, actions.behave.name, None, clock - 1, 600),
            MappingProxyType(
                {
                    **{
                        key: working.get(who, key, core.state())
                        for key in activity.KEYS
                    },
                    needs.KEY: cast(
                        core.JSON, needs.of(int(who), core.state())
                    ),
                    flags.KEY: working.get(who, flags.KEY, core.state()),
                }
            ),
        )
        for who in ("0", "1")
    }
    return core.GameState(
        clock,
        MappingProxyType(characters),
        MappingProxyType(
            {
                **core.state().data,
                time_hooks.TICKED: ticked,
                time_hooks.SETTLED_DAY: settled_day,
            }
        ),
    )


def settled() -> core.GameState:
    """中午、Tick 与 NewDay 都已结算的 GameState，body.needs 取调用时内核状态里的值"""
    return state(NOON, NOON, game_time.day(NOON))


def tick_due() -> core.GameState:
    """中午、Tick 还没结算的 GameState，body.needs 取调用时内核状态里的值"""
    return state(NOON, NOON - 5, game_time.day(NOON))


class PrecedenceTest(FastTestCase):
    """前提不成立时事件不触发，前提成立时触发"""

    def setUp(self) -> None:
        """玩家与 H 中的干员1在一起；源石技艺不中断"""
        super().setUp()
        self.player = self.world.chara(0, "博士")
        self.npc = self.world.chara(1, "干员")
        aim(self.player.cid, 1)
        kernel_data.set_needs(self.player.cid, hit=100)
        kernel_data.set_needs(self.npc.cid, hit=100)
        kernel_data.put(flags.set, self.npc.cid, is_h=True)
        self.arts_due = False
        self.enterContext(
            mock.patch.object(
                realtime_settle,
                "arts_break_due",
                lambda game=None: self.arts_due,
            )
        )

    def assert_waits(
        self,
        trigger: Trigger,
        data: object,
        before: Callable[[], core.GameState],
        after: Callable[[], core.GameState],
    ) -> None:
        """
        before() 造的现场里前提不成立，触发交回 None；after() 造的现场里前提成立，触发交回 data
        Keyword arguments:
        trigger -- 触发函数
        data -- 前提成立时应交回的数据
        before -- 造出前提不成立的现场，交回 GameState
        after -- 造出前提成立的现场，交回 GameState
        """
        self.assertIsNone(trigger(before()), "前提不成立时不触发")
        self.assertEqual(trigger(after()), data, "前提成立时触发")

    def test_new_day_waits_for_tick(self) -> None:
        """0 点 ticked 还是 23:55：NewDay 不触发；ticked 到 0 点：交回今天"""
        yesterday = game_time.day(MIDNIGHT) - 1
        self.assert_waits(
            time_hooks._new_day_due,
            game_time.day(MIDNIGHT),
            lambda: state(MIDNIGHT, MIDNIGHT - 5, yesterday),
            lambda: state(MIDNIGHT, MIDNIGHT, yesterday),
        )

    def test_world_and_character_events_wait_for_the_clock(self) -> None:
        """Tick 没结算时，OrphanClass、ArtsBreak、BecomeTired、TargetLeft、PlayerSpent 都不触发"""
        kernel_data.set_world(modes.set_sex_class, True)
        kernel_data.set_needs(self.npc.cid, hit=1)
        self.arts_due = True
        self.enterContext(
            mock.patch.object(
                character_behavior, "target_left", lambda cid, game: True
            )
        )
        cases: tuple[tuple[Trigger, object], ...] = (
            (time_hooks._orphan_class_due, True),
            (time_hooks._arts_break_due, True),
            (events._become_tired_when, "1"),
            (actions._target_left_when, "1"),
        )
        for trigger, data in cases:
            with self.subTest(trigger.__name__):
                self.assert_waits(trigger, data, tick_due, settled)
        self.arts_due = False
        kernel_data.set_needs(self.player.cid, hit=1)
        self.assert_waits(events._player_spent_when, "0", tick_due, settled)

    def test_player_ends_wait_for_arts_break(self) -> None:
        """ArtsBreak 成立时，PlayerSpent、HEnd、GroupExit 都不触发"""

        def arts(due: bool) -> core.GameState:
            self.arts_due = due
            return settled()

        kernel_data.put(flags.set, self.npc.cid, tired=True)
        cases: tuple[tuple[Trigger, object, Callable[[], None]], ...] = (
            (events._player_spent_when, "0", self.spend_player),
            (events._h_end_when, "1", lambda: None),
            (events._group_exit_when, "1", self.group_sex),
        )
        for trigger, data, scene in cases:
            with self.subTest(trigger.__name__):
                self.setUp_scene(scene)
                self.assert_waits(
                    trigger, data, lambda: arts(True), lambda: arts(False)
                )

    def test_npc_h_ends_wait_for_player_spent(self) -> None:
        """玩家力竭时，HEnd、GroupExit、HLeftBehind 都不触发"""

        def spent(hit_point: int) -> core.GameState:
            kernel_data.set_needs(self.player.cid, hit=hit_point)
            return settled()

        self.enterContext(
            mock.patch.object(
                handle_premise, "handle_not_in_player_scene", lambda cid: 1
            )
        )
        cases: tuple[tuple[Trigger, object, Callable[[], None]], ...] = (
            (events._h_end_when, "1", self.tire_npc),
            (events._group_exit_when, "1", self.group_sex),
            (events._h_left_behind_when, "1", self.rest_npc),
        )
        for trigger, data, scene in cases:
            with self.subTest(trigger.__name__):
                self.setUp_scene(scene)
                self.assert_waits(
                    trigger, data, lambda: spent(1), lambda: spent(100)
                )

    def test_stop_following_waits_for_become_tired(self) -> None:
        """跟随中的干员体力到 1 而疲劳标记还没设：StopFollowing 不触发；设上之后交回他"""
        kernel_data.put(flags.set, self.npc.cid, is_h=False)
        kernel_data.put(flags.set, self.npc.cid, is_follow=1)
        kernel_data.set_needs(self.npc.cid, hit=1)
        self.enterContext(
            mock.patch.object(attr_calculation, "get_tired_level", lambda v: 2)
        )

        def tired(flag: bool) -> core.GameState:
            kernel_data.put(flags.set, self.npc.cid, tired=flag)
            return settled()

        self.assertEqual(events._become_tired_when(tired(False)), "1")
        self.assert_waits(
            events._stop_following_when,
            "1",
            lambda: tired(False),
            lambda: tired(True),
        )

    def test_triggers_read_hit_from_their_state(self) -> None:
        """
        BecomeTired 与 PlayerSpent 从交给触发函数的 GameState 读体力：状态里体力为 1 时触发，
        同一步里还没套用的写入把体力改成 100 也一样触发。状态里干员体力为 100 时 BecomeTired 不触发
        """
        kernel_data.put(flags.set, self.npc.cid, is_h=False)
        kernel_data.set_needs(self.npc.cid, hit=1)
        kernel_data.set_needs(self.player.cid, hit=1)
        spent = settled()
        kernel_data.put(flags.set, self.npc.cid, is_h=True)
        spent_h = settled()
        kernel_data.put(flags.set, self.npc.cid, is_h=False)
        with working.based_on(core.state()):
            needs.set(1, hit=100)
            needs.set(0, hit=100)
            self.assertEqual(events._become_tired_when(spent), "1")
            self.assertEqual(events._player_spent_when(spent_h), "0")
        kernel_data.set_needs(self.npc.cid, hit=100)
        self.assertIsNone(events._become_tired_when(settled()))

    def test_h_left_behind_waits_for_the_tired_end(self) -> None:
        """被留在 H 里的干员疲劳（tired_case 为 h）：HLeftBehind 不触发；不疲劳时交回他"""
        self.enterContext(
            mock.patch.object(
                handle_premise, "handle_not_in_player_scene", lambda cid: 1
            )
        )

        def tired(flag: bool) -> core.GameState:
            kernel_data.put(flags.set, self.npc.cid, tired=flag)
            return settled()

        self.assertEqual(events._h_end_when(tired(True)), "1")
        self.assert_waits(
            events._h_left_behind_when,
            "1",
            lambda: tired(True),
            lambda: tired(False),
        )

    def setUp_scene(self, scene: Callable[[], None]) -> None:
        """
        每个子用例从同一现场开始：玩家体力满、干员在 H 中且疲劳、不在群交，再跑 scene
        Keyword arguments:
        scene -- 改现场的函数
        """
        kernel_data.set_needs(self.player.cid, hit=100)
        kernel_data.put(flags.set, self.npc.cid, is_h=True)
        kernel_data.put(flags.set, self.npc.cid, tired=True)
        kernel_data.set_world(modes.set_group_sex, False)
        self.arts_due = False
        scene()

    def spend_player(self) -> None:
        """玩家体力到 1，交互对象还在 H 中"""
        kernel_data.set_needs(self.player.cid, hit=1)

    def tire_npc(self) -> None:
        """干员疲劳"""
        kernel_data.put(flags.set, self.npc.cid, tired=True)

    def rest_npc(self) -> None:
        """干员不疲劳"""
        kernel_data.put(flags.set, self.npc.cid, tired=False)

    def group_sex(self) -> None:
        """群交中"""
        kernel_data.set_world(modes.set_group_sex, True)
