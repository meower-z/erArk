"""存档载入时对旧存档角色数据的迁移与修正，以及幼年角色相关数据的清理"""

from __future__ import annotations

import dataclasses
import datetime
from types import FunctionType
from Script.Core import cache_control, constant, game_path_config, game_type
from Script.Core import get_text
from Script.Config import character_config, game_config
from Script.Design import attr_calculation, character_handle, child_stage_gate
from typing import Any, TypedDict
from Script.Design import game_time
from Script.Modules.domains import abilities, action_info, activity, body_manage
from Script.Modules.domains import commission, diplomacy, dirty, economy
from Script.Modules.domains import education, first_record, flags, fridge
from Script.Modules.domains import growth, h_meters, h_state, hypnosis
from Script.Modules.domains import inventory, library, maintenance, medical
from Script.Modules.domains import modes, needs, physical_exam, player_ability
from Script.Modules.domains import player_collection, playthrough, power
from Script.Modules.domains import pregnancy, prison, production, recruit
from Script.Modules.domains import roster, status, visitor, wardrobe, work
from Script.Modules.domains import chara_key, chara_life, chara_profile
from Script.Modules.domains import identity, relations
from Script.Modules.domains.chara_key import CharaKey
from Script.Modules.save_load import upgrade

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
        "first_hand_in_hand",
        "first_kiss_id",
        "first_sex_id",
        "first_a_sex_id",
        "first_u_sex_id",
        "first_w_sex_id",
    ):
        if (
            hasattr(first_record, attr_name)
            and getattr(first_record, attr_name) > 0
        ):
            old_id = getattr(first_record, attr_name)
            setattr(first_record, attr_name, id_map.get(old_id, old_id))
    # 部位交初体验dict中的对象角色ID
    for part_record in getattr(
        first_record, "first_part_sex_dict", {}
    ).values():
        if isinstance(part_record, dict) and part_record.get("id", -1) > 0:
            part_record["id"] = id_map.get(part_record["id"], part_record["id"])


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
    if isinstance(loaded_dict["npc_tem_data"], list):
        old_tem_list = loaded_dict["npc_tem_data"]
        new_tem_dict = {}
        for tem in old_tem_list:
            new_tem_dict[tem.AdvNpc] = tem
        loaded_dict["npc_tem_data"] = new_tem_dict
        update_count += len(old_tem_list)

    # 2. 建立旧id到新id的映射
    old_to_new_id = {0: 0}  # 玩家id保持为0
    old_character_data = loaded_dict["character_data"]

    for old_cid in old_character_data:
        if old_cid != 0:
            old_to_new_id[old_cid] = identity.of(old_cid).adv

    # 3. 转换 character_data，身份表按同样顺序换成新 id
    new_character_data = {}
    records = []
    for old_cid, character in old_character_data.items():
        new_cid = old_to_new_id[old_cid]
        new_character_data[new_cid] = character
        records.append(dataclasses.replace(identity.of(old_cid), cid=new_cid))
        update_count += 1
    loaded_dict["character_data"] = new_character_data
    identity.replace_all(records)

    # 4. 转换npc_id_got
    old_npc_id_got = loaded_dict.get("npc_id_got", set())
    new_npc_id_got = set()
    for old_id in old_npc_id_got:
        if old_id in old_to_new_id:
            new_npc_id_got.add(old_to_new_id[old_id])
    loaded_dict["npc_id_got"] = new_npc_id_got

    # 5. 转换其他引用角色ID的数据结构
    # 5.1 玩家收藏品
    if 0 in new_character_data:
        pl_data = new_character_data[0]
        if hasattr(pl_data, "pl_collection"):
            # token_list
            if hasattr(pl_data.pl_collection, "token_list"):
                old_token = pl_data.pl_collection.token_list.copy()
                pl_data.pl_collection.token_list = {}
                for old_id, value in old_token.items():
                    new_id = old_to_new_id.get(old_id, old_id)
                    pl_data.pl_collection.token_list[new_id] = value

            # first_panties
            if hasattr(pl_data.pl_collection, "first_panties"):
                old_panties = pl_data.pl_collection.first_panties.copy()
                pl_data.pl_collection.first_panties = {}
                for old_id, value in old_panties.items():
                    new_id = old_to_new_id.get(old_id, old_id)
                    pl_data.pl_collection.first_panties[new_id] = value

            # npc_panties
            if hasattr(pl_data.pl_collection, "npc_panties"):
                old_npc_panties = pl_data.pl_collection.npc_panties.copy()
                pl_data.pl_collection.npc_panties = {}
                for old_id, value in old_npc_panties.items():
                    new_id = old_to_new_id.get(old_id, old_id)
                    pl_data.pl_collection.npc_panties[new_id] = value

            # npc_socks
            if hasattr(pl_data.pl_collection, "npc_socks"):
                old_npc_socks = pl_data.pl_collection.npc_socks.copy()
                pl_data.pl_collection.npc_socks = {}
                for old_id, value in old_npc_socks.items():
                    new_id = old_to_new_id.get(old_id, old_id)
                    pl_data.pl_collection.npc_socks[new_id] = value

            # npc_panties_tem (Dict[int, list]) - 临时获得的角色内裤
            if hasattr(pl_data.pl_collection, "npc_panties_tem"):
                old_panties_tem = pl_data.pl_collection.npc_panties_tem.copy()
                pl_data.pl_collection.npc_panties_tem = {}
                for old_id, value in old_panties_tem.items():
                    new_id = old_to_new_id.get(old_id, old_id)
                    pl_data.pl_collection.npc_panties_tem[new_id] = value

            # npc_socks_tem (Dict[int, list]) - 临时获得的角色袜子
            if hasattr(pl_data.pl_collection, "npc_socks_tem"):
                old_socks_tem = pl_data.pl_collection.npc_socks_tem.copy()
                pl_data.pl_collection.npc_socks_tem = {}
                for old_id, value in old_socks_tem.items():
                    new_id = old_to_new_id.get(old_id, old_id)
                    pl_data.pl_collection.npc_socks_tem[new_id] = value

            # eqip_token[1] - 已装备信物的干员id列表
            if (
                hasattr(pl_data.pl_collection, "eqip_token")
                and len(pl_data.pl_collection.eqip_token) > 1
            ):
                old_equip_list = pl_data.pl_collection.eqip_token[1]
                pl_data.pl_collection.eqip_token[1] = [
                    old_to_new_id.get(oid, oid) for oid in old_equip_list
                ]

            # milk_total (Dict[int, int])
            if hasattr(pl_data.pl_collection, "milk_total"):
                old_milk = pl_data.pl_collection.milk_total.copy()
                pl_data.pl_collection.milk_total = {}
                for old_id, value in old_milk.items():
                    new_id = old_to_new_id.get(old_id, old_id)
                    pl_data.pl_collection.milk_total[new_id] = value

            # urine_total (Dict[int, int])
            if hasattr(pl_data.pl_collection, "urine_total"):
                old_urine = pl_data.pl_collection.urine_total.copy()
                pl_data.pl_collection.urine_total = {}
                for old_id, value in old_urine.items():
                    new_id = old_to_new_id.get(old_id, old_id)
                    pl_data.pl_collection.urine_total[new_id] = value

    # 5.2 每个角色的favorability字典（角色id:好感度）
    for _char_id, character in new_character_data.items():
        if hasattr(character, "favorability"):
            old_fav = character.favorability.copy()
            character.favorability = {}
            for old_id, value in old_fav.items():
                new_id = old_to_new_id.get(old_id, old_id)
                character.favorability[new_id] = value

    # 5.3 每个角色的target_character_id
    activity.remap_targets(new_character_data, old_to_new_id)

    # 5.4 每个角色的assistant_character_id
    for _char_id, character in new_character_data.items():
        if hasattr(character, "assistant_character_id"):
            old_assistant = character.assistant_character_id
            character.assistant_character_id = old_to_new_id.get(
                old_assistant, old_assistant
            )

    # 5.4b 每个角色的其他角色ID引用
    for _char_id, character in new_character_data.items():
        # ask_group_sex_refuse_chara_id_list (位于action_info中)
        if hasattr(character, "action_info") and hasattr(
            character.action_info, "ask_group_sex_refuse_chara_id_list"
        ):
            character.action_info.ask_group_sex_refuse_chara_id_list = [
                old_to_new_id.get(oid, oid)
                for oid in character.action_info.ask_group_sex_refuse_chara_id_list
            ]

        # sp_flag.bagging_chara_id (注意：是sp_flag不是state_active)
        if hasattr(character, "sp_flag") and hasattr(
            character.sp_flag, "bagging_chara_id"
        ):
            if character.sp_flag.bagging_chara_id != 0:
                character.sp_flag.bagging_chara_id = old_to_new_id.get(
                    character.sp_flag.bagging_chara_id,
                    character.sp_flag.bagging_chara_id,
                )

        # pl_ability.carry_chara_id_in_time_stop (注意：是pl_ability不是sp_flag)
        if hasattr(character, "pl_ability") and hasattr(
            character.pl_ability, "carry_chara_id_in_time_stop"
        ):
            if character.pl_ability.carry_chara_id_in_time_stop != 0:
                character.pl_ability.carry_chara_id_in_time_stop = (
                    old_to_new_id.get(
                        character.pl_ability.carry_chara_id_in_time_stop,
                        character.pl_ability.carry_chara_id_in_time_stop,
                    )
                )

        # pl_ability.free_in_time_stop_chara_id (注意：是pl_ability不是sp_flag)
        if hasattr(character, "pl_ability") and hasattr(
            character.pl_ability, "free_in_time_stop_chara_id"
        ):
            if character.pl_ability.free_in_time_stop_chara_id != 0:
                character.pl_ability.free_in_time_stop_chara_id = (
                    old_to_new_id.get(
                        character.pl_ability.free_in_time_stop_chara_id,
                        character.pl_ability.free_in_time_stop_chara_id,
                    )
                )

        # action_info.interacting_character_end_info[0] (注意：是action_info中的)
        if hasattr(character, "action_info") and hasattr(
            character.action_info, "interacting_character_end_info"
        ):
            if character.action_info.interacting_character_end_info[0] != -1:
                character.action_info.interacting_character_end_info[0] = (
                    old_to_new_id.get(
                        character.action_info.interacting_character_end_info[0],
                        character.action_info.interacting_character_end_info[0],
                    )
                )

        # action_info.social_contact_last_time (Dict[int, datetime])
        if hasattr(character, "action_info") and hasattr(
            character.action_info, "social_contact_last_time"
        ):
            old_social = character.action_info.social_contact_last_time.copy()
            character.action_info.social_contact_last_time = {}
            for old_id, value in old_social.items():
                new_id = old_to_new_id.get(old_id, old_id)
                character.action_info.social_contact_last_time[new_id] = value

        # action_info.social_contact_last_cut_down_time (Dict[int, datetime])
        if hasattr(character, "action_info") and hasattr(
            character.action_info, "social_contact_last_cut_down_time"
        ):
            old_cutdown = (
                character.action_info.social_contact_last_cut_down_time.copy()
            )
            character.action_info.social_contact_last_cut_down_time = {}
            for old_id, value in old_cutdown.items():
                new_id = old_to_new_id.get(old_id, old_id)
                character.action_info.social_contact_last_cut_down_time[
                    new_id
                ] = value

        # first_record中的角色ID字段（含first_part_sex_dict与历史周目快照）
        if hasattr(character, "first_record"):
            _remap_first_record_ids(character.first_record, old_to_new_id)
        for history_record in getattr(
            character, "first_record_history", {}
        ).values():
            _remap_first_record_ids(history_record, old_to_new_id)

        # h_state.group_sex_body_template_dict 中的角色ID
        if hasattr(character, "h_state") and hasattr(
            character.h_state, "group_sex_body_template_dict"
        ):
            template_dict = character.h_state.group_sex_body_template_dict
            for template_key in ["A", "B"]:
                if template_key in template_dict:
                    # 处理对单部位字典
                    if len(template_dict[template_key]) > 0 and isinstance(
                        template_dict[template_key][0], dict
                    ):
                        for _part_key, part_value in template_dict[
                            template_key
                        ][0].items():
                            if (
                                isinstance(part_value, list)
                                and len(part_value) > 0
                                and part_value[0] != -1
                            ):
                                part_value[0] = old_to_new_id.get(
                                    part_value[0], part_value[0]
                                )
                    # 处理阴茎侍奉列表
                    if len(template_dict[template_key]) > 1 and isinstance(
                        template_dict[template_key][1], list
                    ):
                        serve_data = template_dict[template_key][1]
                        if len(serve_data) > 0 and isinstance(
                            serve_data[0], list
                        ):
                            serve_data[0] = [
                                (
                                    old_to_new_id.get(oid, oid)
                                    if oid != -1
                                    else oid
                                )
                                for oid in serve_data[0]
                            ]

    # 5.5 基建各领域模块中的角色引用
    # 招募线的主招聘专员、待确认招募、借书人与外交官
    recruit.remap(old_to_new_id)
    library.remap(old_to_new_id)
    diplomacy.remap(old_to_new_id)
    power.remap_operators(old_to_new_id)
    production.remap(old_to_new_id)
    # 换工程部与体检数据里的角色id，正在进行的体检除外
    maintenance.remap(old_to_new_id)
    physical_exam.remap(old_to_new_id)

    # 冰箱两个表里的角色id
    fridge.remap(old_to_new_id)

    # 医疗部的门诊、住院医生名单与分科配置
    medical.remap_doctors(old_to_new_id)

    economy.remap_traders(old_to_new_id)

    # 访客、邀请目标与外勤委托的队伍里的角色id
    _remap_visitor_and_commission(old_to_new_id)

    # 关押区囚犯名册
    prison.remap(old_to_new_id)

    # 岗位名册与监狱长
    work.set_warden(normalize_single_character_id(work.warden(), 0))
    work.remap(old_to_new_id)

    # 5.6 关系数据中的角色引用
    for _char_id, character in new_character_data.items():
        if hasattr(character, "relationship"):
            rel = character.relationship
            # father_id
            if hasattr(rel, "father_id") and rel.father_id > 0:
                rel.father_id = old_to_new_id.get(rel.father_id, rel.father_id)
            # mother_id
            if hasattr(rel, "mother_id") and rel.mother_id > 0:
                rel.mother_id = old_to_new_id.get(rel.mother_id, rel.mother_id)
            # child_id_list
            if hasattr(rel, "child_id_list"):
                rel.child_id_list = [
                    old_to_new_id.get(cid, cid) for cid in rel.child_id_list
                ]
            # firend_id_list
            if hasattr(rel, "firend_id_list"):
                rel.firend_id_list = [
                    old_to_new_id.get(fid, fid) for fid in rel.firend_id_list
                ]

    # 5.7 cache级别的角色ID引用
    # forbidden_npc_id
    if "forbidden_npc_id" in loaded_dict:
        old_forbidden = loaded_dict["forbidden_npc_id"].copy()
        loaded_dict["forbidden_npc_id"] = {
            old_to_new_id.get(oid, oid) for oid in old_forbidden
        }

    # 5.8 achievement中的角色ID引用
    if "achievement" in loaded_dict:
        ach = loaded_dict["achievement"]

        # body_report_chara_count_list (List[int]) - 出具过身体检查报告的干员id列表
        if hasattr(ach, "body_report_chara_count_list"):
            ach.body_report_chara_count_list = [
                old_to_new_id.get(oid, oid)
                for oid in ach.body_report_chara_count_list
            ]

        # group_sex_record (Dict[int, list]) - 群交记录
        if hasattr(ach, "group_sex_record") and ach.group_sex_record:
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
    from Script.Design import attr_calculation

    migrated_count = 0
    character_data = loaded_dict.get("character_data", {})
    npc_tem_data = loaded_dict.get("npc_tem_data", {})
    # 下面的循环按旧属性名复制角色数据。版本 21 的存档对象上没有这些属性，lift 先把角色键的值写上去。
    # 读档随后的 adopt_old_save 把它们写回角色键
    chara_key.lift(loaded_dict)

    # 记录迁移信息用于日志
    migration_log = []

    for old_id, new_id in old_to_new_id_map.items():
        # 检查旧角色是否存在于存档中
        if not identity.exists(old_id):
            continue

        # 检查新角色模板是否存在于当前游戏配置中
        if new_id not in character_config.character_tem_list:
            continue

        old_character = character_data[old_id]
        new_tem = character_config.character_tem_list[new_id]
        old_name = identity.of(old_id).name
        new_name = new_tem.Name

        # ========== 1. 创建新角色基础数据 ==========
        # 搬进 GameState 的属性（如 dormitory、nick_name）在这里按旧属性名写在新角色对象上。
        # 读档随后的 adopt_old_save 把它们写进 GameState
        new_character: Any = game_type.Character()

        # 从新模板写入身份，生日沿用旧角色
        identity.put(
            character_handle.template_identity(
                new_id, new_tem, identity.of(old_id).birthday
            )
        )
        new_character.dormitory = new_tem.Dormitory

        # 从新模板生成衣服
        cloth = attr_calculation.get_cloth_zero()
        cloth.cloth_wear = attr_calculation.get_cloth_wear_zero()
        for cloth_id in new_tem.Cloth:
            if cloth_id in game_config.config_clothing_tem:
                cloth_type = game_config.config_clothing_tem[
                    cloth_id
                ].clothing_type
                cloth.clothing_tem.append(cloth_id)
                cloth.cloth_wear[cloth_type].append(cloth_id)
        wardrobe.put(new_id, cloth)

        # ========== 2. 复制旧角色的动态数据 ==========
        # 数值属性
        h_meters.copy_replaced(old_character, new_character, old_id, new_id)
        if not upgrade.copy_v0_needs(old_character, new_character):
            needs.set(new_id, **needs.of(old_id))
        if not upgrade.copy_pickled(
            old_character, new_character, new_tem.Hp, new_tem.Mp
        ):
            needs.set(new_id, hit_max=new_tem.Hp, mana_max=new_tem.Mp, drunk=0)
        activity.copy_on_replace(
            old_character, new_character, old_id, new_id, old_to_new_id_map
        )

        # 字典/集合属性
        status.replace(new_id, status.of(old_id))
        abilities.copy_tables(old_id, new_id)
        inventory.replace_items(new_id, inventory.items(old_id))
        new_character.chara_setting = (
            old_character.chara_setting.copy()
            if hasattr(old_character, "chara_setting")
            and old_character.chara_setting
            else {}
        )
        new_character.assistant_services = (
            old_character.assistant_services.copy()
            if hasattr(old_character, "assistant_services")
            and old_character.assistant_services
            else {}
        )
        body_manage.replace(new_id, body_manage.of(old_id))

        # 好感度数据（需要转换内部ID引用）
        new_character.favorability = {}
        if old_character.favorability:
            for fav_id, fav_value in old_character.favorability.items():
                new_fav_id = old_to_new_id_map.get(fav_id, fav_id)
                new_character.favorability[new_fav_id] = fav_value

        new_character.trust = old_character.trust

        # 信赖相关
        new_character.assistant_character_id = (
            old_to_new_id_map.get(
                old_character.assistant_character_id,
                old_character.assistant_character_id,
            )
            if hasattr(old_character, "assistant_character_id")
            else 0
        )

        # 其他字符串属性
        new_character.nick_name = (
            old_character.nick_name
            if hasattr(old_character, "nick_name")
            else ""
        )
        new_character.nick_name_to_pl = (
            old_character.nick_name_to_pl
            if hasattr(old_character, "nick_name_to_pl")
            else ""
        )

        # 位置数据
        new_character.officeroom = (
            old_character.officeroom.copy()
            if hasattr(old_character, "officeroom") and old_character.officeroom
            else []
        )
        new_character.permanent_dormitory = getattr(
            old_character,
            "permanent_dormitory",
            getattr(old_character, "pre_dormitory", ""),
        )

        # 时间相关

        # 复杂对象属性 - 直接复制引用后更新内部ID
        inventory.replace_foods(new_id, inventory.foods(old_id))
        dirty.copy_replaced(old_character, new_character, old_id, new_id)
        h_state.copy_replaced(old_character, new_character, old_id, new_id)
        for domain in (flags, action_info, player_ability, player_collection):
            domain.copy_to(old_id, new_id)
        new_character.work = old_character.work
        new_character.entertainment = (
            old_character.entertainment
            if hasattr(old_character, "entertainment")
            else game_type.CHARA_ENTERTAINMENT()
        )
        if "pregnancy" in vars(old_character):
            vars(new_character)["pregnancy"] = old_character.pregnancy
        else:
            pregnancy.copy_character(old_id, new_id)
        if "child_growth" in vars(old_character):
            vars(new_character)["child_growth"] = old_character.child_growth
        else:
            growth.copy_character(old_id, new_id)
        hypnosis.copy_replaced(old_character, new_character, old_id, new_id)
        new_character.author_flag = (
            old_character.author_flag
            if hasattr(old_character, "author_flag")
            else game_type.AUTHOR_FLAG()
        )

        # 关系数据 - 复制并转换ID
        new_character.relationship = (
            old_character.relationship
            if hasattr(old_character, "relationship")
            else game_type.RELATIONSHIP()
        )
        # 更新relationship中的势力和出身地为新模板值
        new_character.relationship.nation = new_tem.Nation
        new_character.relationship.birthplace = new_tem.Birthplace
        # 转换关系中的角色ID
        if (
            hasattr(new_character.relationship, "father_id")
            and new_character.relationship.father_id > 0
        ):
            new_character.relationship.father_id = old_to_new_id_map.get(
                new_character.relationship.father_id,
                new_character.relationship.father_id,
            )
        if (
            hasattr(new_character.relationship, "mother_id")
            and new_character.relationship.mother_id > 0
        ):
            new_character.relationship.mother_id = old_to_new_id_map.get(
                new_character.relationship.mother_id,
                new_character.relationship.mother_id,
            )
        if (
            hasattr(new_character.relationship, "child_id_list")
            and new_character.relationship.child_id_list
        ):
            new_character.relationship.child_id_list = [
                old_to_new_id_map.get(cid, cid)
                for cid in new_character.relationship.child_id_list
            ]
        if (
            hasattr(new_character.relationship, "firend_id_list")
            and new_character.relationship.firend_id_list
        ):
            new_character.relationship.firend_id_list = [
                old_to_new_id_map.get(fid, fid)
                for fid in new_character.relationship.firend_id_list
            ]

        # first_record中的角色ID转换（含first_part_sex_dict与历史周目快照）
        if hasattr(new_character, "first_record"):
            _remap_first_record_ids(
                new_character.first_record, old_to_new_id_map
            )
        for history_record in getattr(
            new_character, "first_record_history", {}
        ).values():
            _remap_first_record_ids(history_record, old_to_new_id_map)
        first_record.remap_ids(new_id, old_to_new_id_map)

        # h_state中的角色ID转换
        if hasattr(new_character, "h_state") and hasattr(
            new_character.h_state, "group_sex_body_template_dict"
        ):
            if new_character.h_state.group_sex_body_template_dict:
                old_group = (
                    new_character.h_state.group_sex_body_template_dict.copy()
                )
                new_character.h_state.group_sex_body_template_dict = {}
                for oid, value in old_group.items():
                    new_character.h_state.group_sex_body_template_dict[
                        old_to_new_id_map.get(oid, oid)
                    ] = value
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
                            (
                                old_to_new_id_map.get(oid, oid)
                                if oid != -1
                                else oid
                            )
                            for oid in serve_data[0]
                        ]
        h_state.remap_group_sex_ids(new_id, old_to_new_id_map)

        # ========== 3. 将新角色添加到 character_data ==========
        character_data[new_id] = new_character

        # ========== 4. 更新npc_id_got ==========
        if "npc_id_got" in loaded_dict:
            if old_id in loaded_dict["npc_id_got"]:
                loaded_dict["npc_id_got"].discard(old_id)
                loaded_dict["npc_id_got"].add(new_id)
        roster.remap({old_id: new_id}, characters=character_data)

        # ========== 5. 更新npc_tem_data ==========
        if old_id in npc_tem_data:
            del npc_tem_data[old_id]
        npc_tem_data[new_id] = new_tem

        # 记录迁移日志
        migration_log.append((old_name, new_name, old_id, new_id))
        migrated_count += 1

    # 如果没有迁移任何角色，直接返回
    if migrated_count == 0:
        return 0

    # ========== 6. 更新所有角色中对旧ID的引用 ==========
    activity.remap_targets(character_data, old_to_new_id_map)
    for _char_id, character in character_data.items():
        # 好感度字典
        if hasattr(character, "favorability") and character.favorability:
            old_fav = character.favorability.copy()
            character.favorability = {}
            for fav_id, value in old_fav.items():
                character.favorability[
                    old_to_new_id_map.get(fav_id, fav_id)
                ] = value

        # assistant_character_id
        if hasattr(character, "assistant_character_id"):
            character.assistant_character_id = old_to_new_id_map.get(
                character.assistant_character_id,
                character.assistant_character_id,
            )

        # first_record中的角色ID（含first_part_sex_dict与历史周目快照）
        if hasattr(character, "first_record"):
            _remap_first_record_ids(character.first_record, old_to_new_id_map)
        for history_record in getattr(
            character, "first_record_history", {}
        ).values():
            _remap_first_record_ids(history_record, old_to_new_id_map)
        first_record.remap_ids(_char_id, old_to_new_id_map)

        # relationship中的角色ID
        if hasattr(character, "relationship"):
            rel = character.relationship
            if hasattr(rel, "father_id") and rel.father_id > 0:
                rel.father_id = old_to_new_id_map.get(
                    rel.father_id, rel.father_id
                )
            if hasattr(rel, "mother_id") and rel.mother_id > 0:
                rel.mother_id = old_to_new_id_map.get(
                    rel.mother_id, rel.mother_id
                )
            if hasattr(rel, "child_id_list") and rel.child_id_list:
                rel.child_id_list = [
                    old_to_new_id_map.get(cid, cid) for cid in rel.child_id_list
                ]
            if hasattr(rel, "firend_id_list") and rel.firend_id_list:
                rel.firend_id_list = [
                    old_to_new_id_map.get(fid, fid)
                    for fid in rel.firend_id_list
                ]

        # h_state中的角色ID
        if hasattr(character, "h_state") and hasattr(
            character.h_state, "group_sex_body_template_dict"
        ):
            if character.h_state.group_sex_body_template_dict:
                old_group = (
                    character.h_state.group_sex_body_template_dict.copy()
                )
                character.h_state.group_sex_body_template_dict = {}
                for oid, value in old_group.items():
                    character.h_state.group_sex_body_template_dict[
                        old_to_new_id_map.get(oid, oid)
                    ] = value
                for (
                    _cid,
                    serve_data,
                ) in character.h_state.group_sex_body_template_dict.items():
                    if (
                        isinstance(serve_data, list)
                        and len(serve_data) > 0
                        and isinstance(serve_data[0], list)
                    ):
                        serve_data[0] = [
                            (
                                old_to_new_id_map.get(oid, oid)
                                if oid != -1
                                else oid
                            )
                            for oid in serve_data[0]
                        ]
        h_state.remap_group_sex_ids(_char_id, old_to_new_id_map)

    # ========== 7. 更新内核角色域与玩家收藏品中的角色ID引用 ==========
    all_cids = tuple(character_data)
    for domain in (flags, action_info, player_ability, player_collection):
        domain.remap(all_cids, old_to_new_id_map)

    # ========== 8. 更新基建各领域模块中的角色引用 ==========
    # 招募线的主招聘专员、待确认招募、借书人与外交官
    recruit.remap(old_to_new_id_map)
    library.remap(old_to_new_id_map)
    diplomacy.remap(old_to_new_id_map)
    power.remap_operators(old_to_new_id_map)
    work.set_warden(normalize_single_character_id(work.warden(), 0))
    work.remap(old_to_new_id_map)
    production.remap(old_to_new_id_map)
    maintenance.remap(old_to_new_id_map)
    physical_exam.remap(old_to_new_id_map)

    # 冰箱两个表里的角色id
    fridge.remap(old_to_new_id_map)

    # 医疗部的门诊、住院医生名单与分科配置
    medical.remap_doctors(old_to_new_id_map)

    economy.remap_traders(old_to_new_id_map)

    # 访客、邀请目标与外勤委托的队伍里的角色id
    _remap_visitor_and_commission(old_to_new_id_map)

    # 关押区囚犯名册
    prison.remap(old_to_new_id_map)

    # ========== 9. 更新其他cache级别的角色ID引用 ==========
    # forbidden_npc_id
    if "forbidden_npc_id" in loaded_dict and loaded_dict["forbidden_npc_id"]:
        old_forbidden = loaded_dict["forbidden_npc_id"].copy()
        loaded_dict["forbidden_npc_id"] = set()
        for oid in old_forbidden:
            loaded_dict["forbidden_npc_id"].add(old_to_new_id_map.get(oid, oid))

    # ========== 10. 更新achievement中的角色ID引用 ==========
    if "achievement" in loaded_dict:
        ach = loaded_dict["achievement"]

        # body_report_chara_count_list
        if (
            hasattr(ach, "body_report_chara_count_list")
            and ach.body_report_chara_count_list
        ):
            ach.body_report_chara_count_list = [
                old_to_new_id_map.get(oid, oid)
                for oid in ach.body_report_chara_count_list
            ]

        # group_sex_record
        if hasattr(ach, "group_sex_record") and ach.group_sex_record:
            for record_key, record_list in ach.group_sex_record.items():
                if isinstance(record_list, list):
                    ach.group_sex_record[record_key] = [
                        old_to_new_id_map.get(oid, oid) for oid in record_list
                    ]

    # ========== 11. 删除旧角色数据 ==========
    for old_id in old_to_new_id_map.keys():
        if old_id in character_data:
            del character_data[old_id]
            identity.discard(old_id)

    return migrated_count


