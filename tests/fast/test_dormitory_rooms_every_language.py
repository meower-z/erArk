# -*- coding: UTF-8 -*-
"""
各语言下的开放宿舍房间
======================
游戏带中文、英文、韩文三种语言，每种语言下的开放宿舍房间要相同。
测试为每种语言开一个子进程。
子进程载入配置与地图后，把宿舍区从 1 级逐级升到 5 级。
每升一级，子进程记下 get_open_dormitory_rooms_by_layer 按层列出的房间。
子进程还记下 get_layer_by_dormitory_path 给每个房间算出的层号。
翻译函数在 get_text 首次导入时选定语言，所以每种语言要用单独的进程。
地图预处理文件不按语言区分，所以每个子进程在自己的临时目录里重建它们。
"""

import json
import os
import subprocess
import sys
import tempfile
from typing import Any

from tests.fast.base import FastTestCase
from tests.world import ROOT, START_TIME

LANGUAGES = ("zh_CN", "en_US", "ko_KR")
""" 游戏带的三种语言 """

MAP_CACHE_FILES = ("SceneData", "MapData", "PlaceData", "ScenePath")
""" data/ 下的地图预处理文件 """

LIST_ROOMS = """
import datetime
import json
import sys

sys.path.insert(0, sys.argv[1])
from Script.Core import cache_control, game_type

cache_control.cache = game_type.Cache()
from Script.Config import normal_config

normal_config.init_normal_config()
normal_config.config_normal.language = sys.argv[2]
from Script.Config import game_config, map_config
from Script.Core import get_text

game_config.init()
map_config.init_map_data()
from Script.Design import attr_calculation, basement, game_time
from Script.System.Dormitory_System import common

cache = cache_control.cache
cache.game_time = cache.pre_game_time = game_time.to_game_time(
    datetime.datetime(*json.loads(sys.argv[3]))
)
cache.all_system_setting = attr_calculation.get_system_setting_zero()
cache.rhodes_island = basement.get_base_zero()
basement.get_base_updata()
levels = {}
for level in range(1, 6):
  cache.rhodes_island.facility_level[4] = level
  basement.get_base_updata()
  levels[level] = {
      layer: [
          [room_path, common.get_layer_by_dormitory_path(room_path)]
          for _room_name, room_path in room_list
      ]
      for layer, room_list in common.get_open_dormitory_rooms_by_layer().items()
  }
print(json.dumps({"language": get_text.now_language, "levels": levels}))
"""
""" 子进程：argv[2] 是游戏语言；打印实际语言，以及每个宿舍区等级的 {层号: [[房间路径, 该路径的层号]]} """


def make_data_dir(root: str) -> None:
  """
  在 root 下建 data/，地图预处理文件以外的条目都链到仓库的 data/
  Keyword arguments:
  root -- 子进程的工作目录
  Return arguments:
  无
  """
  os.makedirs(os.path.join(root, "data"))
  for name in os.listdir(os.path.join(ROOT, "data")):
    if name not in MAP_CACHE_FILES:
      os.symlink(
          os.path.join(ROOT, "data", name), os.path.join(root, "data", name)
      )


def list_rooms(root: str, language: str) -> dict[str, Any]:
  """
  在子进程里以给定语言列出每个宿舍区等级的开放宿舍房间
  Keyword arguments:
  root -- 子进程的工作目录，内有 data/
  language -- 游戏语言
  Return arguments:
  dict -- 子进程打印的 JSON
  """
  result = subprocess.run(
      [
          sys.executable,
          "-c",
          LIST_ROOMS,
          ROOT,
          language,
          json.dumps(START_TIME),
      ],
      cwd=root,
      check=True,
      capture_output=True,
      text=True,
      timeout=300,
  )
  listed: dict[str, Any] = json.loads(result.stdout.splitlines()[-1])
  return listed


class DormitoryRoomsEveryLanguageTest(FastTestCase):
  """三种语言下的开放宿舍房间与房间层号"""

  def test_open_rooms_same_in_every_language(self) -> None:
    """
    中文下，每个等级都有开放房间，每个房间的层号等于它所在的层。
    英文、韩文下，每个等级的结果与中文相同。
    Keyword arguments:
    无
    Return arguments:
    无
    """
    listed: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory() as temp_dir:
      for language in LANGUAGES:
        root = os.path.join(temp_dir, language)
        make_data_dir(root)
        listed[language] = list_rooms(root, language)
        self.assertEqual(listed[language]["language"], language)
    for level, rooms_by_layer in listed["zh_CN"]["levels"].items():
      with self.subTest(language="zh_CN", level=level):
        self.assertTrue(rooms_by_layer)
        for layer, room_list in rooms_by_layer.items():
          for _room_path, room_layer in room_list:
            self.assertEqual(room_layer, int(layer))
    for language in LANGUAGES[1:]:
      with self.subTest(language=language):
        self.assertEqual(listed[language]["levels"], listed["zh_CN"]["levels"])
