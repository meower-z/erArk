"""场景地址、地图地址、数值与年龄素质的显示文本"""

from types import FunctionType
from typing import List
from Script.Core import (
    cache_control,
    game_type,
    get_text,
)
from Script.Design import map_handle
from Script.Config import game_config

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """

_: FunctionType = get_text._
""" 翻译api """


def get_scene_path_text(scene_path: List[str]) -> str:
  """
  从场景路径获取场景地址描述文本
  例:控制中枢-博士办公室
  Keyword arguments:
  scene_path -- 场景路径
  Return arguments:
  str -- 场景地址描述文本
  """
  map_list = map_handle.get_map_hierarchy_list_for_scene_path(scene_path, [])
  map_list.reverse()
  scene_path_str = map_handle.get_map_system_path_str_for_list(scene_path)
  scene_path_text = ""
  for now_map in map_list:
    now_map_map_system_str = map_handle.get_map_system_path_str_for_list(
        now_map
    )
    map_name = cache.map_data[now_map_map_system_str].map_name
    scene_path_text += _(map_name) + "-"
  scene_name = cache.scene_data[scene_path_str].scene_name
  return scene_path_text + _(scene_name)


def get_map_path_text(map_path: List[str]) -> str:
  """
  从地图路径获取地图地址描述文本
  例:控制中枢
  Keyword arguments:
  map_path -- 地图路径
  Return arguments:
  str -- 地图地址描述文本
  """
  map_list = map_handle.get_map_hierarchy_list_for_scene_path(map_path, [])
  map_list.reverse()
  map_list.append(map_path)
  now_path_text = ""
  for now_map in map_list:
    now_map_map_system_str = map_handle.get_map_system_path_str_for_list(
        now_map
    )
    map_name = cache.map_data[now_map_map_system_str].map_name
    now_path_text += _(map_name) + "-"
  return now_path_text.rstrip("-")


def get_value_text(value: float) -> str:
  """
  获取数值显示的文本
  Keyword arguments:
  value -- 数值
  Return arguments:
  str -- 文本显示
  """
  int_value = int(value)
  company = ["K", "M", "G", "T", "P", "E", "Z", "Y", "B", "N", "D"]
  sign = "+" if int_value >= 0 else "-"
  absolute_value = abs(int_value)
  digit_count = len(str(absolute_value))
  if digit_count < 4:
    return sign + str(absolute_value)

  company_group = min((digit_count - 1) // 3, len(company))
  compact_value = absolute_value // (1000**company_group)
  return sign + str(compact_value) + company[company_group - 1]


def get_age_talent_text(character_id: int) -> str:
  """
  按角色Id获取年龄素质文本
  Keyword arguments:
  character_id -- 角色Id
  Return arguments:
  str -- 年龄素质文本
  """
  charactert_data = cache.character_data[character_id]
  for talent_id in range(101, 109):
    if charactert_data.talent[talent_id]:
      return game_config.config_talent[talent_id].name
  return ""