def update_tem_character(loaded_dict: dict[str, Any]) -> int:
    """
    更新角色预设
    Keyword arguments:
    loaded_dict -- 存档数据
    """

    update_count = 0

    # 浅拷贝静态角色模板字典，供下方循环删去已匹配项并补入新增模板，不改动全局配置
    cache_dict = dict(character_config.character_tem_list)

    # 更新loaded_dict["npc_tem_data"]，用新的角色预设属性代替旧的属性
    for adv_id, now_npc_tem_data in list(loaded_dict["npc_tem_data"].items()):
        # 修正深靛的序号错误
        if now_npc_tem_data.AdvNpc == 496 and 469 in cache_dict:
            loaded_dict["npc_tem_data"][469] = cache_dict[469]
            if adv_id != 469:
                del loaded_dict["npc_tem_data"][adv_id]
            update_count += 1
            del cache_dict[469]
            continue
        # 修正阿玛雅的序号错误
        if (
            now_npc_tem_data.Name == "阿玛雅"
            and now_npc_tem_data.AdvNpc == 450
            and 448 in cache_dict
        ):
            loaded_dict["npc_tem_data"][448] = cache_dict[448]
            if adv_id != 448:
                del loaded_dict["npc_tem_data"][adv_id]
            update_count += 1
            del cache_dict[448]
            continue
        if now_npc_tem_data.AdvNpc in cache_dict:
            # 更新模板
            loaded_dict["npc_tem_data"][adv_id] = cache_dict[
                now_npc_tem_data.AdvNpc
            ]
            # 从cache_dict中移除已经使用的元素
            del cache_dict[now_npc_tem_data.AdvNpc]

    # 将剩余的元素添加到loaded_dict["npc_tem_data"]
    for adv_id, tem_data in cache_dict.items():
        loaded_dict["npc_tem_data"][adv_id] = tem_data
    update_count += len(cache_dict)

    # 更新新增角色
    update_count += update_new_character(loaded_dict)

    # 修正角色数据中缺失模板的情况
    for key, value in loaded_dict["character_data"].items():
        one = identity.of(key)
        # 跳过玩家
        if key == 0:
            continue
        # 检查角色的adv是否有对应的模板
        if one.adv not in loaded_dict["npc_tem_data"]:
            # 修正深靛的序号错误
            if one.name == _("深靛") and one.adv != 469:
                identity.update(key, adv=469)
                update_count += 1
                continue
            # 修正阿玛雅的序号错误：旧存档里阿玛雅与死芒同为450号，450号中名字是阿玛雅的才是她
            if one.adv == 450 and one.name == _("阿玛雅"):
                identity.update(key, adv=448)
                update_count += 1
                continue
            # 其他情况，创建空白模板
            tem_npc_data = character_handle.create_empty_character_tem()
            tem_npc_data.Name = one.name
            tem_npc_data.AdvNpc = one.adv
            # 早于 adopt_old_save：版本 21 对象无 relationship 与 favorability，从角色键 social.mother_id 读母亲id。
            # 有 relationship.mother_id 时从对象读；带 favorability 无 relationship 的旧存档键未导入（默认 -1），保持 0
            if not {"relationship", "favorability"} & vars(value).keys():
                tem_npc_data.Mother_id = relations.mother_id(key)
            elif hasattr(getattr(value, "relationship", None), "mother_id"):
                tem_npc_data.Mother_id = value.relationship.mother_id
            loaded_dict["npc_tem_data"][one.adv] = tem_npc_data
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
    for key, value in loaded_dict["character_data"].items():
        one = identity.of(key)
        # 阿玛雅：旧存档里她与死芒同为450号，450号中名字是阿玛雅的才是她
        if one.adv == 450 and one.name == _("阿玛雅"):
            # 寻找adv为448的角色
            for key2 in loaded_dict["character_data"]:
                if identity.of(key2).adv == 448:
                    # 将阿玛雅的角色数据复制过去
                    source_cid = key
                    # 版本 21 的存档对象上没有旧属性，lift 先把角色键的值写上去，随对象移到新槽位（旧存档不动）。
                    # 原槽位重建会重置其键，读档随后的 adopt_old_save 再把这些值写到新槽位
                    chara_key.lift(loaded_dict)
                    loaded_dict["character_data"][key2] = value
                    for domain in (
                        flags,
                        action_info,
                        player_ability,
                        player_collection,
                    ):
                        domain.copy_to(key, key2)
                    # 目标槽位写入阿玛雅的身份，adv 设为 448
                    identity.put(dataclasses.replace(one, cid=key2, adv=448))
                    # 将当前角色改为当前模板的角色
                    now_tem_chara = loaded_dict["npc_tem_data"].get(
                        source_cid, None
                    )
                    if now_tem_chara is None:
                        now_tem_chara = loaded_dict["npc_tem_data"].get(
                            one.adv, None
                        )
                    if now_tem_chara is not None:
                        # 创建一个新的角色数据
                        character_handle.init_character(
                            source_cid, now_tem_chara, False, False
                        )
                        # 重新赋值角色数据
                        loaded_dict["character_data"][
                            key
                        ] = game_type.Character()
                    update_count += 1
                    break

    return update_count


