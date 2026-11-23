"""
H 场景成就结算规则（achievement_h_rules）
=========================================
提供五类 H 场景成就的结算函数，覆盖群交、露出、隐奸、睡奸与射精类别。
各函数统计判定值后调用 achievement_rules.settle_achievement 写入达成状态。
本模块不直接导入界面模块，供 achievement_service 调用。
"""

from Script.Config import game_config
from Script.Design import handle_premise, map_handle
from Script.Modules.domains import abilities, achievement, activity, dirty
from Script.Modules.domains import h_state, relations, scene_state
from Script.Modules.gameplay_resolution import achievement_rules


def settle_chara_group_sex() -> list[int]:
    """
    结算群交类的成就\n
    返回：\n
    - return_list: 成就列表，包含已达成的成就ID
    """
    return_list: list[int] = []
    if handle_premise.handle_group_sex_mode_off(0):
        return return_list
    scene_path_str = map_handle.get_map_system_path_str_for_list(
        activity.position(0)
    )
    group_sex_character_count = 0
    conscious_count = 0
    unconscious_count = 0
    daughter_and_mother_flag = 0
    for chara_id in scene_state.occupants(scene_path_str):
        if chara_id == 0:
            continue
        if handle_premise.handle_self_not_h(chara_id):
            continue
        group_sex_character_count += 1
        if handle_premise.handle_unconscious_flag_ge_1(chara_id):
            unconscious_count += 1
        else:
            conscious_count += 1
        if handle_premise.handle_self_is_player_daughter(chara_id):
            mother_id = relations.mother_id(chara_id)
            if mother_id in scene_state.occupants(
                scene_path_str
            ) and handle_premise.handle_self_is_h(mother_id):
                daughter_and_mother_flag = 1
    if (
        len(achievement.get("group_sex_record")[1]) >= 10
        and len(achievement.get("group_sex_record")[2]) >= 20
    ):
        return_list.extend(
            achievement_rules.settle_achievement(1, 904, force=True)
        )
    achievement_checks = [
        (conscious_count, 901),
        (conscious_count, 902),
        (unconscious_count, 903),
        (daughter_and_mother_flag, 905),
    ]
    for judge_value, achievement_id in achievement_checks:
        return_list.extend(
            achievement_rules.settle_achievement(judge_value, achievement_id)
        )
    return return_list


def settle_chara_exhibitionism_sex() -> list[int]:
    """
    结算露出类的成就\n
    返回：\n
    - return_list: 成就列表，包含已达成的成就ID
    """
    return_list: list[int] = []
    if handle_premise.handle_player_not_in_exhibitionism_sex_mode(0):
        return return_list
    mode_id = achievement.get("exhibitionism_sex_record")[1]
    other_chara_count = achievement.get("exhibitionism_sex_record")[2]
    ejaculation_count = achievement.get("exhibitionism_sex_record")[3]
    climax_count = achievement.get("exhibitionism_sex_record")[4]
    flag_932 = 0
    if (
        mode_id in [3, 4]
        and other_chara_count >= 1
        and ejaculation_count >= 1
        and climax_count >= 1
    ):
        flag_932 = 1
    flag_933 = 0
    if other_chara_count >= 10 and ejaculation_count >= 3 and climax_count >= 3:
        flag_933 = 1
    achievement_checks = [
        (ejaculation_count, 931),
        (flag_932, 932),
        (flag_933, 933),
    ]
    for judge_value, achievement_id in achievement_checks:
        return_list.extend(
            achievement_rules.settle_achievement(judge_value, achievement_id)
        )
    return return_list


def settle_chara_hidden_sex() -> list[int]:
    """
    结算隐奸类的成就\n
    返回：\n
    - return_list: 成就列表，包含已达成的成就ID
    """
    return_list: list[int] = []
    if handle_premise.handle_player_not_in_hidden_sex_mode(0):
        return return_list
    mode_id = achievement.get("hidden_sex_record")[1]
    other_chara_count = achievement.get("hidden_sex_record")[2]
    ejaculation_count = achievement.get("hidden_sex_record")[3]
    climax_count = achievement.get("hidden_sex_record")[4]
    flag_913 = 0
    if (
        mode_id == 1
        and other_chara_count >= 10
        and ejaculation_count >= 3
        and climax_count >= 3
    ):
        flag_913 = 1
    achievement_checks = [
        (ejaculation_count, 911),
        (min(ejaculation_count, climax_count), 912),
        (flag_913, 913),
    ]
    for judge_value, achievement_id in achievement_checks:
        return_list.extend(
            achievement_rules.settle_achievement(judge_value, achievement_id)
        )
    return return_list


def settle_chara_sleep_sex() -> list[int]:
    """
    结算睡奸类的成就\n
    返回：\n
    - return_list: 成就列表，包含已达成的成就ID
    """
    return_list: list[int] = []
    if not handle_premise.handle_t_unconscious_flag_1(0):
        return return_list
    mode_id = achievement.get("sleep_sex_record")[1]
    ejaculation_count = achievement.get("sleep_sex_record")[2]
    climax_count = achievement.get("sleep_sex_record")[3]
    flag_923 = 0
    if mode_id == 1 and ejaculation_count >= 3 and climax_count >= 3:
        flag_923 = 1
    achievement_checks = [
        (ejaculation_count, 921),
        (min(ejaculation_count, climax_count), 922),
        (flag_923, 923),
    ]
    for judge_value, achievement_id in achievement_checks:
        return_list.extend(
            achievement_rules.settle_achievement(judge_value, achievement_id)
        )
    return return_list


def settle_semen_shoot() -> list[int]:
    """
    结算射精类的成就\n
    返回：\n
    - return_list: 成就列表，包含已达成的成就ID
    """
    return_list: list[int] = []
    target_character_id = activity.target(0)
    now_semen_shoot_count = h_state.view(0).orgasm_count.get(3, [0, 0])[0]
    all_semen_shoot_count = abilities.experience(0)[21]
    target_dirty = dirty.view(target_character_id)
    inner_all_semen = 0
    cloth_all_semen = 0
    for i in [6, 7, 8, 9]:
        inner_all_semen += target_dirty.body_semen[i][1]
    for i in game_config.config_clothing_type:
        cloth_all_semen += target_dirty.cloth_semen[i][1]
    achievement_checks = [
        (all_semen_shoot_count, 1201),
        (now_semen_shoot_count, 1202),
        (all_semen_shoot_count, 1203),
        (inner_all_semen, 1204),
        (cloth_all_semen, 1205),
        (abilities.talent(target_character_id)[32], 1206),
    ]
    for judge_value, achievement_id in achievement_checks:
        return_list.extend(
            achievement_rules.settle_achievement(judge_value, achievement_id)
        )
    return return_list
