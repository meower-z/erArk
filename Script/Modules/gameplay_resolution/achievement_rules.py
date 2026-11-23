"""
常规成就结算规则（achievement_rules）
=====================================
提供通用成就结算函数 settle_achievement 与七类角色常规成就的结算函数。
涵盖关系、招募、访客、助理、收藏服装、技能与催眠类别。
本模块不直接导入界面模块，供 achievement_service 与 achievement_h_rules 调用。
"""

from Script.Config import game_config
from Script.Design import handle_premise
from Script.Modules.domains import abilities, achievement, flags, identity
from Script.Modules.domains import player_collection, relations, roster


def settle_achievement(
    judge_value: int, achievement_ids: int | list[int], force: bool = False
) -> list[int]:
    """
    通用成就结算函数（支持单个或批量）\n
    输入：\n
    - judge_value: int，判断值\n
    - achievement_ids: int 或 list[int]，成就ID或成就ID列表\n
    - force: bool，是否强制结算成功（默认为False）\n
    返回：\n
    - return_list: 成就列表，包含已达成的成就ID\n
    功能：判断是否达成成就，如果达成则更新缓存中的成就
    """
    if isinstance(achievement_ids, int):
        achievement_ids = [achievement_ids]
    return_list: list[int] = []
    for achievement_id in achievement_ids:
        if not achievement.done(achievement_id):
            if (
                force
                or judge_value
                >= game_config.config_achievement[achievement_id].value
            ):
                achievement.set_entry("achievement_dict", achievement_id, True)
                return_list.append(achievement_id)
    return return_list


def settle_chara_relationship() -> list[int]:
    """
    结算角色关系类的成就\n
    返回：\n
    - return_list: 成就列表，包含已达成的成就ID
    """
    love_flag, obey_flag = 0, 0
    lover_count, slave_count = 0, 0
    daught_lover_flag = 0
    daught_slave_flag = 0
    for chara_id in identity.table():
        if chara_id == 0:
            continue
        if not roster.has(chara_id) and handle_premise.handle_normal_7(
            chara_id
        ):
            continue
        if not love_flag and handle_premise.handle_self_fall_love(chara_id):
            love_flag = 1
        if not obey_flag and handle_premise.handle_self_fall_obey(chara_id):
            obey_flag = 1
        if handle_premise.handle_self_love_4(chara_id):
            lover_count += 1
            if handle_premise.handle_self_is_player_daughter(chara_id):
                daught_lover_flag = 1
        if handle_premise.handle_self_obey_4(chara_id):
            slave_count += 1
            if handle_premise.handle_self_is_player_daughter(chara_id):
                daught_slave_flag = 1
    achievement_checks = [
        (love_flag, 51),
        (lover_count, 52),
        (lover_count, 53),
        (daught_lover_flag, 56),
        (obey_flag, 61),
        (slave_count, 62),
        (slave_count, 63),
        (daught_slave_flag, 66),
    ]
    return_list: list[int] = []
    for judge_value, achievement_id in achievement_checks:
        return_list.extend(settle_achievement(judge_value, achievement_id))
    return return_list


def settle_chara_recruit() -> list[int]:
    """
    结算招募类的成就\n
    返回：\n
    - return_list: 成就列表，包含已达成的成就ID
    """
    recruit_count = 0
    for chara_id in identity.table():
        if chara_id == 0:
            continue
        if not roster.has(chara_id) and handle_premise.handle_normal_7(
            chara_id
        ):
            continue
        recruit_count += 1
    return_list: list[int] = []
    return_list.extend(settle_achievement(recruit_count, [101, 102]))
    return return_list


def settle_chara_visitor() -> list[int]:
    """
    结算访客类的成就\n
    返回：\n
    - return_list: 成就列表，包含已达成的成就ID
    """
    visitor_count = 0
    for chara_id in identity.table():
        now_character_data: identity.Identity = identity.of(chara_id)
        if chara_id == 0:
            continue
        if flags.get(now_character_data.cid, "vistor") > 0:
            visitor_count += 1
    return_list: list[int] = []
    return_list.extend(settle_achievement(visitor_count, [111, 112]))
    return return_list