def update_character_config_data(value: identity.Identity, cid: int) -> int:
    """
    更新角色属性数据，返回更新的条数
    Keyword arguments:
    value -- 角色身份（identity.Identity）
    cid -- 读写设置与助理服务角色键所用的角色id，即角色在身份表里的键
    Return arguments:
    int -- 更新的条数
    """
    update_count = 0
    # 更新角色的各种属性
    experience = abilities.experience(value.cid)
    talent = abilities.talent(value.cid)
    juel = abilities.juel(value.cid)
    ability = abilities.ability(value.cid)
    # 经验
    if len(experience) != len(game_config.config_experience):
        for key in game_config.config_experience:
            if key not in experience:
                experience[key] = 0
                update_count += 1
    # 素质：补齐前先去掉 Talent.csv 里没有的编号 6 与 7。补齐只在素质数与 Talent.csv 不同时运行。
    # 留着这两个键，缺键的存档可能素质数相同而漏补。
    for talent_id in (6, 7):
        update_count += int(talent.pop(talent_id, None) is not None)
    if len(talent) != len(game_config.config_talent):
        for key in game_config.config_talent:
            if key not in talent:
                talent[key] = 0
                update_count += 1
    # 如果没有u插入经验，则增加u处女素质
    if experience[63] == 0 and talent[2] == 0 and value.cid != 0:
        talent[2] = 1
        update_count += 1
    # 去掉玩家的u处女素质
    if value.cid == 0 and talent[2] == 1:
        talent[2] = 0
        update_count += 1
    # 如果没有w插入经验，则增加w处女素质
    if experience[64] == 0 and talent[3] == 0 and value.cid != 0:
        talent[3] = 1
        update_count += 1
    # 去掉玩家的w处女素质
    if value.cid == 0 and talent[3] == 1:
        talent[3] = 0
        update_count += 1
    # 宝珠
    if len(juel) != len(game_config.config_juel):
        for key in game_config.config_juel:
            if key not in juel:
                juel[key] = 0
                update_count += 1
    # 能力
    # 可能存在旧的空编号，所以这里不检查长度
    # if len(value.ability) != len(game_config.config_ability):
    for key in game_config.config_ability:
        if key not in ability:
            ability[key] = 0
            update_count += 1
    # 状态
    for key in game_config.config_character_state:
        if key not in status.of(value.cid):
            status.set(value.cid, key, 0)
            update_count += 1
    # 设置
    chara_setting = chara_profile.chara_setting(cid)
    if len(chara_setting) != len(game_config.config_chara_setting):
        for key in game_config.config_chara_setting:
            if key not in chara_setting:
                chara_setting[key] = 0
                update_count += 1
        chara_profile.chara_setting.set(cid, chara_setting)
    # 道具
    if len(inventory.items(value.cid)) != len(game_config.config_item):
        for key in game_config.config_item:
            if key not in inventory.items(value.cid):
                inventory.set_item(value.cid, key, 0)
                update_count += 1
    # 身体管理
    if len(body_manage.of(value.cid)) == 0:
        body_manage.replace(value.cid, attr_calculation.get_body_manage_zero())
        update_count += 1
    if len(body_manage.of(value.cid)) != len(
        game_config.config_body_manage_requirement
    ):
        for key in game_config.config_body_manage_requirement:
            if key not in body_manage.of(value.cid):
                body_manage.set(value.cid, key, 0)
                update_count += 1
    # 助理服务
    assistant_services = relations.assistant_services(cid)
    if len(assistant_services) != len(game_config.config_assistant_services):
        for key in game_config.config_assistant_services:
            if key not in assistant_services:
                assistant_services[key] = 0
                update_count += 1
        relations.assistant_services.set(cid, assistant_services)
    return update_count


