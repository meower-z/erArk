# -*- coding: UTF-8 -*-
"""
博士寻路：每次选行动走一段，走到为止
====================================
博士在宿舍，寻路去博士办公室。每个角色的结算换成替身：博士当前的移动行为把他移到这一段的终点，
再像行动结束时那样复原行为（移动保留最终目标）。
- 第一段由寻路当场定下，之后每一段在博士下一次选行动时由计划队列排上，不问界面；博士走到博士办公室为止，
  每一段走到新的地点，结束后博士没有交互对象；
- 某一段没让博士走动时寻路结束，只走了这一段。
"""

from unittest import mock

from Script.Core import constant
from Script.Design import character_behavior, character_move, map_handle
from Script.Kernel import core
from tests.fast.base import FastTestCase
from tests.world import play

START = ["宿舍", "1区", "101"]
""" 博士出发的地点 """
TARGET = ["中枢", "博士办公室"]
""" 寻路的目标 """
MAX_LEGS = 30
""" 段数的上限 """


class PlayerRouteOneLegPerPickTest(FastTestCase):
    """寻路的每一段在博士下一次选行动时排上"""

    def setUp(self) -> None:
        """
        博士在宿舍，有一名交互对象
        Keyword arguments:
        无
        Return arguments:
        无
        """
        super().setUp()
        self.world.scene(TARGET)
        self.player = self.world.chara(0, "博士", position=START)
        self.world.chara(1, "交互对象", position=START)
        self.player.target_character_id = 1
        self.legs: list[list[str]] = []

    def run_route(self, moves: bool) -> None:
        """
        博士寻路去 TARGET
        Keyword arguments:
        moves -- 替身是否让博士走到这一段的终点
        Return arguments:
        无
        """

        def loop() -> None:
            """
            博士行动开始时结算的替身：记下这一段，按 moves 移动博士；行为在行动结束时（actions.wrap_up）收掉
            Keyword arguments:
            无
            Return arguments:
            无
            """
            behavior = self.player.behavior
            if behavior.behavior_id != constant.Behavior.MOVE:
                return
            self.legs.append(list(behavior.move_target))
            if moves:
                map_handle.character_move_scene(
                    self.player.position, behavior.move_target, 0
                )

        def settle(character_id: int) -> int:
            """
            状态结算的替身：博士的跑 loop，干员的不结算
            Keyword arguments:
            character_id -- 角色id
            Return arguments:
            int -- 1
            """
            if character_id == 0:
                loop()
            return 1

        with mock.patch.object(
            character_behavior, "judge_character_status", settle
        ):
            play(lambda: character_move.own_charcter_move(list(TARGET)))
        self.assertFalse(core.in_settlement(), "寻路结束后内核停在博士的选择")

    def test_walks_to_target(self) -> None:
        """每次选行动走一段，走到博士办公室为止"""
        self.run_route(moves=True)
        self.assertEqual(self.player.position, TARGET, "博士走到了博士办公室")
        self.assertEqual(self.legs[-1], TARGET, "最后一段的终点是博士办公室")
        self.assertGreater(len(self.legs), 1, "寻路走了不止一段")
        self.assertLessEqual(len(self.legs), MAX_LEGS)
        self.assertEqual(
            len({tuple(leg) for leg in self.legs}),
            len(self.legs),
            "每一段走到新的地点",
        )
        self.assertEqual(self.player.target_character_id, 0)

    def test_stops_when_a_leg_does_not_move(self) -> None:
        """某一段没让博士走动时寻路结束"""
        self.run_route(moves=False)
        self.assertEqual(len(self.legs), 1, "只走了第一段")
        self.assertEqual(self.player.position, START)
