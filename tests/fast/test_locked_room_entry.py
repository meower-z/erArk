# -*- coding: UTF-8 -*-
"""
博士锁门后谁能进门的回归测试（判定部分）
======================================
断言都落在 map_handle.judge_scene_accessible 的返回值上：
- 博士在屋内锁门：被他召集到当前位置（is_follow=4）的角色，不论是不是助理，都能进这间房；别的锁门房间进不了。
- 没在跟随的助理与其他干员一样被挡在门外，只能进锁着的博士房间和博士办公室；智能跟随或强制跟随的助理能进博士所在的锁门房间。
- 博士在门外：锁着的博士房间和博士办公室照样能进，别的锁门房间进不了。
走进门的过程（召集后走进去、博士走回自己的办公室）在 tests/slow/test_locked_room_entry.py。
"""

from Script.Config import game_config
from Script.Design import map_handle
from tests.fast.base import FastTestCase

ROOM = ["中枢", "会议室"]
OTHER_ROOM = ["中枢", "茶水间"]
DR_ROOM = ["中枢", "博士房间"]
DR_OFFICE = ["中枢", "博士办公室"]
CORRIDOR = ["中枢", "走廊"]


class LockedRoomEntryTest(FastTestCase):
  """judge_scene_accessible 对锁门房间的判定"""

  def setUp(self) -> None:
    """
    博士、助理（id 1）与另一名干员（id 2）都在走廊；用到的房间按设施已开放处理
    Keyword arguments:
    无
    Return arguments:
    无
    """
    super().setUp()
    for path in (ROOM, OTHER_ROOM, DR_ROOM, DR_OFFICE):
      scene_name = self.world.scene(path).scene_name
      if scene_name in game_config.config_facility_open_name_set:
        self.cache.rhodes_island.facility_open[
            game_config.config_facility_open_name_to_cid[scene_name]
        ] = 1
    self.pl = self.world.chara(0, "博士", position=CORRIDOR)
    self.assistant = self.world.chara(1, "助理", position=CORRIDOR)
    self.other = self.world.chara(2, "干员", position=CORRIDOR)
    self.pl.assistant_character_id = 1

  def lock(self, path: list) -> None:
    """
    锁上房间的门
    Keyword arguments:
    path -- 房间的场景路径
    Return arguments:
    无
    """
    scene = self.world.scene(path)
    scene.close_flag = scene.close_type

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

  def doctor_locks_inside(self, path: list) -> None:
    """
    博士走进房间并锁门
    Keyword arguments:
    path -- 房间的场景路径
    Return arguments:
    无
    """
    self.world.move(0, path)
    self.lock(path)

  def test_assistant_not_following_is_locked_out(self) -> None:
    """没在跟随的助理进不了博士锁着的会议室"""
    self.doctor_locks_inside(ROOM)
    self.assertEqual(self.access(ROOM, 1), "door_lock")

  def test_summoned_chara_enters_doctors_room(self) -> None:
    """被召集到博士当前位置的助理与非助理干员都能进他锁着的会议室"""
    self.doctor_locks_inside(ROOM)
    for chara in (self.assistant, self.other):
      with self.subTest(cid=chara.cid):
        chara.sp_flag.is_follow = 4
        self.assertEqual(self.access(ROOM, chara.cid), "open")

  def test_summon_opens_only_doctors_room(self) -> None:
    """被召集的角色进不了博士不在的另一间锁门房间"""
    self.doctor_locks_inside(ROOM)
    self.lock(OTHER_ROOM)
    for chara in (self.assistant, self.other):
      with self.subTest(cid=chara.cid):
        chara.sp_flag.is_follow = 4
        self.assertEqual(self.access(OTHER_ROOM, chara.cid), "door_lock")

  def test_following_assistant_enters(self) -> None:
    """智能跟随（1）或强制跟随（2）的助理能进博士锁着的会议室"""
    self.doctor_locks_inside(ROOM)
    for is_follow in (1, 2):
      with self.subTest(is_follow=is_follow):
        self.assistant.sp_flag.is_follow = is_follow
        self.assertEqual(self.access(ROOM, 1), "open")

  def test_non_assistant_locked_out(self) -> None:
    """没被召集的非助理干员跟不跟随都进不了博士锁着的会议室"""
    self.doctor_locks_inside(ROOM)
    for is_follow in (0, 1, 2):
      with self.subTest(is_follow=is_follow):
        self.other.sp_flag.is_follow = is_follow
        self.assertEqual(self.access(ROOM, 2), "door_lock")

  def test_assistant_enters_locked_dr_rooms(self) -> None:
    """博士在屋里锁门时，没在跟随的助理能进博士房间和博士办公室，非助理干员进不了"""
    for path in (DR_ROOM, DR_OFFICE):
      with self.subTest(path=path):
        self.doctor_locks_inside(path)
        self.assertEqual(self.access(path, 1), "open")
        self.assertEqual(self.access(path, 2), "door_lock")

  def test_doctor_outside_enters_own_rooms(self) -> None:
    """博士在走廊：锁着的博士房间和博士办公室能进，锁着的会议室进不了"""
    for path, expected in (
        (DR_ROOM, "open"),
        (DR_OFFICE, "open"),
        (ROOM, "door_lock"),
    ):
      with self.subTest(path=path):
        self.lock(path)
        self.assertEqual(self.access(path, 0), expected)