def update_chara_cloth(
    value: identity.Identity, tem_character: game_type.NpcTem
) -> int:
    """
    更新角色服装数据
    Keyword arguments:
    value -- 角色数据
    """
    from Script.Design import clothing

    cloth = wardrobe.of(value.cid)
    # 数据长度不一致时，重置服装数据
    if len(cloth.cloth_wear) != len(game_config.config_clothing_type):
        cloth.cloth_wear = attr_calculation.get_cloth_wear_zero()
    if len(cloth.cloth_locker_in_shower) != len(
        game_config.config_clothing_type
    ):
        cloth.cloth_locker_in_shower = (
            attr_calculation.get_shower_cloth_locker_zero()
        )
    if len(cloth.cloth_locker_in_dormitory) != len(
        game_config.config_clothing_type
    ):
        cloth.cloth_locker_in_dormitory = (
            attr_calculation.get_cloth_locker_in_dormitory_zero()
        )

    wardrobe.put(value.cid, cloth)
    # 跳过玩家
    if value.cid == 0:
        return 0

    # 判断是否需要重置服装数据
    reset_cloth_flag = False
    if len(cloth.cloth_wear):
        for now_type in cloth.cloth_wear:
            now_type_cloth_data = cloth.cloth_wear[now_type]
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
    if reset_cloth_flag:
        cloth = attr_calculation.get_cloth_zero()
        for cloth_id in tem_character.Cloth:
            if cloth_id not in game_config.config_clothing_tem:
                continue
            type = game_config.config_clothing_tem[cloth_id].clothing_type
            cloth.cloth_wear[type].append(cloth_id)
        bra_id, pan_id = clothing.get_random_underwear()
        if not len(cloth.cloth_wear[6]):
            cloth.cloth_wear[6].append(bra_id)
        if not len(cloth.cloth_wear[9]):
            cloth.cloth_wear[9].append(pan_id)
        wardrobe.put(value.cid, cloth)
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
    taken_advs = {one.adv for one in identity.table().values()}
    add_new_character_list = [
        now_npc_data
        for now_npc_data in loaded_dict["npc_tem_data"].values()
        if now_npc_data.AdvNpc not in taken_advs
    ]

    # 新增该角色，使用adv作为cid
    for now_npc_data in add_new_character_list:
        # 跳过深靛
        if now_npc_data.Name == _("深靛"):
            continue
        new_character_cid = now_npc_data.AdvNpc  # 使用adv作为cid
        character_handle.init_character(
            new_character_cid, now_npc_data, False, False
        )
        loaded_dict["character_data"][new_character_cid] = game_type.Character()
        update_count += 1

    return update_count


