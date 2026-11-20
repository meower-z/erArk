# -*- coding: UTF-8 -*-
"""
玩家的行动收尾后重定交互对象
============================
玩家的行动结束时（character_behavior.player_after_end）：
- 交互对象已不在玩家所在的场景：换成场景里的第一个角色；
- 刚移动过来、交互对象是自己：换成场景里的第一个角色；
- 场景里没有别的角色：交互对象是自己。
"""

from Script.Core import constant
from Script.Design import character_behavior, update
from Script.Kernel import core
from tests import kernel_data
from tests.fast.base import FastTestCase

LOADED_FIRST = update
""" 先于 Script.Modules 导入的 update：Script.Modules 的包初始化要在 update 导入途中进行 """
ELSEWHERE = ["中枢", "走廊"]
""" 别的场景 """
GONE = 1
""" 已离开玩家所在场景的干员 """
HERE = 2
""" 和玩家在同一场景的干员 """


class PlayerTargetAfterActionTest(FastTestCase):
    """玩家行动收尾后的交互对象"""

    def setUp(self) -> None:
        """玩家在默认场景；干员1在别处"""
        super().setUp()
        self.player = self.world.chara(0, "博士")
        self.world.chara(GONE, "离开的干员", position=ELSEWHERE)
        core.reset_state(kernel_data.reprojected(core.state()))

    def test_target_who_left_is_replaced(self) -> None:
        """交互对象（干员1）已离开：换成场景里的干员2"""
        self.world.chara(HERE, "在场的干员")
        self.player.target_character_id = GONE
        character_behavior.player_after_end()
        self.assertEqual(self.player.target_character_id, HERE)

    def test_after_move_targets_first_in_scene(self) -> None:
        """刚移动过来，交互对象是自己：换成场景里的干员2"""
        self.world.chara(HERE, "在场的干员")
        self.player.target_character_id = 0
        self.cache.pl_pre_behavior_instruce.append(constant.Behavior.MOVE)
        character_behavior.player_after_end()
        self.assertEqual(self.player.target_character_id, HERE)

    def test_empty_scene_targets_self(self) -> None:
        """场景里没有别的角色：交互对象是自己"""
        self.player.target_character_id = GONE
        character_behavior.player_after_end()
        self.assertEqual(self.player.target_character_id, 0)
