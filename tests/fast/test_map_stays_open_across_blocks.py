# -*- coding: UTF-8 -*-
"""
从大地图移动到另一个区块：移动开始后地图面板仍打开
==================================================
博士在宿舍，在地图面板里点中枢区块（中枢的 0 号场景）。每个角色的结算换成替身：博士当前的移动行为把他移到这一段的终点。
寻路走完后，玩家的面板仍是地图面板（面板按玩家的新位置显示下级地图）；同一区块内的移动走完后回到主界面。
"""

from unittest import mock

from Script.Core import constant
from Script.Design import character_behavior, map_handle
from Script.UI.Panel import see_map_panel
from tests.fast.base import FastTestCase
from tests.world import play
from Script.UI.Moudle import view

START = ["宿舍", "1区", "101"]
""" 博士出发的地点 """
BLOCK = ["中枢", "0"]
""" 另一个区块的 0 号场景 """
SAME_BLOCK = ["宿舍", "1区", "102"]
""" 同一区块里的另一个地点 """


class MapStaysOpenAcrossBlocksTest(FastTestCase):
    """跨区块移动后地图面板仍打开"""

    def setUp(self) -> None:
        """
        博士在宿舍
        Keyword arguments:
        无
        Return arguments:
        无
        """
        super().setUp()
        self.world.scene(BLOCK)
        self.world.scene(SAME_BLOCK)
        self.player = self.world.chara(0, "博士", position=START)

    def move(self, scene_path: list[str]) -> None:
        """
        在地图面板里点 scene_path，推进到寻路结束
        Keyword arguments:
        scene_path -- 目标场景
        Return arguments:
        无
        """

        def settle(character_id: int) -> int:
            """
            状态结算的替身：博士在移动时走到这一段的终点
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
                map_handle.character_move_scene(
                    self.player.position, behavior.move_target, 0
                )
            return 1

        panel = see_map_panel.SeeMapPanel.__new__(see_map_panel.SeeMapPanel)
        view.now_panel_id = constant.Panel.SEE_MAP
        with mock.patch.object(
            character_behavior, "judge_character_status", settle
        ):
            play(lambda: panel.move_now(list(scene_path)))

    def test_map_open_after_moving_to_another_block(self) -> None:
        """移动到另一个区块后仍是地图面板"""
        self.move(BLOCK)
        self.assertEqual(self.player.position, BLOCK)
        self.assertEqual(view.now_panel_id, constant.Panel.SEE_MAP)

    def test_main_panel_after_moving_in_the_same_block(self) -> None:
        """同一区块里移动后回到主界面"""
        self.move(SAME_BLOCK)
        self.assertEqual(self.player.position, SAME_BLOCK)
        self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)