STAGE_TALENT_TUPLE = (101, 102, 103)
""" 成长阶段素质：101婴儿 / 102幼女 / 103学员，静态干员不持有 """
BODY_TALENT_TUPLE = (104, 105, 106, 107, 108)
""" 体型素质 """
ADULT_BODY_TALENT = 104
""" 少女素质：没开世界设定1、或角色模板没有体型素质时，静态干员身上的成长阶段素质换成它 """
WORLD_SETTING_SHRINK = 1
""" 世界设定1在存档 world_setting 里的键：开着它开局的存档，全岛干员的体型素质104~107在开局时换成了103 """
AGE_DRUG_ITEM_TUPLE = (31, 32)
""" 外表年龄增长药、外表年龄减少药的道具id，读档时从所有角色的道具栏中清掉 """
FOLLOW_MOTHER_BEHAVIOR = "follow_mother"
""" 跟随母亲行为id，读档时一律换成发呆 """
YOUNG_CHILD_H_FLAG_TUPLE = (
    "is_h",
    "unconscious_h",
    "hidden_sex_mode",
    "condom_cloth_flag",
    "exhibitionism_sex_mode",
    "sleep_h_awake",
    "milk",
    "masturebate",
    "masturebate_before_sleep",
    "npc_masturebate_for_player",
    "go_to_join_group_sex",
    "see_pl_h",
    "see_h_reaction_settled",
    "sex_toy_level",
)
""" 101/102阶段的孩子读档时换回默认值的 SPECIAL_FLAG 字段：H（含无意识H与睡奸中醒来）、隐奸、避孕套装饰、露出、
挤奶与自慰后续链、群交邀请、看H反应、玩具档位 """
YOUNG_CHILD_H_TALENT_TUPLE = (20, 21, 22, 23, 24, 25, 26, 27, 32, 35)
""" 101/102阶段的孩子读档时清掉的素质：受精、妊娠、临盆、产后、育儿、假孕孕肚、孕肚、泌乳、精液膨腹、无意识妊娠 """
KEEP_PREGNANCY_ATTR_SET = {
    "reproduction_period",
    "born_time",
    "growth_acceleration_days",
}
""" 101/102阶段的孩子读档时保留的 PREGNANCY 字段：生殖周期、出生时间、成长加速天数 """


