# -*- coding: UTF-8 -*-
"""
已不在场的干员从内核的 GameState 里移除
======================================
GameState 由缓存投影出来（actions.state_from_cache，同读档、开新游戏）时有玩家、干员1、干员2；
之后干员2从 cache.npc_id_got 里删掉（例如被删掉的角色）。
每一步套用效果前的 plan_queue.roster_changes 交回移除它的 RemoveCharacter，
套用之后 GameState 只剩玩家与干员1，下次扫描事件不再读到它。
"""

from Script.Kernel import core
from Script.Modules.domains import roster
from Script.Modules.gameplay_resolution import actions, plan_queue
from tests import kernel_data
from tests.fast.base import FastTestCase


class RosterDropsRemovedTest(FastTestCase):
    """roster_changes 移除已不在场的干员"""

    def test_removed_character_leaves_game_state(self) -> None:
        """
        GameState 里有玩家、干员1、干员2，在场的只剩干员1：roster_changes 只交回移除干员2的 RemoveCharacter，
        套用后只剩 0 与 1
        Keyword arguments:
        无
        Return arguments:
        无
        """
        self.assertFalse(core.in_settlement(), "内核不在结算里")
        for cid, name in ((0, "博士"), (1, "阿米娅"), (2, "凯尔希")):
            self.world.chara(cid, name)
        kernel_data.put(roster.set_active, {1, 2})
        game = actions.state_from_cache()
        self.assertEqual(sorted(game.characters), ["0", "1", "2"])
        core.reset_state(game)
        kernel_data.put(roster.set_active, {1})
        effects = plan_queue.roster_changes()
        self.assertEqual(effects, (core.RemoveCharacter("2"),))
        after = core.preview(game, effects)
        self.assertEqual(sorted(after.characters), ["0", "1"])
