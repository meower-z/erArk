# -*- coding: UTF-8 -*-
"""
检验三种游戏语言下，init_character_dormitory 给模板 Dormitory 不是「无」的
干员分到相同的场景路径。翻译函数在 get_text 首次导入时选定语言，所以每种
语言各用一个子进程。子进程的工作目录是临时目录下以语言命名的子目录。这个
目录的 data/ 链接仓库 data/ 中除地图预处理文件外的条目。子进程按自己的语言
重建地图预处理文件，并把它们写在这个 data/ 下，而不是仓库的 data/ 下。
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
""" 受测的三种游戏语言代码 """

MAP_CACHE_FILES = ("SceneData", "MapData", "PlaceData", "ScenePath")
""" 地图预处理文件名：子进程会重建它们，所以工作目录的 data/ 不链接它们 """

ASSIGN_DORMITORY = """
import json
import sys

sys.path.insert(0, sys.argv[1])
from Script.Core import cache_control, game_type

cache_control.cache = game_type.Cache()
from Script.Config import normal_config

normal_config.init_normal_config()
normal_config.config_normal.language = sys.argv[2]
from Script.Config import character_config, game_config, map_config
from Script.Core import get_text

game_config.init()
character_config.init_character_tem_data()
map_config.init_map_data()
from Script.System.Dormitory_System import common

cache = cache_control.cache
for adv_id, tem in character_config.character_tem_list.items():
  if tem.Dormitory != "无":
    cache.character_data[adv_id] = game_type.Character()
    cache.character_data[adv_id].dormitory = tem.Dormitory
    cache.npc_id_got.add(adv_id)
common.init_character_dormitory()
print(json.dumps({
    "language": get_text.now_language,
    "dormitory": {
        str(chara_id): [
            cache.character_data[chara_id].dormitory,
            cache.character_data[chara_id].dormitory in cache.scene_data,
        ]
        for chara_id in sorted(cache.npc_id_got)
    },
}))
"""
""" argv[1] 是仓库根目录，argv[2] 是游戏语言。打印生效语言与分房结果的 JSON """


def make_data_dir(root: str) -> None:
  """
  在 root 下创建 data/ 目录。再为仓库 data/ 中除 MAP_CACHE_FILES 以外的每个
  条目，在这个目录里建一个同名软链接。
  Keyword arguments:
  root: str -- 子进程的工作目录路径
  Return arguments:
  None -- 无
  """
  os.makedirs(os.path.join(root, "data"))
  for name in os.listdir(os.path.join(ROOT, "data")):
    if name not in MAP_CACHE_FILES:
      os.symlink(
          os.path.join(ROOT, "data", name), os.path.join(root, "data", name)
      )


def assign_dormitory(root: str, language: str) -> dict[str, Any]:
  """
  在工作目录 root 下，以游戏语言 language 运行子进程脚本 ASSIGN_DORMITORY。
  Keyword arguments:
  root: str -- 子进程的工作目录路径，其下已有 data/
  language: str -- 子进程使用的游戏语言代码
  Return arguments:
  dict[str, Any] -- 子进程标准输出末行的 JSON，含生效语言与分房结果
  """
  result = subprocess.run(
      [sys.executable, "-c", ASSIGN_DORMITORY, ROOT, language],
      cwd=root,
      check=True,
      capture_output=True,
      text=True,
      timeout=300,
  )
  assigned: dict[str, Any] = json.loads(result.stdout.splitlines()[-1])
  return assigned


class TemplateDormitoryEveryLanguageTest(FastTestCase):
  """检验三种语言下模板 Dormitory 不是「无」的干员分到的场景路径"""

  def test_same_scene_path_in_every_language(self) -> None:
    """
    断言每个子进程实际生效的语言等于传入的语言代码。断言中文下至少有一名
    模板 Dormitory 不是「无」的干员。断言中文下每名此类干员的宿舍都是
    cache.scene_data 的键。断言英文和韩文下的分房结果与中文下相同。
    Keyword arguments:
    无
    Return arguments:
    None -- 无
    """
    assigned: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory() as temp_dir:
      for language in LANGUAGES:
        root = os.path.join(temp_dir, language)
        make_data_dir(root)
        assigned[language] = assign_dormitory(root, language)
        self.assertEqual(assigned[language]["language"], language)
    self.assertTrue(assigned["zh_CN"]["dormitory"])
    for chara_id, (dormitory, is_scene_path) in assigned["zh_CN"][
        "dormitory"
    ].items():
      with self.subTest(language="zh_CN", chara_id=chara_id):
        self.assertTrue(is_scene_path, dormitory)
    for language in LANGUAGES[1:]:
      with self.subTest(language=language):
        self.assertEqual(
            assigned[language]["dormitory"], assigned["zh_CN"]["dormitory"]
        )