def _is_young_child(character: identity.Identity) -> bool:
    """
    判断角色是否处于幼年阶段（与 child_stage_gate 同口径，按存档里的角色数据判断）
    Keyword arguments:
    character -- 角色数据
    Return arguments:
    bool -- 持有 child_stage_gate.CHILD_STAGE_TALENTS 中任一素质时为True
    """
    return any(
        abilities.talent(character.cid).get(talent_id, 0)
        for talent_id in child_stage_gate.CHILD_STAGE_TALENTS
    )


def _is_player_daughter(character: identity.Identity) -> bool:
    """
    判断角色是否为玩家的女儿（与前提 SELF_IS_PLAYER_DAUGHTER 同口径）
    Keyword arguments:
    character -- 角色数据
    Return arguments:
    bool -- 是否为玩家的女儿
    """
    return character.cid != 0 and relations.father_id(character.cid) == 0


def _migrate_static_talent(
    character: identity.Identity, world_setting_shrink: bool
) -> int:
    """
    整理静态干员（非玩家、非女儿的角色）的素质：持有成长阶段素质时把它换成体型素质
    Keyword arguments:
    character -- 角色数据
    world_setting_shrink -- 存档是否开着世界设定1
    Return arguments:
    int -- 改动的素质数
    功能: 开着世界设定1时取回 data/character 角色模板的体型素质，模板没有体型素质或没开世界设定1时取少女
    """
    from Script.Config import character_config

    talent = abilities.talent(character.cid)
    count = 0
    stage_list = [
        talent_id
        for talent_id in STAGE_TALENT_TUPLE
        if talent.get(talent_id, 0)
    ]
    if not stage_list:
        return count
    for talent_id in stage_list:
        talent[talent_id] = 0
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
        if not talent.get(talent_id, 0):
            talent[talent_id] = 1
            count += 1
    return count


def _reset_behavior_to_idle(character: identity.Identity) -> None:
    """
    把角色的当前行为换成1分钟的发呆，交互对象换回自己
    Keyword arguments:
    character -- 角色数据
    Return arguments:
    None
    """
    activity.update_behavior(
        character.cid, behavior_id=constant.Behavior.SHARE_BLANKLY, duration=1
    )
    activity.set_state(character.cid, constant.CharacterStatus.STATUS_ARDER)
    activity.set_target(character.cid, character.cid)


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


def _clear_child_activity(character: identity.Identity) -> int:
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
    behavior_id = activity.behavior(character.cid).behavior_id
    if (
        behavior_id == FOLLOW_MOTHER_BEHAVIOR
        or behavior_id not in game_config.config_behavior
    ):
        _reset_behavior_to_idle(character)
        count += 1
    entertainment_list = chara_life.entertainment_type(character.cid)
    if any(
        one not in game_config.config_entertainment
        for one in entertainment_list
    ):
        chara_life.entertainment_type.set(
            character.cid,
            [
                one if one in game_config.config_entertainment else 0
                for one in entertainment_list
            ],
        )
        count += 1
    with growth.editing(character.cid, create=False) as growth_data:
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
    if hasattr(default_value, "__dict__"):
        if vars(now_value) == vars(default_value):
            return 0
    elif now_value == default_value:
        return 0
    setattr(owner, attr_name, default_value)
    return 1


def _reset_key[T](key: CharaKey[T], cid: int, default_value: T) -> int:
    """
    角色键的值与 default_value 不同时，把它换成 default_value
    Keyword arguments:
    key -- 角色键
    cid -- 角色id
    default_value -- 要换成的值
    Return arguments:
    int -- 换了为1，没换为0
    """
    if key(cid) == default_value:
        return 0
    key.set(cid, default_value)
    return 1


def _clear_young_child_h_state(character: identity.Identity) -> int:
    """
    101/102阶段的孩子：污浊、H状态与身体道具、H相关标记与后续链、泌乳、妊娠与卵，换成新角色的默认值
    Keyword arguments:
    character -- 孩子的角色数据
    Return arguments:
    int -- 改动的项数
    功能: 妊娠数据里的生殖周期、出生时间、成长加速天数与奶量上限保留，其余换成默认值；只改孩子本人，不动母亲
    """
    talent = abilities.talent(character.cid)
    count = int(dirty.clear(character.cid))
    count += int(h_state.clear(character.cid))
    for flag_name in YOUNG_CHILD_H_FLAG_TUPLE:
        default_val = flags.DEFAULTS[flag_name]
        if flags.get(character.cid, flag_name) != default_val:
            flags.set(character.cid, **{flag_name: default_val})
            count += 1
    for talent_id in YOUNG_CHILD_H_TALENT_TUPLE:
        if talent.get(talent_id, 0):
            talent[talent_id] = 0
            count += 1
    count += pregnancy.reset_except(character.cid, KEEP_PREGNANCY_ATTR_SET)
    if needs.of(character.cid)["milk"] != 0:
        needs.set(character.cid, milk=0)
        count += 1
    return count


