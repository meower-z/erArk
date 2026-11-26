# -*- coding: UTF-8 -*-
"""
博士寻路途中不换交互对象，走到目标才重定
========================================
博士在宿舍，交互对象在身边，寻路去博士办公室；第一段走到的地点有另一名干员。
每个角色的结算换成替身：博士当前的移动行为把他移到这一段的终点，第一段还把那名干员带到同一个地点。
- 之后每一段开始时，博士的交互对象仍是出发时的那一个；
- 走到博士办公室（那里没有别人）后，博士没有交互对象。
"""

from unittest import mock

from Script.Core import constant
from Script.Design import character_behavior, map_handle
from Script.UI.Panel import see_map_panel
from tests.fast.base import FastTestCase
from tests.world import play
from tests.chara_activity import aim
from Script.Modules.domains import activity

START = ["宿舍", "1区", "101"]
""" 博士出发的地点 """
TARGET = ["中枢", "博士办公室"]
""" 寻路的目标 """


class RouteTargetBetweenLegsTest(FastTestCase):
    """寻路途中的交互对象"""

    def setUp(self) -> None:
        """博士与交互对象在宿舍，另一名干员也在宿舍，第一段时被带到第一段的终点"""
        super().setUp()
        self.world.scene(TARGET)
        self.player = self.world.chara(0, "博士", position=START)
        self.world.chara(1, "交互对象", position=START)
        self.passer = self.world.chara(2, "路人", position=START)
        aim(self.player.cid, 1)
        self.targets: list[int] = []

    def test_target_kept_until_arrival(self) -> None:
        """每一段开始时交互对象不变，到达后没有交互对象"""

        def settle(character_id: int) -> int:
            """
            状态结算的替身：博士的移动记下交互对象并走到这一段的终点，干员的不结算
            Keyword arguments:
            character_id -- 角色id
            Return arguments:
            int -- 1
            """
            behavior = activity.behavior(self.player.cid)
            if character_id or behavior.behavior_id != constant.Behavior.MOVE:
                return 1
            self.targets.append(activity.target(self.player.cid))
            if len(self.targets) == 1:
                map_handle.character_move_scene(
                    activity.position(self.passer.cid), behavior.move_target, 2
                )
            map_handle.character_move_scene(
                activity.position(self.player.cid), behavior.move_target, 0
            )
            return 1

        with mock.patch.object(
            character_behavior, "judge_character_status", settle
        ):
            play(lambda: see_map_panel.pick_route(list(TARGET)))
        self.assertEqual(activity.position(self.player.cid), TARGET)
        self.assertGreater(len(self.targets), 2, "寻路走了不止两段")
        self.assertEqual(self.targets, [1] * len(self.targets))
        self.assertEqual(activity.target(self.player.cid), 0)