def settle_chara_assistant() -> list[int]:
    """
    结算助理类的成就\n
    返回：\n
    - return_list: 成就列表，包含已达成的成就ID
    """
    return_list: list[int] = []
    assistant_chara_id = relations.assistant_character_id(0)
    if assistant_chara_id == 0:
        return return_list
    flag_132 = 1
    for service_id in [4, 5, 6, 7]:
        if relations.assistant_services(assistant_chara_id)[service_id] == 0:
            flag_132 = 0
    flag_136 = 0
    if (
        relations.favorability(assistant_chara_id)[0]
        >= game_config.config_favorability_level[8].Favorability_point
        and relations.trust(assistant_chara_id)
        >= game_config.config_trust_level[8].Trust_point
    ):
        flag_136 = 1
    achievement_checks = [
        (assistant_chara_id, 131),
        (flag_132, 132),
        (flag_136, 136),
    ]
    for judge_value, achievement_id in achievement_checks:
        return_list.extend(settle_achievement(judge_value, achievement_id))
    return return_list


def settle_chara_clothing() -> list[int]:
    """
    结算角色服装类的成就\n
    返回：\n
    - return_list: 成就列表，包含已达成的成就ID
    """
    return_list: list[int] = []
    clothing_count = 0
    for items in player_collection.get("first_panties").values():
        clothing_count += len(items)
    for items in player_collection.get("npc_panties").values():
        clothing_count += len(items)
    for items in player_collection.get("npc_socks").values():
        clothing_count += len(items)
    return_list = settle_achievement(clothing_count, [221, 222, 223])
    return return_list


def settle_chara_ability() -> list[int]:
    """
    结算角色能力类的成就\n
    返回：\n
    - return_list: 成就列表，包含已达成的成就ID
    """
    return_list: list[int] = []

    achievement_checks = [
        (abilities.ability(0)[40], 501),
        (abilities.ability(0)[40], 502),
        (abilities.ability(0)[40], 503),
        (abilities.ability(0)[41], 506),
        (abilities.ability(0)[41], 507),
        (abilities.ability(0)[41], 508),
        (abilities.ability(0)[42], 511),
        (abilities.ability(0)[42], 512),
        (abilities.ability(0)[42], 513),
        (abilities.ability(0)[43], 516),
        (abilities.ability(0)[43], 517),
        (abilities.ability(0)[43], 518),
        (abilities.ability(0)[44], 521),
        (abilities.ability(0)[44], 522),
        (abilities.ability(0)[44], 523),
        (abilities.ability(0)[45], 526),
        (abilities.ability(0)[45], 527),
        (abilities.ability(0)[45], 528),
        (abilities.ability(0)[46], 531),
        (abilities.ability(0)[46], 532),
        (abilities.ability(0)[46], 533),
        (abilities.ability(0)[47], 536),
        (abilities.ability(0)[47], 537),
        (abilities.ability(0)[47], 538),
        (abilities.ability(0)[48], 541),
        (abilities.ability(0)[48], 542),
        (abilities.ability(0)[48], 543),
        (abilities.ability(0)[49], 546),
        (abilities.ability(0)[49], 547),
        (abilities.ability(0)[49], 548),
    ]
    for judge_value, achievement_id in achievement_checks:
        return_list.extend(settle_achievement(judge_value, achievement_id))
    return return_list


def settle_chara_hypnosis() -> list[int]:
    """
    结算催眠类的成就\n
    返回：\n
    - return_list: 成就列表，包含已达成的成就ID
    """
    return_list: list[int] = []
    hypnosis_flag = 0
    full_hypnosis_count = 0
    for chara_id in identity.table():
        if chara_id == 0:
            continue
        if not roster.has(chara_id) and handle_premise.handle_normal_7(
            chara_id
        ):
            continue
        if not hypnosis_flag and handle_premise.handle_self_hypnosis_ne_0(
            chara_id
        ):
            hypnosis_flag = 1
        if handle_premise.handle_self_has_been_complete_hypnosis(chara_id):
            full_hypnosis_count += 1

    achievement_checks = [
        (hypnosis_flag, 621),
        (full_hypnosis_count, 622),
        (full_hypnosis_count, 623),
    ]
    for judge_value, achievement_id in achievement_checks:
        return_list.extend(settle_achievement(judge_value, achievement_id))
    return return_list