def _clear_young_child_egg_index(
    player: identity.Identity, young_child_id_set: set
) -> int:
    """
    从玩家收藏品中删掉指向101/102阶段孩子的持有卵索引，以及她们排出的体外无壳卵
    Keyword arguments:
    player -- 玩家的角色数据
    young_child_id_set -- 101/102阶段孩子的角色id集合
    Return arguments:
    int -- 删掉的条数
    """
    held = player_collection.get("held_eggs", player.cid)
    count = 0
    for held_id in [
        held_id
        for held_id, (chara_id, _) in held.items()
        if chara_id in young_child_id_set
    ]:
        del held[held_id]
        count += 1
    if count:
        player_collection.put("held_eggs", held, player.cid)
    soft = player_collection.get("soft_eggs", player.cid)
    soft_removed = 0
    for egg_id in [
        egg_id
        for egg_id, egg_data in soft.items()
        if egg_data.get("mother_id") in young_child_id_set
    ]:
        del soft[egg_id]
        soft_removed += 1
    if soft_removed:
        player_collection.put("soft_eggs", soft, player.cid)
    return count + soft_removed


def _remove_from_group_sex_template(
    character: identity.Identity, young_child_id_set: set
) -> int:
    """从角色的群交部位模板（A、B）里去掉101/102阶段的孩子"""
    return h_state.remove_from_group_sex_template(
        character.cid, young_child_id_set
    )


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
    for cid in identity.ids():
        if (
            player_ability.get(cid, "free_in_time_stop_chara_id")
            in young_child_id_set
        ):
            player_ability.set(cid, free_in_time_stop_chara_id=0)
            count += 1
        if flags.get(cid, "bagging_chara_id") in young_child_id_set:
            flags.set(cid, bagging_chara_id=0)
            count += 1
        end_info = action_info.get(cid, "interacting_character_end_info")
        if cid in young_child_id_set or (
            isinstance(end_info, list)
            and end_info
            and end_info[0] in young_child_id_set
        ):
            default_end = [-1, datetime.datetime(1, 1, 1)]
            if end_info != default_end:
                action_info.set(
                    cid, "interacting_character_end_info", default_end
                )
                count += 1
        refuse = action_info.get(cid, "ask_group_sex_refuse_chara_id_list")
        removed = _discard_id(refuse, young_child_id_set)
        if removed:
            action_info.set(cid, "ask_group_sex_refuse_chara_id_list", refuse)
            count += removed
        first_panties = player_collection.get("first_panties", cid)
        fp_changed = False
        for chara_id in young_child_id_set:
            if first_panties.get(chara_id):
                first_panties[chara_id] = ""
                fp_changed = True
                count += 1
        if fp_changed:
            player_collection.put("first_panties", first_panties, cid)
        for field_name in (
            "npc_panties",
            "npc_panties_tem",
            "npc_socks",
            "npc_socks_tem",
        ):
            item_dict = player_collection.get(field_name, cid)
            changed_items = False
            for chara_id in young_child_id_set:
                if item_dict.get(chara_id):
                    item_dict[chara_id] = []
                    changed_items = True
                    count += 1
            if changed_items:
                player_collection.put(field_name, item_dict, cid)
        for field_name in ("milk_total", "urine_total"):
            total_dict = player_collection.get(field_name, cid)
            changed_totals = False
            for chara_id in young_child_id_set:
                if total_dict.get(chara_id):
                    total_dict[chara_id] = 0
                    changed_totals = True
                    count += 1
            if changed_totals:
                player_collection.put(field_name, total_dict, cid)
    for chara_id in young_child_id_set:
        for flag_name, default_val in (
            ("be_bagged", False),
            ("imprisonment", False),
            ("escaping", False),
            ("field_commission", 0),
        ):
            if flags.get(chara_id, flag_name) != default_val:
                flags.set(chara_id, **{flag_name: default_val})
                count += 1
        count += _reset_key(chara_life.borrow_book_id_set, chara_id, set())
    count += fridge.drop(young_child_id_set)
    count += prison.drop_prisoners(young_child_id_set)
    for commission_id, one in commission.ongoing().items():
        team = list(one.team)
        count += _discard_id(team, young_child_id_set)
        commission.set_team(commission_id, team)
    count += _cancel_empty_field_commission()
    count += education.drop_must_attend(young_child_id_set)
    count += physical_exam.drop(young_child_id_set)
    for book_id, borrower_id in library.holders().items():
        if borrower_id in young_child_id_set:
            library.set_holder(book_id, library.FREE)
            count += 1
    return count


def _cancel_empty_field_commission() -> int:
    """
    取消没有成员的外勤委托，写进当前缓冲区。游戏里没有取消委托的流程，这里只做完成结算里的两步：
    派出且在载具表里的载具每辆外勤中数减 1，委托从进行中的委托里删掉。
    奖励、已完成、成就、招募与损坏都不结算，派遣时扣的资源不退
    Return arguments:
    int -- 改动的项数：收回的载具数加删掉的委托数
    """
    count = 0
    for commission_id, one in commission.ongoing().items():
        if one.team:
            continue
        for vehicle_id in one.vehicles:
            if vehicle_id in commission.vehicles():
                commission.add_vehicle(vehicle_id, out=-1)
                count += 1
        commission.finish(commission_id)
        count += 1
    return count


def _remap_visitor_and_commission(old_to_new_id: dict[int, int]) -> None:
    """
    角色换id时调用。邀请目标先按 normalize_single_character_id 归一成 int。
    随后访客、邀请目标与进行中的外勤委托的队伍里的旧id换成新id，写进当前缓冲区
    Keyword arguments:
    old_to_new_id -- 旧id到新id，表里没有的id不变
    """
    target, progress = visitor.invite()
    visitor.set_invite(normalize_single_character_id(target, 0), progress)
    visitor.remap(old_to_new_id)
    commission.remap(old_to_new_id)


