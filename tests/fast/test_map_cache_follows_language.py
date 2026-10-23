# -*- coding: UTF-8 -*-
"""
地图预处理文件跟随游戏语言
==========================
map_config.init_map_data 在 data/ 下写出地图预处理文件
（SceneData、MapData、PlaceData、ScenePath），之后启动时读入它们。
场景名与地图名经过翻译，玩家在系统设置里换语言后重启，载入的名字要是新语言的。
测试在临时目录里摆出 data/map 与 data/po（链到仓库），每种语言各开一个子进程载入地图，
因为翻译函数在 get_text 首次导入时按 config.ini 的语言选定。
"""

import json
import os
import subprocess
import sys
import tempfile
from typing import Any

from tests.fast.base import FastTestCase
from tests.world import ROOT

LANGUAGES = ("zh_CN", "en_US", "ko_KR")
""" 游戏带的三种语言 """

PICKLE_FILES = ("SceneData", "MapData", "PlaceData")
""" data/ 下的 pickle 地图预处理文件 """

LOAD_MAP = """
import hashlib
import json
import sys

sys.path.insert(0, sys.argv[1])
from Script.Core import cache_control, game_type

cache_control.cache = game_type.Cache()
from Script.Config import normal_config

normal_config.init_normal_config()
normal_config.config_normal.language = sys.argv[2]
from Script.Config import map_config
from Script.Core import constant
from Script.Design import map_handle

map_config.init_map_data()
cache = cache_control.cache
print(json.dumps({
    "scene_names": {k: v.scene_name for k, v in cache.scene_data.items()},
    "map_names": {k: v.map_name for k, v in cache.map_data.items()},
    "place_and_path_sha256": hashlib.sha256(json.dumps(
        [constant.place_data, map_handle.scene_path_edge], sort_keys=True
    ).encode()).hexdigest(),
}))
"""
""" 子进程：以 argv[2] 为游戏语言在当前目录载入地图，打印场景名、地图名，以及地点标签与寻路数据的摘要 """


def make_data_dir(root: str) -> None:
  """
  在临时目录里建 data/，其中 map 与 po 链到仓库
  Keyword arguments:
  root -- 临时目录
  Return arguments:
  无
  """
  os.makedirs(os.path.join(root, "data"))
  for name in ("map", "po"):
    os.symlink(
        os.path.join(ROOT, "data", name), os.path.join(root, "data", name)
    )


def load_map(root: str, language: str) -> dict[str, Any]:
  """
  在子进程里以给定语言载入 root 下的地图
  Keyword arguments:
  root -- 工作目录，内有 data/
  language -- 游戏语言
  Return arguments:
  dict -- 场景名、地图名，以及地点标签与寻路数据的摘要
  """
  result = subprocess.run(
      [sys.executable, "-c", LOAD_MAP, ROOT, language],
      cwd=root,
      check=True,
      capture_output=True,
      text=True,
      timeout=120,
  )
  loaded: dict[str, Any] = json.loads(result.stdout.splitlines()[-1])
  return loaded


def pickle_mtimes(root: str) -> dict[str, int]:
  """
  pickle 地图预处理文件的修改时间
  Keyword arguments:
  root -- 工作目录，内有 data/
  Return arguments:
  dict -- 文件名: 修改时间（纳秒）
  """
  return {
      name: os.stat(os.path.join(root, "data", name)).st_mtime_ns
      for name in PICKLE_FILES
  }


class MapCacheFollowsLanguageTest(FastTestCase):
  """换语言后再载入，地图数据与新语言下全新构建的相同；语言不变时直接读入预处理文件"""

  def test_load_after_language_switch(self) -> None:
    """
    每种语言各在空目录里构建一次；再在每个目录里换成下一种语言载入两次
    Keyword arguments:
    无
    Return arguments:
    无
    功能描述:
        换语言后的第一次载入要与该语言的全新构建相同；
        紧接着的第二次载入也相同，并且不改写 pickle 预处理文件。
    """
    with tempfile.TemporaryDirectory() as temp_dir:
      roots: dict[str, str] = {}
      fresh: dict[str, dict[str, Any]] = {}
      for language in LANGUAGES:
        roots[language] = os.path.join(temp_dir, language)
        make_data_dir(roots[language])
        fresh[language] = load_map(roots[language], language)
      self.assertNotEqual(
          fresh["zh_CN"]["scene_names"], fresh["en_US"]["scene_names"]
      )
      for index, built_language in enumerate(LANGUAGES):
        language = LANGUAGES[(index + 1) % len(LANGUAGES)]
        root = roots[built_language]
        with self.subTest(built=built_language, loaded=language):
          self.assertEqual(load_map(root, language), fresh[language])
          mtimes = pickle_mtimes(root)
          self.assertEqual(load_map(root, language), fresh[language])
          self.assertEqual(pickle_mtimes(root), mtimes)
