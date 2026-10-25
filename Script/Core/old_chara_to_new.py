"""存档载入时对旧存档角色数据的迁移与修正，以及幼年角色相关数据的清理"""

from __future__ import annotations

import datetime
from types import FunctionType
from Script.Core import (
    cache_control,
    constant,
    game_path_config,
    game_type,
    get_text,
)
from Script.Config import game_config
from Script.Design import attr_calculation, character_handle, child_stage_gate
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
  from typing import Any

game_path = game_path_config.game_path
cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """
_: FunctionType = get_text._
""" 翻译api """


def _remap_first_record_ids(
    first_record: game_type.FIRST_RECORD, id_map: dict
) -> None:
  """
  重映射FIRST_RECORD实例中的角色ID（平铺字段与first_part_sex_dict）
  Keyword arguments:
  first_record -- FIRST_RECORD实例（当前记录或first_record_history中的历史周目快照）
  id_map -- 旧角色id到新角色id的映射
  Return arguments:
  None
  """
  # 平铺字段的重映射保留hasattr守卫，服务尚未走存档迁移的更老路径
  for attr_name in (
      'first_hand_in_hand',
      'first_kiss_id',
      'first_sex_id',
      'first_a_sex_id',
      'first_u_sex_id',
      'first_w_sex_id',
  ):
    if (
        hasattr(first_record, attr_name)
        and getattr(first_record, attr_name) > 0
    ):
      old_id = getattr(first_record, attr_name)
      setattr(first_record, attr_name, id_map.get(old_id, old_id))
  # 部位交初体验dict中的对象角色ID
  for part_record in getattr(first_record, 'first_part_sex_dict', {}).values():
    if isinstance(part_record, dict) and part_record.get('id', -1) > 0:
      part_record['id'] = id_map.get(part_record['id'], part_record['id'])


def normalize_single_character_id(raw_value: Any, default: int = 0) -> int:
  """
  将旧存档中的单角色id字段归一化为int
  Keyword arguments:
  raw_value -- 原始字段值，可能是int/list/set等旧格式
  default -- 无法识别时使用的默认值
  Return arguments:
  int -- 归一化后的角色id
  """
  if isinstance(raw_value, int):
    return raw_value

  if isinstance(raw_value, (list, tuple, set)):
    for item in raw_value:
      normalized_id = normalize_single_character_id(item, default)
      if normalized_id != default:
        return normalized_id
    return default

  if isinstance(raw_value, dict):
    for item in raw_value.values():
      normalized_id = normalize_single_character_id(item, default)
      if normalized_id != default:
        return normalized_id
    for item in raw_value.keys():
      normalized_id = normalize_single_character_id(item, default)
      if normalized_id != default:
        return normalized_id
    return default

  try:
    return int(raw_value)
  except (TypeError, ValueError):
    return default


def normalize_line_chara_id_data(
    line_data: Any, chara_index: int, min_length: int
) -> list:
  """
  将旧存档中的产线/招募线数据归一化为标准列表结构
  Keyword arguments:
  line_data -- 原始线体数据
  chara_index -- 主角色id所在下标
  min_length -- 最低需要补齐的长度
  Return arguments:
  list -- 归一化后的线体数据
  """
  if isinstance(line_data, tuple):
    line_data = list(line_data)
  elif not isinstance(line_data, list):
    line_data = [0] * min_length
  else:
    line_data = line_data.copy()

  while len(line_data) < min_length:
    line_data.append(0)

  line_data[chara_index] = normalize_single_character_id(
      line_data[chara_index], 0
  )
  return line_data


def migrate_old_save_data(loaded_dict: dict[str, Any]) -> int:
  """
  将旧版存档的角色ID从顺序排列迁移到基于adv的格式

  迁移内容：
  1. npc_tem_data: List -> Dict (键为AdvNpc)
  2. character_data: 键从顺序id改为adv
  3. npc_id_got: 集合中的id改为adv
  4. 所有引用character_id的数据结构

  Returns:
      int: 迁移的数据条目数
  """
  update_count = 0

  # 1. 转换npc_tem_data
  if isinstance(loaded_dict['npc_tem_data'], list):
    old_tem_list = loaded_dict['npc_tem_data']
    new_tem_dict = {}
    for tem in old_tem_list:
      new_tem_dict[tem.AdvNpc] = tem
    loaded_dict['npc_tem_data'] = new_tem_dict
    update_count += len(old_tem_list)

  # 2. 建立旧id到新id的映射
  old_to_new_id = {0: 0}  # 玩家id保持为0
  old_character_data = loaded_dict['character_data']

  for old_cid, character in old_character_data.items():
    if old_cid != 0:
      old_to_new_id[old_cid] = character.adv

  # 3. 转换character_data
  new_character_data = {}
  for old_cid, character in old_character_data.items():
    if old_cid == 0:
      new_character_data[0] = character
      character.cid = 0
    else:
      new_cid = character.adv
      character.cid = new_cid
      new_character_data[new_cid] = character
    update_count += 1
  loaded_dict['character_data'] = new_character_data

  # 4. 转换npc_id_got
  old_npc_id_got = loaded_dict.get('npc_id_got', set())
  new_npc_id_got = set()
  for old_id in old_npc_id_got:
    if old_id in old_to_new_id:
      new_npc_id_got.add(old_to_new_id[old_id])
  loaded_dict['npc_id_got'] = new_npc_id_got

  # 5. 转换其他引用角色ID的数据结构
  # 5.1 玩家收藏品
  if 0 in new_character_data:
    pl_data = new_character_data[0]
    if hasattr(pl_data, 'pl_collection'):
      # token_list
      if hasattr(pl_data.pl_collection, 'token_list'):
        old_token = pl_data.pl_collection.token_list.copy()
        pl_data.pl_collection.token_list = {}
        for old_id, value in old_token.items():
          new_id = old_to_new_id.get(old_id, old_id)
          pl_data.pl_collection.token_list[new_id] = value

      # first_panties
      if hasattr(pl_data.pl_collection, 'first_panties'):
        old_panties = pl_data.pl_collection.first_panties.copy()
        pl_data.pl_collection.first_panties = {}
        for old_id, value in old_panties.items():
          new_id = old_to_new_id.get(old_id, old_id)
          pl_data.pl_collection.first_panties[new_id] = value

      # npc_panties
      if hasattr(pl_data.pl_collection, 'npc_panties'):
        old_npc_panties = pl_data.pl_collection.npc_panties.copy()
        pl_data.pl_collection.npc_panties = {}
        for old_id, value in old_npc_panties.items():
          new_id = old_to_new_id.get(old_id, old_id)
          pl_data.pl_collection.npc_panties[new_id] = value

      # npc_socks
      if hasattr(pl_data.pl_collection, 'npc_socks'):
        old_npc_socks = pl_data.pl_collection.npc_socks.copy()
        pl_data.pl_collection.npc_socks = {}
        for old_id, value in old_npc_socks.items():
          new_id = old_to_new_id.get(old_id, old_id)
          pl_data.pl_collection.npc_socks[new_id] = value

      # npc_panties_tem (Dict[int, list]) - 临时获得的角色内裤
      if hasattr(pl_data.pl_collection, 'npc_panties_tem'):
        old_panties_tem = pl_data.pl_collection.npc_panties_tem.copy()
        pl_data.pl_collection.npc_panties_tem = {}
        for old_id, value in old_panties_tem.items():
          new_id = old_to_new_id.get(old_id, old_id)
          pl_data.pl_collection.npc_panties_tem[new_id] = value

      # npc_socks_tem (Dict[int, list]) - 临时获得的角色袜子
      if hasattr(pl_data.pl_collection, 'npc_socks_tem'):
        old_socks_tem = pl_data.pl_collection.npc_socks_tem.copy()
        pl_data.pl_collection.npc_socks_tem = {}
        for old_id, value in old_socks_tem.items():
          new_id = old_to_new_id.get(old_id, old_id)
          pl_data.pl_collection.npc_socks_tem[new_id] = value

      # eqip_token[1] - 已装备信物的干员id列表
      if (
          hasattr(pl_data.pl_collection, 'eqip_token')
          and len(pl_data.pl_collection.eqip_token) > 1
      ):
        old_equip_list = pl_data.pl_collection.eqip_token[1]
        pl_data.pl_collection.eqip_token[1] = [
            old_to_new_id.get(oid, oid) for oid in old_equip_list
        ]

      # milk_total (Dict[int, int])
      if hasattr(pl_data.pl_collection, 'milk_total'):
        old_milk = pl_data.pl_collection.milk_total.copy()
        pl_data.pl_collection.milk_total = {}
        for old_id, value in old_milk.items():
          new_id = old_to_new_id.get(old_id, old_id)
          pl_data.pl_collection.milk_total[new_id] = value

      # urine_total (Dict[int, int])
      if hasattr(pl_data.pl_collection, 'urine_total'):
        old_urine = pl_data.pl_collection.urine_total.copy()
        pl_data.pl_collection.urine_total = {}
        for old_id, value in old_urine.items():
          new_id = old_to_new_id.get(old_id, old_id)
          pl_data.pl_collection.urine_total[new_id] = value

  # 5.2 每个角色的favorability字典（角色id:好感度）
  for _char_id, character in new_character_data.items():
    if hasattr(character, 'favorability'):
      old_fav = character.favorability.copy()
      character.favorability = {}
      for old_id, value in old_fav.items():
        new_id = old_to_new_id.get(old_id, old_id)
        character.favorability[new_id] = value

  # 5.3 每个角色的target_character_id
  for _char_id, character in new_character_data.items():
    if hasattr(character, 'target_character_id'):
      old_target = character.target_character_id
      character.target_character_id = old_to_new_id.get(old_target, old_target)

  # 5.4 每个角色的assistant_character_id
  for _char_id, character in new_character_data.items():
    if hasattr(character, 'assistant_character_id'):
      old_assistant = character.assistant_character_id
      character.assistant_character_id = old_to_new_id.get(
          old_assistant, old_assistant
      )

  # 5.4b 每个角色的其他角色ID引用
  for _char_id, character in new_character_data.items():
    # ask_group_sex_refuse_chara_id_list (位于action_info中)
    if hasattr(character, 'action_info') and hasattr(
        character.action_info, 'ask_group_sex_refuse_chara_id_list'
    ):
      character.action_info.ask_group_sex_refuse_chara_id_list = [
          old_to_new_id.get(oid, oid)
          for oid in character.action_info.ask_group_sex_refuse_chara_id_list
      ]

    # sp_flag.bagging_chara_id (注意：是sp_flag不是state_active)
    if hasattr(character, 'sp_flag') and hasattr(
        character.sp_flag, 'bagging_chara_id'
    ):
      if character.sp_flag.bagging_chara_id != 0:
        character.sp_flag.bagging_chara_id = old_to_new_id.get(
            character.sp_flag.bagging_chara_id,
            character.sp_flag.bagging_chara_id,
        )

    # pl_ability.carry_chara_id_in_time_stop (注意：是pl_ability不是sp_flag)
    if hasattr(character, 'pl_ability') and hasattr(
        character.pl_ability, 'carry_chara_id_in_time_stop'
    ):
      if character.pl_ability.carry_chara_id_in_time_stop != 0:
        character.pl_ability.carry_chara_id_in_time_stop = old_to_new_id.get(
            character.pl_ability.carry_chara_id_in_time_stop,
            character.pl_ability.carry_chara_id_in_time_stop,
        )

    # pl_ability.free_in_time_stop_chara_id (注意：是pl_ability不是sp_flag)
    if hasattr(character, 'pl_ability') and hasattr(
        character.pl_ability, 'free_in_time_stop_chara_id'
    ):
      if character.pl_ability.free_in_time_stop_chara_id != 0:
        character.pl_ability.free_in_time_stop_chara_id = old_to_new_id.get(
            character.pl_ability.free_in_time_stop_chara_id,
            character.pl_ability.free_in_time_stop_chara_id,
        )

    # action_info.interacting_character_end_info[0] (注意：是action_info中的)
    if hasattr(character, 'action_info') and hasattr(
        character.action_info, 'interacting_character_end_info'
    ):
      if character.action_info.interacting_character_end_info[0] != -1:
        character.action_info.interacting_character_end_info[0] = (
            old_to_new_id.get(
                character.action_info.interacting_character_end_info[0],
                character.action_info.interacting_character_end_info[0],
            )
        )

    # action_info.social_contact_last_time (Dict[int, datetime])
    if hasattr(character, 'action_info') and hasattr(
        character.action_info, 'social_contact_last_time'
    ):
      old_social = character.action_info.social_contact_last_time.copy()
      character.action_info.social_contact_last_time = {}
      for old_id, value in old_social.items():
        new_id = old_to_new_id.get(old_id, old_id)
        character.action_info.social_contact_last_time[new_id] = value

    # action_info.social_contact_last_cut_down_time (Dict[int, datetime])
    if hasattr(character, 'action_info') and hasattr(
        character.action_info, 'social_contact_last_cut_down_time'
    ):
      old_cutdown = (
          character.action_info.social_contact_last_cut_down_time.copy()
      )
      character.action_info.social_contact_last_cut_down_time = {}
      for old_id, value in old_cutdown.items():
        new_id = old_to_new_id.get(old_id, old_id)
        character.action_info.social_contact_last_cut_down_time[new_id] = value

    # first_record中的角色ID字段（含first_part_sex_dict与历史周目快照）
    if hasattr(character, 'first_record'):
      _remap_first_record_ids(character.first_record, old_to_new_id)
    for history_record in getattr(
        character, 'first_record_history', {}
    ).values():
      _remap_first_record_ids(history_record, old_to_new_id)

    # collection_character (Set) - 收藏的角色列表
    if (
        hasattr(character, 'collection_character')
        and character.collection_character
    ):
      old_collection = character.collection_character.copy()
      character.collection_character = {
          old_to_new_id.get(oid, oid) for oid in old_collection
      }

    # h_state.group_sex_body_template_dict 中的角色ID
    if hasattr(character, 'h_state') and hasattr(
        character.h_state, 'group_sex_body_template_dict'
    ):
      template_dict = character.h_state.group_sex_body_template_dict
      for template_key in ['A', 'B']:
        if template_key in template_dict:
          # 处理对单部位字典
          if len(template_dict[template_key]) > 0 and isinstance(
              template_dict[template_key][0], dict
          ):
            for _part_key, part_value in template_dict[template_key][0].items():
              if (
                  isinstance(part_value, list)
                  and len(part_value) > 0
                  and part_value[0] != -1
              ):
                part_value[0] = old_to_new_id.get(part_value[0], part_value[0])
          # 处理阴茎侍奉列表
          if len(template_dict[template_key]) > 1 and isinstance(
              template_dict[template_key][1], list
          ):
            serve_data = template_dict[template_key][1]
            if len(serve_data) > 0 and isinstance(serve_data[0], list):
              serve_data[0] = [
                  old_to_new_id.get(oid, oid) if oid != -1 else oid
                  for oid in serve_data[0]
              ]

  # 5.5 rhodes_island中的角色引用
  if 'rhodes_island' in loaded_dict:
    ri = loaded_dict['rhodes_island']

    # hr_operator_ids_list
    if hasattr(ri, 'hr_operator_ids_list'):
      ri.hr_operator_ids_list = [
          old_to_new_id.get(oid, oid) for oid in ri.hr_operator_ids_list
      ]

    # recruited_id (Set[int])
    if hasattr(ri, 'recruited_id') and ri.recruited_id:
      # 如果ri.recruited_id是int类型的话，则先转为set
      if isinstance(ri.recruited_id, int):
        ri.recruited_id = {ri.recruited_id}
      ri.recruited_id = {old_to_new_id.get(oid, oid) for oid in ri.recruited_id}

    # power_operator_ids_list
    if hasattr(ri, 'power_operator_ids_list'):
      ri.power_operator_ids_list = [
          old_to_new_id.get(oid, oid) for oid in ri.power_operator_ids_list
      ]

    # main_power_facility_operator_ids (List[int] - 主力供能设施的调控员id列表)
    if hasattr(ri, 'main_power_facility_operator_ids'):
      ri.main_power_facility_operator_ids = [
          old_to_new_id.get(oid, oid)
          for oid in ri.main_power_facility_operator_ids
      ]

    # maintenance_place (Dict[int, str] - 角色id:地点)
    if hasattr(ri, 'maintenance_place'):
      old_maint = ri.maintenance_place.copy()
      ri.maintenance_place = {}
      for old_id, place in old_maint.items():
        new_id = old_to_new_id.get(old_id, old_id)
        ri.maintenance_place[new_id] = place

    # equipment_maintain_operator_ids (List[int] - 手动选择的装备维护对象干员id列表)
    if hasattr(ri, 'equipment_maintain_operator_ids'):
      ri.equipment_maintain_operator_ids = [
          old_to_new_id.get(oid, oid)
          for oid in ri.equipment_maintain_operator_ids
      ]

    # milk_in_fridge (Dict[int, int] - 干员id:母乳ml存量)
    if hasattr(ri, 'milk_in_fridge'):
      old_milk = ri.milk_in_fridge.copy()
      ri.milk_in_fridge = {}
      for old_id, value in old_milk.items():
        new_id = old_to_new_id.get(old_id, old_id)
        ri.milk_in_fridge[new_id] = value

    # medical_clinic_doctor_ids
    if hasattr(ri, 'medical_clinic_doctor_ids'):
      ri.medical_clinic_doctor_ids = [
          old_to_new_id.get(oid, oid) for oid in ri.medical_clinic_doctor_ids
      ]

    # medical_hospital_doctor_ids
    if hasattr(ri, 'medical_hospital_doctor_ids'):
      ri.medical_hospital_doctor_ids = [
          old_to_new_id.get(oid, oid) for oid in ri.medical_hospital_doctor_ids
      ]

    # book_borrow_dict (Dict[int, int])
    if hasattr(ri, 'book_borrow_dict'):
      old_borrow = ri.book_borrow_dict.copy()
      ri.book_borrow_dict = {}
      for book_id, old_id in old_borrow.items():
        if old_id != -1:
          ri.book_borrow_dict[book_id] = old_to_new_id.get(old_id, old_id)
        else:
          ri.book_borrow_dict[book_id] = old_id

    # trade_operator_ids_list
    if hasattr(ri, 'trade_operator_ids_list'):
      ri.trade_operator_ids_list = [
          old_to_new_id.get(oid, oid) for oid in ri.trade_operator_ids_list
      ]

    # resource_type_main_trader (Dict[str, int])
    if hasattr(ri, 'resource_type_main_trader'):
      old_traders = ri.resource_type_main_trader.copy()
      ri.resource_type_main_trader = {}
      for key, old_id in old_traders.items():
        ri.resource_type_main_trader[key] = old_to_new_id.get(old_id, old_id)

    # assembly_line (Dict[int, List])
    if hasattr(ri, 'assembly_line'):
      for line_id, line_data in ri.assembly_line.items():
        line_data = normalize_line_chara_id_data(line_data, 1, 5)
        ri.assembly_line[line_id] = line_data
        if line_data[1] != 0:
          line_data[1] = old_to_new_id.get(line_data[1], line_data[1])

    # production_worker_ids
    if hasattr(ri, 'production_worker_ids'):
      ri.production_worker_ids = [
          old_to_new_id.get(oid, oid) for oid in ri.production_worker_ids
      ]

    # visitor_info (Dict[int, datetime])
    if hasattr(ri, 'visitor_info'):
      old_visitors = ri.visitor_info.copy()
      ri.visitor_info = {}
      for old_id, value in old_visitors.items():
        new_id = old_to_new_id.get(old_id, old_id)
        ri.visitor_info[new_id] = value

    # invite_visitor
    if hasattr(ri, 'invite_visitor') and ri.invite_visitor:
      ri.invite_visitor[0] = normalize_single_character_id(
          ri.invite_visitor[0], 0
      )
      ri.invite_visitor[0] = old_to_new_id.get(
          ri.invite_visitor[0], ri.invite_visitor[0]
      )

    # diplomat_of_country (Dict[int, List])
    if hasattr(ri, 'diplomat_of_country'):
      for _country_id, data in ri.diplomat_of_country.items():
        if len(data) > 0:
          data[0] = normalize_single_character_id(data[0], 0)
        if len(data) > 0 and data[0] != 0:
          data[0] = old_to_new_id.get(data[0], data[0])

    # ongoing_field_commissions (Dict[int, List])
    if hasattr(ri, 'ongoing_field_commissions'):
      for _commission_id, data in ri.ongoing_field_commissions.items():
        if len(data) > 0 and isinstance(data[0], list):
          data[0] = [old_to_new_id.get(oid, oid) for oid in data[0]]

    # herb_garden_line (Dict[int, List])
    if hasattr(ri, 'herb_garden_line'):
      for line_id, line_data in ri.herb_garden_line.items():
        line_data = normalize_line_chara_id_data(line_data, 1, 5)
        ri.herb_garden_line[line_id] = line_data
        if line_data[1] != 0:
          line_data[1] = old_to_new_id.get(line_data[1], line_data[1])

    # herb_garden_operator_ids
    if hasattr(ri, 'herb_garden_operator_ids'):
      ri.herb_garden_operator_ids = [
          old_to_new_id.get(oid, oid) for oid in ri.herb_garden_operator_ids
      ]

    # green_house_line (Dict[int, List])
    if hasattr(ri, 'green_house_line'):
      for line_id, line_data in ri.green_house_line.items():
        line_data = normalize_line_chara_id_data(line_data, 1, 5)
        ri.green_house_line[line_id] = line_data
        if line_data[1] != 0:
          line_data[1] = old_to_new_id.get(line_data[1], line_data[1])

    # green_house_operator_ids
    if hasattr(ri, 'green_house_operator_ids'):
      ri.green_house_operator_ids = [
          old_to_new_id.get(oid, oid) for oid in ri.green_house_operator_ids
      ]

    # current_warden_id
    if hasattr(ri, 'current_warden_id') and ri.current_warden_id != 0:
      ri.current_warden_id = normalize_single_character_id(
          ri.current_warden_id, 0
      )
      ri.current_warden_id = old_to_new_id.get(
          ri.current_warden_id, ri.current_warden_id
      )

    # current_prisoners (Dict[int, List])
    if hasattr(ri, 'current_prisoners'):
      old_prisoners = ri.current_prisoners.copy()
      ri.current_prisoners = {}
      for old_id, value in old_prisoners.items():
        new_id = old_to_new_id.get(old_id, old_id)
        ri.current_prisoners[new_id] = value

    # maintenance_equipment_chara_id (Dict[int, int])
    if hasattr(ri, 'maintenance_equipment_chara_id'):
      old_maint_eq = ri.maintenance_equipment_chara_id.copy()
      ri.maintenance_equipment_chara_id = {}
      for old_id, old_target in old_maint_eq.items():
        new_id = old_to_new_id.get(old_id, old_id)
        new_target = old_to_new_id.get(old_target, old_target)
        ri.maintenance_equipment_chara_id[new_id] = new_target

    # urine_in_fridge (Dict[int, int])
    if hasattr(ri, 'urine_in_fridge'):
      old_urine = ri.urine_in_fridge.copy()
      ri.urine_in_fridge = {}
      for old_id, value in old_urine.items():
        new_id = old_to_new_id.get(old_id, old_id)
        ri.urine_in_fridge[new_id] = value

    # today_physical_examination_chara_id_dict (Dict[int, set])
    if hasattr(ri, 'today_physical_examination_chara_id_dict'):
      old_exam = ri.today_physical_examination_chara_id_dict.copy()
      ri.today_physical_examination_chara_id_dict = {}
      for old_id, value in old_exam.items():
        new_id = old_to_new_id.get(old_id, old_id)
        ri.today_physical_examination_chara_id_dict[new_id] = value

    # examined_operator_ids (Set[int])
    if hasattr(ri, 'examined_operator_ids'):
      ri.examined_operator_ids = {
          old_to_new_id.get(oid, oid) for oid in ri.examined_operator_ids
      }

    # waiting_for_exam_operator_ids (Set[int])
    if hasattr(ri, 'waiting_for_exam_operator_ids'):
      ri.waiting_for_exam_operator_ids = {
          old_to_new_id.get(oid, oid)
          for oid in ri.waiting_for_exam_operator_ids
      }

    # manually_selected_exam_operator_ids (Set[int])
    if hasattr(ri, 'manually_selected_exam_operator_ids'):
      ri.manually_selected_exam_operator_ids = {
          old_to_new_id.get(oid, oid)
          for oid in ri.manually_selected_exam_operator_ids
      }

    # medical_doctor_specializations (Dict[str, Dict[str, List[int]]])
    if hasattr(ri, 'medical_doctor_specializations'):
      for _pos_key, system_dict in ri.medical_doctor_specializations.items():
        for sys_key, id_list in system_dict.items():
          system_dict[sys_key] = [
              old_to_new_id.get(oid, oid) for oid in id_list
          ]

    # recruit_line (Dict[int, List]) - 招募线id:[0进度, 1策略id, 2主招聘专员id, 3效率]
    if hasattr(ri, 'recruit_line'):
      for line_id, line_data in ri.recruit_line.items():
        line_data = normalize_line_chara_id_data(line_data, 2, 4)
        ri.recruit_line[line_id] = line_data
        if line_data[2] != 0:
          line_data[2] = old_to_new_id.get(line_data[2], line_data[2])

    # all_work_npc_set (Dict[int, set]) - 工作id:干员id集合
    if hasattr(ri, 'all_work_npc_set'):
      for work_id, npc_set in ri.all_work_npc_set.items():
        if npc_set:
          ri.all_work_npc_set[work_id] = {
              old_to_new_id.get(oid, oid) for oid in npc_set
          }

  # 5.6 关系数据中的角色引用
  for _char_id, character in new_character_data.items():
    if hasattr(character, 'relationship'):
      rel = character.relationship
      # father_id
      if hasattr(rel, 'father_id') and rel.father_id > 0:
        rel.father_id = old_to_new_id.get(rel.father_id, rel.father_id)
      # mother_id
      if hasattr(rel, 'mother_id') and rel.mother_id > 0:
        rel.mother_id = old_to_new_id.get(rel.mother_id, rel.mother_id)
      # child_id_list
      if hasattr(rel, 'child_id_list'):
        rel.child_id_list = [
            old_to_new_id.get(cid, cid) for cid in rel.child_id_list
        ]
      # firend_id_list
      if hasattr(rel, 'firend_id_list'):
        rel.firend_id_list = [
            old_to_new_id.get(fid, fid) for fid in rel.firend_id_list
        ]

  # 5.7 场景数据中的角色列表
  if 'scene_data' in loaded_dict:
    for _scene_name, scene in loaded_dict['scene_data'].items():
      if hasattr(scene, 'character_list'):
        old_list = scene.character_list.copy()
        scene.character_list = set()
        for old_id in old_list:
          scene.character_list.add(old_to_new_id.get(old_id, old_id))

  # 5.8 cache级别的角色ID引用
  # forbidden_npc_id
  if 'forbidden_npc_id' in loaded_dict:
    old_forbidden = loaded_dict['forbidden_npc_id'].copy()
    loaded_dict['forbidden_npc_id'] = {
        old_to_new_id.get(oid, oid) for oid in old_forbidden
    }

  # old_character_id
  if 'old_character_id' in loaded_dict and loaded_dict['old_character_id'] != 0:
    loaded_dict['old_character_id'] = old_to_new_id.get(
        loaded_dict['old_character_id'], loaded_dict['old_character_id']
    )

  # 5.9 achievement中的角色ID引用
  if 'achievement' in loaded_dict:
    ach = loaded_dict['achievement']

    # body_report_chara_count_list (List[int]) - 出具过身体检查报告的干员id列表
    if hasattr(ach, 'body_report_chara_count_list'):
      ach.body_report_chara_count_list = [
          old_to_new_id.get(oid, oid)
          for oid in ach.body_report_chara_count_list
      ]

    # group_sex_record (Dict[int, list]) - 群交记录
    if hasattr(ach, 'group_sex_record') and ach.group_sex_record:
      # 键为记录类型，值为角色id列表
      for record_key, record_list in ach.group_sex_record.items():
        if isinstance(record_list, list):
          ach.group_sex_record[record_key] = [
              old_to_new_id.get(oid, oid) for oid in record_list
          ]

  return update_count


def migrate_character_replacement(
    loaded_dict: dict, old_to_new_id_map: dict
) -> int:
  """
  将旧角色的数据迁移到新角色，用于角色替换场景
  例如：将1478号梅捷缇克缇的数据迁移到4056号缇缇

  迁移内容：
  1. 从新角色模板创建新角色基础数据
  2. 复制旧角色的全部动态数据到新角色（除模板属性外）
  3. 更新所有引用旧角色ID的数据结构
  4. 转移玩家收藏品中的旧角色数据到新角色
  5. 删除旧角色数据

  Keyword arguments:
  loaded_dict -- 存档数据字典
  old_to_new_id_map -- 旧角色ID到新角色ID的映射字典，如 {1478: 4056}

  Returns:
      int: 成功迁移的角色数量
  """
  from Script.Design import character_handle, attr_calculation

  migrated_count = 0
  character_data = loaded_dict.get('character_data', {})
  npc_tem_data = loaded_dict.get('npc_tem_data', {})

  # 记录迁移信息用于日志
  migration_log = []

  for old_id, new_id in old_to_new_id_map.items():
    # 检查旧角色是否存在于存档中
    if old_id not in character_data:
      continue

    # 检查新角色模板是否存在于当前游戏配置中
    if new_id not in cache.npc_tem_data:
      continue

    old_character = character_data[old_id]
    new_tem = cache.npc_tem_data[new_id]
    old_name = old_character.name
    new_name = new_tem.Name

    # ========== 1. 创建新角色基础数据 ==========
    new_character = game_type.Character()

    # 从新模板设置基础属性（不迁移的属性）
    new_character.cid = new_id
    new_character.name = new_tem.Name
    new_character.adv = new_tem.AdvNpc
    new_character.sex = new_tem.Sex
    new_character.profession = new_tem.Profession
    new_character.race = new_tem.Race
    new_character.hit_point_max = new_tem.Hp
    new_character.mana_point_max = new_tem.Mp
    new_character.token_text = new_tem.Token
    new_character.dormitory = new_tem.Dormitory
    new_character.text_color = new_tem.TextColor if new_tem.TextColor else ''
    new_character.talk_size = new_tem.Talk_Size

    # 从新模板生成衣服
    new_character.cloth = attr_calculation.get_cloth_zero()
    new_character.cloth.cloth_wear = attr_calculation.get_cloth_wear_zero()
    for cloth_id in new_tem.Cloth:
      if cloth_id in game_config.config_clothing_tem:
        cloth_type = game_config.config_clothing_tem[cloth_id].clothing_type
        new_character.cloth.clothing_tem.append(cloth_id)
        new_character.cloth.cloth_wear[cloth_type].append(cloth_id)

    # ========== 2. 复制旧角色的动态数据 ==========
    # 数值属性
    new_character.hit_point = old_character.hit_point
    new_character.mana_point = old_character.mana_point
    new_character.sanity_point = old_character.sanity_point
    new_character.sanity_point_max = old_character.sanity_point_max
    new_character.eja_point = old_character.eja_point
    new_character.eja_point_max = old_character.eja_point_max
    new_character.semen_point = old_character.semen_point
    new_character.semen_point_max = old_character.semen_point_max
    new_character.tem_extra_semen_point = old_character.tem_extra_semen_point
    new_character.angry_point = old_character.angry_point
    new_character.tired_point = old_character.tired_point
    new_character.urinate_point = old_character.urinate_point
    new_character.hunger_point = old_character.hunger_point
    new_character.sleep_point = old_character.sleep_point
    new_character.desire_point = old_character.desire_point
    new_character.state = old_character.state
    if hasattr(old_character, 'last_behavior_id_list'):
      new_character.last_behavior_id_list = (
          old_character.last_behavior_id_list.copy()
          if old_character.last_behavior_id_list
          else [0]
      )
    # 如果旧的角色数据没有last_behavior_id_list，则初始化创建一个
    else:
      new_character.last_behavior_id_list = [0]

    # 字典/集合属性
    new_character.status_data = (
        old_character.status_data.copy() if old_character.status_data else {}
    )
    new_character.ability = (
        old_character.ability.copy() if old_character.ability else {}
    )
    new_character.experience = (
        old_character.experience.copy() if old_character.experience else {}
    )
    new_character.juel = old_character.juel.copy() if old_character.juel else {}
    new_character.talent = (
        old_character.talent.copy() if old_character.talent else {}
    )
    new_character.item = old_character.item.copy() if old_character.item else {}
    new_character.chara_setting = (
        old_character.chara_setting.copy()
        if hasattr(old_character, 'chara_setting')
        and old_character.chara_setting
        else {}
    )
    new_character.assistant_services = (
        old_character.assistant_services.copy()
        if hasattr(old_character, 'assistant_services')
        and old_character.assistant_services
        else {}
    )
    new_character.body_manage = (
        old_character.body_manage.copy()
        if hasattr(old_character, 'body_manage') and old_character.body_manage
        else {}
    )

    # 好感度数据（需要转换内部ID引用）
    new_character.favorability = {}
    if old_character.favorability:
      for fav_id, fav_value in old_character.favorability.items():
        new_fav_id = old_to_new_id_map.get(fav_id, fav_id)
        new_character.favorability[new_fav_id] = fav_value

    new_character.trust = old_character.trust

    # 信赖相关
    new_character.target_character_id = old_to_new_id_map.get(
        old_character.target_character_id, old_character.target_character_id
    )
    new_character.assistant_character_id = (
        old_to_new_id_map.get(
            old_character.assistant_character_id,
            old_character.assistant_character_id,
        )
        if hasattr(old_character, 'assistant_character_id')
        else 0
    )

    # 收藏角色列表（需要转换ID）
    new_character.collection_character = set()
    if (
        hasattr(old_character, 'collection_character')
        and old_character.collection_character
    ):
      for coll_id in old_character.collection_character:
        new_character.collection_character.add(
            old_to_new_id_map.get(coll_id, coll_id)
        )

    # 其他字符串属性
    new_character.nick_name = (
        old_character.nick_name if hasattr(old_character, 'nick_name') else ''
    )
    new_character.nick_name_to_pl = (
        old_character.nick_name_to_pl
        if hasattr(old_character, 'nick_name_to_pl')
        else ''
    )

    # 位置数据
    new_character.position = (
        old_character.position.copy() if old_character.position else ['0', '0']
    )
    new_character.officeroom = (
        old_character.officeroom.copy()
        if hasattr(old_character, 'officeroom') and old_character.officeroom
        else []
    )
    new_character.permanent_dormitory = getattr(
        old_character,
        'permanent_dormitory',
        getattr(old_character, 'pre_dormitory', ''),
    )

    # 时间相关
    new_character.birthday = old_character.birthday
    new_character.last_hunger_time = (
        old_character.last_hunger_time
        if hasattr(old_character, 'last_hunger_time')
        else datetime.datetime(1, 1, 1)
    )

    # 复杂对象属性 - 直接复制引用后更新内部ID
    new_character.behavior = old_character.behavior
    new_character.second_behavior = (
        old_character.second_behavior.copy()
        if hasattr(old_character, 'second_behavior')
        and old_character.second_behavior
        else {}
    )
    new_character.must_settle_second_behavior_id_list = (
        old_character.must_settle_second_behavior_id_list.copy()
        if hasattr(old_character, 'must_settle_second_behavior_id_list')
        and old_character.must_settle_second_behavior_id_list
        else []
    )
    new_character.must_show_second_behavior_id_list = (
        old_character.must_show_second_behavior_id_list.copy()
        if hasattr(old_character, 'must_show_second_behavior_id_list')
        and old_character.must_show_second_behavior_id_list
        else []
    )
    new_character.event = old_character.event
    new_character.food_bag = (
        old_character.food_bag.copy()
        if hasattr(old_character, 'food_bag') and old_character.food_bag
        else {}
    )
    new_character.dirty = old_character.dirty
    new_character.h_state = old_character.h_state
    new_character.pl_ability = (
        old_character.pl_ability
        if hasattr(old_character, 'pl_ability')
        else game_type.PLAYER_ABILITY()
    )
    new_character.pl_collection = (
        old_character.pl_collection
        if hasattr(old_character, 'pl_collection')
        else game_type.PLAYER_COLLECTION()
    )
    new_character.sp_flag = old_character.sp_flag
    new_character.action_info = old_character.action_info
    new_character.work = old_character.work
    new_character.entertainment = (
        old_character.entertainment
        if hasattr(old_character, 'entertainment')
        else game_type.CHARA_ENTERTAINMENT()
    )
    new_character.pregnancy = (
        old_character.pregnancy
        if hasattr(old_character, 'pregnancy')
        else game_type.PREGNANCY()
    )
    new_character.hypnosis = (
        old_character.hypnosis
        if hasattr(old_character, 'hypnosis')
        else game_type.HYPNOSIS()
    )
    new_character.author_flag = (
        old_character.author_flag
        if hasattr(old_character, 'author_flag')
        else game_type.AUTHOR_FLAG()
    )

    # 关系数据 - 复制并转换ID
    new_character.relationship = (
        old_character.relationship
        if hasattr(old_character, 'relationship')
        else game_type.RELATIONSHIP()
    )
    # 更新relationship中的势力和出身地为新模板值
    new_character.relationship.nation = new_tem.Nation
    new_character.relationship.birthplace = new_tem.Birthplace
    # 转换关系中的角色ID
    if (
        hasattr(new_character.relationship, 'father_id')
        and new_character.relationship.father_id > 0
    ):
      new_character.relationship.father_id = old_to_new_id_map.get(
          new_character.relationship.father_id,
          new_character.relationship.father_id,
      )
    if (
        hasattr(new_character.relationship, 'mother_id')
        and new_character.relationship.mother_id > 0
    ):
      new_character.relationship.mother_id = old_to_new_id_map.get(
          new_character.relationship.mother_id,
          new_character.relationship.mother_id,
      )
    if (
        hasattr(new_character.relationship, 'child_id_list')
        and new_character.relationship.child_id_list
    ):
      new_character.relationship.child_id_list = [
          old_to_new_id_map.get(cid, cid)
          for cid in new_character.relationship.child_id_list
      ]
    if (
        hasattr(new_character.relationship, 'firend_id_list')
        and new_character.relationship.firend_id_list
    ):
      new_character.relationship.firend_id_list = [
          old_to_new_id_map.get(fid, fid)
          for fid in new_character.relationship.firend_id_list
      ]

    # first_record中的角色ID转换（含first_part_sex_dict与历史周目快照）
    if hasattr(new_character, 'first_record'):
      _remap_first_record_ids(new_character.first_record, old_to_new_id_map)
    for history_record in getattr(
        new_character, 'first_record_history', {}
    ).values():
      _remap_first_record_ids(history_record, old_to_new_id_map)

    # action_info中的角色ID转换
    if hasattr(new_character, 'action_info'):
      ai = new_character.action_info
      if (
          hasattr(ai, 'ask_group_sex_refuse_chara_id_list')
          and ai.ask_group_sex_refuse_chara_id_list
      ):
        ai.ask_group_sex_refuse_chara_id_list = [
            old_to_new_id_map.get(oid, oid)
            for oid in ai.ask_group_sex_refuse_chara_id_list
        ]
      if (
          hasattr(ai, 'social_contact_last_time')
          and ai.social_contact_last_time
      ):
        old_social = ai.social_contact_last_time.copy()
        ai.social_contact_last_time = {}
        for oid, value in old_social.items():
          ai.social_contact_last_time[old_to_new_id_map.get(oid, oid)] = value
      if (
          hasattr(ai, 'social_contact_last_cut_down_time')
          and ai.social_contact_last_cut_down_time
      ):
        old_cut = ai.social_contact_last_cut_down_time.copy()
        ai.social_contact_last_cut_down_time = {}
        for oid, value in old_cut.items():
          ai.social_contact_last_cut_down_time[
              old_to_new_id_map.get(oid, oid)
          ] = value
      if (
          hasattr(ai, 'interacting_character_end_info')
          and ai.interacting_character_end_info[0] != -1
      ):
        ai.interacting_character_end_info[0] = old_to_new_id_map.get(
            ai.interacting_character_end_info[0],
            ai.interacting_character_end_info[0],
        )

    # sp_flag中的角色ID转换
    if hasattr(new_character, 'sp_flag'):
      sf = new_character.sp_flag
      if hasattr(sf, 'bagging_chara_id') and sf.bagging_chara_id != 0:
        sf.bagging_chara_id = old_to_new_id_map.get(
            sf.bagging_chara_id, sf.bagging_chara_id
        )

    # pl_ability中的角色ID转换
    if hasattr(new_character, 'pl_ability'):
      pa = new_character.pl_ability
      if (
          hasattr(pa, 'carry_chara_id_in_time_stop')
          and pa.carry_chara_id_in_time_stop != 0
      ):
        pa.carry_chara_id_in_time_stop = old_to_new_id_map.get(
            pa.carry_chara_id_in_time_stop, pa.carry_chara_id_in_time_stop
        )
      if (
          hasattr(pa, 'free_in_time_stop_chara_id')
          and pa.free_in_time_stop_chara_id != 0
      ):
        pa.free_in_time_stop_chara_id = old_to_new_id_map.get(
            pa.free_in_time_stop_chara_id, pa.free_in_time_stop_chara_id
        )

    # h_state中的角色ID转换
    if hasattr(new_character, 'h_state') and hasattr(
        new_character.h_state, 'group_sex_body_template_dict'
    ):
      if new_character.h_state.group_sex_body_template_dict:
        old_group = new_character.h_state.group_sex_body_template_dict.copy()
        new_character.h_state.group_sex_body_template_dict = {}
        for oid, value in old_group.items():
          new_character.h_state.group_sex_body_template_dict[
              old_to_new_id_map.get(oid, oid)
          ] = value
        # 转换group_sex_body_template_dict中serve_data的角色ID
        for (
            _char_id,
            serve_data,
        ) in new_character.h_state.group_sex_body_template_dict.items():
          if (
              isinstance(serve_data, list)
              and len(serve_data) > 0
              and isinstance(serve_data[0], list)
          ):
            serve_data[0] = [
                old_to_new_id_map.get(oid, oid) if oid != -1 else oid
                for oid in serve_data[0]
            ]

    # ========== 3. 将新角色添加到character_data ==========
    character_data[new_id] = new_character

    # ========== 4. 更新npc_id_got ==========
    if 'npc_id_got' in loaded_dict:
      if old_id in loaded_dict['npc_id_got']:
        loaded_dict['npc_id_got'].discard(old_id)
        loaded_dict['npc_id_got'].add(new_id)

    # ========== 5. 更新npc_tem_data ==========
    if old_id in npc_tem_data:
      del npc_tem_data[old_id]
    npc_tem_data[new_id] = cache.npc_tem_data[new_id]

    # 记录迁移日志
    migration_log.append((old_name, new_name, old_id, new_id))
    migrated_count += 1

  # 如果没有迁移任何角色，直接返回
  if migrated_count == 0:
    return 0

  # ========== 6. 更新所有角色中对旧ID的引用 ==========
  for _char_id, character in character_data.items():
    # 好感度字典
    if hasattr(character, 'favorability') and character.favorability:
      old_fav = character.favorability.copy()
      character.favorability = {}
      for fav_id, value in old_fav.items():
        character.favorability[old_to_new_id_map.get(fav_id, fav_id)] = value

    # target_character_id
    if hasattr(character, 'target_character_id'):
      character.target_character_id = old_to_new_id_map.get(
          character.target_character_id, character.target_character_id
      )

    # assistant_character_id
    if hasattr(character, 'assistant_character_id'):
      character.assistant_character_id = old_to_new_id_map.get(
          character.assistant_character_id, character.assistant_character_id
      )

    # collection_character
    if (
        hasattr(character, 'collection_character')
        and character.collection_character
    ):
      old_coll = character.collection_character.copy()
      character.collection_character = set()
      for coll_id in old_coll:
        character.collection_character.add(
            old_to_new_id_map.get(coll_id, coll_id)
        )

    # first_record中的角色ID（含first_part_sex_dict与历史周目快照）
    if hasattr(character, 'first_record'):
      _remap_first_record_ids(character.first_record, old_to_new_id_map)
    for history_record in getattr(
        character, 'first_record_history', {}
    ).values():
      _remap_first_record_ids(history_record, old_to_new_id_map)

    # action_info中的角色ID
    if hasattr(character, 'action_info'):
      ai = character.action_info
      if (
          hasattr(ai, 'ask_group_sex_refuse_chara_id_list')
          and ai.ask_group_sex_refuse_chara_id_list
      ):
        ai.ask_group_sex_refuse_chara_id_list = [
            old_to_new_id_map.get(oid, oid)
            for oid in ai.ask_group_sex_refuse_chara_id_list
        ]
      if (
          hasattr(ai, 'social_contact_last_time')
          and ai.social_contact_last_time
      ):
        old_social = ai.social_contact_last_time.copy()
        ai.social_contact_last_time = {}
        for oid, value in old_social.items():
          ai.social_contact_last_time[old_to_new_id_map.get(oid, oid)] = value
      if (
          hasattr(ai, 'social_contact_last_cut_down_time')
          and ai.social_contact_last_cut_down_time
      ):
        old_cut = ai.social_contact_last_cut_down_time.copy()
        ai.social_contact_last_cut_down_time = {}
        for oid, value in old_cut.items():
          ai.social_contact_last_cut_down_time[
              old_to_new_id_map.get(oid, oid)
          ] = value
      if (
          hasattr(ai, 'interacting_character_end_info')
          and ai.interacting_character_end_info[0] != -1
      ):
        ai.interacting_character_end_info[0] = old_to_new_id_map.get(
            ai.interacting_character_end_info[0],
            ai.interacting_character_end_info[0],
        )

    # sp_flag中的角色ID
    if hasattr(character, 'sp_flag'):
      sf = character.sp_flag
      if hasattr(sf, 'bagging_chara_id') and sf.bagging_chara_id != 0:
        sf.bagging_chara_id = old_to_new_id_map.get(
            sf.bagging_chara_id, sf.bagging_chara_id
        )

    # pl_ability中的角色ID（仅玩家有）
    if hasattr(character, 'pl_ability'):
      pa = character.pl_ability
      if (
          hasattr(pa, 'carry_chara_id_in_time_stop')
          and pa.carry_chara_id_in_time_stop != 0
      ):
        pa.carry_chara_id_in_time_stop = old_to_new_id_map.get(
            pa.carry_chara_id_in_time_stop, pa.carry_chara_id_in_time_stop
        )
      if (
          hasattr(pa, 'free_in_time_stop_chara_id')
          and pa.free_in_time_stop_chara_id != 0
      ):
        pa.free_in_time_stop_chara_id = old_to_new_id_map.get(
            pa.free_in_time_stop_chara_id, pa.free_in_time_stop_chara_id
        )

    # relationship中的角色ID
    if hasattr(character, 'relationship'):
      rel = character.relationship
      if hasattr(rel, 'father_id') and rel.father_id > 0:
        rel.father_id = old_to_new_id_map.get(rel.father_id, rel.father_id)
      if hasattr(rel, 'mother_id') and rel.mother_id > 0:
        rel.mother_id = old_to_new_id_map.get(rel.mother_id, rel.mother_id)
      if hasattr(rel, 'child_id_list') and rel.child_id_list:
        rel.child_id_list = [
            old_to_new_id_map.get(cid, cid) for cid in rel.child_id_list
        ]
      if hasattr(rel, 'firend_id_list') and rel.firend_id_list:
        rel.firend_id_list = [
            old_to_new_id_map.get(fid, fid) for fid in rel.firend_id_list
        ]

    # h_state中的角色ID
    if hasattr(character, 'h_state') and hasattr(
        character.h_state, 'group_sex_body_template_dict'
    ):
      if character.h_state.group_sex_body_template_dict:
        old_group = character.h_state.group_sex_body_template_dict.copy()
        character.h_state.group_sex_body_template_dict = {}
        for oid, value in old_group.items():
          character.h_state.group_sex_body_template_dict[
              old_to_new_id_map.get(oid, oid)
          ] = value
        for (
            cid,
            serve_data,
        ) in character.h_state.group_sex_body_template_dict.items():
          if (
              isinstance(serve_data, list)
              and len(serve_data) > 0
              and isinstance(serve_data[0], list)
          ):
            serve_data[0] = [
                old_to_new_id_map.get(oid, oid) if oid != -1 else oid
                for oid in serve_data[0]
            ]

  # ========== 7. 更新玩家收藏品 (pl_collection) ==========
  if 0 in character_data:
    pl_data = character_data[0]
    if hasattr(pl_data, 'pl_collection'):
      pc = pl_data.pl_collection

      # token_list
      if hasattr(pc, 'token_list') and pc.token_list:
        old_tokens = pc.token_list.copy()
        for old_id, new_id in old_to_new_id_map.items():
          if old_id in old_tokens:
            pc.token_list[new_id] = old_tokens[old_id]
            del pc.token_list[old_id]

      # first_panties
      if hasattr(pc, 'first_panties') and pc.first_panties:
        old_panties = pc.first_panties.copy()
        for old_id, new_id in old_to_new_id_map.items():
          if old_id in old_panties:
            pc.first_panties[new_id] = old_panties[old_id]
            del pc.first_panties[old_id]

      # npc_panties
      if hasattr(pc, 'npc_panties') and pc.npc_panties:
        old_npc_panties = pc.npc_panties.copy()
        for old_id, new_id in old_to_new_id_map.items():
          if old_id in old_npc_panties:
            pc.npc_panties[new_id] = old_npc_panties[old_id]
            del pc.npc_panties[old_id]

      # npc_socks
      if hasattr(pc, 'npc_socks') and pc.npc_socks:
        old_npc_socks = pc.npc_socks.copy()
        for old_id, new_id in old_to_new_id_map.items():
          if old_id in old_npc_socks:
            pc.npc_socks[new_id] = old_npc_socks[old_id]
            del pc.npc_socks[old_id]

      # npc_panties_tem
      if hasattr(pc, 'npc_panties_tem') and pc.npc_panties_tem:
        old_panties_tem = pc.npc_panties_tem.copy()
        for old_id, new_id in old_to_new_id_map.items():
          if old_id in old_panties_tem:
            pc.npc_panties_tem[new_id] = old_panties_tem[old_id]
            del pc.npc_panties_tem[old_id]

      # npc_socks_tem
      if hasattr(pc, 'npc_socks_tem') and pc.npc_socks_tem:
        old_socks_tem = pc.npc_socks_tem.copy()
        for old_id, new_id in old_to_new_id_map.items():
          if old_id in old_socks_tem:
            pc.npc_socks_tem[new_id] = old_socks_tem[old_id]
            del pc.npc_socks_tem[old_id]

      # eqip_token[1] - 已装备信物的干员id列表
      if hasattr(pc, 'eqip_token') and len(pc.eqip_token) > 1:
        pc.eqip_token[1] = [
            old_to_new_id_map.get(oid, oid) for oid in pc.eqip_token[1]
        ]

      # milk_total
      if hasattr(pc, 'milk_total') and pc.milk_total:
        old_milk = pc.milk_total.copy()
        for old_id, new_id in old_to_new_id_map.items():
          if old_id in old_milk:
            pc.milk_total[new_id] = old_milk[old_id]
            del pc.milk_total[old_id]

      # urine_total
      if hasattr(pc, 'urine_total') and pc.urine_total:
        old_urine = pc.urine_total.copy()
        for old_id, new_id in old_to_new_id_map.items():
          if old_id in old_urine:
            pc.urine_total[new_id] = old_urine[old_id]
            del pc.urine_total[old_id]

  # ========== 8. 更新rhodes_island中的角色引用 ==========
  if 'rhodes_island' in loaded_dict:
    ri = loaded_dict['rhodes_island']

    # hr_operator_ids_list
    if hasattr(ri, 'hr_operator_ids_list'):
      ri.hr_operator_ids_list = [
          old_to_new_id_map.get(oid, oid) for oid in ri.hr_operator_ids_list
      ]

    # recruited_id
    if hasattr(ri, 'recruited_id') and ri.recruited_id:
      old_recruited = ri.recruited_id.copy()
      ri.recruited_id = set()
      for oid in old_recruited:
        ri.recruited_id.add(old_to_new_id_map.get(oid, oid))

    # power_operator_ids_list
    if hasattr(ri, 'power_operator_ids_list'):
      ri.power_operator_ids_list = [
          old_to_new_id_map.get(oid, oid) for oid in ri.power_operator_ids_list
      ]

    # main_power_facility_operator_ids
    if hasattr(ri, 'main_power_facility_operator_ids'):
      ri.main_power_facility_operator_ids = [
          old_to_new_id_map.get(oid, oid)
          for oid in ri.main_power_facility_operator_ids
      ]

    # maintenance_place
    if hasattr(ri, 'maintenance_place') and ri.maintenance_place:
      old_maint = ri.maintenance_place.copy()
      ri.maintenance_place = {}
      for oid, place in old_maint.items():
        ri.maintenance_place[old_to_new_id_map.get(oid, oid)] = place

    # equipment_maintain_operator_ids
    if hasattr(ri, 'equipment_maintain_operator_ids'):
      ri.equipment_maintain_operator_ids = [
          old_to_new_id_map.get(oid, oid)
          for oid in ri.equipment_maintain_operator_ids
      ]

    # milk_in_fridge
    if hasattr(ri, 'milk_in_fridge') and ri.milk_in_fridge:
      old_milk = ri.milk_in_fridge.copy()
      ri.milk_in_fridge = {}
      for oid, value in old_milk.items():
        ri.milk_in_fridge[old_to_new_id_map.get(oid, oid)] = value

    # medical_clinic_doctor_ids
    if hasattr(ri, 'medical_clinic_doctor_ids'):
      ri.medical_clinic_doctor_ids = [
          old_to_new_id_map.get(oid, oid)
          for oid in ri.medical_clinic_doctor_ids
      ]

    # medical_hospital_doctor_ids
    if hasattr(ri, 'medical_hospital_doctor_ids'):
      ri.medical_hospital_doctor_ids = [
          old_to_new_id_map.get(oid, oid)
          for oid in ri.medical_hospital_doctor_ids
      ]

    # book_borrow_dict
    if hasattr(ri, 'book_borrow_dict') and ri.book_borrow_dict:
      old_borrow = ri.book_borrow_dict.copy()
      ri.book_borrow_dict = {}
      for book_id, old_id in old_borrow.items():
        if old_id != -1:
          ri.book_borrow_dict[book_id] = old_to_new_id_map.get(old_id, old_id)
        else:
          ri.book_borrow_dict[book_id] = old_id

    # trade_operator_ids_list
    if hasattr(ri, 'trade_operator_ids_list'):
      ri.trade_operator_ids_list = [
          old_to_new_id_map.get(oid, oid) for oid in ri.trade_operator_ids_list
      ]

    # resource_type_main_trader
    if (
        hasattr(ri, 'resource_type_main_trader')
        and ri.resource_type_main_trader
    ):
      old_traders = ri.resource_type_main_trader.copy()
      ri.resource_type_main_trader = {}
      for key, oid in old_traders.items():
        ri.resource_type_main_trader[key] = old_to_new_id_map.get(oid, oid)

    # assembly_line
    if hasattr(ri, 'assembly_line') and ri.assembly_line:
      for line_id, line_data in ri.assembly_line.items():
        line_data = normalize_line_chara_id_data(line_data, 1, 5)
        ri.assembly_line[line_id] = line_data
        if line_data[1] != 0:
          line_data[1] = old_to_new_id_map.get(line_data[1], line_data[1])

    # production_worker_ids
    if hasattr(ri, 'production_worker_ids'):
      ri.production_worker_ids = [
          old_to_new_id_map.get(oid, oid) for oid in ri.production_worker_ids
      ]

    # visitor_info
    if hasattr(ri, 'visitor_info') and ri.visitor_info:
      old_visitors = ri.visitor_info.copy()
      ri.visitor_info = {}
      for oid, value in old_visitors.items():
        ri.visitor_info[old_to_new_id_map.get(oid, oid)] = value

    # invite_visitor
    if hasattr(ri, 'invite_visitor') and ri.invite_visitor:
      ri.invite_visitor[0] = normalize_single_character_id(
          ri.invite_visitor[0], 0
      )
      ri.invite_visitor[0] = old_to_new_id_map.get(
          ri.invite_visitor[0], ri.invite_visitor[0]
      )

    # diplomat_of_country
    if hasattr(ri, 'diplomat_of_country') and ri.diplomat_of_country:
      for _country_id, data in ri.diplomat_of_country.items():
        if len(data) > 0:
          data[0] = normalize_single_character_id(data[0], 0)
        if len(data) > 0 and data[0] != 0:
          data[0] = old_to_new_id_map.get(data[0], data[0])

    # ongoing_field_commissions
    if (
        hasattr(ri, 'ongoing_field_commissions')
        and ri.ongoing_field_commissions
    ):
      for _commission_id, data in ri.ongoing_field_commissions.items():
        if len(data) > 0 and isinstance(data[0], list):
          data[0] = [old_to_new_id_map.get(oid, oid) for oid in data[0]]

    # herb_garden_line
    if hasattr(ri, 'herb_garden_line') and ri.herb_garden_line:
      for line_id, line_data in ri.herb_garden_line.items():
        line_data = normalize_line_chara_id_data(line_data, 1, 5)
        ri.herb_garden_line[line_id] = line_data
        if line_data[1] != 0:
          line_data[1] = old_to_new_id_map.get(line_data[1], line_data[1])

    # herb_garden_operator_ids
    if hasattr(ri, 'herb_garden_operator_ids'):
      ri.herb_garden_operator_ids = [
          old_to_new_id_map.get(oid, oid) for oid in ri.herb_garden_operator_ids
      ]

    # green_house_line
    if hasattr(ri, 'green_house_line') and ri.green_house_line:
      for line_id, line_data in ri.green_house_line.items():
        line_data = normalize_line_chara_id_data(line_data, 1, 5)
        ri.green_house_line[line_id] = line_data
        if line_data[1] != 0:
          line_data[1] = old_to_new_id_map.get(line_data[1], line_data[1])

    # green_house_operator_ids
    if hasattr(ri, 'green_house_operator_ids'):
      ri.green_house_operator_ids = [
          old_to_new_id_map.get(oid, oid) for oid in ri.green_house_operator_ids
      ]

    # current_warden_id
    if hasattr(ri, 'current_warden_id') and ri.current_warden_id != 0:
      ri.current_warden_id = normalize_single_character_id(
          ri.current_warden_id, 0
      )
      ri.current_warden_id = old_to_new_id_map.get(
          ri.current_warden_id, ri.current_warden_id
      )

    # current_prisoners
    if hasattr(ri, 'current_prisoners') and ri.current_prisoners:
      old_prisoners = ri.current_prisoners.copy()
      ri.current_prisoners = {}
      for oid, value in old_prisoners.items():
        ri.current_prisoners[old_to_new_id_map.get(oid, oid)] = value

    # maintenance_equipment_chara_id
    if (
        hasattr(ri, 'maintenance_equipment_chara_id')
        and ri.maintenance_equipment_chara_id
    ):
      old_maint_eq = ri.maintenance_equipment_chara_id.copy()
      ri.maintenance_equipment_chara_id = {}
      for oid, old_target in old_maint_eq.items():
        new_id = old_to_new_id_map.get(oid, oid)
        new_target = old_to_new_id_map.get(old_target, old_target)
        ri.maintenance_equipment_chara_id[new_id] = new_target

    # urine_in_fridge
    if hasattr(ri, 'urine_in_fridge') and ri.urine_in_fridge:
      old_urine = ri.urine_in_fridge.copy()
      ri.urine_in_fridge = {}
      for oid, value in old_urine.items():
        ri.urine_in_fridge[old_to_new_id_map.get(oid, oid)] = value

    # today_physical_examination_chara_id_dict
    if (
        hasattr(ri, 'today_physical_examination_chara_id_dict')
        and ri.today_physical_examination_chara_id_dict
    ):
      old_exam = ri.today_physical_examination_chara_id_dict.copy()
      ri.today_physical_examination_chara_id_dict = {}
      for oid, value in old_exam.items():
        ri.today_physical_examination_chara_id_dict[
            old_to_new_id_map.get(oid, oid)
        ] = value

    # examined_operator_ids
    if hasattr(ri, 'examined_operator_ids') and ri.examined_operator_ids:
      old_examined = ri.examined_operator_ids.copy()
      ri.examined_operator_ids = set()
      for oid in old_examined:
        ri.examined_operator_ids.add(old_to_new_id_map.get(oid, oid))

    # waiting_for_exam_operator_ids
    if (
        hasattr(ri, 'waiting_for_exam_operator_ids')
        and ri.waiting_for_exam_operator_ids
    ):
      old_waiting = ri.waiting_for_exam_operator_ids.copy()
      ri.waiting_for_exam_operator_ids = set()
      for oid in old_waiting:
        ri.waiting_for_exam_operator_ids.add(old_to_new_id_map.get(oid, oid))

    # manually_selected_exam_operator_ids
    if (
        hasattr(ri, 'manually_selected_exam_operator_ids')
        and ri.manually_selected_exam_operator_ids
    ):
      old_manual = ri.manually_selected_exam_operator_ids.copy()
      ri.manually_selected_exam_operator_ids = set()
      for oid in old_manual:
        ri.manually_selected_exam_operator_ids.add(
            old_to_new_id_map.get(oid, oid)
        )

    # medical_doctor_specializations
    if (
        hasattr(ri, 'medical_doctor_specializations')
        and ri.medical_doctor_specializations
    ):
      for _pos_key, system_dict in ri.medical_doctor_specializations.items():
        for sys_key, id_list in system_dict.items():
          system_dict[sys_key] = [
              old_to_new_id_map.get(oid, oid) for oid in id_list
          ]

    # recruit_line
    if hasattr(ri, 'recruit_line') and ri.recruit_line:
      for line_id, line_data in ri.recruit_line.items():
        line_data = normalize_line_chara_id_data(line_data, 2, 4)
        ri.recruit_line[line_id] = line_data
        if line_data[2] != 0:
          line_data[2] = old_to_new_id_map.get(line_data[2], line_data[2])

    # all_work_npc_set
    if hasattr(ri, 'all_work_npc_set') and ri.all_work_npc_set:
      for work_id, npc_set in ri.all_work_npc_set.items():
        if npc_set:
          new_set = set()
          for oid in npc_set:
            new_set.add(old_to_new_id_map.get(oid, oid))
          ri.all_work_npc_set[work_id] = new_set

  # ========== 9. 更新场景数据中的角色列表 ==========
  if 'scene_data' in loaded_dict:
    for _scene_name, scene in loaded_dict['scene_data'].items():
      if hasattr(scene, 'character_list') and scene.character_list:
        old_list = scene.character_list.copy()
        scene.character_list = set()
        for oid in old_list:
          scene.character_list.add(old_to_new_id_map.get(oid, oid))

  # ========== 10. 更新其他cache级别的角色ID引用 ==========
  # forbidden_npc_id
  if 'forbidden_npc_id' in loaded_dict and loaded_dict['forbidden_npc_id']:
    old_forbidden = loaded_dict['forbidden_npc_id'].copy()
    loaded_dict['forbidden_npc_id'] = set()
    for oid in old_forbidden:
      loaded_dict['forbidden_npc_id'].add(old_to_new_id_map.get(oid, oid))

  # old_character_id
  if 'old_character_id' in loaded_dict and loaded_dict['old_character_id'] != 0:
    loaded_dict['old_character_id'] = old_to_new_id_map.get(
        loaded_dict['old_character_id'], loaded_dict['old_character_id']
    )

  # ========== 11. 更新achievement中的角色ID引用 ==========
  if 'achievement' in loaded_dict:
    ach = loaded_dict['achievement']

    # body_report_chara_count_list
    if (
        hasattr(ach, 'body_report_chara_count_list')
        and ach.body_report_chara_count_list
    ):
      ach.body_report_chara_count_list = [
          old_to_new_id_map.get(oid, oid)
          for oid in ach.body_report_chara_count_list
      ]

    # group_sex_record
    if hasattr(ach, 'group_sex_record') and ach.group_sex_record:
      for record_key, record_list in ach.group_sex_record.items():
        if isinstance(record_list, list):
          ach.group_sex_record[record_key] = [
              old_to_new_id_map.get(oid, oid) for oid in record_list
          ]

  # ========== 12. 删除旧角色数据 ==========
  for old_id in old_to_new_id_map.keys():
    if old_id in character_data:
      del character_data[old_id]

  return migrated_count


def update_tem_character(loaded_dict: dict[str, Any]) -> int:
  """
  更新角色预设
  Keyword arguments:
  loaded_dict -- 存档数据
  """

  update_count = 0

  # cache.npc_tem_data 现在是Dict，直接使用
  cache_dict = dict(cache.npc_tem_data)

  # 更新loaded_dict["npc_tem_data"]，用新的角色预设属性代替旧的属性
  for adv_id, now_npc_tem_data in list(loaded_dict['npc_tem_data'].items()):
    # 修正深靛的序号错误
    if now_npc_tem_data.AdvNpc == 496 and 469 in cache_dict:
      loaded_dict['npc_tem_data'][469] = cache_dict[469]
      if adv_id != 469:
        del loaded_dict['npc_tem_data'][adv_id]
      update_count += 1
      del cache_dict[469]
      continue
    # 修正阿玛雅的序号错误
    if (
        now_npc_tem_data.Name == '阿玛雅'
        and now_npc_tem_data.AdvNpc == 450
        and 448 in cache_dict
    ):
      loaded_dict['npc_tem_data'][448] = cache_dict[448]
      if adv_id != 448:
        del loaded_dict['npc_tem_data'][adv_id]
      update_count += 1
      del cache_dict[448]
      continue
    if now_npc_tem_data.AdvNpc in cache_dict:
      # 更新模板
      loaded_dict['npc_tem_data'][adv_id] = cache_dict[now_npc_tem_data.AdvNpc]
      # 从cache_dict中移除已经使用的元素
      del cache_dict[now_npc_tem_data.AdvNpc]

  # 将剩余的元素添加到loaded_dict["npc_tem_data"]
  for adv_id, tem_data in cache_dict.items():
    loaded_dict['npc_tem_data'][adv_id] = tem_data
  update_count += len(cache_dict)

  # 更新新增角色
  update_count += update_new_character(loaded_dict)

  # 修正角色数据中缺失模板的情况
  for _key, value in loaded_dict['character_data'].items():
    # 跳过玩家
    if value.cid == 0:
      continue
    # 检查角色的adv是否有对应的模板
    if value.adv not in loaded_dict['npc_tem_data']:
      # 修正深靛的序号错误
      if value.name == _('深靛') and value.adv != 469:
        value.adv = 469
        value.cid = 469
        update_count += 1
        continue
      # 修正阿玛雅的序号错误：旧存档里阿玛雅与死芒同为450号，450号中名字是阿玛雅的才是她
      if value.adv == 450 and value.name == _('阿玛雅'):
        value.adv = 448
        value.cid = 448
        update_count += 1
        continue
      # 其他情况，创建空白模板
      tem_npc_data = character_handle.create_empty_character_tem()
      tem_npc_data.Name = value.name
      tem_npc_data.AdvNpc = value.adv
      if hasattr(value, 'relationship') and hasattr(
          value.relationship, 'mother_id'
      ):
        tem_npc_data.Mother_id = value.relationship.mother_id
      loaded_dict['npc_tem_data'][value.adv] = tem_npc_data
      update_count += 1

  return update_count


def fix_wrong_character(loaded_dict: dict[str, Any]) -> int:
  """
  修正编号错误的角色数据
  Keyword arguments:
  loaded_dict -- 存档数据
  """

  update_count = 0

  # 遍历角色属性，修正错误的adv编号
  for key, value in loaded_dict['character_data'].items():
    # 阿玛雅：旧存档里她与死芒同为450号，450号中名字是阿玛雅的才是她
    if value.adv == 450 and value.name == _('阿玛雅'):
      # 寻找adv为448的角色
      for key2, value2 in loaded_dict['character_data'].items():
        if value2.adv == 448:
          # 将阿玛雅的角色数据复制过去
          loaded_dict['character_data'][key2] = loaded_dict['character_data'][
              key
          ]
          # 将adv改为448
          loaded_dict['character_data'][key2].adv = 448
          # 将当前角色改为当前模板的角色
          now_tem_chara = loaded_dict['npc_tem_data'].get(value.cid, None)
          if now_tem_chara is None:
            now_tem_chara = loaded_dict['npc_tem_data'].get(value.adv, None)
          if now_tem_chara is not None:
            # 创建一个新的角色数据
            new_character = character_handle.init_character(
                value.cid, now_tem_chara
            )
            # 重新赋值角色数据
            loaded_dict['character_data'][key] = new_character
          update_count += 1
          break

  return update_count


def update_character_config_data(value: game_type.Character) -> int:
  """
  更新角色属性数据
  Keyword arguments:
  value -- 角色数据
  """
  update_count = 0
  # 更新角色的各种属性
  # 经验
  if len(value.experience) != len(game_config.config_experience):
    for key in game_config.config_experience:
      if key not in value.experience:
        value.experience[key] = 0
        update_count += 1
  # 素质
  if len(value.talent) != len(game_config.config_talent):
    for key in game_config.config_talent:
      if key not in value.talent:
        value.talent[key] = 0
        update_count += 1
        # print(f"debug key = {key}")
  # 如果没有u插入经验，则增加u处女素质
  if value.experience[63] == 0 and value.talent[2] == 0 and value.cid != 0:
    value.talent[2] = 1
    update_count += 1
  # 去掉玩家的u处女素质
  if value.cid == 0 and value.talent[2] == 1:
    value.talent[2] = 0
    update_count += 1
  # 如果没有w插入经验，则增加w处女素质
  if value.experience[64] == 0 and value.talent[3] == 0 and value.cid != 0:
    value.talent[3] = 1
    update_count += 1
  # 去掉玩家的w处女素质
  if value.cid == 0 and value.talent[3] == 1:
    value.talent[3] = 0
    update_count += 1
  # 宝珠
  if len(value.juel) != len(game_config.config_juel):
    for key in game_config.config_juel:
      if key not in value.juel:
        value.juel[key] = 0
        update_count += 1
  # 能力
  # 可能存在旧的空编号，所以这里不检查长度
  # if len(value.ability) != len(game_config.config_ability):
  for key in game_config.config_ability:
    if key not in value.ability:
      value.ability[key] = 0
      update_count += 1
  # 状态
  for key in game_config.config_character_state:
    if key not in value.status_data:
      value.status_data[key] = 0
      update_count += 1
    # 该状态的性高潮记录
    if game_config.config_character_state[key].type == 0:
      value.h_state.orgasm_level.setdefault(key, 0)
      value.h_state.orgasm_count.setdefault(key, [0, 0])
      value.h_state.orgasm_edge_count.setdefault(key, 0)
      value.h_state.extra_orgasm_feel.setdefault(key, 0)
      value.h_state.time_stop_orgasm_count.setdefault(key, 0)
      # 对错误数据的修复
      if value.h_state.orgasm_count[key] == 0:
        value.h_state.orgasm_count[key] = [0, 0]
        update_count += 1
  # 设置
  if len(value.chara_setting) != len(game_config.config_chara_setting):
    for key in game_config.config_chara_setting:
      if key not in value.chara_setting:
        value.chara_setting[key] = 0
        update_count += 1
  # 道具
  if len(value.item) != len(game_config.config_item):
    for key in game_config.config_item:
      if key not in value.item:
        value.item[key] = 0
        update_count += 1
  # 身体管理
  if len(value.body_manage) == 0:
    value.body_manage = attr_calculation.get_body_manage_zero()
    update_count += 1
  if len(value.body_manage) != len(game_config.config_body_manage_requirement):
    for key in game_config.config_body_manage_requirement:
      if key not in value.body_manage:
        value.body_manage[key] = 0
        update_count += 1
  # 助理服务
  if len(value.assistant_services) != len(
      game_config.config_assistant_services
  ):
    for key in game_config.config_assistant_services:
      if key not in value.assistant_services:
        value.assistant_services[key] = 0
        update_count += 1
  # 身体道具
  if len(value.h_state.body_item) != len(game_config.config_body_item):
    # 如果body_item是列表而不是字典，则初始化为空字典
    if isinstance(value.h_state.body_item, list):
      value.h_state.body_item = {}
    for key in game_config.config_body_item:
      if key not in value.h_state.body_item:
        item_id = game_config.config_body_item[key].item_id
        item_name = game_config.config_item[item_id].name
        value.h_state.body_item[key] = [item_name, False, None]
        update_count += 1
  # 行为
  # 如果行为id是int的话
  if isinstance(value.behavior.behavior_id, int):
    # 遍历Behavior，找到和当前行为id一致的行为键名
    for key in vars(constant.Behavior_Int).keys():
      # 跳过 Python 内置属性
      if key.startswith('__'):
        continue
      # 如果当前行为 ID 与常量值匹配，则更新为常量名称
      if value.behavior.behavior_id == getattr(constant.Behavior_Int, key):
        value.behavior.behavior_id = getattr(constant.Behavior, key)
        # update_count += 1
        # print(f"debug 更新了行为id: {key} -> {value.behavior.behavior_id}")
        break
  second_behavior_copy = value.second_behavior.copy()
  # 遍历原始的二级行为字典，处理整型键的更新或删除
  for second_behavior_id, behavior_data in second_behavior_copy.items():
    # 仅处理整型键
    if isinstance(second_behavior_id, int):
      # 查找匹配的常量名称
      for key in vars(constant.SecondBehavior_Int).keys():
        # 跳过 Python 内置属性
        if key.startswith('__'):
          continue
        # 如果当前行为 ID 与常量值匹配，则更新为常量名称
        if second_behavior_id == getattr(constant.SecondBehavior_Int, key):
          new_behavior_id = getattr(constant.SecondBehavior, key)
          # 添加新的键值对，并删除旧的整型键
          value.second_behavior[new_behavior_id] = behavior_data
          del value.second_behavior[second_behavior_id]
          # 匹配成功后跳出查找
          break
      else:
        # 如果未找到匹配的常量，也删除该整型键
        del value.second_behavior[second_behavior_id]
  # 遍历二段行为数据库
  for behavior_id in game_config.config_behavior:
    if '二段结算' not in game_config.config_behavior[behavior_id].tag:
      continue
    # 如果二段行为不在角色的二段行为中，则添加
    if behavior_id not in value.second_behavior:
      value.second_behavior[behavior_id] = 0
      update_count += 1
      # print(f"debug 添加了二段行为: {behavior_id}")
  # 角色扮演的跨版本数据结构处理，如果是int类型，则将其转化为列表
  if isinstance(value.hypnosis.roleplay, int):
    value.hypnosis.roleplay = []
    update_count += 1
    # print(f"debug 更新了角色扮演数据: {value.roleplay}")

  return update_count


def update_chara_cloth(
    value: game_type.Character, tem_character: game_type.NpcTem
) -> int:
  """
  更新角色服装数据
  Keyword arguments:
  value -- 角色数据
  """
  from Script.Design import clothing

  # 数据长度不一致时，重置服装数据
  if len(value.cloth.cloth_wear) != len(game_config.config_clothing_type):
    value.cloth.cloth_wear = attr_calculation.get_cloth_wear_zero()
  if len(value.cloth.cloth_locker_in_shower) != len(
      game_config.config_clothing_type
  ):
    value.cloth.cloth_locker_in_shower = (
        attr_calculation.get_shower_cloth_locker_zero()
    )
  if len(value.cloth.cloth_locker_in_dormitory) != len(
      game_config.config_clothing_type
  ):
    value.cloth.cloth_locker_in_dormitory = (
        attr_calculation.get_cloth_locker_in_dormitory_zero()
    )
  empty_dirty_data = attr_calculation.get_zero_dirty()
  if len(value.dirty.cloth_semen) != len(game_config.config_clothing_type):
    value.dirty.cloth_semen = empty_dirty_data.cloth_semen
  if len(value.dirty.cloth_locker_semen) != len(
      game_config.config_clothing_type
  ):
    value.dirty.cloth_locker_semen = empty_dirty_data.cloth_locker_semen
  # 衣柜精液表换成自己的 dict 与列表：存档里它可能与穿着的表是同一个 dict 或共用列表，
  # 上面两表都重置时也取自同一个 get_zero_dirty() 的结果，各部位共用同一个列表
  value.dirty.cloth_locker_semen = {
      clothing_type: list(semen_list)
      for clothing_type, semen_list in value.dirty.cloth_locker_semen.items()
  }

  # 跳过玩家
  if value.cid == 0:
    return 0
  # print(f"debug value.cid = {value.cid}")

  # 判断是否需要重置服装数据
  reset_cloth_flag = False
  if len(value.cloth.cloth_wear):
    for now_type in value.cloth.cloth_wear:
      now_type_cloth_data = value.cloth.cloth_wear[now_type]
      for now_cloth_id in now_type_cloth_data:
        # 查找该编号的服装数据是否存在，如果不存在，则重置该角色的服装数据
        if (
            # now_cloth_id >= 10001 and
            now_cloth_id
            not in game_config.config_clothing_tem
        ):
          reset_cloth_flag = True
          break
      if reset_cloth_flag:
        break
  # 进行服装数据的重置
  # print(f"debug old value.cloth.cloth_wear = {value.cloth.cloth_wear}")
  if reset_cloth_flag:
    value.cloth = attr_calculation.get_cloth_zero()
    for cloth_id in tem_character.Cloth:
      if cloth_id not in game_config.config_clothing_tem:
        continue
      type = game_config.config_clothing_tem[cloth_id].clothing_type
      value.cloth.cloth_wear[type].append(cloth_id)
    bra_id, pan_id = clothing.get_random_underwear()
    if not len(value.cloth.cloth_wear[6]):
      value.cloth.cloth_wear[6].append(bra_id)
    if not len(value.cloth.cloth_wear[9]):
      value.cloth.cloth_wear[9].append(pan_id)
    # print(f"debug new value.cloth.cloth_wear = {value.cloth.cloth_wear}")
    return 1
  return 0


def update_new_character(loaded_dict: dict[str, Any]) -> int:
  """
  更新新角色
  Keyword arguments:
  loaded_dict -- 存档数据
  """
  update_count = 0
  # 遍历角色预设，如果该角色在预设中但不在角色属性中，将其添加到需要增加的角色属性中
  add_new_character_list = [
      now_npc_data
      for now_npc_data in loaded_dict['npc_tem_data'].values()
      if not any(
          char_data.adv == now_npc_data.AdvNpc
          for char_data in loaded_dict['character_data'].values()
      )
  ]

  # 新增该角色，使用adv作为cid
  for now_npc_data in add_new_character_list:
    # 跳过深靛
    if now_npc_data.Name == _('深靛'):
      continue
    new_character_cid = now_npc_data.AdvNpc  # 使用adv作为cid
    # print(f"debug new_character_cid = {new_character_cid}")
    new_character = character_handle.init_character(
        new_character_cid, now_npc_data
    )
    loaded_dict['character_data'][new_character_cid] = new_character
    update_count += 1

  return update_count


STAGE_TALENT_TUPLE = (101, 102, 103)
""" 成长阶段素质：101婴儿 / 102幼女 / 103学员，静态干员不持有 """
BODY_TALENT_TUPLE = (104, 105, 106, 107, 108)
""" 体型素质 """
ADULT_BODY_TALENT = 104
""" 少女素质：没开世界设定1、或角色模板没有体型素质时，静态干员身上的成长阶段素质换成它 """
MINOR_TALENT_TUPLE = (6, 7)
""" 未初潮、未成年素质：静态干员与103阶段的女儿不持有 """
WORLD_SETTING_SHRINK = 1
""" 世界设定1在存档 world_setting 里的键：开着它开局的存档，全岛干员的体型素质104~107在开局时换成了103 """
AGE_DRUG_ITEM_TUPLE = (31, 32)
""" 外表年龄增长药、外表年龄减少药的道具id，读档时从所有角色的道具栏中清掉 """
FOLLOW_MOTHER_BEHAVIOR = 'follow_mother'
""" 跟随母亲行为id，读档时一律换成发呆 """
YOUNG_CHILD_H_FLAG_TUPLE = (
    'is_h',
    'unconscious_h',
    'hidden_sex_mode',
    'condom_cloth_flag',
    'exhibitionism_sex_mode',
    'sleep_h_awake',
    'milk',
    'masturebate',
    'masturebate_before_sleep',
    'npc_masturebate_for_player',
    'go_to_join_group_sex',
    'see_pl_h',
    'see_h_reaction_settled',
    'sex_toy_level',
)
""" 101/102阶段的孩子读档时换回默认值的 SPECIAL_FLAG 字段：H（含无意识H与睡奸中醒来）、隐奸、避孕套装饰、露出、挤奶与自慰后续链、群交邀请、看H反应、玩具档位 """
YOUNG_CHILD_H_TALENT_TUPLE = (20, 21, 22, 23, 24, 25, 26, 27, 32, 35)
""" 101/102阶段的孩子读档时清掉的素质：受精、妊娠、临盆、产后、育儿、假孕孕肚、孕肚、泌乳、精液膨腹、无意识妊娠 """
KEEP_PREGNANCY_ATTR_SET = {
    'reproduction_period',
    'born_time',
    'growth_acceleration_days',
    'milk_max',
}
""" 101/102阶段的孩子读档时保留的 PREGNANCY 字段：生殖周期、出生时间、成长加速天数、奶量上限 """


def _is_young_child(character: game_type.Character) -> bool:
  """
  判断角色是否处于幼年阶段（与 child_stage_gate 同口径，按存档里的角色数据判断）
  Keyword arguments:
  character -- 角色数据
  Return arguments:
  bool -- 持有 child_stage_gate.CHILD_STAGE_TALENTS 中任一素质时为True
  """
  return any(
      character.talent.get(talent_id, 0)
      for talent_id in child_stage_gate.CHILD_STAGE_TALENTS
  )


def _is_player_daughter(character: game_type.Character) -> bool:
  """
  判断角色是否为玩家的女儿（与前提 SELF_IS_PLAYER_DAUGHTER 同口径）
  Keyword arguments:
  character -- 角色数据
  Return arguments:
  bool -- 是否为玩家的女儿
  """
  return character.cid != 0 and character.relationship.father_id == 0


def _clear_minor_talent(character: game_type.Character) -> int:
  """
  去掉角色的未初潮与未成年素质
  Keyword arguments:
  character -- 角色数据
  Return arguments:
  int -- 改动的素质数
  """
  count = 0
  for talent_id in MINOR_TALENT_TUPLE:
    if character.talent.get(talent_id, 0):
      character.talent[talent_id] = 0
      count += 1
  return count


def _migrate_static_talent(
    character: game_type.Character, world_setting_shrink: bool
) -> int:
  """
  静态干员（非玩家、非女儿的角色）的素质：去掉未初潮与未成年；持有成长阶段素质时去掉它，换成体型素质
  Keyword arguments:
  character -- 角色数据
  world_setting_shrink -- 存档是否开着世界设定1
  Return arguments:
  int -- 改动的素质数
  功能: 开着世界设定1时取回 data/character 角色模板的体型素质，模板没有体型素质或没开世界设定1时取少女
  """
  from Script.Config import character_config

  count = _clear_minor_talent(character)
  stage_list = [
      talent_id
      for talent_id in STAGE_TALENT_TUPLE
      if character.talent.get(talent_id, 0)
  ]
  if not stage_list:
    return count
  for talent_id in stage_list:
    character.talent[talent_id] = 0
    count += 1
  tem_character = character_config.character_tem_list.get(character.adv)
  body_list = [
      talent_id
      for talent_id in BODY_TALENT_TUPLE
      if world_setting_shrink
      and tem_character is not None
      and tem_character.Talent.get(talent_id, 0)
  ]
  for talent_id in body_list or [ADULT_BODY_TALENT]:
    if not character.talent.get(talent_id, 0):
      character.talent[talent_id] = 1
      count += 1
  return count


def _reset_behavior_to_idle(character: game_type.Character) -> None:
  """
  把角色的当前行为换成1分钟的发呆，交互对象换回自己
  Keyword arguments:
  character -- 角色数据
  Return arguments:
  None
  """
  character.behavior.behavior_id = constant.Behavior.SHARE_BLANKLY
  character.behavior.duration = 1
  character.state = constant.CharacterStatus.STATUS_ARDER
  character.target_character_id = character.cid


def _clear_missing_interest_course(selected_course: dict) -> int:
  """
  从个人课表里删掉目标娱乐已不在 Entertainment.csv 里的兴趣课
  Keyword arguments:
  selected_course -- 个人课表 键int:星期 值dict:{节次int: [课型int, 目标]}
  Return arguments:
  int -- 删掉的节数
  """
  from Script.System.Education_System import education_constant

  count = 0
  for period_data in selected_course.values():
    if not isinstance(period_data, dict):
      continue
    for period in [
        period
        for period, course in period_data.items()
        if isinstance(course, list)
        and len(course) >= 2
        and course[0] == education_constant.COURSE_TYPE_INTEREST
        and course[1] not in game_config.config_entertainment
    ]:
      del period_data[period]
      count += 1
  return count


def _clear_child_activity(character: game_type.Character) -> int:
  """
  清掉角色身上的见学状态、行为表里已没有的行为、娱乐表里已没有的娱乐；101/102阶段的孩子再清掉课表、日程与上课状态
  Keyword arguments:
  character -- 角色数据
  Return arguments:
  int -- 改动的项数
  功能: 跟随母亲行为与 Behavior_Data 里没有的行为换成发呆；当天娱乐槽位里 Entertainment.csv 没有的编号换成0（无），
        单项覆盖与个人课表的兴趣课里的删掉。养成数据只清值、保留结构体；毕业的女儿与学员保留课表与成绩记录，只删掉目标娱乐不在表里的兴趣课
  """
  count = 0
  is_young_child = _is_young_child(character)
  behavior_id = character.behavior.behavior_id
  if (
      behavior_id == FOLLOW_MOTHER_BEHAVIOR
      or behavior_id not in game_config.config_behavior
  ):
    _reset_behavior_to_idle(character)
    count += 1
  entertainment_list = character.entertainment.entertainment_type
  if any(
      one not in game_config.config_entertainment for one in entertainment_list
  ):
    character.entertainment.entertainment_type = [
        one if one in game_config.config_entertainment else 0
        for one in entertainment_list
    ]
    count += 1
  growth_data = character.child_growth
  if growth_data is None:
    return count
  if growth_data.follow_mother_flag:
    growth_data.follow_mother_flag = False
    count += 1
  for slot in [
      slot
      for slot, value in growth_data.schedule_override.items()
      if value not in game_config.config_entertainment
  ]:
    del growth_data.schedule_override[slot]
    count += 1
  count += _clear_missing_interest_course(growth_data.selected_course)
  if not is_young_child:
    return count
  if growth_data.selected_course:
    growth_data.selected_course = {}
    count += 1
  if growth_data.schedule_template_id:
    growth_data.schedule_template_id = 0
    count += 1
  if growth_data.schedule_override:
    growth_data.schedule_override = {}
    count += 1
  if growth_data.skip_class_flag or growth_data.skip_class_day:
    growth_data.skip_class_flag = False
    growth_data.skip_class_day = 0
    count += 1
  return count


def _replace_if_changed(
    owner: object, attr_name: str, default_value: object
) -> int:
  """
  属性值与默认值不同时换成默认值
  Keyword arguments:
  owner -- 属性所在的对象
  attr_name -- 属性名
  default_value -- 默认值（结构体按 vars 比较）
  Return arguments:
  int -- 换了为1，没换为0
  """
  now_value = getattr(owner, attr_name)
  if hasattr(default_value, '__dict__'):
    if vars(now_value) == vars(default_value):
      return 0
  elif now_value == default_value:
    return 0
  setattr(owner, attr_name, default_value)
  return 1


def _get_new_dirty() -> game_type.DIRTY:
  """
  新角色的污浊数据：身上、穿着与衣柜里的服装精液各用各的列表
  Return arguments:
  game_type.DIRTY -- 污浊数据
  """
  dirty_data = attr_calculation.get_dirty_reset(game_type.DIRTY())
  dirty_data.cloth_locker_semen = {
      clothing_type: list(semen_list)
      for clothing_type, semen_list in dirty_data.cloth_semen.items()
  }
  return dirty_data


def _clear_young_child_h_state(character: game_type.Character) -> int:
  """
  101/102阶段的孩子：污浊、H状态与身体道具、H相关标记与后续链、泌乳、妊娠与卵，换成新角色的默认值
  Keyword arguments:
  character -- 孩子的角色数据
  Return arguments:
  int -- 改动的项数
  功能: 妊娠数据里的生殖周期、出生时间、成长加速天数与奶量上限保留，其余换成默认值；只改孩子本人，不动母亲
  """
  count = _replace_if_changed(character, 'dirty', _get_new_dirty())
  count += _replace_if_changed(
      character,
      'h_state',
      attr_calculation.get_h_state_reset(game_type.BODY_H_STATE()),
  )
  default_flag = game_type.SPECIAL_FLAG()
  for flag_name in YOUNG_CHILD_H_FLAG_TUPLE:
    count += _replace_if_changed(
        character.sp_flag, flag_name, getattr(default_flag, flag_name)
    )
  for talent_id in YOUNG_CHILD_H_TALENT_TUPLE:
    if character.talent.get(talent_id, 0):
      character.talent[talent_id] = 0
      count += 1
  default_pregnancy = game_type.PREGNANCY()
  for attr_name, default_value in vars(default_pregnancy).items():
    if attr_name not in KEEP_PREGNANCY_ATTR_SET:
      count += _replace_if_changed(
          character.pregnancy, attr_name, default_value
      )
  return count


def _clear_young_child_egg_index(
    player: game_type.Character, young_child_id_set: set
) -> int:
  """
  从玩家收藏品中删掉指向101/102阶段孩子的持有卵索引，以及她们排出的体外无壳卵
  Keyword arguments:
  player -- 玩家的角色数据
  young_child_id_set -- 101/102阶段孩子的角色id集合
  Return arguments:
  int -- 删掉的条数
  """
  collection = player.pl_collection
  count = 0
  for held_id in [
      held_id
      for held_id, (chara_id, _) in collection.held_eggs.items()
      if chara_id in young_child_id_set
  ]:
    del collection.held_eggs[held_id]
    count += 1
  for egg_id in [
      egg_id
      for egg_id, egg_data in collection.soft_eggs.items()
      if egg_data.get('mother_id') in young_child_id_set
  ]:
    del collection.soft_eggs[egg_id]
    count += 1
  return count


def _remove_from_group_sex_template(
    character: game_type.Character, young_child_id_set: set
) -> int:
  """
  从角色的群交部位模板（A、B）里去掉101/102阶段的孩子：单部位的交互对象换回 [-1, -1]，阴茎侍奉的对象列表里删掉她们
  Keyword arguments:
  character -- 角色数据
  young_child_id_set -- 101/102阶段孩子的角色id集合
  Return arguments:
  int -- 改动的项数
  功能: 阴茎侍奉的对象删空时换回默认的 [[-1], -1]。两部分分别检查结构：模板不是长度至少为2、第一项为字典的列表时整份跳过；
        阴茎侍奉部分不是 [对象列表, 指令状态] 时只跳过这一部分，单部位已做的改动保留。
        group_sex_panel.clear_character_data_in_group_sex_template 只改游戏缓存里玩家的模板、不检查结构，而这里改的是还没载入缓存的存档里每个角色的模板，所以不用它
  """
  count = 0
  for template_data in character.h_state.group_sex_body_template_dict.values():
    if (
        not isinstance(template_data, list)
        or len(template_data) < 2
        or not isinstance(template_data[0], dict)
    ):
      continue
    for part_key, part_value in template_data[0].items():
      if (
          isinstance(part_value, list)
          and part_value
          and part_value[0] in young_child_id_set
      ):
        template_data[0][part_key] = [-1, -1]
        count += 1
    serve_data = template_data[1]
    if (
        not isinstance(serve_data, list)
        or len(serve_data) < 2
        or not isinstance(serve_data[0], list)
    ):
      continue
    serve_id_list = [
        chara_id
        for chara_id in serve_data[0]
        if chara_id not in young_child_id_set
    ]
    if len(serve_id_list) != len(serve_data[0]):
      template_data[1] = (
          [serve_id_list, serve_data[1]] if serve_id_list else [[-1], -1]
      )
      count += 1
  return count


def _discard_id(container: object, young_child_id_set: set) -> int:
  """
  从角色id的集合或列表里删掉101/102阶段的孩子
  Keyword arguments:
  container -- 角色id的 set 或 list（其他类型原样跳过）
  young_child_id_set -- 101/102阶段孩子的角色id集合
  Return arguments:
  int -- 删掉的个数
  """
  if not isinstance(container, (set, list)):
    return 0
  hit_list = [
      chara_id for chara_id in container if chara_id in young_child_id_set
  ]
  for chara_id in hit_list:
    container.remove(chara_id)
  return len(hit_list)


def _clear_young_child_reference(
    loaded_dict: dict[str, Any], young_child_id_set: set
) -> int:
  """
  清掉存档里其他结构对101/102阶段孩子的引用：时停自由活动对象、装袋对象、交互中对象、拒绝群交名单、
     玩家收藏品里她的胖次、袜子、乳汁与圣水，冷库里她的母乳与圣水，囚犯、外勤委托、实操课必修名单、体检名单、借书，
     以及离开场景面板前查看的角色；成员删空的外勤委托取消（见 _cancel_empty_field_commission）
  Keyword arguments:
  loaded_dict -- 存档数据
  young_child_id_set -- 101/102阶段孩子的角色id集合
  Return arguments:
  int -- 改动的项数
  功能: 只改值与目标不同的项；孩子自己的装袋、监禁、逃跑与外勤标记一并清掉，借的书还回去
  """
  count = 0
  character_data = loaded_dict['character_data']
  for character in character_data.values():
    if character.pl_ability.free_in_time_stop_chara_id in young_child_id_set:
      character.pl_ability.free_in_time_stop_chara_id = 0
      count += 1
    if character.sp_flag.bagging_chara_id in young_child_id_set:
      character.sp_flag.bagging_chara_id = 0
      count += 1
    end_info = character.action_info.interacting_character_end_info
    if character.cid in young_child_id_set or (
        isinstance(end_info, list)
        and end_info
        and end_info[0] in young_child_id_set
    ):
      count += _replace_if_changed(
          character.action_info,
          'interacting_character_end_info',
          [-1, datetime.datetime(1, 1, 1)],
      )
    count += _discard_id(
        character.action_info.ask_group_sex_refuse_chara_id_list,
        young_child_id_set,
    )
    collection = character.pl_collection
    for chara_id in young_child_id_set:
      if collection.first_panties.get(chara_id):
        collection.first_panties[chara_id] = ''
        count += 1
      for item_dict in (
          collection.npc_panties,
          collection.npc_panties_tem,
          collection.npc_socks,
          collection.npc_socks_tem,
      ):
        if item_dict.get(chara_id):
          item_dict[chara_id] = []
          count += 1
      for total_dict in (collection.milk_total, collection.urine_total):
        if total_dict.get(chara_id):
          total_dict[chara_id] = 0
          count += 1
  for chara_id in young_child_id_set:
    child = character_data[chara_id]
    count += _replace_if_changed(child.sp_flag, 'be_bagged', False)
    count += _replace_if_changed(child.sp_flag, 'imprisonment', False)
    count += _replace_if_changed(child.sp_flag, 'escaping', False)
    count += _replace_if_changed(child.sp_flag, 'field_commission', 0)
    if child.entertainment.borrow_book_id_set:
      child.entertainment.borrow_book_id_set = set()
      count += 1
  rhodes_island = loaded_dict['rhodes_island']
  for chara_key_dict in (
      rhodes_island.milk_in_fridge,
      rhodes_island.urine_in_fridge,
      rhodes_island.current_prisoners,
      rhodes_island.today_physical_examination_chara_id_dict,
  ):
    for chara_id in young_child_id_set & set(chara_key_dict):
      del chara_key_dict[chara_id]
      count += 1
  for commission_data in rhodes_island.ongoing_field_commissions.values():
    if isinstance(commission_data, list) and commission_data:
      count += _discard_id(commission_data[0], young_child_id_set)
  count += _cancel_empty_field_commission(rhodes_island)
  for class_data in rhodes_island.temp_sex_class.values():
    if isinstance(class_data, dict):
      count += _discard_id(class_data.get('must_attend'), young_child_id_set)
  for exam_set in (
      rhodes_island.examined_operator_ids,
      rhodes_island.waiting_for_exam_operator_ids,
      rhodes_island.manually_selected_exam_operator_ids,
  ):
    count += _discard_id(exam_set, young_child_id_set)
  for book_id, borrower_id in list(rhodes_island.book_borrow_dict.items()):
    if borrower_id in young_child_id_set:
      rhodes_island.book_borrow_dict[book_id] = -1
      count += 1
  if loaded_dict.get('old_character_id') in young_child_id_set:
    loaded_dict['old_character_id'] = 0
    count += 1
  return count


def _cancel_empty_field_commission(
    rhodes_island: game_type.Rhodes_Island,
) -> int:
  """
  取消没有成员的外勤委托：从进行中的委托里移除，派出的载具收回
  Keyword arguments:
  rhodes_island -- 存档里的罗德岛数据
  Return arguments:
  int -- 改动的项数
  功能: 游戏里没有取消委托的流程，这里只做完成结算 judge_field_commission_finish 里收回载具与移除委托的两步：
        载具按 settle_vehicle 不损坏时的做法，每辆的派出数减1；委托从 ongoing_field_commissions 移除。
        奖励、计入已完成、成就、招募、载具损坏与装备损坏都不结算，派遣时扣掉的资源不退
  """
  count = 0
  for commission_id, commission_data in list(
      rhodes_island.ongoing_field_commissions.items()
  ):
    if (
        not isinstance(commission_data, list)
        or not commission_data
        or commission_data[0]
    ):
      continue
    vehicle_id_list = commission_data[2] if len(commission_data) > 2 else []
    for vehicle_id in vehicle_id_list:
      if vehicle_id in rhodes_island.vehicles:
        rhodes_island.vehicles[vehicle_id][1] -= 1
        count += 1
    del rhodes_island.ongoing_field_commissions[commission_id]
    count += 1
  return count


def _take_young_child_off_line(
    loaded_dict: dict[str, Any], young_child_id_set: set
) -> int:
  """
  让101/102阶段的孩子离线：离开所有场景与当前干员列表，位置换成离线位置 ["0", "0"]，交互对象换成自己，
     行为不是发呆或带着移动路线时换成默认行为（发呆），跟随关闭；
     没有职业（work_type 为0）、不在任何职业名单里，空出宿舍床位（宿舍与登记宿舍为空串），助理服务归零（同 handle_assistant_reset）；
     催眠、待触发事件、必须结算与显示的二段行为、快感状态归零；
     别人以她为目标的，目标换回自己（NPC 当前的行为换成发呆）；以她为助理的，助理清零；别人正在搬运她的，搬运对象清零；别人的群交部位模板里去掉她。角色数据保留
  Keyword arguments:
  loaded_dict -- 存档数据
  young_child_id_set -- 101/102阶段孩子的角色id集合
  Return arguments:
  int -- 改动的项数
  功能: 与角色离线结算 handle_chara_off_line 的位置口径相同：位置为 ["0", "0"]
  """
  count = 0
  if not young_child_id_set:
    return count
  for scene in loaded_dict['scene_data'].values():
    for character_id in young_child_id_set & set(scene.character_list):
      scene.character_list.remove(character_id)
      count += 1
  for character_id in young_child_id_set & set(loaded_dict['npc_id_got']):
    loaded_dict['npc_id_got'].remove(character_id)
    count += 1
  for work_npc_set in loaded_dict['rhodes_island'].all_work_npc_set.values():
    for character_id in young_child_id_set & set(work_npc_set):
      work_npc_set.remove(character_id)
      count += 1
  for character_id in young_child_id_set:
    character = loaded_dict['character_data'][character_id]
    count += _replace_if_changed(character, 'position', ['0', '0'])
    behavior = character.behavior
    if (
        behavior.behavior_id != constant.Behavior.SHARE_BLANKLY
        or behavior.move_target
        or behavior.move_src
        or behavior.move_final_target
    ):
      character.behavior = game_type.Behavior()
      character.state = constant.CharacterStatus.STATUS_ARDER
      count += 1
    count += _replace_if_changed(character.sp_flag, 'is_follow', 0)
    count += _replace_if_changed(character, 'target_character_id', character_id)
    count += _replace_if_changed(character.work, 'work_type', 0)
    count += _replace_if_changed(
        character,
        'assistant_services',
        attr_calculation.get_assistant_services_zero(),
    )
    count += _replace_if_changed(character, 'dormitory', '')
    count += _replace_if_changed(character, 'permanent_dormitory', '')
    count += _replace_if_changed(character, 'hypnosis', game_type.HYPNOSIS())
    count += _replace_if_changed(character, 'event', game_type.Chara_Event())
    count += _replace_if_changed(
        character, 'must_settle_second_behavior_id_list', []
    )
    count += _replace_if_changed(
        character, 'must_show_second_behavior_id_list', []
    )
    for state_id in [
        state_id
        for state_id, state in game_config.config_character_state.items()
        if state.type == 0
    ]:
      if character.status_data.get(state_id, 0):
        character.status_data[state_id] = 0
        count += 1
  for character in loaded_dict['character_data'].values():
    if (
        character.target_character_id in young_child_id_set
        and character.target_character_id != character.cid
    ):
      # NPC 正在对孩子进行的行为换成发呆；有孩子参与的会话由读档后的 end_young_child_session 结束
      if character.cid != 0:
        _reset_behavior_to_idle(character)
      character.target_character_id = character.cid
      count += 1
    if character.assistant_character_id in young_child_id_set:
      character.assistant_character_id = 0
      count += 1
    if character.action_info.carry_chara_id in young_child_id_set:
      character.action_info.carry_chara_id = 0
      count += 1
    if character.pl_ability.carry_chara_id_in_time_stop in young_child_id_set:
      character.pl_ability.carry_chara_id_in_time_stop = 0
      count += 1
    count += _remove_from_group_sex_template(character, young_child_id_set)
  count += _clear_young_child_reference(loaded_dict, young_child_id_set)
  return count


def _clear_age_drug_item(character: game_type.Character) -> int:
  """
  从角色道具栏中删掉外表年龄药（道具表里没有这两项）
  Keyword arguments:
  character -- 角色数据
  Return arguments:
  int -- 改动的项数
  """
  count = 0
  for item_id in AGE_DRUG_ITEM_TUPLE:
    if item_id in character.item:
      del character.item[item_id]
      count += 1
  return count


class YoungChildSession(TypedDict, total=False):
  """有101/102阶段的孩子参与、读档后要结束的会话信息，读档整理前为空字典"""

  group: bool
  """ 群交是否要结束 """
  time_stop: bool
  """ 时停是否要结束 """
  single_partner_id_set: set[int]
  """ 与孩子单人H的角色id集合 """
  child_id_set: set[int]
  """ 孩子的角色id集合 """


def _find_young_child_session(
    loaded_dict: dict[str, Any], young_child_id_set: set
) -> YoungChildSession:
  """
  找出有101/102阶段的孩子参与、读档后要结束的会话
  Keyword arguments:
  loaded_dict -- 存档数据（在清掉孩子的H标记、群交模板与对孩子的引用之前调用）
  young_child_id_set -- 101/102阶段孩子的角色id集合
  Return arguments:
  dict -- {"group": 群交是否要结束, "time_stop": 时停是否要结束, "single_partner_id_set": 与孩子单人H的角色id集合, "child_id_set": 孩子的角色id集合}
  功能: 群交：开着群交模式，且玩家以孩子为交互对象、或孩子在某个群交部位模板里、或孩子与玩家同场景在H中；
        时停：开着时停，且玩家以孩子为交互对象、搬运她或让她自由活动；
        单人H（含隐奸、露出）：交互对象是孩子且在H、隐奸或露出中的角色，与玩家同场景的群交参与者归群交结束
  """
  character_data = loaded_dict['character_data']
  player = character_data.get(0)
  session: YoungChildSession = {
      'group': False,
      'time_stop': False,
      'single_partner_id_set': set(),
      'child_id_set': set(young_child_id_set),
  }
  if player is None or not young_child_id_set:
    return session
  if loaded_dict.get('group_sex_mode'):
    in_template = False
    for character in character_data.values():
      for (
          template_data
      ) in character.h_state.group_sex_body_template_dict.values():
        if (
            isinstance(template_data, list)
            and len(template_data) >= 2
            and isinstance(template_data[0], dict)
            and isinstance(template_data[1], list)
        ):
          part_id_list = [
              part_value[0]
              for part_value in template_data[0].values()
              if isinstance(part_value, list) and part_value
          ]
          serve_id_list = (
              template_data[1][0]
              if template_data[1] and isinstance(template_data[1][0], list)
              else []
          )
          if young_child_id_set & set(part_id_list + serve_id_list):
            in_template = True
    child_in_scene_h = any(
        character_data[chara_id].sp_flag.is_h
        and character_data[chara_id].position == player.position
        for chara_id in young_child_id_set
    )
    session['group'] = (
        player.target_character_id in young_child_id_set
        or in_template
        or child_in_scene_h
    )
  if loaded_dict.get('time_stop_mode'):
    time_stop_id_set = {
        player.target_character_id,
        player.pl_ability.free_in_time_stop_chara_id,
        player.action_info.carry_chara_id,
        player.pl_ability.carry_chara_id_in_time_stop,
    }
    session['time_stop'] = bool(time_stop_id_set & young_child_id_set)
  for character in character_data.values():
    if (
        character.cid in young_child_id_set
        or character.target_character_id not in young_child_id_set
    ):
      continue
    if session['group'] and character.position == player.position:
      continue
    if (
        character.sp_flag.is_h
        or character.sp_flag.hidden_sex_mode
        or character.sp_flag.exhibitionism_sex_mode
    ):
      session['single_partner_id_set'].add(character.cid)
  return session


def end_young_child_session(session: YoungChildSession) -> None:
  """
  存档载入缓存后，有101/102阶段的孩子参与的会话各按自己的结束结算收尾，奖励类结算不调用
  Keyword arguments:
  session -- migrate_age_and_body_type 填入的会话信息（见 _find_young_child_session）
  Return arguments:
  None
  功能: 群交按「群交结束」：场景内所有角色H状态归零（SCENE_ALL_CHARACTERS_H_STATE_RESET）、穿回衣服、阴茎位置归零、关闭群交模式；
        时停按「解除时停」：清零时停搬运与自由活动对象、关闭时停；
        单人H按「结束H」：另一方H状态归零（BOTH_H_STATE_RESET 对其一侧）、开门；
        最后孩子一侧H状态归零、穿回衣服。结算读写游戏缓存，所以在读档覆盖缓存之后调用；
        体力气力上限奖励、寸止解放与时停绝顶解放是对这次会话的结算，不调用。各方的交互对象已在转换时换成不指向孩子的值
  """
  from Script.Settle import default, default_cloth

  now_time = cache.game_time
  if session.get('group'):
    default.handle_scene_all_characters_h_state_reset(
        0, 1, game_type.CharacterStatusChange(), now_time
    )
    default_cloth.handle_scene_all_characters_cloth_back(
        0, 1, game_type.CharacterStatusChange(), now_time
    )
    default.handle_scene_all_characters_penis_in_reset(
        0, 1, game_type.CharacterStatusChange(), now_time
    )
    default.handle_group_sex_mode_off(
        0, 1, game_type.CharacterStatusChange(), now_time
    )
  if session.get('time_stop'):
    default.handle_target_not_be_carried_in_time_stop(
        0, 1, game_type.CharacterStatusChange(), now_time
    )
    default.handle_target_not_be_free_in_time_stop(
        0, 1, game_type.CharacterStatusChange(), now_time
    )
    default.handle_time_stop_off(
        0, 1, game_type.CharacterStatusChange(), now_time
    )
  for character_id in sorted(session.get('single_partner_id_set', set())):
    if character_id not in cache.character_data:
      continue
    default.handle_self_h_state_reset(
        character_id, 1, game_type.CharacterStatusChange(), now_time
    )
    default.handle_door_close_reset(
        character_id, 1, game_type.CharacterStatusChange(), now_time
    )
  for character_id in sorted(session.get('child_id_set', set())):
    if character_id not in cache.character_data:
      continue
    default.handle_self_h_state_reset(
        character_id, 1, game_type.CharacterStatusChange(), now_time
    )
    default_cloth.handle_self_cloth_back(
        character_id, 1, game_type.CharacterStatusChange(), now_time
    )


def migrate_age_and_body_type(
    loaded_dict: dict[str, Any], session: YoungChildSession | None = None
) -> int:
  """
  读档时整理成长阶段、体型、见学与上课、行为表与娱乐表里已没有的编号、101/102阶段的H与身体状态和离线、外表年龄药相关的数据；对整理过的存档再读一次，这些数据不变
  Keyword arguments:
  loaded_dict -- 存档数据（角色数据须已经过 update_character_config_data）
  session -- 传入 dict 时填入有孩子参与的会话（见 _find_young_child_session），读档覆盖缓存后交给 end_young_child_session
  Return arguments:
  int -- 改动的项数
  功能: 静态干员见 _migrate_static_talent；103阶段的女儿去掉未初潮与未成年，女儿的成长阶段与体型保持原样；
        见学、表里没有的行为与娱乐编号、101/102阶段的上课状态、101/102阶段的H与身体状态、离线、外表年龄药见 _clear_child_activity、_clear_young_child_h_state、_clear_young_child_egg_index、_take_young_child_off_line、_clear_age_drug_item；
        最后清掉世界设定1的开关
  """
  count = 0
  world_setting = loaded_dict.get('world_setting', {})
  world_setting_shrink = bool(world_setting.get(WORLD_SETTING_SHRINK, 0))
  # 先换静态干员与103女儿的素质：药物缩成101/102的静态干员由此回到成年，不算孩子
  for character in loaded_dict['character_data'].values():
    if character.cid != 0 and not _is_player_daughter(character):
      count += _migrate_static_talent(character, world_setting_shrink)
    elif _is_player_daughter(character) and character.talent.get(103, 0):
      count += _clear_minor_talent(character)
  young_child_id_set = {
      character.cid
      for character in loaded_dict['character_data'].values()
      if _is_young_child(character)
  }
  # 在清掉任何H标记、群交模板与交互对象之前记下有孩子参与的会话
  if session is not None:
    session.update(_find_young_child_session(loaded_dict, young_child_id_set))
  for character in loaded_dict['character_data'].values():
    count += _clear_child_activity(character)
    if character.cid in young_child_id_set:
      count += _clear_young_child_h_state(character)
    count += _clear_age_drug_item(character)
  if 0 in loaded_dict['character_data']:
    count += _clear_young_child_egg_index(
        loaded_dict['character_data'][0], young_child_id_set
    )
  count += _take_young_child_off_line(loaded_dict, young_child_id_set)
  for template_data in loaded_dict[
      'rhodes_island'
  ].child_schedule_template.values():
    slot_data = (
        template_data.get('slot', {}) if isinstance(template_data, dict) else {}
    )
    for slot in [
        slot
        for slot, value in slot_data.items()
        if value not in game_config.config_entertainment
    ]:
      slot_data[slot] = 0
      count += 1
  if world_setting_shrink:
    world_setting[WORLD_SETTING_SHRINK] = 0
    count += 1
  return count