def _take_young_child_off_line(
    loaded_dict: dict[str, Any], young_child_id_set: set
) -> int:
    """
    让101/102阶段的孩子离线：离开所有场景与当前干员列表，位置换成离线位置 ["0", "0"]，交互对象换成自己，
       行为不是发呆或带着移动路线时换成默认行为（发呆），跟随关闭；
       没有职业（work_type 为0）、不在任何职业名单里，空出宿舍床位（宿舍与登记宿舍为空串），助理服务归零（同
       handle_assistant_reset）；
       催眠、待触发事件、必须结算与显示的二段行为、快感状态归零；
       别人以她为目标的，目标换回自己（NPC 当前的行为换成发呆）；以她为助理的，助理清零；
       别人正在搬运她的，搬运对象清零；别人的群交部位模板里去掉她。角色数据保留
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
    if "npc_id_got" in loaded_dict:
        for character_id in young_child_id_set & set(loaded_dict["npc_id_got"]):
            loaded_dict["npc_id_got"].remove(character_id)
            count += 1
    count += roster.drop_active(young_child_id_set)
    count += work.drop(young_child_id_set)
    for character_id in young_child_id_set:
        character = identity.of(character_id)
        if activity.position(character_id) != ["0", "0"]:
            activity.set_position(character_id, ["0", "0"])
            count += 1
        behavior = activity.behavior(character_id)
        if (
            behavior.behavior_id != constant.Behavior.SHARE_BLANKLY
            or behavior.move_target
            or behavior.move_src
            or behavior.move_final_target
        ):
            activity.set_behavior(character_id)
            activity.set_state(
                character_id, constant.CharacterStatus.STATUS_ARDER
            )
            count += 1
        if flags.get(character_id, "is_follow") != 0:
            flags.set(character_id, is_follow=0)
            count += 1
        if activity.target(character_id) != character_id:
            activity.set_target(character_id, character_id)
            count += 1
        count += _reset_key(chara_life.work_type, character_id, 0)
        count += _reset_key(
            relations.assistant_services,
            character_id,
            attr_calculation.get_assistant_services_zero(),
        )
        count += _reset_key(chara_life.dormitory, character_id, "")
        count += _reset_key(chara_life.permanent_dormitory, character_id, "")
        count += int(hypnosis.reset(character_id))
        event = activity.event(character_id)
        if any(
            getattr(event, name) != value
            for name, value in activity.EVENT_DEFAULT.items()
        ):
            activity.set_event(character_id)
            count += 1
        if activity.must_settle(character_id):
            activity.set_must_settle(character_id, [])
            count += 1
        if activity.must_show(character_id):
            activity.set_must_show(character_id, [])
            count += 1
        for state_id in [
            state_id
            for state_id, state in game_config.config_character_state.items()
            if state.type == 0
        ]:
            if status.of(character.cid).get(state_id, 0):
                status.set(character.cid, state_id, 0)
                count += 1
    for character in identity.table().values():
        if (
            activity.target(character.cid) in young_child_id_set
            and activity.target(character.cid) != character.cid
        ):
            # NPC 正在对孩子进行的行为换成发呆；有孩子参与的会话由读档后的 end_young_child_session 结束
            if character.cid != 0:
                _reset_behavior_to_idle(character)
            activity.set_target(character.cid, character.cid)
            count += 1
        if (
            relations.assistant_character_id(character.cid)
            in young_child_id_set
        ):
            relations.assistant_character_id.set(character.cid, 0)
            count += 1
        if (
            action_info.get(character.cid, "carry_chara_id")
            in young_child_id_set
        ):
            action_info.set(character.cid, "carry_chara_id", 0)
            count += 1
        if (
            player_ability.get(character.cid, "carry_chara_id_in_time_stop")
            in young_child_id_set
        ):
            player_ability.set(character.cid, carry_chara_id_in_time_stop=0)
            count += 1
        count += _remove_from_group_sex_template(character, young_child_id_set)
    count += _clear_young_child_reference(loaded_dict, young_child_id_set)
    return count


def _clear_age_drug_item(character: identity.Identity) -> int:
    """
    从角色道具栏中删掉外表年龄药（道具表里没有这两项）
    Keyword arguments:
    character -- 角色数据
    Return arguments:
    int -- 改动的项数
    """
    count = 0
    for item_id in AGE_DRUG_ITEM_TUPLE:
        if item_id in inventory.items(character.cid):
            inventory.drop_item(character.cid, item_id)
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
    dict -- {"group": 群交是否要结束, "time_stop": 时停是否要结束, "single_partner_id_set": 与孩子单人H的角色id集合,
    "child_id_set": 孩子的角色id集合}
    功能: 群交：开着群交模式，且玩家以孩子为交互对象、或孩子在某个群交部位模板里、或孩子与玩家同场景在H中；
          时停：开着时停，且玩家以孩子为交互对象、搬运她或让她自由活动；
          单人H（含隐奸、露出）：交互对象是孩子且在H、隐奸或露出中的角色，与玩家同场景的群交参与者归群交结束
    """
    character_data = identity.table()
    player = character_data.get(0)
    session: YoungChildSession = {
        "group": False,
        "time_stop": False,
        "single_partner_id_set": set(),
        "child_id_set": set(young_child_id_set),
    }
    if player is None or not young_child_id_set:
        return session
    if loaded_dict.get("group_sex_mode", modes.group_sex()):
        in_template = any(
            h_state.group_sex_template_has(character.cid, young_child_id_set)
            for character in character_data.values()
        )
        child_in_scene_h = any(
            flags.get(chara_id, "is_h")
            and activity.position(chara_id) == activity.position(player.cid)
            for chara_id in young_child_id_set
        )
        session["group"] = (
            activity.target(player.cid) in young_child_id_set
            or in_template
            or child_in_scene_h
        )
    if loaded_dict.get("time_stop_mode", modes.time_stop()):
        time_stop_id_set = {
            activity.target(player.cid),
            player_ability.get(0, "free_in_time_stop_chara_id"),
            action_info.get(0, "carry_chara_id"),
            player_ability.get(0, "carry_chara_id_in_time_stop"),
        }
        session["time_stop"] = bool(time_stop_id_set & young_child_id_set)
    for character in character_data.values():
        if (
            character.cid in young_child_id_set
            or activity.target(character.cid) not in young_child_id_set
        ):
            continue
        if session["group"] and activity.position(
            character.cid
        ) == activity.position(player.cid):
            continue
        if (
            flags.get(character.cid, "is_h")
            or flags.get(character.cid, "hidden_sex_mode")
            or flags.get(character.cid, "exhibitionism_sex_mode")
        ):
            session["single_partner_id_set"].add(character.cid)
    return session


def end_young_child_session(session: YoungChildSession) -> None:
    """
    存档载入缓存后，有101/102阶段的孩子参与的会话各按自己的结束结算收尾，奖励类结算不调用
    Keyword arguments:
    session -- migrate_age_and_body_type 填入的会话信息（见 _find_young_child_session）
    Return arguments:
    None
    功能: 群交按「群交结束」：场景内所有角色H状态归零（SCENE_ALL_CHARACTERS_H_STATE_RESET）、穿回衣服、
    阴茎位置归零、关闭群交模式；
          时停按「解除时停」：清零时停搬运与自由活动对象、关闭时停；
          单人H按「结束H」：另一方H状态归零（BOTH_H_STATE_RESET 对其一侧）、开门；
          最后孩子一侧H状态归零、穿回衣服。结算读写游戏缓存，所以在读档覆盖缓存之后调用；
          体力气力上限奖励、寸止解放与时停绝顶解放是对这次会话的结算，不调用。各方的交互对象已在转换时换成不指向孩子的值
    """
    from Script.Settle import default, default_cloth

    now_time = game_time.now()
    if session.get("group"):
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
    if session.get("time_stop"):
        default.handle_target_not_be_carried_in_time_stop(
            0, 1, game_type.CharacterStatusChange(), now_time
        )
        default.handle_target_not_be_free_in_time_stop(
            0, 1, game_type.CharacterStatusChange(), now_time
        )
        default.handle_time_stop_off(
            0, 1, game_type.CharacterStatusChange(), now_time
        )
    for character_id in sorted(session.get("single_partner_id_set", set())):
        if not identity.exists(character_id):
            continue
        default.handle_self_h_state_reset(
            character_id, 1, game_type.CharacterStatusChange(), now_time
        )
        default.handle_door_close_reset(
            character_id, 1, game_type.CharacterStatusChange(), now_time
        )
    for character_id in sorted(session.get("child_id_set", set())):
        if not identity.exists(character_id):
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
    session -- 传入 dict 时填入有孩子参与的会话（见 _find_young_child_session），读档覆盖缓存后交给
    end_young_child_session
    Return arguments:
    int -- 改动的项数
    功能: 静态干员的素质见 _migrate_static_talent，女儿的成长阶段与体型不变；
          见学、表里没有的行为与娱乐编号、101/102阶段的上课状态、101/102阶段的H与身体状态、离线、外表年龄药见
          _clear_child_activity、_clear_young_child_h_state、_clear_young_child_egg_index、_take_young_child_off_line、
          _clear_age_drug_item；
          最后清掉世界设定1的开关
    """
    count = 0
    world_setting = loaded_dict.get("world_setting")
    world_setting_shrink = bool(
        world_setting.get(WORLD_SETTING_SHRINK, 0)
        if isinstance(world_setting, dict)
        else playthrough.setting(playthrough.WORLD, WORLD_SETTING_SHRINK, 0)
    )
    # 先换静态干员的素质：药物缩成101/102的静态干员由此回到成年，不算孩子
    for character in identity.table().values():
        if character.cid != 0 and not _is_player_daughter(character):
            count += _migrate_static_talent(character, world_setting_shrink)
    young_child_id_set = {
        character.cid
        for character in identity.table().values()
        if _is_young_child(character)
    }
    # 在清掉任何H标记、群交模板与交互对象之前记下有孩子参与的会话
    if session is not None:
        session.update(
            _find_young_child_session(loaded_dict, young_child_id_set)
        )
    for character in identity.table().values():
        count += _clear_child_activity(character)
        if character.cid in young_child_id_set:
            count += _clear_young_child_h_state(character)
        count += _clear_age_drug_item(character)
    if identity.exists(0):
        count += _clear_young_child_egg_index(
            identity.of(0), young_child_id_set
        )
    count += _take_young_child_off_line(loaded_dict, young_child_id_set)
    count += education.clear_missing_template_slots(
        game_config.config_entertainment
    )
    if world_setting_shrink:
        if isinstance(world_setting, dict):
            world_setting[WORLD_SETTING_SHRINK] = 0
        else:
            playthrough.set_setting(playthrough.WORLD, WORLD_SETTING_SHRINK, 0)
        count += 1
    return count
