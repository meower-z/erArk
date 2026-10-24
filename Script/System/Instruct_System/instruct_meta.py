# -*- coding: utf-8 -*-
"""
指令元数据管理模块
用于查询指令的分类信息

此模块提供了指令分类信息的查询功能，
支持Web模式下的交互类型选择和部位点击系统

指令分类说明：
1. 系统面板类（SYSTEM_PANEL）：函数内容为 cache.now_panel_id = xxx 的指令
2. 角色交互类（CHARACTER）：普通的角色交互指令
3. 角色交互面板类（CHARACTER_PANEL）：函数内容带有 now_panel.draw() 的指令
"""

from typing import Dict, List, Set, Optional
from Script.System.Instruct_System.instruct_category import (
    InstructCategory,
    BodyPart,
    BODY_PART_NAMES,
)
from Script.System.Instruct_System.interaction_types import (
    InteractionMajorType,
    InteractionMinorType,
    MAJOR_TYPE_NAMES,
    MAJOR_TYPE_ORDER,
    MINOR_TYPE_NAMES,
    MAJOR_TO_MINOR_TYPES,
    get_major_type,
    get_minor_type_name,
    get_major_type_name,
)


def get_instruct_category_name(category: int) -> str:
  """
  获取指令大类的中文名称

  Keyword arguments:
  category -- 指令大类

  Returns:
  str -- 中文名称
  """
  if category == InstructCategory.SYSTEM_PANEL:
    return "系统面板类"
  elif category == InstructCategory.CHARACTER:
    return "角色交互类"
  elif category == InstructCategory.CHARACTER_PANEL:
    return "角色交互面板类"
  return "未知"


def get_interaction_type_name(interaction_type: str) -> str:
  """
  获取交互类型的中文名称（使用新系统的 MinorType）

  Keyword arguments:
  interaction_type -- 交互小类型（InteractionMinorType）

  Returns:
  str -- 中文名称
  """
  return get_minor_type_name(interaction_type)


def get_body_part_name(body_part: str) -> str:
  """
  获取身体部位的中文名称

  Keyword arguments:
  body_part -- 身体部位英文标识

  Returns:
  str -- 中文名称
  """
  return BODY_PART_NAMES.get(body_part, body_part)


# ========== 以下为从 constant 字典直接查询的函数 ==========
# 这些函数直接访问 add_instruct 装饰器注册的数据


def get_panel_instructs_from_constant() -> List[str]:
  """
  从 constant 字典获取所有面板类指令的ID列表

  Returns:
  List[str] -- 面板类指令ID列表
  """
  from Script.Core import constant

  return [
      instruct_id
      for instruct_id, category in constant.instruct_category_data.items()
      if category == InstructCategory.SYSTEM_PANEL
  ]


def get_character_instructs_from_constant() -> List[str]:
  """
  从 constant 字典获取所有角色交互类指令的ID列表

  Returns:
  List[str] -- 角色交互类指令ID列表
  """
  from Script.Core import constant

  return [
      instruct_id
      for instruct_id, category in constant.instruct_category_data.items()
      if category == InstructCategory.CHARACTER
  ]


def get_instructs_by_interaction_type_from_constant(
    interaction_type: Optional[str],
) -> List[str]:
  """
  从 constant 字典根据交互小类型获取指令列表

  Keyword arguments:
  interaction_type -- 交互小类型（InteractionMinorType）

  Returns:
  List[str] -- 符合条件的指令ID列表
  """
  from Script.Core import constant

  return [
      instruct_id
      for instruct_id, itype in constant.instruct_minor_type_data.items()
      if itype == interaction_type
  ]


def get_instructs_by_body_part_from_constant(body_part: str) -> List[str]:
  """
  从 constant 字典根据身体部位获取相关指令列表

  Keyword arguments:
  body_part -- 身体部位名称

  Returns:
  List[str] -- 关联该部位的指令ID列表
  """
  from Script.Core import constant

  return [
      instruct_id
      for instruct_id, parts in constant.instruct_body_parts_data.items()
      if body_part in parts
  ]


def get_web_instruct_info(instruct_id: str) -> Optional[Dict]:
  """
  获取单个指令的Web模式分类信息

  Keyword arguments:
  instruct_id -- 指令ID

  Returns:
  Dict -- 包含分类信息的字典，如果不存在返回None
  """
  from Script.Core import constant

  if instruct_id not in constant.instruct_category_data:
    return None

  minor_type = constant.instruct_minor_type_data.get(
      instruct_id, InteractionMinorType.OTHER_MISC
  )
  major_type = get_major_type(minor_type)

  return {
      "instruct_id": instruct_id,
      "name": constant.handle_instruct_name_data.get(instruct_id, ""),
      "category": constant.instruct_category_data.get(
          instruct_id, InstructCategory.CHARACTER
      ),
      "category_name": get_instruct_category_name(
          constant.instruct_category_data.get(
              instruct_id, InstructCategory.CHARACTER
          )
      ),
      "major_type": major_type,
      "major_type_name": get_major_type_name(major_type),
      "minor_type": minor_type,
      "minor_type_name": get_minor_type_name(minor_type),
      # 保留 interaction_type 字段作为别名，方便兼容
      "interaction_type": minor_type,
      "interaction_type_name": get_minor_type_name(minor_type),
      "body_parts": constant.instruct_body_parts_data.get(instruct_id, []),
      "is_single_part": len(
          constant.instruct_body_parts_data.get(instruct_id, [])
      )
      == 1,
  }


def get_available_interaction_types_from_constant() -> List[Dict]:
  """
  从 constant 字典获取所有可用的交互类型列表（供前端显示）
  使用新的 InteractionMinorType 系统

  Returns:
  List[Dict] -- 交互类型信息列表，每个元素包含 id、name、major_type 和 major_type_name
  """
  from Script.Core import constant

  # 收集所有已注册指令中实际使用的交互小类型
  used_minor_types: Set[str] = set()
  for instruct_id, category in constant.instruct_category_data.items():
    if category == InstructCategory.CHARACTER:
      minor_type = constant.instruct_minor_type_data.get(
          instruct_id, InteractionMinorType.OTHER_MISC
      )
      used_minor_types.add(minor_type)

  # 按照大类顺序组织返回
  result = []
  for major_type in MAJOR_TYPE_ORDER:
    minor_types = MAJOR_TO_MINOR_TYPES.get(major_type, [])
    for minor_type in minor_types:
      if minor_type in used_minor_types:
        result.append(
            {
                "id": minor_type,
                "name": get_minor_type_name(minor_type),
                "major_type": major_type,
                "major_type_name": get_major_type_name(major_type),
            }
        )
  return result


def get_body_parts_for_interaction_type_from_constant(
    interaction_type: Optional[str],
) -> List[str]:
  """
  从 constant 字典获取某个交互小类型涉及的所有身体部位

  Keyword arguments:
  interaction_type -- 交互小类型（InteractionMinorType）

  Returns:
  List[str] -- 身体部位名称列表
  """
  from Script.Core import constant

  parts: Set[str] = set()
  for instruct_id, itype in constant.instruct_minor_type_data.items():
    if itype == interaction_type:
      body_parts = constant.instruct_body_parts_data.get(instruct_id, [])
      parts.update(body_parts)
  return list(parts)
