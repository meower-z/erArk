# -*- coding: UTF-8 -*-
"""
回标题再开新游戏时，上一局排着的行动与玩家的路线不带进新的一局
================================================================
开局后给一名角色排一个行动、给玩家留一条路线，再从标题画面开一局新游戏：计划队列为空，玩家没有路线。
"""

import importlib

from tests import kernel_data
from tests.slow.base import SlowTestCase


class NewGameClearsPlansTest(SlowTestCase):
    """新游戏清掉上一局的计划队列与玩家路线"""

    def test_new_game_clears_plans(self) -> None:
        """上一局的计划队列与路线在新游戏里都不在"""
        plan = importlib.import_module("Script.Modules.domains.plan")
        kernel_data.set_world(
            plan.set_queue, 1, [("plan", {"behavior_id": "wait"})]
        )
        kernel_data.set_world(plan.set_route, (["中枢", "会议室"], []))
        self.world.new_game()
        self.assertEqual(plan.queues(), {}, "计划队列")
        self.assertIsNone(plan.route(), "玩家路线")
