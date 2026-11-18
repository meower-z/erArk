# -*- coding: UTF-8 -*-
"""
已不在场的干员从内核的 GameState 里移除
======================================
干员2已从 cache.npc_id_got 里删掉（例如被删掉的角色），GameState 里还有它：
测试先导入 update 再导入 Script.Modules，和游戏的导入顺序一样。
结算之后的 resync 交回移除它的 Change，套用之后 GameState 只剩玩家与干员1，下次扫描事件不再读到它。
"""

from types import MappingProxyType

from Script.Design import update
from Script.Kernel import core
from Script.Modules.gameplay_resolution import actions
from tests.fast.base import FastTestCase


class RosterDropsRemovedTest(FastTestCase):
    """resync 移除已不在场的干员"""

    def test_removed_character_leaves_game_state(self) -> None:
        """
        GameState 里有玩家、干员1、干员2，在场的只有干员1：resync 交回移除干员2的 Change，套用后只剩 0 与 1
        Keyword arguments:
        无
        Return arguments:
        无
        """
        self.assertFalse(update.in_resolution(), "内核没在跑")
        for cid, name in ((0, "博士"), (1, "阿米娅"), (2, "凯尔希")):
            self.world.chara(cid, name)
        self.cache.npc_id_got = {0, 1}
        characters = {}
        for who in ("0", "1", "2"):
            behavior = self.cache.character_data[int(who)].behavior
            act = core.Action(
                who, actions.behave.name, actions.mirror(behavior), 0, 0
            )
            characters[who] = core.Character(act, MappingProxyType({}))
        game = core.GameState(
            0, MappingProxyType(characters), MappingProxyType({})
        )
        effects = actions.resync(game)
        self.assertIn(core.Change(None, "roster", "remove", ("2",)), effects)
        after = core.preview(game, effects)
        self.assertEqual(tuple(after.characters), ("0", "1"))
