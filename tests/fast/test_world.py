# -*- coding: UTF-8 -*-
"""
world 夹具自身的测试
====================
默认角色穿着衣服、异常位全部正常；裸体角色须写明；复原后游戏状态与随机源回到同一起点；快速层拒绝导入受禁模块。
"""

import datetime
import importlib.util
import random
import uuid

import numpy

from Script.Design import handle_premise
from tests.fast import FORBIDDEN, FastLayerImportError
from tests.fast.base import FastTestCase
from tests.world import FixtureError

ROOM = ["中枢", "博士房间"]


class WorldTest(FastTestCase):
  """MinimalWorld 的造人、场景与复原"""

  def test_default_chara_dressed_and_normal(self) -> None:
    """默认角色不是大致全裸，normal_all 为 1"""
    self.world.chara(0, "博士")
    self.world.chara(1, "干员")
    self.assertEqual(handle_premise.handle_cloth_most_off(1), 0)
    self.assertEqual(handle_premise.handle_normal_all(1), 1)

  def test_naked_chara_on_request(self) -> None:
    """naked=True 的角色全裸，只有异常位4异常"""
    self.world.chara(0, "博士")
    self.world.chara(1, "干员", naked=True)
    self.assertEqual(handle_premise.handle_cloth_off(1), 1)
    self.assertEqual(
        [
            getattr(handle_premise, f"handle_normal_{bit}")(1)
            for bit in range(1, 8)
        ],
        [1, 1, 1, 0, 1, 1, 1],
    )

  def test_npc_before_player_refused(self) -> None:
    """先造 NPC 再造玩家时抛 FixtureError"""
    with self.assertRaises(FixtureError):
      self.world.chara(1, "干员")

  def test_unknown_scene_refused(self) -> None:
    """不存在的场景路径抛 FixtureError"""
    with self.assertRaises(FixtureError):
      self.world.scene(["没有", "这里"])

  def test_reset_restores_state(self) -> None:
    """复原后角色、场景、游戏时间、角色模板都回到基线，缓存对象不变"""
    cache = self.cache
    game_time = cache.game_time
    self.world.chara(0, "博士", position=ROOM)
    room = self.world.scene(ROOM)
    room.close_flag = 1
    cache.game_time = game_time + datetime.timedelta(days=1)
    cache.npc_tem_data[-1] = cache.npc_tem_data[1]
    self.world.reset()
    self.assertIs(self.cache, cache)
    self.assertEqual(cache.character_data, {})
    self.assertEqual(room.close_flag, 0)
    self.assertEqual(room.character_list, set())
    self.assertEqual(cache.game_time, game_time)
    self.assertNotIn(-1, cache.npc_tem_data)

  def test_reset_reseeds_random(self) -> None:
    """每次复原后 random、numpy.random 与 uuid.uuid4 给出同一串值"""
    first = (random.random(), numpy.random.random(), uuid.uuid4())
    self.world.reset()
    self.assertEqual(
        (random.random(), numpy.random.random(), uuid.uuid4()), first
    )

  def test_forbidden_import_refused(self) -> None:
    """查找受禁模块时抛 FastLayerImportError（find_spec 只查找、不执行模块）"""
    for name in sorted(FORBIDDEN):
      with self.subTest(name=name), self.assertRaises(FastLayerImportError):
        importlib.util.find_spec(name)
