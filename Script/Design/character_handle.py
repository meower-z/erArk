"""角色数据的生成与初始化：NPC列表、角色模板、新生孩子、初始位置、娱乐、开放设施与工作，以及获得新角色与增加好感"""

import copy
import random
from types import FunctionType
from typing import Optional
from Script.Core import (
    cache_control,
    constant,
    game_type,
    get_text,
)
from Script.Design import (
    attr_calculation,
    map_handle,
    character,
    handle_npc_ai,
    basement,
    game_time,
)
from Script.Config import game_config, character_config

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """
_: FunctionType = get_text._
""" 翻译api """


def init_character_list() -> None:
  """
  初始生成所有npc数据
  """
  for adv_id, now_npc_data in cache.npc_tem_data.items():
    # print("adv_id=",adv_id,". now_npc_data:",now_npc_data)
    init_character(adv_id, now_npc_data)


def init_character(
    character_id: int,
    character_tem: game_type.NpcTem,
    collect_reset: bool = True,
) -> game_type.Character:
  """
  按id生成角色属性
  Keyword arguments:
  character_id -- 角色id
  character_tem -- 角色生成模板数据
  skip_collect_reset -- 是否进行藏品重置
  returns:
  game_type.Character -- 角色数据
  """
  # print("进入init_character")
  # print("生成阶段，character_id :",character_id)
  # print("character_id=",character_id)
  now_character = game_type.Character()
  now_character.cid = character_id
  now_character.name = character_tem.Name
  # 检测基础干员并加入已有干员列表
  if character_tem.AdvNpc in constant.first_NPC_adv_set:
    cache.npc_id_got.add(character_id)
  cache.npc_name_data.add(now_character.name)  # 加入到已有干员姓名中
  now_character.sex = character_tem.Sex
  now_character.profession = character_tem.Profession
  now_character.race = character_tem.Race
  now_character.relationship.nation = character_tem.Nation
  now_character.relationship.birthplace = character_tem.Birthplace
  # 如果有母亲的话则加上亲子关系
  if character_tem.Mother_id:
    now_character.relationship.father_id = 0
    now_character.relationship.mother_id = character_tem.Mother_id
  now_character.adv = character_tem.AdvNpc
  now_character.target_character_id = character_id
  now_character.favorability = {0: 0}
  now_character.trust = 0
  now_character.ability = copy.deepcopy(character_tem.Ability)
  now_character.experience = copy.deepcopy(character_tem.Experience)
  now_character.talent = copy.deepcopy(character_tem.Talent)
  now_character.hit_point_max = character_tem.Hp
  now_character.mana_point_max = character_tem.Mp
  now_character.dormitory = character_tem.Dormitory
  now_character.token_text = character_tem.Token
  # if character_tem.Chest:
  #     now_character.chest_tem = character_tem.Chest
  # 生成衣服
  now_character.cloth = attr_calculation.get_cloth_zero()
  now_character.cloth.cloth_wear = attr_calculation.get_cloth_wear_zero()
  for cloth_id in character_tem.Cloth:
    type = game_config.config_clothing_tem[cloth_id].clothing_type
    # print(f"debug {character_tem.Name} cloth_id = {cloth_id},name = {game_config.config_clothing_tem[cloth_id].name},type = {type}")
    now_character.cloth.clothing_tem.append(cloth_id)
    now_character.cloth.cloth_wear[type].append(cloth_id)
    # if type in [6,9] and len(now_character.cloth.cloth_wear[type]):
    #     print(f"debug {character_tem.Name} cloth_wear = {now_character.cloth.cloth_wear}")
  # print(f"debug {character_tem.Name} cloth_wear = {now_character.cloth.cloth_wear}")
  # 生成藏品
  if collect_reset and 0 in cache.character_data:
    pl_character_data = cache.character_data[0]
    pl_character_data.pl_collection.token_list[character_id] = False
    pl_character_data.pl_collection.first_panties[character_id] = ""
    pl_character_data.pl_collection.npc_panties[character_id] = []
    pl_character_data.pl_collection.npc_socks[character_id] = []
  # 文本颜色
  if character_tem.TextColor:
    now_character.text_color = character_tem.TextColor
  # 赋予口上大小
  now_character.talk_size = character_tem.Talk_Size
  # 口上版本
  cache.all_system_setting.character_text_version[character_id] = 1
  # 最后集成
  cache.character_data[character_id] = now_character
  character.init_attr(character_id)
  return cache.character_data[character_id]


def first_NPC_work() -> None:
  """
  初始角色的工作安排
  """
  for character_id in cache.npc_id_got:
    character_data = cache.character_data[character_id]
    # 按干员编号认人：角色名随语言翻译
    if character_data.adv in {7}:  # 可露希尔
      character_data.work.work_type = 21
    elif character_data.adv in {3, 171}:  # 凯尔希、华法琳
      character_data.work.work_type = 61
    elif character_data.adv in {56}:  # 特蕾西娅
      character_data.work.work_type = 71
    elif character_data.adv in {130}:  # 杜宾
      character_data.work.work_type = 91
  basement.update_work_people()


def init_character_tem() -> None:
  """
  初始化角色模板数据
  """
  # 必须浅拷贝而非直接引用 character_config.character_tem_list：后者是模块级全局配置池，
  #    进程内持久且跨存档 / 跨周目共享，而 born_new_character 会往 cache.npc_tem_data 写运行时
  #    生成的女儿模板（adv 9000~9999）。直接共享引用会把某一局的女儿写进全局池，使别的存档 /
  #    新开的周目也能看到，进而触发本存档并不存在的女儿的相关事件（跨存档泄漏）
  cache.npc_tem_data = dict(character_config.character_tem_list)


def create_empty_character_tem() -> game_type.NpcTem:
  """
  生成空的角色模板数据
  """
  now_tem = game_type.NpcTem()
  now_tem.Sex = 1
  now_tem.Nation = 0
  now_tem.Birthplace = 0
  now_tem.Ability = {}
  now_tem.Experience = {}
  now_tem.Dormitory = "无"
  now_tem.Token = "无"
  now_tem.Cloth = []
  return now_tem


def born_new_character(mother_id: int, child_name: str) -> int:
  """
  生成新的小孩模板数据
  Returns:
      int: 新角色的id（等于adv）
  """
  mom_character_data: game_type.Character = cache.character_data[mother_id]
  now_tem = create_empty_character_tem()
  now_tem.Name = child_name
  now_tem.Profession = random.randint(0, 8)
  now_tem.Race = mom_character_data.race
  now_tem.Mother_id = mother_id
  # 避免重复adv
  while 1:
    new_adv = random.randint(9000, 9999)
    if character.get_character_id_from_adv(new_adv) == 0:
      break
  now_tem.AdvNpc = new_adv
  # 基础的素质
  now_tem.Talent = {
      0: 1,
      1: 1,
      2: 1,
      3: 1,
      4: 1,
      6: 1,
      7: 1,
      101: 1,
      121: 1,
      126: 1,
      129: 1,
      131: 1,
      451: 1,
  }
  # 遗传母亲的可遗传素质
  for talent_id in game_config.config_talent:
    if (
        game_config.config_talent[talent_id].heredity
        and mom_character_data.talent[talent_id]
    ):
      # 跳过胸部、臀部、腿和脚
      if 122 <= talent_id <= 132:
        continue
      now_tem.Talent[talent_id] = 1
  now_tem.Talent[121] = 1
  now_tem.Hp = random.randint(1000, 2000)
  now_tem.Mp = random.randint(1000, 2000)
  now_id = now_tem.AdvNpc  # 使用adv作为id
  cache.npc_tem_data[now_id] = now_tem
  # 给父母加上该孩子的社会关系
  cache.character_data[0].relationship.child_id_list.append(now_id)
  mom_character_data.relationship.child_id_list.append(now_id)
  # 记录特殊履历：第一次分娩（附记孩子的名字，地点即母亲分娩时所在位置）
  from Script.System.First_Record_System import first_record_handle

  first_record_handle.record_first_special_record(mother_id, 2, child_name)
  # cache.npc_id_got.add(now_id)
  init_character(now_id, cache.npc_tem_data[now_id])
  return now_id


def init_character_position() -> None:
  """初始化角色位置"""
  cache = cache_control.cache
  id_list = cache.npc_id_got
  id_list.add(0)
  for character_id in id_list:
    character_position = cache.character_data[character_id].position
    character_dormitory = cache.character_data[character_id].dormitory
    character_dormitory_str = map_handle.get_map_system_path_for_str(
        character_dormitory
    )
    # print("character_dormitory = ",character_dormitory)
    map_handle.character_move_scene(
        character_position, character_dormitory_str, character_id
    )
  character_position = cache.character_data[0].position
  map_handle.character_move_scene(["0", "0"], character_position, 0)


def init_character_entertainment() -> None:
  """初始化角色娱乐"""
  cache = cache_control.cache
  id_list = cache.npc_id_got
  id_list.add(0)
  for character_id in id_list:
    handle_npc_ai.get_chara_entertainment(character_id)


def init_character_facility_open() -> None:
  """初始化角色开放设施"""
  cache = cache_control.cache
  for open_cid in game_config.config_facility_open:
    if game_config.config_facility_open[open_cid].NPC_id == 0:
      continue
    for character_id in cache.npc_id_got:
      # 跳过玩家id
      if character_id == 0:
        continue
      if (
          game_config.config_facility_open[open_cid].NPC_id
          == cache.character_data[character_id].adv
      ):
        cache.rhodes_island.facility_open[open_cid] = True
        break


def get_new_character(character_id: int, visitor_flag: bool = False) -> None:
  """
  获得新角色
  Keyword arguments:
  character_id -- 角色id
  visitor_flag -- 是否为访客
  """
  from Script.Settle import default
  from Script.System.Dormitory_System import common as dormitory_common

  # 角色上线
  default.handle_chara_on_line(
      character_id,
      1,
      change_data=game_type.CharacterStatusChange(),
      now_time=cache.game_time,
  )

  character_data = cache.character_data[character_id]
  # 清零全特殊状态flag
  character_data.sp_flag = game_type.SPECIAL_FLAG()

  if visitor_flag:
    # 根据访客区的等级，赋予对应的停留时间
    now_level = cache.rhodes_island.facility_level[13]
    facility_cid = game_config.config_facility_effect_data[_("访客区")][
        int(now_level)
    ]
    facility_effect = game_config.config_facility_effect[facility_cid].effect
    stay_days = facility_effect
    end_time = game_time.get_sub_date(day=stay_days, old_date=cache.game_time)
    cache.rhodes_island.visitor_info[character_id] = end_time
    # 赋予访客flag
    character_data.sp_flag.vistor = 1
  else:
    # 如果满足设施开放的前提条件，则开放该设施
    for open_cid in game_config.config_facility_open:
      if (
          game_config.config_facility_open[open_cid].NPC_id
          and game_config.config_facility_open[open_cid].NPC_id
          == character_data.adv
      ):
        cache.rhodes_island.facility_open[open_cid] = True

  # 分配角色宿舍
  dormitory_common.new_character_get_dormitory(character_id)

  # 初始化新角色位置
  character_position = character_data.position
  office_postion = ["中枢", "博士办公室"]
  map_handle.character_move_scene(
      character_position, office_postion, character_id
  )

  # 初始化新角色娱乐
  handle_npc_ai.get_chara_entertainment(character_id)

  # 新角色原地等待30分钟
  character_data.behavior.behavior_id = constant.Behavior.WAIT
  character_data.behavior.duration = 30
  character_data.behavior.start_time = cache.game_time
  character_data.state = constant.CharacterStatus.STATUS_WAIT


def add_favorability(
    character_id: int,
    target_id: int,
    now_add_favorability: int,
    change_data: Optional[
        game_type.CharacterStatusChange | game_type.TargetChange
    ],
    target_change: Optional[
        game_type.TargetChange | game_type.CharacterStatusChange
    ],
) -> None:
  """
  增加目标角色对当前角色的好感
  Keyword arguments:
  character_id -- 当前角色id
  target_id -- 目标角色id
  now_add_favorability -- 增加的好感
  change_data -- 当前角色这一侧的状态变更记录对象，不需要记录时传None
  target_change -- 目标角色这一侧的状态变更记录对象，不需要记录时传None
  Return arguments:
  无
  功能: 两个记录对象在函数体里都判了None，母女见学好感一类不走玩家结算链的调用可以只传其中一个
  """
  target_data: game_type.Character = cache.character_data[target_id]
  target_data.favorability.setdefault(character_id, 0)
  character_data: game_type.Character = cache.character_data[character_id]
  character_data.favorability.setdefault(target_id, 0)
  if target_change is not None:
    target_change.status_data.setdefault(12, 0)
  # if 12 in target_data.status:
  #     disgust = target_data.status[12]
  #     if disgust:
  #         if now_add_favorability >= disgust:
  #             now_add_favorability -= disgust
  #             target_data.status[12] = 0
  #             if now_add_favorability:
  #                 target_data.favorability[character_id] += now_add_favorability
  #                 if target_change is not None:
  #                     target_change.favorability += now_add_favorability
  #             del target_data.status[12]
  #         else:
  #             target_data.status[12] -= now_add_favorability
  #             if target_change is not None:
  #                 target_change.status[12] -= now_add_favorability
  #     else:
  #         target_data.favorability[character_id] += now_add_favorability
  #         if target_change is not None:
  #             target_change.favorability += now_add_favorability
  # else:

  # NPC对玩家
  if (character_id != 0) and (character_data.target_character_id == 0):
    character_data.favorability[target_id] += now_add_favorability
    character_data.favorability[target_id] = min(
        100000, character_data.favorability[target_id]
    )
    # print(f"debug change_data = {change_data}")
    if change_data is not None:
      change_data.favorability += now_add_favorability

  # 对NPC
  if character_data.target_character_id != 0:
    target_data.favorability[character_id] += now_add_favorability
    target_data.favorability[character_id] = min(
        100000, target_data.favorability[character_id]
    )
    if target_change is not None:
      target_change.favorability += now_add_favorability
  # target_data.social_contact_last_cut_down_time[character_id] = now_time
  # if target_change is not None:
  #     add_favorability(target_id, character_id, old_add_favorability, None, None, now_time)

  # 记录好感度增加
  if character_id == 0 or character_data.target_character_id == 0:
    cache.rhodes_island.total_favorability_increased += now_add_favorability


def handle_character_setting() -> None:
  """
  处理角色的初始世界设置
  """
  cache = cache_control.cache
  # 遍历所有角色
  for character_id in cache.character_data:
    if character_id == 0:
      continue
    character_data = cache.character_data[character_id]
    # 淫乱化
    if cache.world_setting[2]:
      character_data.talent[40] = 1
    # 泌乳化
    if cache.world_setting[3]:
      character_data.talent[27] = 1
