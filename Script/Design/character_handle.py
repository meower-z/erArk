"""角色数据的生成与初始化：NPC列表、角色模板、新生孩子、初始位置、娱乐、开放设施与工作，以及获得新角色与增加好感"""

import datetime
import random
from types import FunctionType
from Script.Core import constant, game_type, get_text
from Script.Design import (
    attr_calculation,
    map_handle,
    character,
    handle_npc_ai,
    basement,
    game_time,
)
from Script.Config import game_config, normal_config
from Script.Modules.domains import abilities, activity, facility, flags, needs
from Script.Modules.domains import player_collection, playthrough, roster
from Script.Modules.domains import tallies, visitor, wardrobe, chara_key
from Script.Modules.domains import chara_life, npc_template, relations
from Script.Modules.domains import identity

_: FunctionType = get_text._
""" 翻译api """


def init_character_list() -> None:
    """
    初始生成所有npc数据
    """
    for adv_id, now_npc_data in npc_template.table().items():
        # print("adv_id=",adv_id,". now_npc_data:",now_npc_data)
        init_character(adv_id, now_npc_data, collect_reset=False)


def init_character(
    character_id: int,
    character_tem: game_type.NpcTem,
    collect_reset: bool = True,
    register_roster: bool = True,
) -> identity.Identity:
    """
    按模板初始化角色数据并写入角色身份表
    Keyword arguments:
    character_id -- 角色id
    character_tem -- 角色生成模板数据
    collect_reset -- 为真且玩家存在时初始化藏品条目
    register_roster -- 是否写入在编名册与已用姓名（读档补模板角色时为 False）
    Return arguments:
    identity.Identity -- 写入后的角色身份
    """
    # print("进入init_character")
    # print("生成阶段，character_id :",character_id)
    # print("character_id=",character_id)
    chara_key.reset(character_id)
    # 检测基础干员并加入已有干员列表
    if register_roster:
        if character_tem.AdvNpc in constant.first_NPC_adv_set:
            roster.add(character_id)
        roster.add_name(character_tem.Name)  # 加入到已有干员姓名中
    relations.nation.set(character_id, character_tem.Nation)
    relations.birthplace.set(character_id, character_tem.Birthplace)
    # 如果有母亲的话则加上亲子关系
    if character_tem.Mother_id:
        relations.father_id.set(character_id, 0)
        relations.mother_id.set(character_id, character_tem.Mother_id)
    activity.set_target(character_id, character_id)
    relations.favorability.set(character_id, {0: 0})
    relations.trust.set(character_id, 0)
    abilities.ability(character_id).replace(character_tem.Ability)
    abilities.experience(character_id).replace(character_tem.Experience)
    abilities.talent(character_id).replace(character_tem.Talent)
    abilities.juel(character_id).replace({})
    needs.set(character_id, hit_max=character_tem.Hp, mana_max=character_tem.Mp)
    chara_life.dormitory.set(character_id, character_tem.Dormitory)
    # 生成衣服
    cloth = attr_calculation.get_cloth_zero()
    cloth.cloth_wear = attr_calculation.get_cloth_wear_zero()
    for cloth_id in character_tem.Cloth:
        type = game_config.config_clothing_tem[cloth_id].clothing_type
        cloth.clothing_tem.append(cloth_id)
        cloth.cloth_wear[type].append(cloth_id)
    wardrobe.put(character_id, cloth)
    # 生成藏品
    if collect_reset and identity.exists(0):
        player_collection.set_npc_entries(character_id)
    # 口上版本
    normal_config.system_setting.character_text_version[character_id] = 1
    # 最后集成
    identity.put(template_identity(character_id, character_tem))
    character.init_attr(character_id)
    return identity.of(character_id)


def template_identity(
    character_id: int,
    character_tem: game_type.NpcTem,
    birthday: datetime.date = datetime.date(1, 1, 1),
) -> identity.Identity:
    """
    按角色模板构造只读的角色身份记录
    Keyword arguments:
    character_id -- 角色id
    character_tem -- 角色生成模板数据
    birthday -- 角色生日，默认 0001-01-01
    Return arguments:
    identity.Identity -- 构造出的角色身份记录
    """
    return identity.Identity(
        character_id,
        name=character_tem.Name,
        sex=character_tem.Sex,
        talk_size=character_tem.Talk_Size,
        text_color=character_tem.TextColor or "",
        birthday=birthday,
        adv=character_tem.AdvNpc,
        profession=character_tem.Profession,
        race=character_tem.Race,
        token_text=character_tem.Token,
    )


def first_NPC_work() -> None:
    """
    初始角色的工作安排
    """
    for character_id in roster.active():
        character_data = identity.of(character_id)
        # 按干员编号认人：角色名随语言翻译
        if character_data.adv in {7}:  # 可露希尔
            chara_life.work_type.set(character_id, 21)
        elif character_data.adv in {3, 171}:  # 凯尔希、华法琳
            chara_life.work_type.set(character_id, 61)
        elif character_data.adv in {56}:  # 特蕾西娅
            chara_life.work_type.set(character_id, 71)
        elif character_data.adv in {130}:  # 杜宾
            chara_life.work_type.set(character_id, 91)
    basement.update_work_people()


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
    mom_character_data: identity.Identity = identity.of(mother_id)
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
            and abilities.talent(mother_id)[talent_id]
        ):
            # 跳过胸部、臀部、腿和脚
            if 122 <= talent_id <= 132:
                continue
            now_tem.Talent[talent_id] = 1
    now_tem.Talent[121] = 1
    now_tem.Hp = random.randint(1000, 2000)
    now_tem.Mp = random.randint(1000, 2000)
    now_id = now_tem.AdvNpc  # 使用adv作为id
    npc_template.add(now_tem)
    # 给父母加上该孩子的社会关系
    child_id_list = relations.child_id_list(0)
    child_id_list.append(now_id)
    relations.child_id_list.set(0, child_id_list)
    with relations.child_id_list.editing(mother_id) as child_id_list:
        child_id_list.append(now_id)
    # 记录特殊履历：第一次分娩（附记孩子的名字，地点即母亲分娩时所在位置）
    from Script.System.First_Record_System import first_record_handle

    first_record_handle.record_first_special_record(mother_id, 2, child_name)
    # roster.add(now_id)
    init_character(now_id, now_tem)
    return now_id


