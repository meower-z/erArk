# -*- coding: UTF-8 -*-
"""
行动结束时留住移动的去向
========================
- 带人移动（CARRY_MOVE）结束时，新的空行为保留最终目标，和移动（MOVE）一样，寻路的下一段才接得上。
- 博士的寻路还没走第一段、而计划队列里已排着博士的移动或带人移动（事件排下的）：另一个行动结束时不清掉寻路。
"""

from Script.Core import constant
from Script.Design import character_behavior, character_move
from Script.Kernel import core
from Script.Modules.domains import plan
from Script.Modules.gameplay_resolution import plan_queue, working
from tests.fast.base import FastTestCase

START = ["宿舍", "1区", "101"]
""" 博士出发的地点 """
TARGET = ["中枢", "博士办公室"]
""" 寻路的目标 """


class RouteKeptAfterActionEndTest(FastTestCase):
    """行动结束时的移动去向"""

    def setUp(self) -> None:
        """博士在宿舍；写入记在以当前状态为底的缓冲区里"""
        super().setUp()
        self.player = self.world.chara(0, "博士", position=START)
        self.enterContext(working.based_on(core.state()))

    def test_carry_move_keeps_final_target(self) -> None:
        """带人移动结束：新的空行为的最终目标仍是 TARGET"""
        self.player.behavior.behavior_id = constant.Behavior.CARRY_MOVE
        self.player.behavior.move_final_target = TARGET
        character_behavior.end_action(0)
        self.assertEqual(self.player.behavior.move_final_target, TARGET)

    def test_queued_first_leg_keeps_route(self) -> None:
        """寻路的第一段还在队列里：等待结束时寻路还在"""
        plan.set_route([TARGET, START])
        self.player.behavior.behavior_id = constant.Behavior.WAIT
        plan_queue.plan_next(0, constant.Behavior.MOVE, 1)
        character_move.continue_player_route()
        self.assertEqual(plan.route(), [TARGET, START])

    def test_queued_first_carry_leg_keeps_route(self) -> None:
        """寻路的第一段是带人移动、还在队列里：等待结束时寻路还在"""
        plan.set_route([TARGET, START])
        self.player.behavior.behavior_id = constant.Behavior.WAIT
        plan_queue.plan_next(0, constant.Behavior.CARRY_MOVE, 1)
        character_move.continue_player_route()
        self.assertEqual(plan.route(), [TARGET, START])
