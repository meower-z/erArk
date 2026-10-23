# -*- coding: UTF-8 -*-
"""
英文下地点目录名的翻译
======================
非中文语言下，全干员位置面板逐段翻译角色所在位置的路径，路径的每一段是 data/map 下的一个目录名。
下面这几个场景的目录名不在抽取出的原文里，靠翻译文件里单独的条目翻译。
本测试按场景标签从地图数据里取出标签 Power_Dispatch、Onsen、Golden_Game_Room 各自唯一的场景，
用游戏建翻译链的同一函数 get_text.create_translation_chain 建出 en_US 的翻译链，
检查这几个场景自己的目录名（路径的最后一段）都查到与原文不同的译文。
"""

from Script.Core import constant, get_text
from Script.Design import map_handle
from tests.fast.base import FastTestCase

LANGUAGE = "en_US"
""" 检查的语言 """
SCENE_TAG_LIST = ("Power_Dispatch", "Onsen", "Golden_Game_Room")
""" 各自只标在一个场景上的场景标签 """


class LocationDirNamesTranslate(FastTestCase):
  """en_US 下，按标签取出的场景的目录名查得到译文"""

  def test_scene_dir_names_translate(self) -> None:
    """
    每个标签恰好对应一个场景，场景路径最后一段的目录名在 en_US 翻译链里有不同于原文的译文
    Keyword arguments:
    无
    Return arguments:
    无
    """
    translation = get_text.create_translation_chain(
        LANGUAGE, get_text.mo_files_per_language[LANGUAGE]
    )
    self.assertIsNotNone(translation)
    for scene_tag in SCENE_TAG_LIST:
      with self.subTest(scene_tag=scene_tag):
        scene_path_list = constant.place_data[scene_tag]
        self.assertEqual(len(scene_path_list), 1)
        dir_name = map_handle.get_map_system_path_for_str(scene_path_list[0])[
            -1
        ]
        self.assertNotEqual(translation.gettext(dir_name), dir_name)