def init_character_position() -> None:
    """初始化角色位置"""
    roster.add(0)
    for character_id in roster.active():
        character_position = activity.position(character_id)
        character_dormitory = chara_life.dormitory(character_id)
        character_dormitory_str = map_handle.get_map_system_path_for_str(
            character_dormitory
        )
        # print("character_dormitory = ",character_dormitory)
        map_handle.character_move_scene(
            character_position, character_dormitory_str, character_id
        )
    character_position = activity.position(0)
    map_handle.character_move_scene(["0", "0"], character_position, 0)


def init_character_entertainment() -> None:
    """初始化角色娱乐"""
    roster.add(0)
    for character_id in roster.active():
        handle_npc_ai.get_chara_entertainment(character_id)


def init_character_facility_open() -> None:
    """初始化角色开放设施"""
    for open_cid in game_config.config_facility_open:
        if game_config.config_facility_open[open_cid].NPC_id == 0:
            continue
        for character_id in roster.active():
            # 跳过玩家id
            if character_id == 0:
                continue
            if (
                game_config.config_facility_open[open_cid].NPC_id
                == identity.of(character_id).adv
            ):
                facility.set_open(open_cid, True)
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
        now_time=game_time.now(),
    )

    character_data = identity.of(character_id)
    # 清零全特殊状态flag
    flags.reset(character_id)

    if visitor_flag:
        # 根据访客区的等级，赋予对应的停留时间
        now_level = facility.level(13)
        facility_cid = game_config.config_facility_effect_data[_("访客区")][
            int(now_level)
        ]
        facility_effect = game_config.config_facility_effect[
            facility_cid
        ].effect
        stay_days = facility_effect
        end_time = game_time.get_sub_date(
            day=stay_days, old_date=game_time.now()
        )
        visitor.arrive(character_id, end_time)
        # 赋予访客flag
        flags.set(character_id, vistor=1)
    else:
        # 如果满足设施开放的前提条件，则开放该设施
        for open_cid in game_config.config_facility_open:
            if (
                game_config.config_facility_open[open_cid].NPC_id
                and game_config.config_facility_open[open_cid].NPC_id
                == character_data.adv
            ):
                facility.set_open(open_cid, True)

    # 分配角色宿舍
    dormitory_common.new_character_get_dormitory(character_id)

    # 初始化新角色位置
    character_position = activity.position(character_id)
    office_postion = ["中枢", "博士办公室"]
    map_handle.character_move_scene(
        character_position, office_postion, character_id
    )

    # 初始化新角色娱乐
    handle_npc_ai.get_chara_entertainment(character_id)

    # 新角色原地等待30分钟：她加入内核时以此刻结束的空闲开始，接着开始排上的等待
    from Script.Modules.gameplay_resolution import plan_queue

    activity.set_behavior(character_id, start_time=game_time.now(), duration=0)
    plan_queue.plan_next(
        character_id,
        constant.Behavior.WAIT,
        30,
        state=constant.CharacterStatus.STATUS_WAIT,
    )


def add_favorability(
    character_id: int,
    target_id: int,
    now_add_favorability: int,
    change_data: (
        game_type.CharacterStatusChange | game_type.TargetChange | None
    ),
    target_change: (
        game_type.TargetChange | game_type.CharacterStatusChange | None
    ),
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
    favorability = relations.favorability(target_id)
    favorability.setdefault(character_id, 0)
    relations.favorability.set(target_id, favorability)
    favorability = relations.favorability(character_id)
    favorability.setdefault(target_id, 0)
    relations.favorability.set(character_id, favorability)
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
    if (character_id != 0) and (activity.target(character_id) == 0):
        with relations.favorability.editing(character_id) as favorability:
            favorability[target_id] += now_add_favorability
            favorability[target_id] = min(100000, favorability[target_id])
        # print(f"debug change_data = {change_data}")
        if change_data is not None:
            change_data.favorability += now_add_favorability

    # 对NPC
    if activity.target(character_id) != 0:
        with relations.favorability.editing(target_id) as favorability:
            favorability[character_id] += now_add_favorability
            favorability[character_id] = min(100000, favorability[character_id])
        if target_change is not None:
            target_change.favorability += now_add_favorability
    # target_data.social_contact_last_cut_down_time[character_id] = now_time
    # if target_change is not None:
    #     add_favorability(target_id, character_id, old_add_favorability, None, None, now_time)

    # 记录好感度增加
    if character_id == 0 or activity.target(character_id) == 0:
        tallies.add(tallies.FAVORABILITY, now_add_favorability)


def handle_character_setting() -> None:
    """
    处理角色的初始世界设置
    """
    # 遍历所有角色
    for character_id in identity.table():
        if character_id == 0:
            continue
        # 淫乱化
        if playthrough.setting(playthrough.WORLD, 2):
            abilities.talent(character_id)[40] = 1
        # 泌乳化
        if playthrough.setting(playthrough.WORLD, 3):
            abilities.talent(character_id)[27] = 1
