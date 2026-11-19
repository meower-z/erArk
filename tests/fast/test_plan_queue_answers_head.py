# -*- coding: UTF-8 -*-
"""
计划队列：角色下一次选行动时先答出队首，给别人排的行动打断他
============================================================
博士与一名干员在同一场景。开始前给干员排一个 60 分钟的睡觉，给博士排一个 7 分钟的休息；
博士再点下「等待」（5 分钟）。等待开始时（结算途中）给干员排一个 5 分钟的等待并要求打断他。
每个角色的结算与状态结算换成只记录的替身，只看内核与计划队列：
- 博士先做排给他的休息，再做界面定下的等待；
- 干员先开始睡觉；等待排上后他被打断，在博士的等待开始的同一分钟就开始排给他的等待，
  开始时缓存里换上了这个行为，行为的开始时间是内核里行动开始的那一分钟（不是缓存里玩家行动的结束）；
- 排上的行动都用掉了，队列里不再有它们。
"""

from unittest import mock

from Script.Core import constant
from Script.Design import character_behavior, handle_npc_ai
from Script.Kernel import core
from Script.Modules.gameplay_resolution import actions, plan_queue
from Script.System.Instruct_System import handle_instruct
from tests.fast.base import FastTestCase
from tests.world import play

NPC = 1
""" 被打断的干员 """


class PlanQueueAnswersHeadTest(FastTestCase):
    """队首在角色下一次选行动时开始；给别人排的行动经 Interrupt 马上开始"""

    def test_head_starts_at_next_pick(self) -> None:
        """博士先做排给他的行动；干员被打断后马上开始排给他的行动"""
        self.world.chara(0, "博士")
        self.world.chara(NPC, "干员")
        player = self.cache.character_data[0]
        plan_queue.plan_next(NPC, constant.Behavior.SLEEP, 60)
        plan_queue.plan_next(0, constant.Behavior.REST, 7)
        player_starts: list[tuple[str, int, int]] = []
        npc_starts: list[tuple[str, int, int]] = []

        def loop() -> None:
            """
            博士行动开始时结算的替身：记下博士开始的行为；他的等待开始时给干员排一个等待并打断他
            Keyword arguments:
            无
            Return arguments:
            无
            """
            behavior = player.behavior
            player_starts.append(
                (behavior.behavior_id, core.state().clock, behavior.duration)
            )
            if behavior.behavior_id == constant.Behavior.WAIT:
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
            if character_id == 0:
                loop()
                return 1
            behavior = self.cache.character_data[character_id].behavior
            if behavior.behavior_id == constant.Behavior.SHARE_BLANKLY:
                return 1
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
                character_behavior, "judge_character_status", settle
            ),
            mock.patch.object(
                handle_npc_ai, "choose_state_machine", return_value=None
            ),
        ):
            play(
                lambda: handle_instruct.handle_instruct(constant.Instruct.WAIT)
            )
        start = player_starts[0][1]
        self.assertEqual(
            player_starts,
            [
                (constant.Behavior.REST, start, 7),
                (constant.Behavior.WAIT, start + 7, 5),
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
        self.assertEqual(plan_queue.planned(0), [])
        self.assertEqual(plan_queue.planned(NPC), [])
