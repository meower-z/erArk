# -*- coding: UTF-8 -*-
"""
计划队列：角色下一次选行动时先答出队首，给别人排的行动打断他
============================================================
博士与一名干员在同一场景。开始前给干员排一个 60 分钟的睡觉，给博士排一个 7 分钟的休息；
博士再下一个 10 分钟的等待。等待开始时（结算途中）给干员排一个 5 分钟的等待并要求打断他。
每个角色的结算与状态结算换成只记录的替身，只看内核与计划队列：
- 博士先做排给他的休息，再做界面定下的等待；
- 干员先开始睡觉；等待排上后他被打断，在博士的等待开始的同一分钟就开始排给他的等待，
  开始时缓存里换上了这个行为，行为的开始时间是内核里行动开始的那一分钟（不是缓存里玩家行动的结束）；
- 排上的行动都用掉了，队列里不再有它们。
内核在跑时给博士排行动并要求打断：不打断他（交回 None）；给干员这样排则交回打断他的 Interrupt。
"""

from collections.abc import Callable
from types import MappingProxyType
from unittest import mock

from Script.Core import constant
from Script.Design import update
from Script.Design import character_behavior
from Script.Kernel import core
from Script.Modules.gameplay_resolution import actions, plan_queue
from Script.Modules.tk_ui import player_hook
from tests.fast.base import FastTestCase

NPC = 1
""" 被打断的干员 """


def passes(player_pass: "Callable[[], None]") -> "Callable[..., None]":
    """
    角色结算一次的替身：博士的跑 player_pass，每个角色都记为本回合结算完
    Keyword arguments:
    player_pass -- 博士结算时跑的函数
    Return arguments:
    Callable -- 替身，参数同 character_behavior.character_behavior
    """
    from Script.Core import cache_control

    def settle_pass(character_id: int, *args: object) -> None:
        """
        结算一次：博士的跑 player_pass，再记为本回合结算完
        Keyword arguments:
        character_id -- 角色id
        args -- 时间参数，不使用
        """
        if character_id == 0:
            player_pass()
        cache_control.cache.over_behavior_character.add(character_id)

    return settle_pass


class PlanQueueAnswersHeadTest(FastTestCase):
    """队首在角色下一次选行动时开始；给别人排的行动经 Interrupt 马上开始"""

    def test_head_starts_at_next_pick(self) -> None:
        """博士先做排给他的行动；干员被打断后马上开始排给他的行动"""
        self.world.chara(0, "博士")
        self.world.chara(NPC, "干员")
        player = self.cache.character_data[0]
        player.behavior.behavior_id = constant.Behavior.WAIT
        player.behavior.duration = 10
        player.behavior.start_time = self.cache.game_time
        plan_queue.plan_next(NPC, constant.Behavior.SLEEP, 60)
        plan_queue.plan_next(0, constant.Behavior.REST, 7)
        wait = player.behavior
        player_starts: list[tuple[str, int, int]] = []
        npc_starts: list[tuple[str, int, int]] = []

        def loop() -> None:
            """
            博士结算一次的替身：记下博士开始的行为；他的等待开始时给干员排一个等待并打断他
            Keyword arguments:
            无
            Return arguments:
            无
            """
            behavior = player.behavior
            player_starts.append(
                (behavior.behavior_id, core.state().clock, behavior.duration)
            )
            if behavior is wait:
                plan_queue.plan_next(
                    NPC, constant.Behavior.WAIT, 5, interrupt=True
                )

        def settle(character_id: int) -> int:
            """
            状态结算的替身：记下干员开始的行为、内核时钟与缓存里行为开始的分钟
            Keyword arguments:
            character_id -- 角色id
            Return arguments:
            int -- 1
            """
            behavior = self.cache.character_data[character_id].behavior
            npc_starts.append(
                (
                    behavior.behavior_id,
                    core.state().clock,
                    actions.minutes(behavior.start_time),
                )
            )
            return 1

        with (
            mock.patch.object(
                character_behavior, "character_behavior", passes(loop)
            ),
            mock.patch.object(
                character_behavior, "judge_character_status", settle
            ),
        ):
            update.game_update_flow(10)
        start = player_starts[0][1]
        self.assertEqual(
            player_starts,
            [
                (constant.Behavior.REST, start, 7),
                (constant.Behavior.WAIT, start + 7, 10),
            ],
            "博士先做排给他的休息，再做界面定下的等待",
        )
        self.assertEqual(
            npc_starts,
            [
                (constant.Behavior.SLEEP, start, start),
                (constant.Behavior.WAIT, start + 7, start + 7),
            ],
            "干员被打断，在博士的等待开始的同一分钟开始排给他的等待",
        )
        self.assertEqual(plan_queue.planned(0), ())
        self.assertEqual(plan_queue.planned(NPC), ())

    def test_player_is_never_interrupted(self) -> None:
        """内核在跑时要求打断：博士不被打断，干员被打断"""
        characters = {}
        for cid, name in ((0, "博士"), (NPC, "干员")):
            self.world.chara(cid, name)
            behavior = self.cache.character_data[cid].behavior
            act = core.Action(
                str(cid), actions.behave.name, actions.mirror(behavior), 0, 10
            )
            characters[str(cid)] = core.Character(act, MappingProxyType({}))
        game = core.GameState(
            0, MappingProxyType(characters), MappingProxyType({})
        )
        self.addCleanup(plan_queue._pending.clear)
        with (
            mock.patch.object(player_hook, "running", return_value=True),
            mock.patch.object(core, "state", return_value=game),
        ):
            to_player = plan_queue.plan_next(
                0, constant.Behavior.WAIT, 5, interrupt=True
            )
            to_npc = plan_queue.plan_next(
                NPC, constant.Behavior.WAIT, 5, interrupt=True
            )
        self.assertIsNone(to_player, "博士不被打断")
        self.assertEqual(to_npc, core.Interrupt(str(NPC)), "干员被打断")
