# -*- coding: UTF-8 -*-
"""
博士前往干员位置：到达时她是交互对象，她走开了就跟过去
====================================================
博士在宿舍，在干员位置面板里点「前往」干员2。干员2与排在她前面的干员1都在博士办公室。
每个角色的结算换成替身：博士当前的移动行为把他移到这一段的终点。
- 到达博士办公室时，博士的交互对象是干员2，不是场景里排在前面的干员1；
- 博士走完第一段后干员2去了会议室：博士接着走到会议室，交互对象是干员2。
"""

from unittest import mock

from Script.Core import constant
from Script.Design import character_behavior, map_handle
from Script.UI.Panel import all_npc_position_panel
from tests.fast.base import FastTestCase
from tests.world import play

START = ["宿舍", "1区", "101"]
""" 博士出发的地点 """
TARGET = ["中枢", "博士办公室"]
""" 干员2起初所在的地点 """
MOVED = ["中枢", "会议室"]
""" 干员2走去的地点 """
GO_TO_OPERATOR = 2
""" 干员位置面板的移动类型：博士前往干员位置 """


class GoToOperatorTest(FastTestCase):
    """前往干员位置：到达时交互对象是她，她走开了就跟过去"""

    def setUp(self) -> None:
        """
        博士在宿舍；干员1与干员2都在博士办公室
        Keyword arguments:
        无
        Return arguments:
        无
        """
        super().setUp()
        self.world.scene(TARGET)
        self.world.scene(MOVED)
        self.player = self.world.chara(0, "博士", position=START)
        self.world.chara(1, "干员1", position=TARGET)
        self.operator = self.world.chara(2, "干员2", position=TARGET)

    def go(self, move_after_first_leg: bool) -> None:
        """
        点「前往」干员2，推进到寻路结束
        Keyword arguments:
        move_after_first_leg -- 博士走完第一段后，干员2是否去了会议室
        Return arguments:
        无
        """
        legs: list[list[str]] = []

        def settle(character_id: int) -> int:
            """
            状态结算的替身：博士在移动时走到这一段的终点；干员不结算
            Keyword arguments:
            character_id -- 角色id
            Return arguments:
            int -- 1
            """
            behavior = self.player.behavior
            if (
                character_id == 0
                and behavior.behavior_id == constant.Behavior.MOVE
            ):
                legs.append(list(behavior.move_target))
                map_handle.character_move_scene(
                    self.player.position, behavior.move_target, 0
                )
                if move_after_first_leg and len(legs) == 1:
                    map_handle.character_move_scene(
                        self.operator.position, MOVED, 2
                    )
            return 1

        button = all_npc_position_panel.MoveSonPanel.__new__(
            all_npc_position_panel.MoveSonPanel
        )
        button.chara_id = 2
        button.move_type = GO_TO_OPERATOR
        with mock.patch.object(
            character_behavior, "judge_character_status", settle
        ):
            play(lambda: button.move(2))

    def test_operator_is_target_on_arrival(self) -> None:
        """到达时交互对象是干员2"""
        self.go(move_after_first_leg=False)
        self.assertEqual(self.player.position, TARGET)
        self.assertEqual(self.player.target_character_id, 2)

    def test_follows_a_moving_operator(self) -> None:
        """干员2走开了，博士跟到会议室，交互对象是她"""
        self.go(move_after_first_leg=True)
        self.assertEqual(self.player.position, MOVED)
        self.assertEqual(self.player.target_character_id, 2)
