# -*- coding: UTF-8 -*-
"""
跟随博士的干员进入满员房间的回归测试（判定部分）
==============================================
房间满员（Room_Area 0 满 10 人）时，智能跟随或强制跟随的干员能进博士所在的房间、或博士正迈进的房间；
被召集（is_follow 3、4）、不在跟随、或房间不是博士所在 / 正要进入的房间时，满员挡在门外；跟随的非助理干员进不了博士房间（私密场所）。
断言都落在 map_handle.judge_scene_accessible 的返回值上。
跟着博士走进门的过程在 tests/slow/test_follower_enters_full_room.py。
"""

from Script.Config import game_config
from Script.Core import constant
from Script.Design import map_handle
from tests.fast.base import FastTestCase

ROOM = ["医疗", "体检科"]
DOOR = ["医疗", "内走廊"]
DR_ROOM = ["中枢", "博士房间"]


class FollowerEntersFullRoomTest(FastTestCase):
  """judge_scene_accessible 对满员房间的判定"""

  def setUp(self) -> None:
    """
    博士、跟随者（id 1）与路人（id 2）在门口，体检科里已有 10 人；体检科按设施已开放处理
    Keyword arguments:
    无
    Return arguments:
    无
    """
    super().setUp()
    room_name = self.world.scene(ROOM).scene_name
    self.cache.rhodes_island.facility_open[
        game_config.config_facility_open_name_to_cid[room_name]
    ] = 1
    self.pl = self.world.chara(0, "博士", position=DOOR)
    self.follower = self.world.chara(1, "跟随者", position=DOOR)
    self.world.chara(2, "路人", position=DOOR)
    for cid in range(10, 20):
      self.world.chara(cid, f"占位{cid}", position=ROOM)
    self.assertTrue(
        map_handle.judge_scene_is_full(
            map_handle.get_map_system_path_str_for_list(ROOM)
        )
    )

  def access(self, path: list, cid: int) -> str:
    """
    角色对房间的进门判定
    Keyword arguments:
    path -- 房间的场景路径
    cid -- 角色id
    Return arguments:
    str -- judge_scene_accessible 的返回值
    """
    return map_handle.judge_scene_accessible(
        map_handle.get_map_system_path_str_for_list(path), cid
    )

  def test_follower_steps_in_with_doctor(self) -> None:
    """博士正从门口迈进满员的体检科：智能跟随的干员能进，没在跟随的干员进不了"""
    behavior = self.pl.behavior
    behavior.behavior_id = constant.Behavior.MOVE
    behavior.move_target = ROOM
    behavior.move_final_target = ROOM
    behavior.duration = 1
    self.follower.sp_flag.is_follow = 1
    self.assertEqual(self.access(ROOM, 1), "open")
    self.assertEqual(self.access(ROOM, 2), "full")

  def test_follower_enters_room_with_doctor(self) -> None:
    """博士已在满员的体检科里：跟随（1、2）的干员能进，被召集（3、4）的干员进不了"""
    self.world.move(0, ROOM)
    for is_follow, expected in (
        (1, "open"),
        (2, "open"),
        (3, "full"),
        (4, "full"),
    ):
      with self.subTest(is_follow=is_follow):
        self.follower.sp_flag.is_follow = is_follow
        self.assertEqual(self.access(ROOM, 1), expected)

  def test_follower_blocked_when_doctor_elsewhere(self) -> None:
    """博士在门口站着、不进体检科时，跟随中的干员被满员挡在门外"""
    self.follower.sp_flag.is_follow = 1
    self.assertEqual(self.access(ROOM, 1), "full")

  def test_private_room_unchanged(self) -> None:
    """博士在博士房间里时，跟随的非助理干员进不了博士房间"""
    self.world.move(0, DR_ROOM)
    self.follower.sp_flag.is_follow = 1
    self.assertEqual(self.access(DR_ROOM, 1), "private")
