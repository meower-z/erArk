"""行为结算效果函数（各自用 add_settle_behavior_effect 按 id 注册），以及部位交初体验的记录函数 record_first_part_sex"""

import datetime
from fractions import Fraction
import random, math
from types import FunctionType

from Script.Design import basement, settle_behavior, map_handle
from Script.Design import attr_calculation, game_time, handle_npc_ai_in_h
from Script.Design import handle_premise, hypnosis_state, clothing
from Script.Design import handle_ability, second_behavior, character_move
from Script.Core import cache_control, constant, constant_effect, game_type
from Script.Core import get_text, num
from Script.Config import game_config, normal_config
from Script.UI.Moudle import draw
from Script.System.Instruct_System import handle_instruct
from Script.System.Instruct_System.common_behavior_utils import (
    get_last_valid_sex_behavior_id,
)
from Script.UI.Panel import hypnosis_panel, event_option_panel
from Script.UI.Panel import ejaculation_panel, achievement_panel

from Script.Settle.common_default import base_chara_hp_mp_common_settle
from Script.Settle.common_default import base_chara_state_common_settle
from Script.Settle.common_default import (
    base_chara_favorability_and_trust_common_settle,
)
from Script.Settle.common_default import base_chara_climix_common_settle
from Script.Settle.common_default import base_chara_experience_common_settle

from Script.Settle.item_effect import *
from Script.Modules.domains import (
    abilities,
    achievement,
    action_info,
    activity,
    dirty,
)
from Script.Modules.domains import facility, first_record, flags, fridge, growth
from Script.Modules.domains import h_meters, h_state, history, hypnosis
from Script.Modules.domains import inventory, maintenance, medical, modes, needs
from Script.Modules.domains import official, physical_exam, player_ability
from Script.Modules.domains import player_collection, pregnancy, prison, recruit
from Script.Modules.domains import roster, status, visitor, wardrobe, warehouse
from Script.Modules.domains import chara_life, relations
from Script.Modules.domains import identity

_: FunctionType = get_text._
""" 翻译api """
window_width = normal_config.config_normal.text_width
""" 窗体宽度 """
cache = cache_control.cache
""" 游戏缓存数据 """
width = normal_config.config_normal.text_width
""" 屏幕宽度 """


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.NOTHING
)
def handle_nothing(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    空结算
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    pass


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ADD_SMALL_HIT_POINT
)
def handle_add_small_hit_point(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange | game_type.TargetChange,
    now_time: datetime.datetime,
) -> None:
    """
    增加少量体力
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.dead(character_id):
        return
    add_hit_point = add_time * (10 + needs.of(character_id)["hit_max"] * 0.005)
    now_add_hit_point = add_hit_point
    # 如果气力=0则恢复减半
    if needs.of(character_id)["mana"] == 0:
        now_add_hit_point /= 2
    now_add_hit_point = int(now_add_hit_point)
    needs.add(character_id, "hit", now_add_hit_point)
    change_data.hit_point += now_add_hit_point
    # 如果超过最大值则=最大值
    if needs.of(character_id)["hit"] >= needs.of(character_id)["hit_max"]:
        needs.set(character_id, hit=needs.of(character_id)["hit_max"])


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ADD_SMALL_MANA_POINT
)
def handle_add_small_mana_point(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange | game_type.TargetChange,
    now_time: datetime.datetime,
) -> None:
    """
    增加少量气力
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.dead(character_id):
        return
    add_mana_point = add_time * (20 + needs.of(character_id)["hit_max"] * 0.01)
    add_mana_point = int(add_mana_point)
    needs.add(character_id, "mana", add_mana_point)
    change_data.mana_point += add_mana_point
    if needs.of(character_id)["mana"] > needs.of(character_id)["mana_max"]:
        needs.set(character_id, mana=needs.of(character_id)["mana_max"])


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ADD_INTERACTION_FAVORABILITY
)
def handle_add_interaction_favoravility(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    增加基础互动好感
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    base_chara_favorability_and_trust_common_settle(
        character_id, add_time, True, 0, 0, change_data
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DOWN_INTERACTION_FAVORABILITY
)
def handle_down_interaction_favoravility(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    降低基础互动好感
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    base_chara_favorability_and_trust_common_settle(
        character_id, add_time, True, 0, -1, change_data
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ADD_SMALL_TRUST
)
def handle_add_small_trust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    增加基础互动信赖
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    base_chara_favorability_and_trust_common_settle(
        character_id, add_time, False, 0, 0, change_data
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DOWN_SMALL_TRUST
)
def handle_down_small_trust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    降低基础互动信赖
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    base_chara_favorability_and_trust_common_settle(
        character_id, add_time, False, 0, -1, change_data
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DOWN_BOTH_SMALL_HIT_POINT
)
def handle_sub_both_small_hit_point(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    双方减少少量体力（若没有交互对象则仅减少自己）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    base_chara_hp_mp_common_settle(
        character_id,
        add_time,
        hp_value=-1,
        target_flag=True,
        change_data=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DOWN_BOTH_SMALL_MANA_POINT
)
def handle_sub_both_small_mana_point(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    双方减少少量气力（若没有交互对象则仅减少自己）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    base_chara_hp_mp_common_settle(
        character_id,
        add_time,
        mp_value=-1,
        target_flag=True,
        change_data=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DOWN_BOTH_MEDIUM_HIT_POINT
)
def handle_sub_both_medium_hit_point(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    双方减少中量体力（若没有交互对象则仅减少自己）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    base_chara_hp_mp_common_settle(
        character_id,
        add_time,
        hp_value=-1,
        degree=1,
        target_flag=True,
        change_data=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DOWN_BOTH_MEDIUM_MANA_POINT
)
def handle_sub_both_medium_mana_point(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    双方减少中量气力（若没有交互对象则仅减少自己）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    base_chara_hp_mp_common_settle(
        character_id,
        add_time,
        mp_value=-1,
        degree=1,
        target_flag=True,
        change_data=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DOWN_BOTH_LARGE_HIT_POINT
)
def handle_sub_both_large_hit_point(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    双方减少大量体力（若没有交互对象则仅减少自己）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    base_chara_hp_mp_common_settle(
        character_id,
        add_time,
        hp_value=-1,
        degree=2,
        target_flag=True,
        change_data=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DOWN_BOTH_LARGE_MANA_POINT
)
def handle_sub_both_large_mana_point(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    双方减少大量气力（若没有交互对象则仅减少自己）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    base_chara_hp_mp_common_settle(
        character_id,
        add_time,
        mp_value=-1,
        degree=2,
        target_flag=True,
        change_data=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DOWN_SELF_SMALL_HIT_POINT
)
def handle_sub_self_small_hit_point(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    减少自己少量体力
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    base_chara_hp_mp_common_settle(
        character_id, add_time, hp_value=-1, change_data=change_data
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DOWN_SELF_SMALL_MANA_POINT
)
def handle_sub_self_small_mana_point(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    减少自己少量气力
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    base_chara_hp_mp_common_settle(
        character_id, add_time, mp_value=-1, change_data=change_data
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DOWN_SELF_MEDIUM_HIT_POINT
)
def handle_sub_self_medium_hit_point(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    减少自己中量体力
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    base_chara_hp_mp_common_settle(
        character_id, add_time, hp_value=-1, degree=1, change_data=change_data
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DOWN_SELF_MEDIUM_MANA_POINT
)
def handle_sub_self_medium_mana_point(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    减少自己中量气力
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    base_chara_hp_mp_common_settle(
        character_id, add_time, mp_value=-1, degree=1, change_data=change_data
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DOWN_SELF_LARGE_HIT_POINT
)
def handle_sub_self_large_hit_point(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    减少自己大量体力
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    base_chara_hp_mp_common_settle(
        character_id, add_time, hp_value=-1, degree=2, change_data=change_data
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DOWN_SELF_LARGE_MANA_POINT
)
def handle_sub_self_large_mana_point(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    减少自己大量气力
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    base_chara_hp_mp_common_settle(
        character_id, add_time, mp_value=-1, degree=2, change_data=change_data
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DOWN_TARGET_MEDIUM_HIT_POINT
)
def handle_sub_target_medium_hit_point(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    减少交互对象中量体力
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    base_chara_hp_mp_common_settle(
        activity.target(character_id),
        add_time,
        hp_value=-1,
        degree=1,
        change_data=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DOWN_TARGET_MEDIUM_MANA_POINT
)
def handle_sub_target_medium_mana_point(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    减少交互对象中量气力
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    base_chara_hp_mp_common_settle(
        activity.target(character_id),
        add_time,
        mp_value=-1,
        degree=1,
        change_data=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DOWN_TARGET_LARGE_HIT_POINT
)
def handle_sub_target_large_hit_point(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    减少交互对象大量体力
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    base_chara_hp_mp_common_settle(
        activity.target(character_id),
        add_time,
        hp_value=-1,
        degree=2,
        change_data=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DOWN_TARGET_LARGE_MANA_POINT
)
def handle_sub_target_large_mana_point(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    减少交互对象大量气力
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    base_chara_hp_mp_common_settle(
        activity.target(character_id),
        add_time,
        mp_value=-1,
        degree=2,
        change_data=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.MOOD_TO_GOOD
)
def handle_mood_to_good(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己心情变为好
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    needs.set(character_id, angry=0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.MOOD_TO_NORMAL
)
def handle_mood_to_normal(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己心情变为普通
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    needs.set(character_id, angry=20)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.MOOD_TO_BAD
)
def handle_mood_to_bad(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己心情变为不好
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    needs.set(character_id, angry=40)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.MOOD_TO_ANGRY
)
def handle_mood_to_angry(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己心情变为愤怒
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    needs.set(character_id, angry=75)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_MOOD_TO_GOOD
)
def handle_target_mood_to_good(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象心情变为好
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    handle_mood_to_good(
        activity.target(character_id), add_time, change_data, now_time
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_MOOD_TO_NORMAL
)
def handle_target_mood_to_normal(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象心情变为普通
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    handle_mood_to_normal(
        activity.target(character_id), add_time, change_data, now_time
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_MOOD_TO_BAD
)
def handle_target_mood_to_bad(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象心情变为不好
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    handle_mood_to_bad(
        activity.target(character_id), add_time, change_data, now_time
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_MOOD_TO_ANGRY
)
def handle_target_mood_to_angry(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象心情变为愤怒
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    handle_mood_to_angry(
        activity.target(character_id), add_time, change_data, now_time
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SCENE_ALL_CHARACTERS_DESIRE_POINT_ZERO
)
def handle_scene_all_characters_desire_point_zero(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    场景内所有角色欲望值归零
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    scene_path_str = map_handle.get_map_system_path_str_for_list(
        activity.position(character_id)
    )
    scene_data: game_type.Scene = cache.scene_data[scene_path_str]
    for chara_id in scene_data.character_list:
        if chara_id == 0:
            continue
        needs.set(character_id, desire=0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ADD_BOTH_SMALL_HIT_POINT
)
def handle_add_both_small_hit_point(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    增加双方少量体力
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.dead(character_id):
        return
    add_hit_point = add_time * (10 + needs.of(character_id)["hit_max"] * 0.005)
    now_add_hit_point = add_hit_point
    # 如果气力=0则恢复减半
    if needs.of(character_id)["mana"] == 0:
        now_add_hit_point /= 2
    now_add_hit_point = int(now_add_hit_point)
    needs.add(character_id, "hit", now_add_hit_point)
    change_data.hit_point += now_add_hit_point
    # 如果超过最大值则=最大值
    if needs.of(character_id)["hit"] >= needs.of(character_id)["hit_max"]:
        needs.set(character_id, hit=needs.of(character_id)["hit_max"])
    # 交互对象也同样#
    if activity.target(character_id) != character_id:
        target_data: identity.Identity = identity.of(
            activity.target(character_id)
        )
        change_data.target_change.setdefault(
            target_data.cid, game_type.TargetChange()
        )
        target_change: game_type.TargetChange = change_data.target_change[
            target_data.cid
        ]
        add_hit_point = add_time * (
            10 + needs.of(target_data.cid)["hit_max"] * 0.005
        )
        now_add_hit_point = add_hit_point
        # 如果气力=0则恢复减半
        if needs.of(target_data.cid)["mana"] == 0:
            now_add_hit_point /= 2
        now_add_hit_point = int(now_add_hit_point)
        needs.add(target_data.cid, "hit", now_add_hit_point)
        target_change.hit_point += now_add_hit_point
        # 如果超过最大值则=最大值
        if (
            needs.of(target_data.cid)["hit"]
            >= needs.of(target_data.cid)["hit_max"]
        ):
            needs.set(target_data.cid, hit=needs.of(target_data.cid)["hit_max"])


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ADD_BOTH_SMALL_MANA_POINT
)
def handle_add_both_small_mana_point(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    增加双方少量气力
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.dead(character_id):
        return
    add_mana_point = add_time * (20 + needs.of(character_id)["hit_max"] * 0.01)
    add_mana_point = int(add_mana_point)
    needs.add(character_id, "mana", add_mana_point)
    change_data.mana_point += add_mana_point
    if needs.of(character_id)["mana"] > needs.of(character_id)["mana_max"]:
        needs.set(character_id, mana=needs.of(character_id)["mana_max"])
    # 交互对象也同样#
    if activity.target(character_id) != character_id:
        target_data: identity.Identity = identity.of(
            activity.target(character_id)
        )
        change_data.target_change.setdefault(
            target_data.cid, game_type.TargetChange()
        )
        target_change: game_type.TargetChange = change_data.target_change[
            target_data.cid
        ]
        add_mana_point = add_time * (
            20 + needs.of(target_data.cid)["hit_max"] * 0.01
        )
        add_mana_point = int(add_mana_point)
        needs.add(target_data.cid, "mana", add_mana_point)
        target_change.mana_point += add_mana_point
        # 如果超过最大值则=最大值
        if (
            needs.of(target_data.cid)["mana"]
            >= needs.of(target_data.cid)["mana_max"]
        ):
            needs.set(
                target_data.cid, mana=needs.of(target_data.cid)["mana_max"]
            )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.MOVE_TO_TARGET_SCENE
)
def handle_move_to_target_scene(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    移动至目标场景
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    character_data: identity.Identity = identity.of(character_id)
    if activity.dead(character_id):
        return
    if len(activity.behavior(character_id).move_target):
        # 如果NPC移动提示未屏蔽，且该NPC和玩家位于同一地点，则输出提示信息
        if (
            normal_config.system_setting.draw_setting[8] == 1
            and character_id > 0
            and activity.position(character_id) == activity.position(0)
        ):
            target_position_name = activity.behavior(character_id).move_target[
                -1
            ]
            if target_position_name == "0":
                target_position_name = _("入口")
            draw_text = _("{0}向{1}移动了\n").format(
                character_data.name, target_position_name
            )
            now_draw = draw.NormalDraw()
            now_draw.text = draw_text
            now_draw.width = width
            now_draw.draw()
        map_handle.character_move_scene(
            activity.position(character_id),
            activity.behavior(character_id).move_target,
            character_id,
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.FIRST_KISS
)
def handle_first_kiss(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    记录初吻
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    # target_data.social_contact_data.setdefault(character_id, 0)

    if abilities.talent(character_id)[4] == 1:
        abilities.talent(character_id)[4] = 0
        first_record.set(
            character_id,
            first_kiss_id=target_data.cid,
            first_kiss_time=game_time.now(),
            first_kiss_place=activity.position(character_id),
        )
        # 初吻的二段结算
        second_behavior.character_get_second_behavior(
            character_id, "first_kiss"
        )
    if abilities.talent(target_data.cid)[4] == 1:
        abilities.talent(target_data.cid)[4] = 0
        first_record.set(
            target_data.cid,
            first_kiss_id=character_id,
            first_kiss_time=game_time.now(),
            first_kiss_place=activity.position(target_data.cid),
        )
        # 初吻的二段结算
        second_behavior.character_get_second_behavior(
            target_data.cid, "first_kiss"
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.FIRST_SEX
)
def handle_first_sex(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    记录处女
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))

    item_flag = False

    # 获取玩家最近一条非中断H指令的中文名，避免中断指令覆盖真实破处体位
    behavior_id = get_last_valid_sex_behavior_id()
    behavior_data = game_config.config_behavior[behavior_id]
    instruct_name = behavior_data.name

    if abilities.talent(character_id)[5] == 1 and (not item_flag):
        abilities.talent(character_id)[5] = 0
        first_record.set(
            character_id,
            first_sex_id=target_data.cid,
            first_sex_time=game_time.now(),
            first_sex_place=activity.position(character_id),
            first_sex_posture=instruct_name,
        )
    if abilities.talent(target_data.cid)[0] == 1:
        abilities.talent(target_data.cid)[0] = 0
        # NPC的V破处记录进部位交初体验dict（破处是权威事件，无条件覆盖通用挂钩先建的简版条目）
        with first_record.editing(target_data.cid) as fr:
            fr.first_part_sex_dict[6] = {
                "id": character_id,
                "time": game_time.now(),
                "place": list(activity.position(target_data.cid)),
                "posture": instruct_name,
                "item": 1 if item_flag else -1,
            }
        second_behavior.character_get_second_behavior(
            target_data.cid, "first_sex"
        )
        # 失去性无知
        if abilities.talent(target_data.cid)[222] == 1:
            abilities.talent(target_data.cid)[222] = 0
            now_draw = draw.NormalDraw()
            now_draw.text = _("\n{0}失去了【性无知】\n\n").format(
                target_data.name
            )
            now_draw.draw()

        # 处子血胖次
        pan_id = None
        now_draw = draw.NormalDraw()
        if len(wardrobe.of(target_data.cid).cloth_wear[9]):
            pan_id = wardrobe.of(target_data.cid).cloth_wear[9][-1]
        elif len(wardrobe.of(target_data.cid).cloth_off[9]):
            pan_id = wardrobe.of(target_data.cid).cloth_off[9][-1]
        # BUG 这一块疑似有BUG，但是未能确定来源，所以先多加个限制条件
        elif panties_tem := player_collection.get("npc_panties_tem").get(
            activity.target(character_id)
        ):
            pan_id = panties_tem[-1]
        if pan_id is not None:
            pan_name = game_config.config_clothing_tem[pan_id].name
            wardrobe.set_part(target_data.cid, "cloth_wear", 9, [])
            now_draw.text = _(
                "\n获得了{0}穿着的{1}(沾有处子血)，已自动存入收藏品列表，可在藏物馆查看\n\n"
            ).format(target_data.name, pan_name)
            now_draw.draw()
            player_collection.set_first_panty(
                activity.target(character_id),
                _("{0}(沾有处子血)").format(pan_name),
            )
        else:
            now_draw.text = _(
                "\n{0}的处子血滴了下去，被你谨慎地用试管接了一滴，已自动存入收藏品列表，可在藏物馆查看\n\n"
            ).format(target_data.name)
            player_collection.set_first_panty(
                activity.target(character_id),
                _("一滴{0}的处子血").format(target_data.name),
            )
            now_draw.draw()


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.FIRST_A_SEX
)
def handle_first_a_sex(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    记录A处女
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))

    # 判定是否为道具性交
    item_flag = False
    if cache.input_cache and cache.input_cache[-1] == str(
        constant.Instruct.VIBRATOR_INSERTION_ANAL
    ):
        item_flag = True

    # 获取玩家最近一条非中断H指令的中文名，避免中断指令覆盖真实破处体位
    behavior_id = get_last_valid_sex_behavior_id()
    behavior_data = game_config.config_behavior[behavior_id]
    instruct_name = behavior_data.name

    if abilities.talent(character_id)[5] == 1 and (not item_flag):
        abilities.talent(character_id)[5] = 0
        first_record.set(
            character_id,
            first_sex_id=target_data.cid,
            first_sex_time=game_time.now(),
            first_sex_place=activity.position(character_id),
            first_sex_posture=instruct_name,
        )
    if abilities.talent(target_data.cid)[1] == 1:
        abilities.talent(target_data.cid)[1] = 0
        # NPC的A破处记录进部位交初体验dict（破处是权威事件，无条件覆盖通用挂钩先建的简版条目）
        with first_record.editing(target_data.cid) as fr:
            fr.first_part_sex_dict[8] = {
                "id": character_id,
                "time": game_time.now(),
                "place": list(activity.position(target_data.cid)),
                "posture": instruct_name,
                "item": 1 if item_flag else -1,
            }
        if (not character_id) or (not target_data.cid):
            # a处女的二段结算
            second_behavior.character_get_second_behavior(
                target_data.cid, "first_a_sex"
            )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.FIRST_U_SEX
)
def handle_first_u_sex(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    记录U处女
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))

    # 判定是否为道具性交，已废弃
    # item_flag = False
    # if cache.input_cache[len(cache.input_cache) - 1] == str(constant.Instruct.URINE_COLLECTOR_ON):
    #     item_flag = True

    # 获取玩家最近一条非中断H指令的中文名，避免中断指令覆盖真实破处体位
    behavior_id = get_last_valid_sex_behavior_id()
    behavior_data = game_config.config_behavior[behavior_id]
    instruct_name = behavior_data.name

    if abilities.talent(character_id)[5] == 1:
        abilities.talent(character_id)[5] = 0
        first_record.set(
            character_id,
            first_sex_id=target_data.cid,
            first_sex_time=game_time.now(),
            first_sex_place=activity.position(character_id),
            first_sex_posture=instruct_name,
        )
    if abilities.talent(target_data.cid)[2] == 1:
        abilities.talent(target_data.cid)[2] = 0
        # NPC的U破处记录进部位交初体验dict（若未来接入采尿器道具破处，item记2）
        with first_record.editing(target_data.cid) as fr:
            fr.first_part_sex_dict[9] = {
                "id": character_id,
                "time": game_time.now(),
                "place": list(activity.position(target_data.cid)),
                "posture": instruct_name,
                "item": -1,
            }
        if (not character_id) or (not target_data.cid):
            # 处女的二段结算
            second_behavior.character_get_second_behavior(
                target_data.cid, "first_u_sex"
            )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.FIRST_W_SEX
)
def handle_first_w_sex(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    记录W处女
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))

    # 获取玩家最近一条非中断H指令的中文名，避免中断指令覆盖真实破处体位
    behavior_id = get_last_valid_sex_behavior_id()
    behavior_data = game_config.config_behavior[behavior_id]
    instruct_name = behavior_data.name

    if abilities.talent(character_id)[5] == 1:
        abilities.talent(character_id)[5] = 0
        first_record.set(
            character_id,
            first_sex_id=target_data.cid,
            first_sex_time=game_time.now(),
            first_sex_place=activity.position(character_id),
            first_sex_posture=instruct_name,
        )
    if abilities.talent(target_data.cid)[3] == 1:
        abilities.talent(target_data.cid)[3] = 0
        # NPC的W破处记录进部位交初体验dict（W破处无道具）
        with first_record.editing(target_data.cid) as fr:
            fr.first_part_sex_dict[7] = {
                "id": character_id,
                "time": game_time.now(),
                "place": list(activity.position(target_data.cid)),
                "posture": instruct_name,
                "item": -1,
            }
        if (not character_id) or (not target_data.cid):
            # 处女的二段结算
            second_behavior.character_get_second_behavior(
                target_data.cid, "first_w_sex"
            )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DAY_FIRST_MEET_0
)
def handle_day_first_meet_0(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己变为今天已见过面
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.dead(character_id):
        return
    first_record.set(character_id, day_first_meet=0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DAY_FIRST_MEET_1
)
def handle_day_first_meet_1(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己变为今天未见过面
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.dead(character_id):
        return
    first_record.set(character_id, day_first_meet=1)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.FIRST_KISS_TO_PENIS
)
def handle_first_kiss_to_penis(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    记录阴茎初吻
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    talent = abilities.talent(target_data.cid)
    # target_data.social_contact_data.setdefault(character_id, 0)
    if activity.target(character_id) == character_id:
        return

    if talent[4] == 1:
        talent[4] = 0
        first_record.set(
            target_data.cid,
            first_kiss_id=character_id,
            first_kiss_time=game_time.now(),
            first_kiss_place=activity.position(target_data.cid),
            first_kiss_body_part=1,
        )
        # 阴茎初吻的二段结算
        second_behavior.character_get_second_behavior(
            target_data.cid, "first_kiss_but_penis"
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PENETRATING_VISION_ON
)
def handle_penetrating_vision_on(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    开启透视（含理智消耗）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.dead(character_id):
        return
    player_ability.set(character_id, visual=True)
    needs.add(character_id, "sanity", -1, min=0)
    change_data.sanity_point -= 1
    player_ability.add_sanity_cost(character_id, 1)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PENETRATING_VISION_OFF
)
def handle_penetrating_vision_off(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    关闭透视
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.dead(character_id):
        return
    player_ability.set(character_id, visual=False)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.HORMONE_ON
)
def handle_hormone_on(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    开启信息素
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.dead(character_id):
        return
    player_ability.set(character_id, hormone=True)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.HORMONE_OFF
)
def handle_hormone_off(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    关闭信息素
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.dead(character_id):
        return
    player_ability.set(character_id, hormone=False)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.HYPNOSIS_ONE
)
def handle_hypnosis_one(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    单人催眠（含理智消耗）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    character_data: identity.Identity = identity.of(character_id)
    target_character_data = identity.of(activity.target(character_id))
    change_data.target_change.setdefault(
        target_character_data.cid, game_type.TargetChange()
    )
    target_change: game_type.TargetChange = change_data.target_change[
        target_character_data.cid
    ]
    if activity.dead(character_id):
        return
    # 结算理智消耗
    santi_down = hypnosis_panel.calculate_hypnosis_sanity_cost(
        activity.target(character_id)
    )
    needs.add(character_id, "sanity", -santi_down, min=0)
    change_data.sanity_point -= santi_down
    player_ability.add_sanity_cost(character_id, santi_down)
    # 结算催眠度增加
    hypnosis_degree_grow = hypnosis_panel.hypnosis_degree_calculation(
        activity.target(character_id)
    )
    # debug下催眠增加到999
    if cache.debug_mode:
        hypnosis_degree_grow = 999
    new_hypnosis_degree = (
        hypnosis.degree(activity.target(character_id)) + hypnosis_degree_grow
    )
    # 赋予到角色数据
    hypnosis.set(
        activity.target(character_id),
        hypnosis_degree=min(
            new_hypnosis_degree,
            hypnosis_panel.hypnosis_degree_limit_calculation(),
        ),
    )
    target_change.hypnosis_degree += hypnosis_degree_grow
    # 判断催眠完成
    hypnosis_panel.evaluate_hypnosis_completion(activity.target(character_id))
    # 判断是否理智已耗尽导致催眠结束
    if needs.of(character_id)["sanity"] == 0 and flags.get(
        target_character_data.cid, "unconscious_h"
    ):
        # 空气催眠则重置催眠地点和解开门锁
        if flags.get(target_character_data.cid, "unconscious_h") == 5:
            player_ability.set(character_id, air_hypnosis_position="")
        flags.set(target_character_data.cid, unconscious_h=0)
        hypnosis_state.clear_hypnosis_sub_states(activity.target(character_id))
        now_draw = draw.NormalDraw()
        now_draw.text = _("\n{0}的理智耗尽，催眠结束\n\n").format(
            character_data.name
        )
        now_draw.draw()


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.HYPNOSIS_ALL
)
def handle_hypnosis_all(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    集体催眠（含理智消耗）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    character_data: identity.Identity = identity.of(character_id)
    if activity.dead(character_data.cid):
        return
    # 获取当前场景的全角色名单
    character_data = identity.of(character_id)
    scene_path_str = map_handle.get_map_system_path_str_for_list(
        activity.position(character_data.cid)
    )
    scene_data: game_type.Scene = cache.scene_data[scene_path_str]
    scene_character_list = scene_data.character_list.copy()
    # 催眠角色列表
    hypnosis_character_list = []
    # 去掉里的自己
    if character_id in scene_character_list:
        scene_character_list.remove(character_id)
    # 基础理智消耗
    sanity_point_cost: num.Num = 10
    # 遍历角色列表
    for target_id in scene_character_list:
        # 计算理智消耗
        santi_down = hypnosis_panel.calculate_hypnosis_sanity_cost(target_id)
        sanity_point_cost += santi_down
        hypnosis_character_list.append(target_id)
        # 如果超出了现有理智，则取现有理智
        if sanity_point_cost >= needs.of(character_data.cid)["sanity"]:
            sanity_point_cost = min(
                sanity_point_cost, needs.of(character_data.cid)["sanity"]
            )
            break
    # 结算理智消耗
    needs.add(character_data.cid, "sanity", -sanity_point_cost, min=0)
    change_data.sanity_point -= sanity_point_cost
    player_ability.add_sanity_cost(character_data.cid, sanity_point_cost)
    # 遍历催眠角色列表
    for target_id in hypnosis_character_list:
        target_character_data = identity.of(target_id)
        change_data.target_change.setdefault(
            target_character_data.cid, game_type.TargetChange()
        )
        target_change: game_type.TargetChange = change_data.target_change[
            target_character_data.cid
        ]
        if activity.dead(target_character_data.cid):
            continue
        # 结算催眠度增加
        hypnosis_degree_grow = hypnosis_panel.hypnosis_degree_calculation(
            target_id
        )
        # debug下催眠增加到999
        if cache.debug_mode:
            hypnosis_degree_grow = 999
        new_hypnosis_degree = hypnosis.degree(target_id) + hypnosis_degree_grow
        # 赋予到角色数据
        hypnosis.set(
            target_id,
            hypnosis_degree=min(
                new_hypnosis_degree,
                hypnosis_panel.hypnosis_degree_limit_calculation(),
            ),
        )
        target_change.hypnosis_degree += hypnosis_degree_grow
        # 判断催眠完成
        hypnosis_panel.evaluate_hypnosis_completion(target_id)
    # 判断是否理智已耗尽导致催眠结束
    if needs.of(character_data.cid)["sanity"] == 0:
        for target_id in scene_character_list:
            target_character_data = identity.of(target_id)
            # 空气催眠则重置催眠地点和解开门锁
            if flags.get(target_character_data.cid, "unconscious_h") == 5:
                player_ability.set(character_data.cid, air_hypnosis_position="")
            flags.set(target_character_data.cid, unconscious_h=0)
            hypnosis_state.clear_hypnosis_sub_states(target_id)
            now_draw = draw.NormalDraw()
            now_draw.text = _("\n{0}的理智耗尽，催眠结束\n\n").format(
                character_data.name
            )
            now_draw.draw()


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.HYPNOSIS_CANCEL
)
def handle_hypnosis_cancel(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    解除交互对象的催眠
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_character_data = identity.of(activity.target(character_id))
    if activity.dead(character_id):
        return
    # 空气催眠则重置催眠地点和解开门锁
    if flags.get(target_character_data.cid, "unconscious_h") == 5:
        player_ability.set(character_id, air_hypnosis_position="")
    # 清零催眠H状态
    if flags.get(target_character_data.cid, "unconscious_h") >= 4:
        flags.set(target_character_data.cid, unconscious_h=0)
    # 去掉大部分的心体催眠状态
    hypnosis_state.clear_hypnosis_sub_states(activity.target(character_id))
    # 结算二段行为
    handle_npc_ai_in_h.settle_unconscious_semen_and_cloth(character_id)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_HYPNOSIS_INCREASE_BODY_SENSITIVITY_ON
)
def handle_target_hypnosis_increase_body_sensitivity_on(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    对方开启体控-敏感度提升（含理智消耗）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_character_data = identity.of(activity.target(character_id))
    if activity.dead(character_id):
        return
    santi_down = 10
    hypnosis.set(target_character_data.cid, increase_body_sensitivity=True)
    needs.add(character_id, "sanity", -santi_down, min=0)
    change_data.sanity_point -= santi_down
    player_ability.add_sanity_cost(character_id, santi_down)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_HYPNOSIS_INCREASE_BODY_SENSITIVITY_OFF
)
def handle_target_hypnosis_increase_body_sensitivity_off(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    对方关闭体控-敏感度提升
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_character_data = identity.of(activity.target(character_id))
    if activity.dead(character_id):
        return
    hypnosis.set(target_character_data.cid, increase_body_sensitivity=False)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_HYPNOSIS_FORCE_CLIMAX
)
def handle_target_hypnosis_force_climax(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    对方开启体控-强制高潮（含理智消耗）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.dead(character_id):
        return
    needs.add(character_id, "sanity", -50, min=0)
    change_data.sanity_point -= 50
    player_ability.add_sanity_cost(character_id, 50)

    base_chara_climix_common_settle(
        activity.target(character_id),
        4,
        change_data_to_target_change=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_HYPNOSIS_FORCE_OVULATION_ON
)
def handle_target_hypnosis_force_ovulation_on(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    对方开启体控-强制排卵（含理智消耗）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_character_data = identity.of(activity.target(character_id))
    if activity.dead(character_id):
        return
    santi_down = 10
    hypnosis.set(target_character_data.cid, force_ovulation=True)
    from Script.System.Pregnancy_System import egg_handle

    with pregnancy.editing(activity.target(character_id)) as target_preg:
        target_preg.reproduction_period = 5
        # 无壳卵生：强制进入排卵日的同时给予本日的体外排卵机会（周期直接改写不经过每日推进，需在此补置）
        if egg_handle.is_egg_soft(activity.target(character_id)):
            target_preg.external_ovulation_chance = True
    needs.add(character_id, "sanity", -santi_down, min=0)
    change_data.sanity_point -= santi_down
    player_ability.add_sanity_cost(character_id, santi_down)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_HYPNOSIS_FORCE_OVULATION_OFF
)
def handle_target_hypnosis_force_ovulation_off(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    对方关闭体控-强制排卵
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_character_data = identity.of(activity.target(character_id))
    if activity.dead(character_id):
        return
    hypnosis.set(target_character_data.cid, force_ovulation=False)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_HYPNOSIS_BLOCKHEAD_SWITCH_CHANGE
)
def handle_target_hypnosis_blockhead_switch_change(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    对方切换体控-木头人开关（含理智消耗）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_character_data = identity.of(activity.target(character_id))
    if activity.dead(character_id):
        return
    # 清理会复位全部行为模式标志，本次操作是开启还是关闭须以清理前的开关状态判断
    target_in_blockhead = hypnosis.get(target_character_data.cid, "blockhead")
    hypnosis_state.clear_hypnosis_behavior_mode(activity.target(character_id))
    if not target_in_blockhead:
        hypnosis.set(target_character_data.cid, blockhead=True)
        flags.set(target_character_data.cid, unconscious_h=6)
        santi_down = 10
        needs.add(character_id, "sanity", -santi_down, min=0)
        change_data.sanity_point -= santi_down
        player_ability.add_sanity_cost(character_id, santi_down)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_HYPNOSIS_BLOCKHEAD_OFF
)
def handle_target_hypnosis_blockhead_off(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    对方关闭体控-木头人
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_character_data = identity.of(activity.target(character_id))
    if activity.dead(character_id):
        return
    if hypnosis.get(target_character_data.cid, "blockhead"):
        hypnosis.set(target_character_data.cid, blockhead=False)
        flags.set(target_character_data.cid, unconscious_h=0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_HYPNOSIS_ACTIVE_H_SWITCH_CHANGE
)
def handle_target_hypnosis_active_h_switch_change(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    对方切换体控-逆推开关（含理智消耗）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_character_data = identity.of(activity.target(character_id))
    if activity.dead(character_id):
        return
    # 清理会复位全部行为模式标志，本次操作是开启还是关闭须以清理前的开关状态判断
    target_in_active_h = hypnosis.get(target_character_data.cid, "active_h")
    hypnosis_state.clear_hypnosis_behavior_mode(activity.target(character_id))
    if not target_in_active_h:
        hypnosis.set(target_character_data.cid, active_h=True)
        h_state.set(target_character_data.cid, npc_active_h=True)
        flags.set(target_character_data.cid, unconscious_h=6)
        santi_down = 10
        needs.add(character_id, "sanity", -santi_down, min=0)
        change_data.sanity_point -= santi_down
        player_ability.add_sanity_cost(character_id, santi_down)
        handle_instruct.plan_instruct_common_settle(constant.Behavior.H)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_HYPNOSIS_ACTIVE_H_OFF
)
def handle_target_hypnosis_active_h_off(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    对方关闭体控-逆推
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_character_data = identity.of(activity.target(character_id))
    if activity.dead(character_id):
        return
    if hypnosis.get(target_character_data.cid, "active_h"):
        hypnosis.set(target_character_data.cid, active_h=False)
        h_state.set(target_character_data.cid, npc_active_h=False)
        flags.set(target_character_data.cid, unconscious_h=0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_HYPNOSIS_PAIN_AS_PLEASURE_SWITCH_CHANGE
)
def handle_target_hypnosis_pain_as_pleasure_switch_change(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    对方切换心控-苦痛快感化开关（含理智消耗）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_character_data = identity.of(activity.target(character_id))
    if activity.dead(character_id):
        return
    if hypnosis.get(target_character_data.cid, "pain_as_pleasure"):
        hypnosis.set(target_character_data.cid, pain_as_pleasure=False)
    else:
        hypnosis.set(target_character_data.cid, pain_as_pleasure=True)
        santi_down = 10
        needs.add(character_id, "sanity", -santi_down, min=0)
        change_data.sanity_point -= santi_down
        player_ability.add_sanity_cost(character_id, santi_down)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_HYPNOSIS_PAIN_AS_PLEASURE_OFF
)
def handle_target_hypnosis_pain_as_pleasure_off(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    对方关闭心控-苦痛快感化
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_character_data = identity.of(activity.target(character_id))
    if activity.dead(character_id):
        return
    hypnosis.set(target_character_data.cid, pain_as_pleasure=False)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TIME_STOP_ON
)
def handle_time_stop_on(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    开启时停
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    modes.set_time_stop(True)
    target_chara_set = roster.active()
    target_chara_set.add(0)
    for chara_id in target_chara_set:
        chara_data = identity.of(chara_id)
        flags.set(chara_data.cid, unconscious_h=3)
        # 重置时停中的角色的时停高潮计数
        with h_state.editing(chara_id) as hs:
            for state_id in game_config.config_character_state:
                if game_config.config_character_state[state_id].type == 0:
                    hs.time_stop_orgasm_count[state_id] = 0


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TIME_STOP_OFF
)
def handle_time_stop_off(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    关闭时停
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    modes.set_time_stop(False)
    target_chara_set = roster.active()
    target_chara_set.add(0)
    for chara_id in target_chara_set:
        chara_data = identity.of(chara_id)
        flags.set(chara_data.cid, unconscious_h=0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_BE_CARRIED_IN_TIME_STOP
)
def handle_target_be_carried_in_time_stop(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象变成被时停搬运状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.target(character_id) == character_id:
        return
    player_ability.set(
        character_id,
        carry_chara_id_in_time_stop=activity.target(character_id),
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_NOT_BE_CARRIED_IN_TIME_STOP
)
def handle_target_not_be_carried_in_time_stop(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    清零自己的当前时停搬运对象
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    player_ability.set(character_id, carry_chara_id_in_time_stop=0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_BE_FREE_IN_TIME_STOP
)
def handle_target_be_free_in_time_stop(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    将交互对象设为时停中自由状态（含理智消耗）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    player_ability.set(
        character_id,
        free_in_time_stop_chara_id=activity.target(character_id),
    )
    needs.add(character_id, "sanity", -50, min=0)
    change_data.sanity_point -= 50
    player_ability.add_sanity_cost(character_id, 50)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_NOT_BE_FREE_IN_TIME_STOP
)
def handle_target_not_be_free_in_time_stop(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    清零自己的让某人时停中自由状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    player_ability.set(character_id, free_in_time_stop_chara_id=0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.NPC_ACTIVE_H_ON
)
def handle_npc_active_h_on(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己开启主动H
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.dead(character_id):
        return
    h_state.set(character_id, npc_active_h=True)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.NPC_ACTIVE_H_OFF
)
def handle_npc_active_h_off(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己关闭主动H
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.dead(character_id):
        return
    h_state.set(character_id, npc_active_h=False)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_NPC_ACTIVE_H_ON
)
def handle_target_npc_active_h_on(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    对方开启主动H
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_character_data = identity.of(activity.target(character_id))
    if activity.dead(character_id):
        return
    h_state.set(target_character_data.cid, npc_active_h=True)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_NPC_ACTIVE_H_OFF
)
def handle_target_npc_active_h_off(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    对方关闭主动H
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_character_data = identity.of(activity.target(character_id))
    if activity.dead(character_id):
        return
    h_state.set(target_character_data.cid, npc_active_h=False)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PL_JUST_SHOOT_ON
)
def handle_pl_just_shoot_on(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    玩家变为前指令刚刚射精状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    h_state.set(0, just_shoot=1)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PL_JUST_SHOOT_OFF
)
def handle_pl_just_shoot_off(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    玩家清零前指令刚刚射精状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    h_state.set(0, just_shoot=0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PL_CONDOM_USE_RESET
)
def handle_pl_condom_use_reset(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    重置玩家的避孕套使用状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    h_state.set(0, condom_count=[0, 0])


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SELF_CONDOM_INFO_SHOW_FLAG_ON
)
def handle_self_condom_info_show_flag_on(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己开启避孕套信息显示
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    h_state.set(character_id, condom_info_show_flag=True)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TAGET_CONDOM_INFO_SHOW_FLAG_ON
)
def handle_target_condom_info_show_flag_on(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象开启避孕套信息显示
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    handle_self_condom_info_show_flag_on(
        activity.target(character_id), add_time, change_data, now_time
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SCENE_ALL_CHARACTERS_CONDOM_INFO_SHOW_FLAG_ON
)
def handle_scene_all_characters_condom_info_show_flag_on(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    场景内所有角色开启避孕套信息显示
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    scene_path_str = map_handle.get_map_system_path_str_for_list(
        activity.position(character_id)
    )
    scene_data: game_type.Scene = cache.scene_data[scene_path_str]
    for chara_id in scene_data.character_list:
        # 遍历非玩家的角色
        if chara_id:
            handle_target_condom_info_show_flag_on(
                chara_id, add_time, change_data, now_time
            )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SELF_ORGASM_EDGE_ON
)
def handle_self_orgasm_edge_on(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己开启绝顶寸止
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    with h_state.editing(character_id) as hs:
        hs.orgasm_edge = 1
        for state_id in game_config.config_character_state:
            if game_config.config_character_state[state_id].type == 0:
                hs.orgasm_edge_count[state_id] = 0


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SELF_ORGASM_EDGE_OFF
)
def handle_self_orgasm_edge_off(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己关闭绝顶寸止
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    h_state.set(character_id, orgasm_edge=0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_ORGASM_EDGE_ON
)
def handle_target_orgasm_edge_on(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象开启绝顶寸止
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    handle_self_orgasm_edge_on(
        activity.target(character_id), add_time, change_data, now_time
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_ORGASM_EDGE_OFF
)
def handle_target_orgasm_edge_off(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象关闭绝顶寸止
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    handle_self_orgasm_edge_off(
        activity.target(character_id), add_time, change_data, now_time
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ALL_GROUP_SEX_TEMPLE_ON
)
def handle_all_group_sex_temple_run_on(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    开启全群交模板，进行轮流群交
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    h_state.set(0, all_group_sex_temple_run=True)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ALL_GROUP_SEX_TEMPLE_OFF
)
def handle_all_group_sex_temple_run_off(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    关闭全群交模板，进行单轮群交
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    h_state.set(0, all_group_sex_temple_run=False)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SELF_JOIN_GROUP_SEX_ON
)
def handle_self_join_group_sex_on(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己开始加入群交
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, go_to_join_group_sex=True)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SELF_JOIN_GROUP_SEX_OFF
)
def handle_self_join_group_sex_off(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己停止加入群交
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, go_to_join_group_sex=False)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.CLEAR_GROUP_SEX_TEMPLATE
)
def handle_clear_group_sex_template(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    清空自己的群交模板
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    with h_state.editing(character_id) as hs:
        hs.group_sex_body_template_dict = (
            game_type.BODY_H_STATE().group_sex_body_template_dict
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_GET_WEEKNESSS_BY_DR
)
def handle_target_get_weeknesss_by_dr(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象获得[被博士持有把柄]
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_character_data = identity.of(activity.target(character_id))
    if activity.dead(character_id):
        return
    abilities.talent(target_character_data.cid)[402] = 1
    now_draw = draw.NormalDraw()
    now_draw.width = width
    now_draw.text = _("\n{0}获得了【被博士持有把柄】\n").format(
        target_character_data.name
    )
    now_draw.draw()


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SELF_GET_WEEKNESSS_TO_DR
)
def handle_self_get_weeknesss_to_dr(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己获得[持有博士把柄]
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    character_data: identity.Identity = identity.of(character_id)
    if activity.dead(character_id):
        return
    abilities.talent(character_id)[401] = 1
    now_draw = draw.NormalDraw()
    now_draw.width = width
    now_draw.text = _("\n{0}获得了【持有博士把柄】\n").format(
        character_data.name
    )
    now_draw.draw()


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ENTER_WAITING_FOR_PHYSICAL_EXAM
)
def handle_enter_waiting_for_physical_exam(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己进入等待体检状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    physical_exam.add(physical_exam.WAITING, character_id)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.EXIT_WAITING_FOR_PHYSICAL_EXAM
)
def handle_exit_waiting_for_physical_exam(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己退出等待体检状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    physical_exam.discard(physical_exam.WAITING, character_id)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.WAIT_UNITL_TRAGET_ACTION_END
)
def handle_wait_unitl_traget_action_end(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    玩家等待至交互对象行动结束
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    from Script.Modules.gameplay_resolution import plan_queue

    target_character_data = identity.of(activity.target(character_id))
    if activity.dead(character_id):
        return
    target_start_time = activity.behavior(target_character_data.cid).start_time
    target_end_time = game_time.get_sub_date(
        activity.behavior(target_character_data.cid).duration,
        old_date=target_start_time,
    )
    # 到结束时间还有多少分钟，玩家接着等这么久
    add_time = int((target_end_time - now_time).total_seconds() / 60)
    if add_time > 0:
        plan_queue.plan_next(
            0,
            constant.Behavior.WAIT,
            add_time,
            state=constant.CharacterStatus.STATUS_WAIT,
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.WAIT_UNITL_PLAYER_ACTION_END
)
def handle_wait_unitl_player_action_end(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己等待至玩家行动结束
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.dead(character_id):
        return
    player_action_start_time = activity.behavior(0).start_time
    player_action_end_time = game_time.get_sub_date(
        activity.behavior(0).duration, old_date=player_action_start_time
    )
    # 到结束时间还有多少分钟
    add_time = int((player_action_end_time - now_time).total_seconds() / 60)
    activity.update_behavior(character_id, behavior_id=constant.Behavior.WAIT)
    activity.set_state(character_id, constant.CharacterStatus.STATUS_WAIT)
    activity.update_behavior(character_id, duration=add_time + 1)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SET_TARGET_FOOD_FROM_BAG_LAST
)
def handle_set_target_food_from_bag_last(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    将自己行为目标食物指定为背包里的最后一个食物
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if len(inventory.foods(character_id)) == 0:
        return
    # 获取背包最后一个食物
    last_key = list(inventory.foods(character_id).keys())[-1]
    now_food = inventory.foods(character_id)[last_key]
    activity.update_behavior(character_id, target_food=now_food)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.CLEAR_TARGET_TOILET_PATH
)
def handle_clear_target_toilet_path(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    清空自己记录的目标厕所位置路径
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    action_info.set(character_id, "find_another_toilet", [])


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.MOVE_TO_OWN_DORMITORY
)
def handle_move_to_own_dormitory(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己前往自己的宿舍
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    from Script.StateMachine.default import plan_movement

    if not add_time:
        return
    to_target = map_handle.get_map_system_path_for_str(
        chara_life.dormitory(character_id)
    )
    plan_movement(character_id, to_target)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.STOP_ENDURANCE_SHOOT
)
def handle_stop_endurance_shoot(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    射出忍耐的射精次数
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    from Script.Settle import orgasm_settle

    orgasm_settle.orgasm_judge(character_id, change_data, skip_undure=True)
    second_behavior.second_behavior_effect(character_id, change_data)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_BE_CARRIED
)
def handle_target_be_carried(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    将交互对象设为当前搬运对象
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.target(character_id) == character_id:
        return
    action_info.set(
        character_id, "carry_chara_id", activity.target(character_id)
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_NOT_BE_CARRIED
)
def handle_target_not_be_carried(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    清零自己的当前搬运对象
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.target(character_id) == character_id:
        return
    action_info.set(character_id, "carry_chara_id", 0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.GET_SLEEP_DISTURBED_STATE
)
def handle_get_sleep_disturbed_state(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身获得睡觉中被吵醒状态，一小时内不会再产生睡觉需求
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    action_info.set(
        character_id,
        "sleep_disturbed_end_time",
        game_time.get_sub_date(minute=60, old_date=game_time.now()),
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.FACILITY_DAMAGE_CHECK
)
def handle_facility_damage_check(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    几率判定自己所在地点是否造成损坏
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    # 获取当前位置
    scene_path_str = map_handle.get_map_system_path_str_for_list(
        activity.position(character_id)
    )
    # 计算已损坏次数
    damage_count = maintenance.damage().get(scene_path_str, 0)
    # 计算损坏几率
    damage_rate = 1 / (2**damage_count)
    damage_rate = max(damage_rate, 0)
    # 掷骰子
    if random.random() < (damage_rate / 100):
        # 损坏
        damage_count += 1
        maintenance.set_damage(scene_path_str, damage_count)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ADD_MEDIUM_HIT_POINT
)
def handle_add_medium_hit_point(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    增加中量体力
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.dead(character_id):
        return
    add_hit_point: num.Num = int(
        add_time * (20 + needs.of(character_id)["hit_max"] * 0.01)
    )
    needs.add(character_id, "hit", add_hit_point)
    if needs.of(character_id)["hit"] > needs.of(character_id)["hit_max"]:
        add_hit_point -= (
            needs.of(character_id)["hit"] - needs.of(character_id)["hit_max"]
        )
        needs.set(character_id, hit=needs.of(character_id)["hit_max"])
    change_data.hit_point += add_hit_point


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ADD_MEDIUM_MANA_POINT
)
def handle_add_medium_mana_point(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    增加中量气力
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.dead(character_id):
        return
    add_mana_point: num.Num = int(
        add_time * (30 + needs.of(character_id)["hit_max"] * 0.02)
    )
    needs.add(character_id, "mana", add_mana_point)
    if needs.of(character_id)["mana"] > needs.of(character_id)["mana_max"]:
        add_mana_point -= (
            needs.of(character_id)["mana"] - needs.of(character_id)["mana_max"]
        )
        needs.set(character_id, mana=needs.of(character_id)["mana_max"])
    change_data.mana_point += add_mana_point


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.INTERRUPT_TARGET_ACTIVITY
)
def handle_interrupt_target_activity(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    打断交互目标活动
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if activity.dead(target_data.cid):
        return
    if activity.target(character_id) == 0:
        return
    # if target_data.behavior.behavior_id == constant.Behavior.DEAD:
    if activity.behavior(target_data.cid).behavior_id:
        if (
            activity.behavior(target_data.cid).start_time
            <= activity.behavior(character_id).start_time
        ):
            target_end_time = game_time.get_sub_date(
                activity.behavior(target_data.cid).duration,
                old_date=activity.behavior(target_data.cid).start_time,
            )
            if target_end_time >= activity.behavior(character_id).start_time:
                from Script.Modules.gameplay_resolution import plan_queue

                # 对方的行为在她自己的结束函数（actions.wrap_up）里收尾
                plan_queue.interrupt(target_data.cid)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.OPTION_FATER
)
def handle_option_fater(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    开启子选项面板
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    event_option_panel.line_feed.draw()
    now_draw = event_option_panel.Event_option_Panel(character_id, width)
    now_draw.draw()


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_TO_PLAYER
)
def handle_target_to_player(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象设为对玩家交互
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    activity.set_target(character_id, 0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.OPEN_INSTRUCT_FILTER_H
)
def handle_open_instruct_filter_h(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    开启H面板过滤器（已弃用）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    handle_instruct.instruct_filter_H_change(True)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.CLOSE_INSTRUCT_FILTER_H
)
def handle_close_instruct_filter_h(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    关闭H面板过滤器（已弃用）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    handle_instruct.instruct_filter_H_change(False)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ADD_THIS_EVENT_TO_TRIGGERED_RECORD
)
def handle_add_this_event_to_already_triggered(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    将玩家当前触发的事件加入总次数已触发记录
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if activity.event(0).son_event_id:
        history.trigger(activity.event(0).son_event_id)
    else:
        history.trigger(activity.event(0).event_id)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ADD_THIS_EVENT_TO_TODAY_TRIGGERED_RECORD
)
def handle_add_this_event_to_today_already_triggered(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    将玩家当前触发的事件加入今日已触发记录
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if activity.event(0).son_event_id:
        history.trigger_today(activity.event(0).son_event_id)
    else:
        history.trigger_today(activity.event(0).event_id)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.GROUP_SEX_MODE_ON
)
def handle_group_sex_mode_on(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    开启群交模式
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    # 如果已经开启，则不处理
    if modes.group_sex():
        return
    modes.set_group_sex(True)
    # 结算成就
    achievement.put("group_sex_record", {1: [], 2: []})
    achievement_panel.achievement_flow(_("群交"))


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.GROUP_SEX_MODE_OFF
)
def handle_group_sex_mode_off(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    关闭群交模式
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    modes.set_group_sex(False)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SEX_CLASS_MODE_ON
)
def handle_sex_class_mode_on(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    开启性技实操课（课堂H）模式，并把场景内可参加的学生全部拉进H状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    from Script.System.Education_System import sex_class_handle

    # 如果已经开启，则不处理
    if modes.sex_class():
        return
    modes.set_sex_class(True)
    # 必须同时置群交模式：群交模板面板、射精面板等十余处读取点判的都是那个标志，
    #    只置 sex_class_mode 的话整个模板界面都不会出现。行为效果串里的10010已经置过，这里兜底
    modes.set_group_sex(True)
    # 把在场可参加的学生一并拉进H状态——效果串里的462/464只管玩家自己与当前交互对象，
    # 其余到场学生要在这里补上，否则她们会被NPC AI派去做别的事
    for student_id in sex_class_handle.get_scene_student_list():
        # 与开课后才到场的学生（状态机 722）走同一个函数（Plan 25 §3.2）
        sex_class_handle.pull_student_into_class(student_id)
        # 出勤不在这里记：开课指令先调 sex_class_handle.start_sex_class() 记过一次了，
        #    这里再记会让每个到场学生每节实操课 +2（2026-09-12 第五轮修正）


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SEX_CLASS_MODE_OFF
)
def handle_sex_class_mode_off(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    关闭性技实操课（课堂H）模式

    玩家点「结束性技实操课」（6021）走这里。课堂 H 以别的方式结束（结束群交、玩家体力归零、学生全部力竭、群交中被撞见、
       转单人 H 后再结束 H）时，效果串里没有它，由 sex_class_handle.settle_orphan_class
       在玩家这一步的实时数据结算里按「玩家已不在 H」
       一并下课（Plan 32 §3.1）；两处都调 end_sex_class，它没有 running 的课时直接返回，重复调无妨。
    口上在效果结算之前就已经输出了（settle_behavior.handle_instruct_data 里先出口上、后跑效果循环），
       所以这里清 running 不会影响"提前/按时/拖堂"三档下课口上的判定。
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    from Script.System.Education_System import sex_class_handle

    modes.set_sex_class(False)
    sex_class_handle.end_sex_class()


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.RETAIN_COMMAND_WITH_EVENT_TEXT
)
def handle_retain_command_with_event_text(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    用事件文本代替指令文本，限指令后置
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    pass


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PL_TARGET_TO_ME
)
def handle_pl_target_to_me(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    将玩家的交互对象设为自己
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    activity.set_target(0, character_id)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_TO_SELF
)
def handle_target_to_self(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    将交互对象设为对自己交互
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    activity.set_target(character_id, character_id)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_TO_MASTUREBATE
)
def handle_target_to_masturebate(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    将交互对象设为对当前场景中的首位自慰角色
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    now_position = activity.position(character_id)
    now_scene_str = map_handle.get_map_system_path_str_for_list(now_position)
    now_scene_data = cache.scene_data[now_scene_str]
    if len(now_scene_data.character_list) >= 2:
        # 遍历当前角色列表
        for chara_id in now_scene_data.character_list:
            # 遍历非自己且非玩家的角色
            if chara_id != character_id and chara_id != 0:
                # 检测是否在自慰
                if (
                    activity.behavior(chara_id).behavior_id
                    == constant.Behavior.MASTUREBATE
                ):
                    activity.set_target(character_id, chara_id)
                    break


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_TO_MOST_DESIRE
)
def handle_target_to_most_desire(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    将交互对象设为场景内欲望值最高的角色
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    now_position = activity.position(character_id)
    now_scene_str = map_handle.get_map_system_path_str_for_list(now_position)
    now_scene_data = cache.scene_data[now_scene_str]
    target_chara_id = 0
    max_desire_value = -1
    if len(now_scene_data.character_list) >= 2:
        # 遍历当前角色列表
        for chara_id in now_scene_data.character_list:
            # 跳过玩家
            if chara_id == 0:
                continue
            # 检测欲望值
            if needs.of(chara_id)["desire"] > max_desire_value:
                max_desire_value = needs.of(chara_id)["desire"]
                target_chara_id = chara_id
        # 设置交互对象
        if target_chara_id:
            activity.set_target(character_id, target_chara_id)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.NOT_TIRED
)
def handle_not_tired(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    从疲劳中恢复
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, tired=False)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_ADD_SMALL_S_FEEL
)
def handle_target_add_small_s_feel(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象增加少量S快（S感补正）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    base_chara_state_common_settle(
        activity.target(character_id),
        add_time,
        0,
        50,
        change_data_to_target_change=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_ADD_SMALL_B_FEEL
)
def handle_target_add_small_b_feel(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象增加少量Ｂ快（B感补正）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    base_chara_state_common_settle(
        activity.target(character_id),
        add_time,
        1,
        50,
        change_data_to_target_change=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_ADD_SMALL_C_FEEL
)
def handle_target_add_small_c_feel(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象增加少量Ｃ快（C感补正）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    base_chara_state_common_settle(
        activity.target(character_id),
        add_time,
        2,
        50,
        change_data_to_target_change=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_ADD_SMALL_P_FEEL
)
def handle_target_add_small_p_feel(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象增加少量Ｐ快（P感补正）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if activity.dead(target_data.cid):
        return
    status.setdefault(target_data.cid, 3, 0)
    now_lust_multiple = 30
    now_add_lust: float = add_time + now_lust_multiple
    adjust = handle_ability.get_ability_adjust(
        abilities.ability(target_data.cid)[3]
    )
    now_add_lust *= adjust
    h_meters.add(target_data.cid, "eja", num.exact(now_add_lust))
    action_info.set(target_data.cid, "last_eaj_add_time", now_time)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_ADD_SMALL_V_FEEL
)
def handle_target_add_small_v_feel(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象增加少量Ｖ快（V感补正）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    base_chara_state_common_settle(
        activity.target(character_id),
        add_time,
        4,
        50,
        change_data_to_target_change=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_ADD_SMALL_A_FEEL
)
def handle_target_add_small_a_feel(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象增加少量Ａ快（A感补正）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    base_chara_state_common_settle(
        activity.target(character_id),
        add_time,
        5,
        50,
        change_data_to_target_change=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_ADD_SMALL_U_FEEL
)
def handle_target_add_small_u_feel(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象增加少量Ｕ快（U感补正）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    base_chara_state_common_settle(
        activity.target(character_id),
        add_time,
        6,
        50,
        change_data_to_target_change=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_ADD_SMALL_W_FEEL
)
def handle_target_add_small_w_feel(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象增加少量Ｗ快（W感补正）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    base_chara_state_common_settle(
        activity.target(character_id),
        add_time,
        7,
        50,
        change_data_to_target_change=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_ADD_SMALL_LUBRICATION
)
def handle_target_add_small_lubrication(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象增加少量润滑（欲望补正）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    base_chara_state_common_settle(
        activity.target(character_id),
        add_time,
        8,
        ability_level=abilities.ability(target_data.cid)[33],
        change_data_to_target_change=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_ADD_SMALL_LEARN
)
def handle_target_add_small_learn(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象增加少量习得（技巧补正）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    base_chara_state_common_settle(
        activity.target(character_id),
        add_time,
        9,
        ability_level=abilities.ability(target_data.cid)[30],
        change_data_to_target_change=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_ADD_SMALL_RESPECT
)
def handle_target_add_small_repect(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象增加少量恭顺（顺从补正）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if character_id != 0 and activity.target(character_id) != 0:
        return
    base_chara_state_common_settle(
        activity.target(character_id),
        add_time,
        10,
        ability_level=abilities.ability(target_data.cid)[31],
        change_data_to_target_change=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_ADD_SMALL_FRIENDLY
)
def handle_target_add_small_friendly(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象增加少量好意（亲密补正）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if character_id != 0 and activity.target(character_id) != 0:
        return
    base_chara_state_common_settle(
        activity.target(character_id),
        add_time,
        11,
        ability_level=abilities.ability(target_data.cid)[32],
        change_data_to_target_change=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_ADD_SMALL_DESIRE
)
def handle_target_add_small_desire(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象增加少量欲情（欲望补正）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if character_id != 0 and activity.target(character_id) != 0:
        return
    base_chara_state_common_settle(
        activity.target(character_id),
        add_time,
        12,
        ability_level=abilities.ability(target_data.cid)[33],
        change_data_to_target_change=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_ADD_SMALL_HAPPY
)
def handle_target_add_small_happy(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象增加少量快乐（快乐刻印补正）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if character_id != 0 and activity.target(character_id) != 0:
        return
    base_chara_state_common_settle(
        activity.target(character_id),
        add_time,
        13,
        ability_level=abilities.ability(target_data.cid)[13],
        change_data_to_target_change=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_ADD_SMALL_LEAD
)
def handle_target_add_small_lead(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象增加少量先导（施虐补正）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if character_id != 0 and activity.target(character_id) != 0:
        return
    base_chara_state_common_settle(
        activity.target(character_id),
        add_time,
        14,
        ability_level=abilities.ability(target_data.cid)[35],
        change_data_to_target_change=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_ADD_SMALL_SUBMIT
)
def handle_target_add_small_submit(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象增加少量屈服（屈服刻印补正）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if character_id != 0 and activity.target(character_id) != 0:
        return
    base_chara_state_common_settle(
        activity.target(character_id),
        add_time,
        15,
        ability_level=abilities.ability(target_data.cid)[14],
        change_data_to_target_change=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_ADD_SMALL_SHY
)
def handle_target_add_small_shy(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象增加少量羞耻（露出补正）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if character_id != 0 and activity.target(character_id) != 0:
        return
    base_chara_state_common_settle(
        activity.target(character_id),
        add_time,
        16,
        ability_level=abilities.ability(target_data.cid)[34],
        change_data_to_target_change=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_ADD_SMALL_PAIN
)
def handle_target_add_small_pain(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象增加少量苦痛（苦痛刻印补正）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if character_id != 0 and activity.target(character_id) != 0:
        return
    base_chara_state_common_settle(
        activity.target(character_id),
        add_time,
        17,
        ability_level=abilities.ability(target_data.cid)[15],
        change_data_to_target_change=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_ADD_SMALL_TERROR
)
def handle_target_add_small_terror(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象增加少量恐怖（恐怖刻印补正）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if character_id != 0 and activity.target(character_id) != 0:
        return
    base_chara_state_common_settle(
        activity.target(character_id),
        add_time,
        18,
        10,
        ability_level=abilities.ability(target_data.cid)[17],
        change_data_to_target_change=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_ADD_SMALL_DEPRESSION
)
def handle_target_add_small_depression(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象增加少量抑郁
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if character_id != 0 and activity.target(character_id) != 0:
        return
    base_chara_state_common_settle(
        activity.target(character_id),
        add_time,
        19,
        change_data_to_target_change=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_ADD_SMALL_DISGUST
)
def handle_target_add_small_disgust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象增加少量反感（反发刻印补正）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if character_id != 0 and activity.target(character_id) != 0:
        return
    base_chara_state_common_settle(
        activity.target(character_id),
        add_time,
        20,
        5,
        ability_level=abilities.ability(target_data.cid)[18],
        change_data_to_target_change=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ADD_SMALL_P_FEEL
)
def handle_add_small_p_feel(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身增加少量Ｐ快
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.dead(character_id):
        return
    now_lust_multiple = 10
    now_add_lust = (
        add_time + now_lust_multiple + h_meters.of(character_id)["eja"] * 0.4
    )
    now_add_lust = int(now_add_lust)
    h_meters.add(character_id, "eja", now_add_lust)
    change_data.eja_point += now_add_lust
    action_info.set(character_id, "last_eaj_add_time", now_time)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.BOTH_ADD_SMALL_LEARN
)
def handle_both_add_small_learn(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    双方增加少量习得（若没有交互对象则仅增加自己）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.dead(character_id):
        return
    base_chara_state_common_settle(
        character_id, add_time, 9, 10, change_data=change_data
    )
    # 交互对象也同样#
    if activity.target(character_id) != character_id:
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            9,
            10,
            change_data_to_target_change=change_data,
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ADD_SMALL_LEARN_OLD
)
def handle_add_small_learn_old(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己增加少量习得
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    handle_add_small_learn(character_id, add_time, change_data, now_time)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ADD_SMALL_LUBRICATION
)
def handle_add_small_lubrication(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己增加少量润滑（欲望补正）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.dead(character_id):
        return
    base_chara_state_common_settle(
        character_id,
        add_time,
        8,
        ability_level=abilities.ability(character_id)[33],
        change_data=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ADD_SMALL_LEARN
)
def handle_add_small_learn(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己增加少量习得（技巧补正）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.dead(character_id):
        return
    base_chara_state_common_settle(
        character_id,
        add_time,
        9,
        ability_level=abilities.ability(character_id)[30],
        change_data=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ADD_SMALL_RESPECT
)
def handle_add_small_respect(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己增加少量恭顺（顺从补正）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.dead(character_id):
        return
    base_chara_state_common_settle(
        character_id,
        add_time,
        10,
        ability_level=abilities.ability(character_id)[31],
        change_data=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ADD_SMALL_FRIENDLY
)
def handle_add_small_friendly(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己增加少量好意（亲密补正）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.dead(character_id):
        return
    base_chara_state_common_settle(
        character_id,
        add_time,
        11,
        ability_level=abilities.ability(character_id)[32],
        change_data=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ADD_SMALL_DESIRE
)
def handle_add_small_desire(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己增加少量欲情（欲望补正）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.dead(character_id):
        return
    base_chara_state_common_settle(
        character_id,
        add_time,
        12,
        ability_level=abilities.ability(character_id)[33],
        change_data=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ADD_SMALL_HAPPY
)
def handle_add_small_happy(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己增加少量快乐（快乐刻印补正）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.dead(character_id):
        return
    base_chara_state_common_settle(
        character_id,
        add_time,
        13,
        ability_level=abilities.ability(character_id)[13],
        change_data=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ADD_SMALL_LEAD
)
def handle_add_small_lead(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己增加少量先导（施虐补正）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.dead(character_id):
        return
    base_chara_state_common_settle(
        character_id,
        add_time,
        14,
        ability_level=abilities.ability(character_id)[35],
        change_data=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ADD_SMALL_SUBMIT
)
def handle_add_small_submit(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己增加少量屈服（屈服刻印补正）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.dead(character_id):
        return
    base_chara_state_common_settle(
        character_id,
        add_time,
        15,
        ability_level=abilities.ability(character_id)[14],
        change_data=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ADD_SMALL_SHY
)
def handle_add_small_shy(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己增加少量羞耻（露出补正）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.dead(character_id):
        return
    base_chara_state_common_settle(
        character_id,
        add_time,
        16,
        ability_level=abilities.ability(character_id)[34],
        change_data=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SELF_ADD_MIDDLE_DISGUST
)
def handle_self_add_middle_disgust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己增加中量反感（反发刻印补正）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    base_chara_state_common_settle(
        character_id,
        add_time,
        20,
        100,
        ability_level=abilities.ability(character_id)[18],
        change_data=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DIRTY_RESET
)
def handle_dirty_reset(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    污浊情况(身体+衣服)归零
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    dirty.reset(character_id)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ASSISTANT_RESET
)
def handle_assistant_reset(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    助理数据归零
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    relations.assistant_services.set(
        character_id, attr_calculation.get_assistant_services_zero()
    )
    if relations.assistant_character_id(0) == character_id:
        relations.assistant_character_id.set(0, 0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DOOR_CLOSE
)
def handle_door_close(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    当前场景进入关门状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    now_position = activity.position(character_id)
    now_position_str = map_handle.get_map_system_path_str_for_list(now_position)
    now_scene_data = cache.scene_data[now_position_str]
    now_scene_data.close_flag = now_scene_data.close_type


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DOOR_CLOSE_RESET
)
def handle_door_close_reset(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    当前场景取消关门状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    now_position = activity.position(character_id)
    now_position_str = map_handle.get_map_system_path_str_for_list(now_position)
    now_scene_data = cache.scene_data[now_position_str]
    now_scene_data.close_flag = 0


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.MOVE_TO_PRE_SCENE
)
def handle_move_to_pre_scene(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    角色移动至前一场景
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.dead(character_id):
        return
    # 如果前一场景的移动数据与当前场景相同，则删除掉前一场景的移动数据
    past_moves = action_info.get(character_id, "past_move_position_list")
    while past_moves and past_moves[-1] == activity.position(character_id):
        past_moves.pop(-1)
    action_info.set(character_id, "past_move_position_list", past_moves)
    # 然后再判断是否还有前一场景的移动数据，如果有则移动至前一场景
    if past_moves:
        activity.update_behavior(character_id, move_target=past_moves[-1])
        handle_move_to_target_scene(
            character_id, add_time, change_data, now_time
        )
        # 删除掉前一场景的移动数据
        action_info.pop_past_move(character_id, -1)
    # 博士被赶回前一场景后，原寻路目标已不可达，取消本次连续寻路以避免再次进入并触发循环。
    if character_id == 0:
        activity.update_behavior(character_id, move_final_target=[])


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_MOVE_TO_PRE_SCENE
)
def handle_target_move_to_pre_scene(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象移动至前一场景
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    handle_move_to_pre_scene(
        activity.target(character_id), add_time, change_data, now_time
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SCENE_OTHERS_MOVE_TO_PRE_SCENE
)
def handle_scene_others_move_to_pre_scene(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    场景内除自己和交互对象以外的其他角色移动至前一场景
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    scene_path_str = map_handle.get_map_system_path_str_for_list(
        activity.position(character_id)
    )
    scene_data: game_type.Scene = cache.scene_data[scene_path_str]
    # 遍历场景内所有角色
    for chara_id in scene_data.character_list.copy():
        # 跳过自己和交互对象
        if chara_id == character_id or chara_id == activity.target(
            character_id
        ):
            continue
        handle_move_to_pre_scene(chara_id, add_time, change_data, now_time)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SCENE_ALL_CHARA_MOVE_TO_PRE_SCENE
)
def handle_scene_all_chara_move_to_pre_scene(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    场景除自己以外的全部角色移动至前一场景
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    scene_path_str = map_handle.get_map_system_path_str_for_list(
        activity.position(character_id)
    )
    scene_data: game_type.Scene = cache.scene_data[scene_path_str]
    # 遍历场景内所有角色
    for chara_id in scene_data.character_list.copy():
        # 跳过自己
        if chara_id == character_id:
            continue
        handle_move_to_pre_scene(chara_id, add_time, change_data, now_time)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SCENE_ALL_CHARA_EXCEPT_MASTUREBATE_TO_PL_MOVE_TO_PRE_SCENE
)
def handle_scene_all_chara_except_masturebate_to_pl_move_to_pre_scene(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    场景内不逆推自己的角色移动至前一场景
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    scene_path_str = map_handle.get_map_system_path_str_for_list(
        activity.position(character_id)
    )
    scene_data: game_type.Scene = cache.scene_data[scene_path_str]
    # 遍历场景内所有角色
    for chara_id in scene_data.character_list.copy():
        # 跳过玩家
        if chara_id == 0:
            continue
        # 跳过逆推自己的角色
        if handle_premise.handle_masturebate_to_pl_flag_1(chara_id):
            continue
        handle_move_to_pre_scene(chara_id, add_time, change_data, now_time)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SELF_H_STATE_RESET
)
def handle_self_h_state_reset(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己H状态结构体归零，同步高潮程度记录，清零H相关二段状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    from Script.System.Sex_System import group_sex_panel

    # H状态数据归零
    h_state.reset(character_id)
    # 清零阴茎污浊
    with dirty.editing(character_id) as d:
        d.penis_dirty_dict["semen"] = False
    # 清零阴茎位置
    h_state.set(character_id, insert_position=-1)
    # 清零自慰状态
    flags.set(character_id, masturebate=0)
    flags.set(character_id, npc_masturebate_for_player=False)
    # 清零前往群交
    flags.set(character_id, go_to_join_group_sex=False)
    # 清零自己在群交模板中的数据
    group_sex_panel.clear_character_data_in_group_sex_template(character_id)
    # 清零隐奸模式
    flags.set(character_id, hidden_sex_mode=0)
    # 清零露出模式
    flags.set(character_id, exhibitionism_sex_mode=0)
    # 清零玩具档位
    flags.set(character_id, sex_toy_level=0)
    # 记录高潮进度
    with h_state.editing(character_id) as hs:
        for state_id in game_config.config_character_state:
            if game_config.config_character_state[state_id].type == 0:
                hs.orgasm_level[state_id] = attr_calculation.get_status_level(
                    num.whole(status.of(character_id)[state_id])
                )
    # 清零H相关二段状态
    for second_behavior_id in activity.second_behaviors(character_id):
        behavior_data = game_config.config_behavior[second_behavior_id]
        if "H装备" in behavior_data.tag or "侍奉" in behavior_data.tag:
            second_behavior.character_get_second_behavior(
                character_id, second_behavior_id, reset=True
            )
    # 囚犯干员回到自己监牢
    if handle_premise.handle_imprisonment_1(
        character_id
    ) and handle_premise.handle_not_in_dormitory(character_id):
        dormitory_list = map_handle.get_map_system_path_for_str(
            chara_life.dormitory(character_id)
        )
        map_handle.character_move_scene(
            activity.position(character_id), dormitory_list, character_id
        )
    # 退出H模式
    flags.set(character_id, is_h=False)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.BOTH_H_STATE_RESET
)
def handle_both_h_state_reset(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    双方H状态结构体归零，同步高潮程度记录，清零H相关二段状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    handle_self_h_state_reset(character_id, add_time, change_data, now_time)
    handle_self_h_state_reset(
        activity.target(character_id), add_time, change_data, now_time
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.UPDATE_ORGASM_LEVEL
)
def handle_update_orgasm_level(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    双方同步高潮程度记录
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    with h_state.editing(character_id) as hs, h_state.editing(
        target_data.cid
    ) as ths:
        for state_id in game_config.config_character_state:
            if game_config.config_character_state[state_id].type == 0:
                hs.orgasm_level[state_id] = attr_calculation.get_status_level(
                    num.whole(status.of(character_id)[state_id])
                )
                ths.orgasm_level[state_id] = attr_calculation.get_status_level(
                    num.whole(status.of(target_data.cid)[state_id])
                )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SCENE_ALL_CHARACTERS_UPDATE_ORGASM_LEVEL
)
def handle_scene_all_characters_update_orgasm_level(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    场景内所有角色同步高潮程度记录
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    scene_path_str = map_handle.get_map_system_path_str_for_list(
        activity.position(character_id)
    )
    scene_data: game_type.Scene = cache.scene_data[scene_path_str]
    for chara_id in scene_data.character_list:
        with h_state.editing(chara_id) as hs:
            for state_id in game_config.config_character_state:
                if game_config.config_character_state[state_id].type == 0:
                    hs.orgasm_level[state_id] = (
                        attr_calculation.get_status_level(
                            num.whole(status.of(chara_id)[state_id])
                        )
                    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SCENE_ALL_CHARACTERS_H_STATE_RESET
)
def handle_scene_all_characters_h_state_reset(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    场景内所有角色H状态结构体归零，同步高潮程度记录，清零H相关二段状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    scene_path_str = map_handle.get_map_system_path_str_for_list(
        activity.position(character_id)
    )
    scene_data: game_type.Scene = cache.scene_data[scene_path_str]
    for chara_id in scene_data.character_list.copy():
        handle_self_h_state_reset(chara_id, add_time, change_data, now_time)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ALL_CHARACTERS_UNCONSCIOUS_SEMEN_RESET
)
def handle_all_character_unconscious_semen_reset(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    清零所有角色的无意识精液情况
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    for chara_id in identity.table():
        with dirty.editing(chara_id) as d:
            d.body_semen_in_unconscious = []
            d.cloth_semen_in_unconscious = []


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.CHARA_OFF_LINE
)
def handle_chara_off_line(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    角色离线，归零若干数据结构体，从当前干员列表中移除，离开地图
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    activity.set_behavior(character_id)  # 行动数据归零
    activity.set_event(character_id)  # 事件数据归零
    handle_assistant_reset(
        character_id, add_time, change_data, now_time
    )  # 助理数据归零
    handle_dirty_reset(
        character_id, add_time, change_data, now_time
    )  # 污浊情况归零
    h_state.reset(character_id)  # H状态数据归零
    # 归零快感状态
    for state_id in game_config.config_character_state:
        if game_config.config_character_state[state_id].type == 0:
            status.set(character_id, state_id, 0)
    # 清零跟随数据
    flags.set(character_id, is_follow=0)
    # 从当前干员列表中移除
    if roster.has(character_id):
        roster.remove(character_id)
    # 离开地图
    old_scene_path_str = map_handle.get_map_system_path_str_for_list(
        activity.position(character_id)
    )
    if character_id in cache.scene_data[old_scene_path_str].character_list:
        cache.scene_data[old_scene_path_str].character_list.remove(character_id)
    activity.set_position(character_id, ["0", "0"])


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.CHARA_ON_LINE
)
def handle_chara_on_line(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    角色上线，加入当前干员列表，进入地图
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    # 基础属性重置
    needs.set(character_id, hit=needs.of(character_id)["hit_max"])
    needs.set(character_id, mana=needs.of(character_id)["mana_max"])
    needs.set(character_id, hunger=0, tired=0, urine=0, sleep=0)
    # 清零各特殊状态flag
    old_imprisonment = flags.get(character_id, "imprisonment")
    # 外交访问状态需要跨上线保留，否则外交官随罗德岛抵达驻在国回岛后会丢失驻在国信息
    old_in_diplomatic_visit = flags.get(character_id, "in_diplomatic_visit")
    flags.reset(character_id)
    flags.set(character_id, in_diplomatic_visit=old_in_diplomatic_visit)
    if old_imprisonment:
        flags.set(character_id, imprisonment=True)
    # 赋予默认行动数据：与内核加入角色时给的空闲一致，此刻开始、0分钟；已在内核里的角色当前的行动被打断
    from Script.Modules.gameplay_resolution import plan_queue

    activity.set_target(character_id, character_id)
    activity.update_behavior(
        character_id,
        behavior_id=constant.Behavior.SHARE_BLANKLY,
        start_time=now_time,
        duration=0,
    )
    activity.set_state(character_id, constant.CharacterStatus.STATUS_ARDER)
    plan_queue.interrupt(character_id)
    # 加入当前干员列表
    if not roster.has(character_id):
        roster.add(character_id)
    # 进入地图
    now_scene_path_str = map_handle.get_map_system_path_str_for_list(
        activity.position(character_id)
    )
    if character_id not in cache.scene_data[now_scene_path_str].character_list:
        cache.scene_data[now_scene_path_str].character_list.add(character_id)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.T_BE_BAGGED
)
def handle_t_be_bagged(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象变成被装袋搬走状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    flags.set(target_data.cid, be_bagged=True)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.T_BE_IMPRISONMENT
)
def handle_t_be_imprisonment(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象变成被监禁状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    flags.set(target_data.cid, imprisonment=True)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SHOWER_FLAG_TO_1
)
def handle_shower_flag_to_1(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身变成要脱衣服（洗澡）状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, shower=1)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PLACE_ALL_CHARA_ADD_1_BEEN_Hypnosis_EXPERIENCE
)
def handle_place_all_chara_add_1_been_hypnosis_experience(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    场景内所有其他角色均增加1被催眠经验
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.dead(character_id):
        return
    # 获取当前场景的全角色名单
    scene_path_str = map_handle.get_map_system_path_str_for_list(
        activity.position(character_id)
    )
    scene_data: game_type.Scene = cache.scene_data[scene_path_str]
    scene_character_list = scene_data.character_list.copy()
    # 去掉里的自己
    if character_id in scene_character_list:
        scene_character_list.remove(character_id)
    for target_id in scene_character_list:
        base_chara_experience_common_settle(
            target_id, 123, change_data_to_target_change=change_data
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SHOWER_FLAG_TO_0
)
def handle_shower_flag_to_0(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身清零洗澡状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, shower=0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SHOWER_FLAG_TO_2
)
def handle_shower_flag_to_2(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身变成要洗澡状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, shower=2)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SHOWER_FLAG_TO_3
)
def handle_shower_flag_to_3(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身变成要披浴巾状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, shower=3)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SHOWER_FLAG_TO_4
)
def handle_shower_flag_to_4(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身变成洗完澡状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, shower=4)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.EAT_FOOD_FLAG_TO_0
)
def handle_eat_food_flag_to_0(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange | game_type.TargetChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身清零吃饭状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, eat_food=0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.EAT_FOOD_FLAG_TO_1
)
def handle_eat_food_flag_to_1(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身变成要取餐状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, eat_food=1)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.EAT_FOOD_FLAG_TO_2
)
def handle_eat_food_flag_to_2(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身变成要进食状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, eat_food=2)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SLEEP_FLAG_TO_0
)
def handle_sleep_flag_to_0(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身清零要睡眠状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, sleep=False)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SLEEP_FLAG_TO_1
)
def handle_sleep_flag_to_1(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身变成要睡眠状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, sleep=True)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.REST_FLAG_TO_0
)
def handle_rest_flag_to_0(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身清零要休息状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, rest=False)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.REST_FLAG_TO_1
)
def handle_rest_flag_to_1(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身变成要休息状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, rest=True)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PEE_FLAG_TO_0
)
def handle_pee_flag_to_0(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身清零要撒尿状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, pee=False)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PEE_FLAG_TO_1
)
def handle_pee_flag_to_1(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身变成要撒尿状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, pee=True)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SWIM_FLAG_TO_1
)
def handle_swim_flag_to_1(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身变成要换泳衣状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, swim=1)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SWIM_FLAG_TO_2
)
def handle_swim_flag_to_2(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身变成要游泳状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, swim=2)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.MAINTENANCE_FLAG_TO_0
)
def handle_maintenance_flag_to_0(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身清零要检修状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, work_maintenance=False)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.MORNING_SALUTATION_FLAG_TO_0
)
def handle_morning_salutation_flag_to_0(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    将自身早安问候设为未问候
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, morning_salutation=0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DORMITORY_ADMIN_PHASE_TO_0
)
def handle_dormitory_admin_phase_to_0(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身宿舍管理员阶段设为0（到岗整理）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    chara_life.dormitory_admin_phase.set(character_id, 0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DORMITORY_ADMIN_PHASE_TO_1
)
def handle_dormitory_admin_phase_to_1(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身宿舍管理员阶段设为1（移动处理）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    chara_life.dormitory_admin_phase.set(character_id, 1)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.CANCEL_ALL_WORK_AND_ENTERTAINMENT_FLAG
)
def handle_cancel_all_work_and_entertainment_flag(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身取消所有工作和娱乐状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, swim=0)
    flags.set(character_id, bathhouse_entertainment=0)
    flags.set(character_id, work_maintenance=False)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SELF_INTELLIGENT_FOLLOW_ON
)
def handle_self_intelligent_follow_on(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身进入智能跟随状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, is_follow=1)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_INTELLIGENT_FOLLOW_ON
)
def handle_target_intelligent_follow_on(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象进入智能跟随状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    handle_self_intelligent_follow_on(
        activity.target(character_id), add_time, change_data, now_time
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SELF_INTELLIGENT_FOLLOW_OFF
)
def handle_self_intelligent_follow_off(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身退出智能跟随状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, is_follow=0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_INTELLIGENT_FOLLOW_OFF
)
def handle_target_intelligent_follow_off(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象退出智能跟随状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    handle_self_intelligent_follow_off(
        activity.target(character_id), add_time, change_data, now_time
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SELF_INTELLIGENT_FOLLOW_ON_IF_ASSISTANT
)
def handle_self_intelligent_follow_on_if_assistant(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    如果自己是助理且打开了跟随服务，则自己进入智能跟随状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if handle_premise.handle_is_assistant(
        character_id
    ) and handle_premise.handle_assistant_follow_1(character_id):
        handle_self_intelligent_follow_on(
            character_id, add_time, change_data, now_time
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SELF_STOP_MOVE
)
def handle_self_stop_move(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己停止移动
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, move_stop=True)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.H_FLAG_TO_0
)
def handle_h_flag_to_0(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身清零H状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, is_h=False)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.H_FLAG_TO_1
)
def handle_h_flag_to_1(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身变成H状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    # 只在从非H状态首次进入H时撤销旧移动计划；H状态中本effect仍会被反复结算，
    # 此时is_h已为真而跳过，避免误删进入H后角色新下达的移动指令
    if not flags.get(character_id, "is_h"):
        character_move.cancel_movement_plan(character_id)
    flags.set(character_id, is_h=True)
    # 进入H即视为已目击本场H：即使之后合法离场(如力竭)清了is_h，回场也不会被当作新旁观者而重复触发"H中被发现"面板
    flags.set(character_id, see_pl_h=True)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.T_H_FLAG_TO_0
)
def handle_t_h_flag_to_0(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象清零H状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    handle_h_flag_to_0(
        activity.target(character_id), add_time, change_data, now_time
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.T_H_FLAG_TO_1
)
def handle_t_h_flag_to_1(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象变成H状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    handle_h_flag_to_1(
        activity.target(character_id), add_time, change_data, now_time
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SCENE_ALL_CHARACTERS_H_FLAG_TO_1
)
def handle_scene_all_characters_h_flag_to_1(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    场景内所有角色变成H状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    scene_path_str = map_handle.get_map_system_path_str_for_list(
        activity.position(character_id)
    )
    scene_data: game_type.Scene = cache.scene_data[scene_path_str]
    for chara_id in scene_data.character_list:
        if chara_id == 0:
            continue
        handle_h_flag_to_1(chara_id, add_time, change_data, now_time)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SELF_HIDDEN_SEX_FLAG_TO_0
)
def handle_self_hidden_sex_flag_to_0(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己清零隐奸状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, hidden_sex_mode=0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_HIDDEN_SEX_FLAG_TO_0
)
def handle_target_hidden_sex_flag_to_0(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象清零隐奸状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    handle_self_hidden_sex_flag_to_0(
        activity.target(character_id), add_time, change_data, now_time
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.BOTH_HIDDEN_SEX_FLAG_TO_0
)
def handle_both_hidden_sex_flag_to_0(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    双方清零隐奸状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    handle_self_hidden_sex_flag_to_0(
        character_id, add_time, change_data, now_time
    )
    handle_self_hidden_sex_flag_to_0(
        activity.target(character_id), add_time, change_data, now_time
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SELF_EXHIBITIONISM_SEX_FLAG_TO_0
)
def handle_self_exhibitionism_sex_flag_to_0(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己清零露出H状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, exhibitionism_sex_mode=0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_EXHIBITIONISM_SEX_FLAG_TO_0
)
def handle_target_exhibitionism_sex_flag_to_0(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象清零露出H状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    handle_self_exhibitionism_sex_flag_to_0(
        activity.target(character_id), add_time, change_data, now_time
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.BOTH_EXHIBITIONISM_SEX_FLAG_TO_0
)
def handle_both_exhibitionism_sex_flag_to_0(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    双方清零露出H状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    handle_self_exhibitionism_sex_flag_to_0(
        character_id, add_time, change_data, now_time
    )
    handle_self_exhibitionism_sex_flag_to_0(
        activity.target(character_id), add_time, change_data, now_time
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.UNCONSCIOUS_FLAG_TO_0
)
def handle_unconscious_flag_to_0(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身清零无意识状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, unconscious_h=0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.UNCONSCIOUS_FLAG_TO_1
)
def handle_unconscious_flag_to_1(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身变成无意识_睡眠状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, unconscious_h=1)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.UNCONSCIOUS_FLAG_TO_2
)
def handle_unconscious_flag_to_2(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身变成无意识_醉酒状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, unconscious_h=2)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.UNCONSCIOUS_FLAG_TO_3
)
def handle_unconscious_flag_to_3(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身变成无意识_时停状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, unconscious_h=3)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.UNCONSCIOUS_FLAG_TO_4
)
def handle_unconscious_flag_to_4(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身变成无意识_平然状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, unconscious_h=4)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.UNCONSCIOUS_FLAG_TO_5
)
def handle_unconscious_flag_to_5(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身变成无意识_空气状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, unconscious_h=5)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.UNCONSCIOUS_FLAG_TO_6
)
def handle_unconscious_flag_to_6(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身变成无意识_心控状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, unconscious_h=6)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.UNCONSCIOUS_FLAG_TO_7
)
def handle_unconscious_flag_to_7(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身变成无意识_体控状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, unconscious_h=7)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.HELP_BUY_FOOD_FLAG_TO_0
)
def handle_help_buy_food_flag_to_0(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身清零要帮忙买午饭状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, help_buy_food=0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.BATHHOUSE_ENTERTAINMENT_FLAG_TO_0
)
def handle_bathhouse_entertainment_flag_to_0(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身清零大浴场娱乐状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, bathhouse_entertainment=0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.BATHHOUSE_ENTERTAINMENT_FLAG_TO_1
)
def handle_bathhouse_entertainment_flag_to_1(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身变成大浴场娱乐_要更衣状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, bathhouse_entertainment=1)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.BATHHOUSE_ENTERTAINMENT_FLAG_TO_2
)
def handle_bathhouse_entertainment_flag_to_2(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身变成大浴场娱乐_要娱乐状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, bathhouse_entertainment=2)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.MILK_FLAG_TO_0
)
def handle_milk_flag_to_0(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身清零要挤奶状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, milk=False)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.HYPNOSIS_FLAG_TO_0
)
def handle_hypnosis_flag_to_0(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身清零催眠系的flag与催眠子项
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if flags.get(character_id, "unconscious_h") in [4, 5, 6, 7]:
        flags.set(character_id, unconscious_h=0)
    hypnosis_state.clear_hypnosis_sub_states(character_id)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_ANGRY_WITH_PLAYER_FLAG_TO_0
)
def handle_target_angry_with_player_flag_to_0(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象清零对玩家的愤怒状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_character = identity.of(activity.target(character_id))
    flags.set(target_character.cid, angry_with_player=False)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SEE_PL_H
)
def handle_see_pl_h(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身进入目击H状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, see_pl_h=True)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.CANCEL_SEE_PL_H
)
def handle_cancel_see_pl_h(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身退出目击H状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, see_pl_h=False)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.MASTUREBATE_FLAG_TO_0
)
def handle_masturebate_flag_to_0(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身清零要自慰状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, masturebate=0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.MASTUREBATE_BEFORE_SLEEP_FLAG_TO_0
)
def handle_masturebate_before_flag_to_0(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身清零要睡前自慰状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, masturebate_before_sleep=0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.MASTUREBATE_BEFORE_SLEEP_FLAG_TO_2
)
def handle_masturebate_before_flag_to_2(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身变为已睡前自慰状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, masturebate_before_sleep=2)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.MASTUREBATE_TO_PL_FLAG_0
)
def handle_masturebate_to_pl_flag_0(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身清零要找玩家逆推来自慰状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, npc_masturebate_for_player=False)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ALL_CHARA_MASTUREBATE_IN_GROUP_SEX_FLAG_0
)
def handle_all_chara_masturebate_in_group_sex_flag_0(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    全角色清零群交中自慰状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息
    now_time -- 结算的时间
    """
    if not add_time:
        return
    for chara_id in roster.active():
        character_data: identity.Identity = identity.of(chara_id)
        if handle_premise.handle_masturebate_flag_3(chara_id):
            flags.set(character_data.cid, masturebate=0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.HELP_MAKE_FOOD_FLAG_TO_0
)
def handle_help_make_food_flag_to_0(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身清零做午饭状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    flags.set(character_id, help_make_food=0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TALK_ADD_ADJUST
)
def handle_talk_add_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （聊天用）根据发起者的话术技能进行双方的好感度、好意、快乐调整，并记录当前谈话时间
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    ability = abilities.ability(character_id)
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if character_id != 0 and activity.target(character_id) != 0:
            return
        # 获取调整值#
        ability.setdefault(40, 0)
        adjust = handle_ability.get_ability_adjust(ability[40])
        # 好感度变化#
        base_chara_favorability_and_trust_common_settle(
            character_id, add_time, True, 0, adjust, change_data
        )
        # 好意变化#
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            11,
            ability_level=ability[40],
            change_data_to_target_change=change_data,
        )
        # 快乐变化#
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            13,
            ability_level=ability[40],
            change_data_to_target_change=change_data,
        )
        # 记录谈话时间#
        action_info.set(target_data.cid, "talk_time", now_time)
        # print("聊天计数器时间变为 ：",target_data.action_info.talk_time)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.COFFEE_ADD_ADJUST
)
def handle_coffee_add_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （泡咖啡用）根据发起者的料理技能进行好感度、信赖、好意调整
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    ability = abilities.ability(character_id)
    if not add_time:
        return
    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if character_id != 0 and activity.target(character_id) != 0:
            return
        # 获取调整值#
        ability.setdefault(43, 0)
        adjust = handle_ability.get_ability_adjust(ability[43])
        # 好感度变化#
        base_chara_favorability_and_trust_common_settle(
            character_id, add_time, True, 0, adjust, change_data
        )
        # 信赖变化#
        base_chara_favorability_and_trust_common_settle(
            character_id, add_time, False, 0, adjust, change_data
        )
        # 好意变化#
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            11,
            ability_level=ability[43],
            change_data_to_target_change=change_data,
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_COFFEE_ADD_ADJUST
)
def handle_target_coffee_add_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （泡咖啡用）根据交互对象的料理技能进行好感度、信赖、好意调整
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    ability = abilities.ability(target_data.cid)
    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if character_id != 0 and activity.target(character_id) != 0:
            return
        # 获取调整值#
        ability.setdefault(43, 0)
        adjust = handle_ability.get_ability_adjust(ability[43])
        # 好感度变化#
        base_chara_favorability_and_trust_common_settle(
            character_id, add_time, True, 0, adjust, change_data
        )
        # 信赖变化#
        base_chara_favorability_and_trust_common_settle(
            character_id, add_time, False, 0, adjust, change_data
        )
        # 好意变化#
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            11,
            ability_level=ability[43],
            change_data_to_target_change=change_data,
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.MAKE_FOOD_ADD_ADJUST
)
def handle_make_food_add_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （制作食物用）根据当前行为中的菜谱难度等级，动态获得料理经验与习得。
    收益仅按单份结算，不随制作数量变化。
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    ability = abilities.ability(character_id)
    if not add_time:
        return
    if activity.dead(character_id):
        return
    # 读取当前行为中的菜谱难度等级（最低为1）
    cook_difficulty = 1
    now_food = activity.behavior(character_id).target_food
    if now_food is not None and now_food.recipe in game_config.config_recipes:
        cook_difficulty = max(
            1, game_config.config_recipes[now_food.recipe].difficulty
        )
    # 料理经验：随菜谱难度等级提升而增加（难度即为基础获得值）
    base_chara_experience_common_settle(
        character_id, 83, base_value=cook_difficulty, change_data=change_data
    )
    # 习得：随菜谱难度等级提升而增加（独立于制作数量与总耗时，仅按单份结算）
    ability.setdefault(30, 0)
    base_chara_state_common_settle(
        character_id,
        cook_difficulty,
        9,
        base_value=cook_difficulty * 10,
        ability_level=ability[30],
        change_data=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TASTE_WINE_ADD_ADJUST
)
def handle_taste_wine_add_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （品酒用）根据酒量随机选一个酒，并结算部分饮用效果
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    from Script.System.Sex_System.drunk_sex_common import taste_wine

    if not add_time:
        return
    if activity.dead(character_id):
        return
    # 根据酒量随机选一个酒，并结算部分饮用效果
    taste_wine(character_id)
    # 删除该食物
    handle_delete_food(
        character_id,
        add_time=add_time,
        change_data=change_data,
        now_time=now_time,
    )
    # 增加饮酒经验
    base_chara_experience_common_settle(
        character_id, 94, change_data=change_data
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.OFFICIAL_WORK_ADD_ADJUST
)
def handle_official_work_add_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （处理公务用）根据自己（如果有的话再加上交互对象）的学识以及办公室等级来处理当前的剩余工作量
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    from Script.Design import basement

    target_data: identity.Identity = identity.of(activity.target(character_id))

    if activity.dead(character_id):
        return
    if activity.dead(target_data.cid):
        return
    now_draw_text = ""
    # 获取调整值#
    adjust = handle_ability.get_ability_adjust(
        abilities.ability(character_id)[45]
    )
    # 如果有交互对象，且对方不在无意识状态下，则算上对方的学识加成
    if activity.target(
        character_id
    ) != character_id and handle_premise.handle_unconscious_flag_0(
        activity.target(character_id)
    ):
        adjust_target = handle_ability.get_ability_adjust(
            abilities.ability(target_data.cid)[45]
        )
        adjust += adjust_target
        now_draw_text += _("在{0}的帮助下，").format(target_data.name)
    # 设施加成
    adjust *= basement.calc_facility_efficiency(22)
    # 处理工作
    finish_work = int(add_time * adjust)
    official.set_office_work(int(max(official.office_work() - finish_work, 0)))
    # 输出处理结果
    if activity.position(character_id) == activity.position(0):
        now_draw = draw.NormalDraw()
        now_draw_text += _("共处理了{0}公务，").format(finish_work)
        if official.office_work() > 0:
            now_draw_text += _("还有{0}需要处理\n").format(
                official.office_work()
            )
        else:
            now_draw_text += _("已经全部处理完毕\n\n")
        now_draw.text = now_draw_text
        now_draw.width = width
        now_draw.draw()
    # 输出待办事项
    basement.draw_todo()
    # 结算成就
    achievement.add("handle_official_business_count", 1)
    achievement_panel.achievement_flow(_("公务"))


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.CURE_PATIENT_ADD_ADJUST
)
@medical.editing()
def handle_cure_patient_add_just(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （诊疗病人用）根据发起者(如果有的话再加上交互对象)的医疗技能治愈了一名病人，并获得一定的龙门币
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    ability = abilities.ability(character_id)
    if not add_time:
        return
    from Script.System.Medical_System import medical_constant, medical_service

    character_data: identity.Identity = identity.of(character_id)
    if activity.dead(character_id):
        return

    # 玩家自己根据诊疗病人列表单独处理
    if character_id == 0:
        # 遍历所有本次被诊疗的病人
        for patient_id in medical.state().examined_patient_ids:
            # 获取该病人的数据
            patient_obj = medical.state().today.get(patient_id)
            if patient_obj is None:
                patient_obj = medical.state().hospitalized.get(patient_id)
            if patient_obj is None:
                continue
            # 病人的病情等级
            severity_level = patient_obj.severity_level
            # 根据病情等级获取额外习得
            base_chara_state_common_settle(
                character_id,
                add_time,
                9,
                ability_level=ability[46],
                extra_adjust=(severity_level + 1) / 2,
                change_data=change_data,
            )
            # 病人的检查次数
            exam_count = patient_obj.player_used_checks
            # 根据检查次数计算医疗经验
            base_chara_experience_common_settle(
                character_id, 88, base_value=exam_count, change_data=change_data
            )
        # 清空本次被诊疗的病人列表
        medical.state().examined_patient_ids.clear()
        return

    before_income = medical.state().income_today

    # 如果已有病人则选取该病人
    patient_id = chara_life.medical_patient_id(character_id)
    patient_obj = None
    # 先从今日病人中寻找
    if patient_id:
        patient_obj = medical.state().today.get(patient_id)
        # 再从住院病人中寻找
        if patient_obj is None:
            patient_obj = medical.state().hospitalized.get(patient_id)

    # 否则获取一个新的病人
    if patient_obj is None:
        patient_obj = medical_service.acquire_patient_for_doctor(character_data)

    # 没有病人则直接返回
    if patient_obj is None:
        chara_life.medical_patient_id.set(character_id, 0)
        return

    # 病情等级
    severity_level = patient_obj.severity_level

    # 进行诊断
    medical_service.advance_diagnose(patient_obj.patient_id, character_data)
    income_delta = medical.state().income_today - before_income

    # 根据病情等级获取额外习得和医疗经验
    base_chara_state_common_settle(
        character_id,
        add_time,
        9,
        ability_level=ability[46],
        extra_adjust=(severity_level + 1) / 2,
        change_data=change_data,
    )
    base_chara_experience_common_settle(
        character_id, 88, base_value=severity_level, change_data=change_data
    )

    # 仅在玩家场景输出
    if activity.position(character_id) != activity.position(0):
        return

    now_draw = draw.NormalDraw()
    now_draw.width = width
    severity_name = patient_obj.severity_name or _("未知病情")
    if (
        patient_obj.state
        == medical_constant.MedicalPatientState.WAITING_MEDICATION
    ):
        now_draw.text = _(
            "\n在{doctor}的努力下，为一名{severity}患者完成诊断，获得{income}龙门币。\n"
        ).format(
            doctor=character_data.name,
            severity=severity_name,
            income=income_delta,
        )
    else:
        now_draw.text = _(
            "\n{doctor}为一名{severity}患者推进诊疗进度。\n"
        ).format(
            doctor=character_data.name,
            severity=severity_name,
        )
    now_draw.draw()


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PERFORM_SURGERY
)
def handle_perform_surgery(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """执行手术治疗并根据结果输出提示"""
    from Script.System.Medical_System import medical_service

    if not add_time:
        return

    doctor_data: identity.Identity = identity.of(character_id)
    if activity.dead(character_id):
        return

    # 获取病人id
    patient_id = chara_life.surgery_patient_id(doctor_data.cid)

    # 执行手术
    medical_service.attempt_surgery(
        patient_id, doctor_data, target_base=cache.rhodes_island
    )

    # 获取大量习得
    base_chara_state_common_settle(
        character_id,
        add_time,
        9,
        ability_level=abilities.ability(character_id)[46],
        extra_adjust=3,
        change_data=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.WARD_ROUND_PROCESS
)
def handle_ward_round_process(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """病房查房：推进住院病人治疗进度并输出提示"""
    from Script.System.Medical_System import medical_service

    if not add_time:
        return

    doctor_data: identity.Identity = identity.of(character_id)
    if activity.dead(character_id):
        return

    outcome = medical_service.conduct_ward_round(doctor_data)

    # 仅在玩家或与玩家同场景时输出提示
    show_message = character_id == 0 or activity.position(
        character_id
    ) == activity.position(0)
    if not show_message:
        return

    result_flag = outcome.get("result")

    severity_before_name = _("未知病情")
    severity_after_name = _("未知病情")

    severity_before = outcome.get("severity_before")
    if isinstance(severity_before, int) and severity_before >= 0:
        config_before = game_config.config_medical_severity.get(severity_before)
        if config_before:
            severity_before_name = config_before.name

    severity_after = outcome.get("severity_after")
    if isinstance(severity_after, int) and severity_after >= 0:
        config_after = game_config.config_medical_severity.get(severity_after)
        if config_after:
            severity_after_name = config_after.name
    elif outcome.get("discharged"):
        severity_after_name = _("痊愈")

    # 仅在玩家场景输出
    if activity.position(character_id) != activity.position(0):
        return

    draw_text = draw.NormalDraw()
    draw_text.width = width

    if result_flag in {"no_candidate", "no_doctor"}:
        draw_text.text = _(
            "\n{doctor}巡视病房，但当前没有需要处理的住院患者。\n"
        ).format(doctor=doctor_data.name)
    elif result_flag == "missing_config":
        draw_text.text = _(
            "\n{doctor}处理住院病人时遇到异常配置，已将该患者提前出院。\n"
        ).format(doctor=doctor_data.name)
    elif outcome.get("discharged"):
        draw_text.text = _(
            "\n在{doctor}的查房下，一名{severity}患者顺利出院。\n"
        ).format(
            doctor=doctor_data.name,
            severity=severity_before_name,
        )
    elif outcome.get("success"):
        draw_text.text = _(
            "\n{doctor}为一名{before}患者完成住院治疗，病情下降至{after}。\n"
        ).format(
            doctor=doctor_data.name,
            before=severity_before_name,
            after=severity_after_name,
        )
    else:
        draw_text.text = _(
            "\n{doctor}尝试为一名{severity}患者用药，但药物库存不足，需等待补给。\n"
        ).format(
            doctor=doctor_data.name,
            severity=severity_before_name,
        )

    draw_text.draw()


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ASK_COPY_KEY
)
def handle_ask_copy_key(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （要求复制钥匙用）获取交互对象的所在楼层的钥匙
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    from Script.System.Dormitory_System import dormitory_manager_system

    key_item_id = dormitory_manager_system.ask_copy_key(character_id)
    now_draw = draw.NormalDraw()
    now_draw.width = width
    if key_item_id:
        key_name = game_config.config_item[key_item_id].name
        now_draw.text = _("\n获得了：【{0}】\n").format(key_name)
    else:
        now_draw.text = _("\n获得钥匙失败\n")
    now_draw.draw()


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.RECRUIT_ADD_ADJUST
)
def handle_recruit_add_just(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （招募干员用）根据发起者的话术技能增加招募槽
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    from Script.UI.Panel import recruit_panel

    if not add_time:
        return
    character_data: identity.Identity = identity.of(character_id)
    target_data: identity.Identity = identity.of(activity.target(character_id))

    if activity.dead(character_id):
        return
    if activity.dead(target_data.cid):
        return

    # 获取能力调整值
    adjust = handle_ability.get_ability_adjust(
        abilities.ability(character_id)[40]
    )

    # 确定使用哪个招募栏位
    select_index = -1
    recruit_lines = recruit.lines()
    # 如果角色是主招聘专员，则使用其指定的栏位
    for recruit_line_id, line in recruit_lines.items():
        if character_id == line["main"]:
            select_index = recruit_line_id
            break
    # 如果不是或是玩家来招募，则随机一个指派过去
    if select_index == -1 or character_id == 0:
        select_index = random.choice(list(recruit_lines))
        # 如果不是主招聘专员也不是玩家，则降低效率
        if character_id != 0:
            adjust /= 5

    # 获得招募策略
    recruit_strategy_id = recruit_lines[select_index]["strategy"]
    # 如果该招募槽的策略为11号停止招募，则直接返回
    if recruit_strategy_id == 11:
        return
    else:
        recruit_strategy_data = game_config.config_recruitment_strategy[
            recruit_strategy_id
        ]
        # 乘以策略调整值
        adjust *= recruit_strategy_data.adjust

    # 设施效率
    adjust *= basement.calc_facility_efficiency(7)
    # 获得加成
    now_add_lust = adjust * 2 * random.uniform(0.8, 1.2)
    # debug下直接拉满
    if cache.debug_mode:
        now_add_lust += 100

    # 如果是玩家在招募或玩家与招募者在同一位置的话，显示招募进度的增加情况
    if activity.position(character_id) == activity.position(0):
        now_draw = draw.NormalDraw()
        now_draw.width = width
        now_draw.text = _(
            "\n在{0}的努力下，{1}号招募位进度+{2}%，现在为{3}%\n"
        ).format(
            character_data.name,
            select_index,
            round(now_add_lust, 1),
            round(recruit_lines[select_index]["progress"] + now_add_lust, 1),
        )
        now_draw.draw()

    # 增加对应槽的招募值，并进行结算
    progress = recruit_lines[select_index]["progress"] + now_add_lust
    recruit.set_line(select_index, progress=progress)
    recruit_panel.update_recruit()


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.INVITE_VISITOR_ADD_ADJUST
)
def handle_invite_visitor_add_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （邀请访客用）根据发起者(如果有的话再加上交互对象)的话术技能增加邀请槽
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    from Script.UI.Panel import invite_visitor_panel

    if not add_time:
        return
    character_data: identity.Identity = identity.of(character_id)
    target_data: identity.Identity = identity.of(activity.target(character_id))

    if activity.dead(character_id):
        return
    if activity.dead(target_data.cid):
        return

    target, progress = visitor.invite()
    # 如果没有选择目标则直接返回
    if target == 0:
        # 玩家使用时显示提示
        if character_id == 0:
            now_draw = draw.NormalDraw()
            now_draw.width = width
            now_draw.text = _("\n请先使用邀请系统选择邀请的对象，再进行邀请\n")
            now_draw.draw()
        return

    # 如果该角色已经被招募，则直接返回
    if roster.has(target) or target in recruit.pending():
        visitor.set_invite(0)
        # 玩家使用时显示提示
        if character_id == 0:
            now_draw = draw.NormalDraw()
            now_draw.width = width
            now_draw.text = _("\n该角色已经被招募，邀请已重置\n")
            now_draw.draw()
        return

    # 获取调整值#
    adjust = handle_ability.get_ability_adjust(
        abilities.ability(character_id)[40]
    )
    # 设施效率
    adjust *= basement.calc_facility_efficiency(13)
    # 获得加成 #
    now_add_lust = adjust * 2 * random.uniform(0.8, 1.2)
    # debug下直接拉满
    if cache.debug_mode:
        now_add_lust += 100

    # 如果是玩家在邀请或玩家与邀请者在同一位置的话，显示进度的增加情况
    if activity.position(character_id) == activity.position(0):
        now_draw = draw.NormalDraw()
        now_draw.width = width
        now_draw.text = _(
            "\n在{0}的努力下，邀请进度+{1}%，现在为{2}%\n"
        ).format(
            character_data.name,
            round(now_add_lust, 1),
            round(progress + now_add_lust, 1),
        )
        now_draw.draw()

    # 增加对应槽的邀请值，并进行结算
    visitor.set_invite(target, progress + now_add_lust)
    invite_visitor_panel.update_invite_visitor()


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.MILK_ADD_ADJUST
)
def handle_milk_add_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （挤奶用）把交互对象的乳汁转移到厨房的冰箱里
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return

    now_milk = int(needs.of(activity.target(character_id))["milk"])
    activity.update_behavior(
        character_id,
        milk_ml=activity.behavior(character_id).milk_ml + (now_milk),
    )
    fridge.add(fridge.MILK, activity.target(character_id), now_milk)
    player_collection.add_total(
        "milk_total", activity.target(character_id), now_milk
    )
    needs.set(activity.target(character_id), milk=0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SALUTATION_3_ADD_ADJUST
)
def handle_salutation_3_add_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （早安咬与晚安咬）触发交互对象一次射精，射到发起者嘴里
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    ejaculation_panel.ejaculation_flow(2, 0, character_id)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.AROMATHERAPY_ADD_ADJUST
)
def handle_aromatherapy_add_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （香薰疗愈用）对各配方结算各效果
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_character_data = identity.of(activity.target(character_id))

    # 如果没有选择配方则直接返回
    if flags.get(target_character_data.cid, "aromatherapy") == 0:
        return

    # 回复
    if flags.get(target_character_data.cid, "aromatherapy") == 1:
        needs.set(
            target_character_data.cid,
            hit=needs.of(target_character_data.cid)["hit_max"],
        )
        needs.set(
            target_character_data.cid,
            mana=needs.of(target_character_data.cid)["mana_max"],
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.URETHRAL_SWAB_ADD_ADJUST
)
def handle_urethral_swab_add_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    根据交互对象的U属性(润滑+扩张)对其进行苦痛调整
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    ability = abilities.ability(target_data.cid)
    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if activity.dead(target_data.cid):
            return
        # 润滑调整
        status.setdefault(target_data.cid, 8, 0)
        pain_adjust = attr_calculation.get_pain_adjust(
            num.whole(status.of(target_data.cid)[8])
        )

        # 扩长等级相对于插入等级的调整，棉棒默认为无影响
        dilate_level = ability[11]
        size_adjust = attr_calculation.get_pain_adjust(
            dilate_level, level_flag=True
        )

        # 最终调整值
        final_adjust = pain_adjust * size_adjust

        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            17,
            base_value=100,
            ability_level=ability[15],
            extra_adjust=final_adjust,
            change_data_to_target_change=change_data,
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.URETHRAL_FINGER_INSERTION_ADD_ADJUST
)
def handle_urethral_finger_insertion_add_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    根据交互对象的U属性(润滑+扩张)对其进行苦痛调整
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    ability = abilities.ability(target_data.cid)
    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if activity.dead(target_data.cid):
            return
        # 润滑调整
        status.setdefault(target_data.cid, 8, 0)
        pain_adjust = attr_calculation.get_pain_adjust(
            num.whole(status.of(target_data.cid)[8])
        )

        # 扩长等级相对于插入等级的调整，手指为-2级扩张
        dilate_level = ability[11] - 2
        size_adjust = attr_calculation.get_pain_adjust(
            dilate_level, level_flag=True
        )

        # 最终调整值
        final_adjust = pain_adjust * size_adjust

        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            17,
            base_value=400,
            ability_level=ability[15],
            extra_adjust=final_adjust,
            change_data_to_target_change=change_data,
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.MASTUREBATE_ADD_ADJUST
)
def handle_masturebate_add_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （自慰用）选择自己最高感度的部位，增加该部位快感和经验
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    ability = abilities.ability(character_id)
    if not add_time:
        return
    # 根据NPC的部位喜好，选择一个部位
    part_id = handle_npc_ai_in_h.evaluate_npc_body_part_prefs(character_id)
    # 增加快感
    base_chara_state_common_settle(
        character_id,
        add_time,
        part_id,
        50,
        ability_level=ability[30],
        change_data=change_data,
    )
    # 增加部位经验
    base_chara_experience_common_settle(
        character_id, part_id, 1, change_data=change_data
    )
    # 如果已持有玩家的阴茎倒模
    if handle_premise.handle_have_penis_mold(character_id):
        # 额外增加一次快感
        base_chara_state_common_settle(
            character_id,
            add_time,
            part_id,
            50,
            ability_level=ability[30],
            change_data=change_data,
        )
        # 增加1道具使用经验
        base_chara_experience_common_settle(
            character_id, 51, 1, change_data=change_data
        )
        # 增加对玩家好感
        handle_add_interaction_favoravility(
            character_id, add_time, change_data, now_time
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DIRTY_RESET_IN_SHOWER
)
def handle_dirty_reset_in_shower(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自身部分部位污浊保留一定比例，其他污浊体归零
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    # 保留比例
    keep_rate_dict: dict[int, num.Num] = {
        6: Fraction(1, 5),
        7: Fraction(7, 10),
        8: Fraction(3, 10),
        15: 1,
    }
    # 身体管理被要求不洗精液时则上调比例
    if handle_premise.handle_ask_not_wash_semen(character_id):
        keep_rate_dict[6] = Fraction(4, 5)
        keep_rate_dict[7] = Fraction(9, 10)
    # 保留数据
    with dirty.editing(character_id) as d:
        keep_data = {}
        for body_cid in keep_rate_dict:
            # 计算保留数据，使用原数据以继承0号和3号元素
            body_dirty = d.body_semen[body_cid].copy()
            new_dirty: num.Num = body_dirty[1] * keep_rate_dict[body_cid]
            if new_dirty < 5:
                new_dirty = 0
            body_dirty[1] = new_dirty
            body_dirty[2] = attr_calculation.get_semen_now_level(
                new_dirty, body_cid, 0
            )
            keep_data[body_cid] = body_dirty
        # 被要求禁止洗衣服时，先保存衣物污浊，待身体清洗结算后恢复
        keep_cloth_semen = (
            {ct: sd.copy() for ct, sd in d.cloth_semen.items()}
            if handle_premise.handle_ask_not_wash_cloth(character_id)
            else {}
        )
        dirty.reset(character_id)
        for body_cid in keep_rate_dict:
            d.body_semen[body_cid] = keep_data[body_cid]
        for clothing_type, semen_data in keep_cloth_semen.items():
            d.cloth_semen[clothing_type] = semen_data


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ORGASM_EDGE_RELEASE
)
def handle_orgasm_edge_release(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （绝顶解放）交互对象变为寸止解放状态，将寸止计数转化为绝顶并立即结算
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    from Script.Settle import orgasm_settle

    if not add_time:
        return
    target_id = activity.target(character_id)
    # 如果没有交互对象
    if target_id == character_id:
        return
    # 仅在交互对象确有寸止累计时才建立其TargetChange并解放，避免空条目影响显示判定
    if h_state.get(target_id, "orgasm_edge") != 0:
        orgasm_settle.release_orgasm_edge_now(
            target_id,
            change_data.target_change.setdefault(
                target_id, game_type.TargetChange()
            ),
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TIME_STOP_ORGASM_RELEASE
)
def handle_time_stop_orgasm_release(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （解除时停）交互对象变为时停解放状态，结算时停绝顶和时停精液
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    from Script.Settle import orgasm_settle

    if not add_time:
        return
    for chara_id in roster.active():
        if chara_id == 0:
            continue
        # 变为时停解放状态
        h_state.set(chara_id, time_stop_release=True)
        ts_counts = h_state.view(chara_id).time_stop_orgasm_count
        # 将时停绝顶计数转化为绝顶
        settlement_change = (
            change_data.target_change.setdefault(
                chara_id, game_type.TargetChange()
            )
            if any(ts_counts.values())
            else change_data
        )
        orgasm_settle.orgasm_settle_in_second_behavior(
            chara_id,
            settlement_change,
            un_count_orgasm_dict=ts_counts,
        )
        # 清零时停绝顶计数
        with h_state.editing(chara_id) as hs:
            for state_id in game_config.config_character_state:
                if game_config.config_character_state[state_id].type == 0:
                    hs.time_stop_orgasm_count[state_id] = 0
        # 触发角色的二段行为
        handle_npc_ai_in_h.settle_unconscious_semen_and_cloth(chara_id)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.END_H_ADD_HPMP_MAX
)
def handle_end_h_add_hpmp_max(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （结束H）自己和交互对象根据本次H中的绝顶次数增加体力气力上限
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    from Script.Design import handle_ability
    from Script.Settle import orgasm_settle

    # 计奖前先释放行为者憋住的累计寸止绝顶，使其计入下方奖励统计（无累计时空转）
    orgasm_settle.release_orgasm_edge_now(character_id, change_data)
    id_list = [character_id]
    if activity.target(character_id) != character_id:
        id_list.append(activity.target(character_id))
    for chara_id in id_list:
        now_character_data: identity.Identity = identity.of(chara_id)
        info_text = now_character_data.name
        # 如果玩家有忍耐的射精次数，则射出
        if chara_id == 0 and handle_premise.handle_pl_endure_orgasm_count_ge_1(
            chara_id
        ):
            handle_stop_endurance_shoot(
                chara_id, add_time, change_data, now_time
            )
        # 统计绝顶次数
        orgasm_count = 0
        for state_id in game_config.config_character_state:
            # 跳过非快感
            if game_config.config_character_state[state_id].type != 0:
                continue
            now_part_count = h_state.view(chara_id).orgasm_count[state_id][0]
            orgasm_count += now_part_count
            if now_part_count > 0:
                if chara_id == 0 and state_id == 3:
                    info_text += _("射精{0}次，总射精{1}ml，").format(
                        now_part_count,
                        h_state.get(chara_id, "shoot_semen_amount"),
                    )
                    h_state.set(chara_id, shoot_semen_amount=0)
                else:
                    info_text += _("{0}绝顶{1}次，").format(
                        game_config.config_character_state[state_id].name,
                        now_part_count,
                    )
        # 如果有绝顶，则增加体力气力上限
        if orgasm_count > 0:
            # 去掉最后的逗号，换成换行符
            info_text = info_text[:-1] + "\n"
            needs.add(chara_id, "hit_max", orgasm_count * 2)
            needs.add(chara_id, "mana_max", orgasm_count * 3)
            info_text += _(
                "在激烈的H之后，{0}的体力上限增加了{1}，气力上限增加了{2}"
            ).format(
                now_character_data.name, orgasm_count * 2, orgasm_count * 3
            )
            # 减少欲望值
            needs.set(
                chara_id,
                desire=max(
                    int(needs.of(chara_id)["desire"] - orgasm_count * 20), 0
                ),
            )
            # 玩家则额外增加精液量上限
            if chara_id == 0 and h_meters.of(0)["semen_max"] < 999:
                h_meters.add(0, "semen_max", orgasm_count, max=999)
                info_text += _("，精液量上限增加了{0}").format(orgasm_count)
            info_text += "\n"
            # 输出提示信息
            info_draw = draw.NormalDraw()
            info_draw.text = info_text
            info_draw.width = width
            info_draw.draw()
        # npc则自动进行一次能力上升结算
        if chara_id != 0 and normal_config.system_setting.base_setting[2]:
            handle_ability.gain_ability(chara_id)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.GROUP_SEX_END_H_ADD_HPMP_MAX
)
def handle_group_sex_end_h_add_hpmp_max(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （群交结束H）在场全部角色根据本次H中的绝顶次数增加体力气力上限
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    from Script.Design import handle_ability
    from Script.Settle import orgasm_settle

    scene_path_str = map_handle.get_map_system_path_str_for_list(
        activity.position(character_id)
    )
    scene_data: game_type.Scene = cache.scene_data[scene_path_str]
    for chara_id in scene_data.character_list:
        now_character_data: identity.Identity = identity.of(chara_id)
        # 统计绝顶奖励前，先为该在场参与者解放并结算其累计的寸止绝顶，使其计入退出奖励；无累计者不建立空TargetChange条目
        if h_state.get(chara_id, "orgasm_edge") != 0:
            orgasm_settle.release_orgasm_edge_now(
                chara_id,
                change_data.target_change.setdefault(
                    chara_id, game_type.TargetChange()
                ),
            )
        orgasm_count = 0
        info_text = now_character_data.name
        for state_id in game_config.config_character_state:
            # 跳过非快感
            if game_config.config_character_state[state_id].type != 0:
                continue
            now_part_count = h_state.view(chara_id).orgasm_count[state_id][0]
            orgasm_count += now_part_count
            if now_part_count > 0:
                if chara_id == 0 and state_id == 3:
                    info_text += _("射精{0}次，总射精{1}ml，").format(
                        now_part_count,
                        h_state.get(chara_id, "shoot_semen_amount"),
                    )
                    h_state.set(chara_id, shoot_semen_amount=0)
                else:
                    info_text += _("{0}绝顶{1}次，").format(
                        game_config.config_character_state[state_id].name,
                        now_part_count,
                    )
        # 如果有绝顶，则增加体力气力上限
        if orgasm_count > 0:
            # 去掉最后的逗号，换成换行符
            info_text = info_text[:-1] + "\n"
            needs.add(chara_id, "hit_max", orgasm_count * 2)
            needs.add(chara_id, "mana_max", orgasm_count * 3)
            info_text += _(
                "在激烈的H之后，{0}的体力上限增加了{1}，气力上限增加了{2}"
            ).format(
                now_character_data.name, orgasm_count * 2, orgasm_count * 3
            )
            # 减少欲望值
            needs.add(chara_id, "desire", -(orgasm_count * 20), min=0)
            # 玩家则额外增加精液量上限
            if chara_id == 0 and h_meters.of(0)["semen_max"] < 999:
                h_meters.add(0, "semen_max", orgasm_count, max=999)
                info_text += _("，精液量上限增加了{0}").format(orgasm_count)
            info_text += "\n"
            # 输出提示信息
            info_draw = draw.NormalDraw()
            info_draw.text = info_text
            info_draw.width = width
            info_draw.draw()
        # npc则自动进行一次能力上升结算
        if chara_id != 0 and normal_config.system_setting.base_setting[2]:
            handle_ability.gain_ability(chara_id)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.GROUP_SEX_FAIL_ADD_JUST
)
def handle_group_sex_fail_add_just(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （群交失败）在场全部角色减体力气力，拒绝者进行邀请H失败结算
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    original_target_character_id = activity.target(character_id)
    scene_path_str = map_handle.get_map_system_path_str_for_list(
        activity.position(character_id)
    )
    scene_data: game_type.Scene = cache.scene_data[scene_path_str]
    # 遍历场景内所有角色
    for chara_id in scene_data.character_list:
        handle_sub_self_small_mana_point(
            chara_id, add_time, change_data, now_time
        )
        handle_sub_self_small_hit_point(
            chara_id, add_time, change_data, now_time
        )
        # 跳过玩家
        if chara_id == 0:
            continue
        # 如果是拒绝者，则进行邀请H失败结算
        if handle_premise.handle_group_sex_fail_and_self_refuse(chara_id):
            activity.set_target(character_id, chara_id)
            handle_do_h_failed_adjust(0, add_time, change_data, now_time)
    activity.set_target(character_id, original_target_character_id)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.BOARD_GAME_WIN_ADD_ADJUST
)
def handle_board_game_win_add_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （桌游获胜用）根据游戏难度获得好感度、信赖、习得、粉红凭证
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    ability = abilities.ability(character_id)
    if not add_time:
        return
    character_data: identity.Identity = identity.of(character_id)
    target_data: identity.Identity = identity.of(activity.target(character_id))
    change_data.target_change.setdefault(
        target_data.cid, game_type.TargetChange()
    )
    target_change = change_data.target_change[target_data.cid]

    ai_level = activity.behavior(character_id).board_game_ai_difficulty
    # 好感
    base_chara_favorability_and_trust_common_settle(
        activity.target(character_id),
        add_time * 2,
        True,
        0,
        ai_level,
        target_change,
    )
    # 信赖
    base_chara_favorability_and_trust_common_settle(
        activity.target(character_id),
        add_time * 2,
        False,
        0,
        ai_level,
        target_change,
    )
    # 习得
    base_chara_state_common_settle(
        character_id,
        add_time,
        9,
        ability_level=ability[45],
        extra_adjust=ai_level,
        change_data=change_data,
    )
    base_chara_state_common_settle(
        activity.target(character_id),
        add_time,
        9,
        ability_level=ability[45],
        extra_adjust=ai_level,
        change_data=target_change,
    )
    # 粉红凭证
    add_pink_certificates = int(add_time // 2 * ai_level)
    warehouse.add(4, add_pink_certificates)
    # 输出提示信息
    game_name = game_config.config_board_game[
        activity.behavior(character_id).board_game_type
    ].name
    info_draw = draw.NormalDraw()
    info_draw.text = _("{0}在{1}中获胜，获得了{2}粉红凭证\n\n").format(
        character_data.name, game_name, add_pink_certificates
    )
    info_draw.width = width
    info_draw.draw()


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.BOARD_GAME_LOSE_ADD_ADJUST
)
def handle_board_game_lose_add_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （桌游输了用）根据游戏难度获得好感度、习得
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    ability = abilities.ability(character_id)
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    change_data.target_change.setdefault(
        target_data.cid, game_type.TargetChange()
    )
    target_change = change_data.target_change[target_data.cid]

    ai_level = activity.behavior(character_id).board_game_ai_difficulty
    # 好感
    base_chara_favorability_and_trust_common_settle(
        activity.target(character_id),
        add_time * 2,
        True,
        0,
        ai_level,
        target_change,
    )
    # 习得
    base_chara_state_common_settle(
        character_id,
        add_time,
        9,
        ability_level=ability[45],
        extra_adjust=ai_level,
        change_data=change_data,
    )
    base_chara_state_common_settle(
        activity.target(character_id),
        add_time,
        9,
        ability_level=ability[45],
        extra_adjust=ai_level,
        change_data=target_change,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.MAINTENANCE_ADD_ADJUST
)
def handle_maintenance_add_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （维护设施用）修复当前地点的损坏设施
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    # 获取当前位置
    scene_path_str = map_handle.get_map_system_path_str_for_list(
        activity.position(character_id)
    )
    # 检查是否在损坏设施数据中
    damage = maintenance.damage()
    if scene_path_str in damage:
        repair_num = abilities.ability(character_id)[48]
        # 修复后如果小于等于0则去掉
        maintenance.set_damage(
            scene_path_str, damage[scene_path_str] - repair_num
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TRAIN_PRISONERS_ADD_ADJUST
)
def handle_train_prisoners_add_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （训练囚犯用）对所有被关押的囚犯进行日常训练
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    from Script.Core import value_handle

    ability = abilities.ability(character_id)
    if not add_time:
        return
    character_data: identity.Identity = identity.of(character_id)
    now_train_id = prison.setting(1)
    all_prisoner_ids = prison.prisoner_ids()
    # 如果未设定训练则返回
    if now_train_id == 0:
        return
    # 如果没有囚犯则返回
    if len(all_prisoner_ids) == 0:
        return
    # 部位快感训练
    if now_train_id == 1:
        # 根据部位感度等级进行加权选择目标部位
        all_part_data = {}
        for state_id in game_config.config_character_state:
            if game_config.config_character_state[state_id].type == 0:
                # 跳过P
                if state_id == 3:
                    continue
                ability_id = game_config.config_pleasure_relations[
                    state_id
                ].ability_id
                all_part_data[state_id] = ability[ability_id]
                all_part_data[state_id] = max(all_part_data[state_id], 1)
        # 选择部位
        target_part_id = value_handle.get_random_for_weight(all_part_data)

        def now_tarin(now_prisoner_cid: int) -> None:
            base_chara_state_common_settle(
                now_prisoner_cid,
                add_time,
                target_part_id,
                0,
                ability_level=abilities.ability(character_data.cid)[30],
                change_data_to_target_change=change_data,
            )
            exp_id = target_part_id
            base_chara_experience_common_settle(
                now_prisoner_cid,
                exp_id,
                change_data_to_target_change=change_data,
            )

    # 部位扩张训练
    elif now_train_id == 2:
        # 根据部位扩张等级进行加权选择目标部位
        all_part_data = {}
        for part_id in [9, 10, 11, 12]:
            all_part_data[part_id] = ability[part_id]
            all_part_data[part_id] = max(all_part_data[part_id], 1)
        # 选择部位
        target_part_id = value_handle.get_random_for_weight(all_part_data)

        def now_tarin(now_prisoner_cid: int) -> None:
            base_chara_state_common_settle(
                now_prisoner_cid,
                add_time,
                target_part_id - 5,
                0,
                ability_level=abilities.ability(character_data.cid)[
                    target_part_id
                ],
                change_data_to_target_change=change_data,
            )
            exp_id = target_part_id + 56
            base_chara_experience_common_settle(
                now_prisoner_cid,
                exp_id,
                change_data_to_target_change=change_data,
            )

    # 苦痛快感训练
    elif now_train_id == 3:

        def now_tarin(now_prisoner_cid: int) -> None:
            base_chara_state_common_settle(
                now_prisoner_cid,
                add_time,
                0,
                0,
                ability_level=abilities.ability(character_data.cid)[36],
                change_data_to_target_change=change_data,
            )
            base_chara_state_common_settle(
                now_prisoner_cid,
                add_time,
                17,
                0,
                change_data_to_target_change=change_data,
            )
            exp_id = 32
            base_chara_experience_common_settle(
                now_prisoner_cid,
                exp_id,
                change_data_to_target_change=change_data,
            )

    # 性爱技巧训练
    elif now_train_id == 4:
        # 根据性爱技巧等级进行加权选择目标部位
        all_part_data = {}
        for part_id in [70, 71, 72, 73, 74, 75, 76]:
            all_part_data[part_id] = ability[part_id]
            all_part_data[part_id] = max(all_part_data[part_id], 1)
        # 选择部位
        target_part_id = value_handle.get_random_for_weight(all_part_data)

        def now_tarin(now_prisoner_cid: int) -> None:
            base_chara_state_common_settle(
                now_prisoner_cid,
                add_time,
                9,
                0,
                ability_level=abilities.ability(character_data.cid)[
                    target_part_id
                ],
                change_data_to_target_change=change_data,
            )
            base_chara_state_common_settle(
                now_prisoner_cid,
                add_time,
                9,
                0,
                ability_level=abilities.ability(character_data.cid)[30],
                change_data_to_target_change=change_data,
            )

    # 身体锻炼训练
    elif now_train_id == 5:

        def now_tarin(now_prisoner_cid: int) -> None:
            handle_add_hpmp_max(
                now_prisoner_cid, add_time, change_data, now_time
            )

    # 心理服从训练
    else:

        def now_tarin(now_prisoner_cid: int) -> None:
            base_chara_state_common_settle(
                now_prisoner_cid,
                add_time,
                11,
                0,
                ability_level=abilities.ability(character_data.cid)[32],
                change_data_to_target_change=change_data,
            )
            base_chara_state_common_settle(
                now_prisoner_cid,
                add_time,
                15,
                0,
                ability_level=abilities.ability(character_data.cid)[14],
                change_data_to_target_change=change_data,
            )

    # 遍历犯人
    for now_prisoner_cid in all_prisoner_ids:
        # 1异常或睡觉中的角色不进行训练
        if not handle_premise.handle_normal_1(
            now_prisoner_cid
        ) or handle_premise.handle_action_sleep(now_prisoner_cid):
            continue
        now_tarin(now_prisoner_cid)
        base_chara_hp_mp_common_settle(
            now_prisoner_cid,
            add_time,
            hp_value=-1,
            mp_value=-1,
            degree=1,
            change_data_to_target_change=change_data,
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.RECOVER_FROM_UNCONSCIOUS_ADD_ADJUST
)
def handle_recover_from_unconscious_add_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象从无意识H中恢复意识的结算
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    # 如果交互对象是在H中，则进行恢复意识结算
    if handle_premise.handle_self_is_h(activity.target(character_id)):
        handle_npc_ai_in_h.recover_from_unconscious_h(character_id)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_DIRTY_RESET_IN_SHOWER
)
def handle_target_dirty_reset_in_shower(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象进行污浊清洗(525)
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    handle_dirty_reset_in_shower(
        activity.target(character_id), add_time, change_data, now_time
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.GIVE_GIFT_ADD_ADJUST
)
def handle_give_gift_add_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （赠送礼物用）根据礼物的类型结算交互对象的对应数值
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    target_data: identity.Identity = identity.of(activity.target(character_id))
    gift_id = activity.behavior(character_id).gift_id
    # 如果没有礼物则返回
    if gift_id == 0:
        return

    gift_data = game_config.config_gift_items[gift_id]
    # 礼物持有数量-1
    item_id = gift_data.item_id
    inventory.add_item(character_id, item_id, -1)
    achievement.add("gift_count", 1)

    # 好感礼物
    if gift_data.type == 3:
        # 话术修正
        talk_adjust = handle_ability.get_ability_adjust(
            abilities.ability(character_id)[40]
        )
        # 更新最后赠送时间
        action_info.set(target_data.cid, "last_gift_time", game_time.now())
        # 好感礼物小
        if gift_data.item_id == 172:
            base_chara_favorability_and_trust_common_settle(
                character_id, 10, True, 0, talk_adjust * 1.5, change_data
            )
            base_chara_state_common_settle(
                activity.target(character_id),
                10,
                11,
                ability_level=abilities.ability(target_data.cid)[32],
                change_data_to_target_change=change_data,
            )
        # 好感礼物中
        elif gift_data.item_id == 173:
            # 补正到至少4级话术
            talk_adjust = max(talk_adjust, handle_ability.get_ability_adjust(4))
            base_chara_favorability_and_trust_common_settle(
                character_id, 30, True, 0, talk_adjust * 2, change_data
            )
            base_chara_favorability_and_trust_common_settle(
                character_id, 10, False, 0, talk_adjust * 2, change_data
            )
            base_chara_state_common_settle(
                activity.target(character_id),
                30,
                11,
                ability_level=abilities.ability(target_data.cid)[32],
                change_data_to_target_change=change_data,
            )
        # 好感礼物大
        elif gift_data.item_id == 174:
            # 补正到至少6级话术
            talk_adjust = max(talk_adjust, handle_ability.get_ability_adjust(6))
            base_chara_favorability_and_trust_common_settle(
                character_id, 60, True, 0, talk_adjust * 3, change_data
            )
            base_chara_favorability_and_trust_common_settle(
                character_id, 30, False, 0, talk_adjust * 3, change_data
            )
            base_chara_state_common_settle(
                activity.target(character_id),
                120,
                11,
                ability_level=abilities.ability(target_data.cid)[32],
                change_data_to_target_change=change_data,
            )
            base_chara_experience_common_settle(
                activity.target(character_id),
                40,
                change_data_to_target_change=change_data,
            )
    # 道歉礼物
    elif gift_data.type == 2:
        # 降低反发刻印
        abilities.ability(target_data.cid)[18] = 0
        # 其他数据结算
        base_chara_favorability_and_trust_common_settle(
            character_id, 10, True, 0, 0, change_data
        )
        base_chara_state_common_settle(
            activity.target(character_id),
            10,
            11,
            ability_level=abilities.ability(target_data.cid)[32],
            change_data_to_target_change=change_data,
        )
        handle_target_angry_with_player_flag_to_0(
            character_id, add_time, change_data, now_time
        )
        # 显示绘制信息
        now_draw = draw.WaitDraw()
        draw_text = _("\n  {0}的反发刻印从1级降为了0\n\n").format(
            target_data.name
        )
        now_draw.style = "gold_enrod"
        now_draw.text = draw_text
        now_draw.draw()
    # 药物礼物
    elif gift_data.type == 11:
        # 这是药物ID，执行药物使用逻辑
        from Script.UI.Panel import gift_panel

        gift_panel.handle_drug_use_effect(
            activity.target(character_id), gift_id
        )
    # 阴茎倒模
    elif gift_data.type == 13:
        # 对方获得阴茎倒模
        inventory.add_item(target_data.cid, 175, 1)
        # 增加好感与羞耻
        base_chara_favorability_and_trust_common_settle(
            character_id, 100, True, change_data=change_data
        )
        base_chara_state_common_settle(
            activity.target(character_id),
            100,
            16,
            ability_level=abilities.ability(target_data.cid)[34],
            change_data_to_target_change=change_data,
        )

    # 结算成就
    achievement_panel.achievement_flow(_("礼物"))


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.MAINTAIN_EQUIPMENT_ADD_ADJUST
)
def handle_maintain_equipment_add_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （维护装备用）进行一次装备的维修保养
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    from Script.UI.Panel import equipmen_panel

    # 如果和玩家在同一个地方，则触发绘制信息
    draw_flag = False
    if handle_premise.handle_in_player_scene(character_id):
        draw_flag = True
    # 进行装备维护
    equipmen_panel.smith_maintain_equipment_once(character_id, draw_flag)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.READ_ADD_ADJUST
)
def handle_read_add_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （读书用）根据书的不同对发起者(如果有的话再加上交互对象)获得对应的知识，并进行NPC的还书判定
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    from Script.UI.Panel import borrow_book_panel

    ability = abilities.ability(character_id)
    if not add_time:
        return
    character_data: identity.Identity = identity.of(character_id)

    if activity.dead(character_id):
        return
    book_id = activity.behavior(character_id).book_id
    book_data = game_config.config_book[book_id]
    book_difficulty = book_data.difficulty
    book_difficulty_int = max(book_data.difficulty, 1)  # 确保难度至少为1
    book_type = book_data.type
    exp_id = game_config.config_book_type[book_type].exp_id

    # 根据书籍难度额外结算习得珠
    base_chara_state_common_settle(
        character_id,
        add_time,
        9,
        extra_adjust=book_difficulty,
        change_data=change_data,
    )
    # 如果有交互对象，则交互对象也加
    if activity.target(character_id) != character_id:
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            9,
            extra_adjust=book_difficulty_int,
            change_data_to_target_change=change_data,
        )

    # 经验结算
    experience_index_list = []
    experience_index_list.append(92)
    # 书籍的额外经验增长
    for __ in range(book_difficulty_int):
        if exp_id != 0:
            experience_index_list.append(exp_id)

    # 遍历集合增加对应经验
    for experience_index in experience_index_list:
        base_chara_experience_common_settle(
            character_id, experience_index, 1, change_data=change_data
        )
        # 如果有交互对象，则交互对象也加
        if activity.target(character_id) != character_id:
            base_chara_experience_common_settle(
                character_id,
                experience_index,
                1,
                target_flag=True,
                change_data=change_data,
            )

    # 结算书籍的阅读进度
    read_book_progress = chara_life.read_book_progress(character_id)
    read_book_progress.setdefault(book_id, 0)
    chara_life.read_book_progress.set(character_id, read_book_progress)
    info_text = _("\n{0}阅读了{1}，").format(
        character_data.name, book_data.name
    )
    if chara_life.read_book_progress(character_id)[book_id] < 100:
        base = 5
        adjust = (
            handle_ability.get_ability_adjust(ability[45]) / book_difficulty_int
        )
        # 如果当前位置是在图书馆，则根据图书馆等级提高阅读效率
        if handle_premise.handle_in_library(character_id):
            facility_data = game_config.config_facility[10]
            facility_name = facility_data.name
            library_level = facility.level(10)
            facility_effect_cid = game_config.config_facility_effect_data[
                facility_name
            ][int(library_level)]
            facility_effect = game_config.config_facility_effect[
                facility_effect_cid
            ].effect
            adjust *= (100 + facility_effect) / 100
        # 如果是0难度书籍，则阅读效率提高
        if book_difficulty == 0:
            adjust *= 3
        # 计算阅读进度
        read_progress = int(base * adjust * random.uniform(0.5, 1.5))
        read_progress = max(read_progress, 1)
        old_progress = chara_life.read_book_progress(character_id)[book_id]
        with chara_life.read_book_progress.editing(
            character_id
        ) as read_book_progress:
            read_book_progress[book_id] += read_progress
        # 绘制提示信息
        info_text += _("阅读进度增加了{0}%，从{1}%增加到{2}%").format(
            read_progress,
            old_progress,
            chara_life.read_book_progress(character_id)[book_id],
        )
        # 如果阅读进度大于等于100，则结算读完的奖励
        if (
            chara_life.read_book_progress(character_id)[book_id] >= 100
            or cache.debug_mode
        ):
            chara_life.read_book_progress.set_item(character_id, book_id, 100)
            # 如果是技能书籍，则增加对应技能的经验
            if exp_id != 0:
                if book_difficulty == 0:
                    add_value = 5
                elif book_difficulty == 1:
                    add_value = 10
                elif book_difficulty == 2:
                    add_value = 20
                else:
                    add_value = 40
                base_chara_experience_common_settle(
                    character_id, exp_id, add_value, change_data=change_data
                )
            # 结算习得
            extra_adjust = book_difficulty * book_difficulty
            base_chara_state_common_settle(
                character_id,
                add_time,
                9,
                ability_level=ability[45],
                extra_adjust=extra_adjust,
                change_data=change_data,
            )
            # 绘制信息
            info_text += _("，读完了这本书，获得了大量的知识和经验。\n")
        else:
            info_text += "。\n"
    else:
        info_text += _("不过已经读完过了，无法再增加阅读进度。\n")
        # NPC的还书判定
        if character_id:
            borrow_book_panel.check_return_book(character_id)
    # 仅在是玩家的情况下输出该提示信息
    if character_id == 0:
        info_draw = draw.NormalDraw()
        info_draw.text = info_text
        info_draw.style = "gold_enrod"
        info_draw.draw()
        # 结算成就
        achievement_panel.achievement_flow(_("读书"))


def _teach_subject(teacher_id: int) -> tuple[int, int]:
    """
    教师这一节所授的科目与课型。
    全局课表上这一节有这位教师的课、而且科目已知时，取课表的科目与课型。
    查不到时科目用学识（FALLBACK_SUBJECT_ABILITY），课型按教师所在的场景判。
    Keyword arguments:
    teacher_id -- 教师的角色id
    Return arguments:
    tuple -- (科目能力id, 课型编号)
    """
    from Script.System.Education_System import (
        education_constant,
        schedule_handle,
    )

    teaching = schedule_handle.get_now_teaching(teacher_id)
    if teaching is not None and teaching["ability_id"] > 0:
        return teaching["ability_id"], teaching["course_type"]
    return (
        education_constant.FALLBACK_SUBJECT_ABILITY,
        schedule_handle.get_course_type_by_position(
            activity.position(teacher_id)
        ),
    )


def _settle_class_student(
    teacher_id: int,
    student_id: int,
    scene_name: str,
    lesson: tuple[int, int, int],
    add_time: int,
    change_data: game_type.CharacterStatusChange,
) -> bool:
    """
    一名听课学生这一侧的授课收益（512 的学生侧，557 结算被玩家授课拉来的学生时也用）。
    NPC 教师授课时，只结算本节课表排在这间教室、节次与教师开讲节次相同的学生。
    玩家授课时不按课表筛学生，该生本节课表排在这间教室时才计一节出勤。
    收益交给 settle_student_class_gain，同一节只结算一次。
    玩家授课并且真的结算了时，再加该生对玩家的好感与信赖。
    Keyword arguments:
    teacher_id -- 教师的角色id，0 为玩家
    student_id -- 学生的角色id
    scene_name -- 授课场景的名字
    lesson -- (科目能力id, 课型编号, 教师开讲的节次)
    add_time -- 结算时间
    change_data -- 教师的结算信息记录对象
    Return arguments:
    bool -- 是否结算了
    """
    from Script.System.Education_System import growth_handle, schedule_handle

    ability_id, course_type, teacher_period = lesson
    student_course = schedule_handle.get_now_course(student_id)
    scheduled_here = (
        student_course is not None and student_course["classroom"] == scene_name
    )
    if teacher_id != 0 and not scheduled_here:
        return False
    if (
        teacher_id != 0
        and student_course is not None
        and student_course["period"] != teacher_period
    ):
        return False
    if not growth_handle.settle_student_class_gain(
        student_id,
        teacher_id,
        ability_id,
        course_type,
        add_time,
        change_data_to_target_change=change_data,
        count_attend=scheduled_here,
    ):
        return False
    if teacher_id == 0:
        student_data: identity.Identity = identity.of(student_id)
        for favorability_flag in (True, False):
            base_chara_favorability_and_trust_common_settle(
                teacher_id,
                add_time,
                favorability_flag,
                0,
                abilities.ability(student_id)[32],
                change_data,
                student_data.cid,
            )
    return True


def _settle_pulled_by_player_teach(student_id: int, add_time: int) -> bool:
    """
    玩家授课时，在同一场景、与玩家同一时刻开始听课的学生这一侧的收益，按 _settle_class_student 结算。
    玩家开讲时已在听课的学生由 512 结算过，节次内由 settle_student_class_gain 的每节标记挡下第二份。
    变化记在一个用完即弃的新记录对象里，不显示。
    Keyword arguments:
    student_id -- 学生的角色id
    add_time -- 结算时间
    Return arguments:
    bool -- 她是否在听玩家这次授课。为 True 时这次听课已由这里结算完，调用方不再按课表结算
    """
    if (
        activity.behavior(0).behavior_id != constant.Behavior.TEACH
        or activity.position(0) != activity.position(student_id)
        or activity.behavior(0).start_time
        != activity.behavior(student_id).start_time
    ):
        return False
    ability_id, course_type = _teach_subject(0)
    scene_name = cache.scene_data[
        map_handle.get_map_system_path_str_for_list(
            activity.position(student_id)
        )
    ].scene_name
    _settle_class_student(
        0,
        student_id,
        scene_name,
        (ability_id, course_type, game_time.get_class_period(0)),
        add_time,
        game_type.CharacterStatusChange(),
    )
    return True


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TEACH_ADD_ADJUST
)
def handle_teach_add_just(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （教学用）结算一次授课，科目与课型由 _teach_subject 取。
    教师获得该科目的习得与经验。
    场景里正在听课的学生逐个交给 _settle_class_student 结算。
    NPC 教师授课时，结算了的学生重新排上听课；玩家授课时她们接着听手上的课。
    被玩家授课拉来、稍后才坐下的学生不在这里结算，由 557 结算。
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    from Script.System.Education_System import growth_handle
    from Script.Modules.gameplay_resolution import plan_queue

    ability_id, course_type = _teach_subject(character_id)

    # 教师自身的教学相长：加当节所授科目的习得与经验
    growth_handle.settle_teacher_class_gain(
        character_id, ability_id, add_time, change_data=change_data
    )

    # 教师开讲的节次：按教师自己的行为开始时刻取（NPC 教师只发给听课节次与它相同的学生，Plan 32 §3.8 L6）
    teacher_period = game_time.get_class_period(character_id)

    # 遍历当前场景的其他角色
    scene_path_str = map_handle.get_map_system_path_str_for_list(
        activity.position(character_id)
    )
    scene_data: game_type.Scene = cache.scene_data[scene_path_str]
    # 场景角色数大于等于2时进行检测
    if len(scene_data.character_list) >= 2:
        # 遍历当前角色列表
        for chara_id in scene_data.character_list:
            # 跳过自己
            if chara_id == character_id:
                continue
            else:
                # 如果对方在听课
                if (
                    activity.behavior(chara_id).behavior_id
                    == constant.Behavior.ATTENT_CLASS
                ):
                    if not _settle_class_student(
                        character_id,
                        chara_id,
                        scene_data.scene_name,
                        (ability_id, course_type, teacher_period),
                        add_time,
                        change_data,
                    ):
                        continue

                    # NPC 教师授课时该生重新开始听课，排进他的计划队列；
                    # 玩家授课时不排：排上的听课与玩家同一刻、同一场景开始，557 会把她当作被拉来的学生再结算一份
                    if character_id != 0 and not plan_queue.plan_has(
                        chara_id, constant.Behavior.ATTENT_CLASS
                    ):
                        plan_queue.plan_next(
                            chara_id,
                            constant.Behavior.ATTENT_CLASS,
                            activity.behavior(chara_id).duration,
                            interrupt=True,
                        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SELF_STUDY_ADD_ADJUST
)
def handle_self_study_add_just(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （自习用）本节无教师时的降级行为，按自习基础值增加习得与所选科目的经验，不受师生等级差影响
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    from Script.System.Education_System import (
        education_constant,
        growth_handle,
        schedule_handle,
    )

    now_course = schedule_handle.get_now_course(character_id)
    # 查不到课表就没有科目可自习，回落为学识（与玩家手动授课 512 共用 FALLBACK_SUBJECT_ABILITY，Plan 31）
    ability_id = education_constant.FALLBACK_SUBJECT_ABILITY
    if now_course is not None and now_course["ability_id"] > 0:
        ability_id = now_course["ability_id"]
    growth_handle.settle_student_class_gain(
        character_id,
        -1,
        ability_id,
        education_constant.COURSE_TYPE_THEORY,
        add_time,
        change_data=change_data,
        count_attend=now_course is not None,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ATTENT_CLASS_ADD_ADJUST
)
def handle_attent_class_add_just(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （听课用）学生开始听课时，从学生这一侧结算本节课的收益与出勤（Plan 22 第五轮加，Plan 31 §3.1 放宽）
    NPC 的行为结算发生在行为**开始**时，而且各按自己的时间线推进：玩家一步跨满一整节时，
    教师换教室（或先处理需求）晚到几分钟，
       学生这一步里早已听完这一节、走去了下一节，教师开讲那一刻的广播（512）发不到她，303 也不再把时间线在前的她拉回来。
       所以学生坐下听课时，本节授课教师判「能到岗」（class_ai.judge_teacher_available，学生当初就是按它坐下来等的）就按与广播完全相同的口径结算
       （科目、课型取课表，速度系数按师生等级差），不再要求教师此刻已在同一间教室、正在授课；
       settle_student_class_gain 按节次去重，教师随后开讲时的广播不会重复。
    代价：教师判能到岗、这一节却被临时叫走（比如被玩家拉进 H）时，学生照样拿到这节课，与「能到岗」判据的既有含义一致。
    不走这里的：课表上没排教师（那是自习，由 548 结算）、授课者是玩家（临时实操课，那是课堂 H，不是授课）、
       学生不在本节的教室里（她是在那间教室坐下来等教师的）。
    她在玩家授课的场景、与玩家同一时刻开始听课时，由 _settle_pulled_by_player_teach 结算，下面按课表的结算不再走。
    「这一节」按学生自己的行为开始时刻取；
    这一节已由实操课记过出勤的（sex_class_handle.settle_attend 也写去重标记，Plan 32 §3.8 L7），
       settle_student_class_gain 按去重不再结算，同一节只落一种记录
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    from Script.System.Education_System import (
        class_ai,
        growth_handle,
        schedule_handle,
    )

    if _settle_pulled_by_player_teach(character_id, add_time):
        return
    now_course = schedule_handle.get_now_course(character_id)
    if now_course is None or now_course["ability_id"] <= 0:
        return
    teacher_id = now_course["teacher_id"]
    # 没排教师（-1）与玩家的临时实操课（0）都不是这里的事
    if teacher_id <= 0 or not identity.exists(teacher_id):
        return
    classroom = now_course["classroom"]
    if not class_ai.judge_in_scene(character_id, classroom):
        return
    if not class_ai.judge_teacher_available(teacher_id, classroom):
        return
    growth_handle.settle_student_class_gain(
        character_id,
        teacher_id,
        now_course["ability_id"],
        now_course["course_type"],
        add_time,
        change_data=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SKIP_CLASS_ADD_ADJUST
)
def handle_skip_class_add_just(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （翘课用）置翘课flag并记下挂上的日期，小幅回复心情，本节不获得任何学习收益
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间（结算传进来的是行为结束时刻）
    """
    if not add_time:
        return
    start_time = activity.behavior(character_id).start_time or game_time.now()
    with growth.editing(character_id) as growth_data:
        assert growth_data is not None
        growth_data.skip_class_flag = True
        growth_data.skip_class_day = start_time.toordinal()
    # 翘课换来的那点轻松：抑郁小幅回落。不给任何学习收益，这是翘课的代价
    if 19 in status.of(character_id):
        status.set(
            character_id, 19, max(0, status.of(character_id)[19] - add_time)
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.INTERN_CLASS_ADD_ADJUST
)
def handle_intern_class_add_just(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （实习课用）找同场景中该岗位的在岗干员当导师，按师徒等级差学该岗位的能力
    实习课是三种个人式课型里唯一需要自己结算的：体育课与兴趣课执行的是自带效果串的既有行为，
       而实习课的导师执行的是**他自己的工作行为**，那串效果只给他自己发工作产出，
       里面没有任何把经验分给身边学徒的部分（对比理论课：教师的 teach 行为里有512效果专门结算全场学生）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    from Script.System.Education_System import (
        education_constant,
        growth_handle,
        schedule_handle,
    )

    now_course = schedule_handle.get_now_course(character_id)
    if (
        now_course is None
        or now_course["course_type"] != education_constant.COURSE_TYPE_INTERN
    ):
        return
    work_type_id = now_course["target"]
    if work_type_id not in game_config.config_work_type:
        return
    ability_id = game_config.config_work_type[work_type_id].ability_id
    if not ability_id:
        return
    # 导师 = 此刻和自己在同一场景、且正干着这个岗位的干员；找不到就是无人在岗，降级为见习
    mentor_id = schedule_handle.get_intern_mentor(character_id, work_type_id)
    growth_handle.settle_student_class_gain(
        character_id,
        mentor_id,
        ability_id,
        education_constant.COURSE_TYPE_INTERN,
        add_time,
        change_data=change_data,
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.CHECK_REPORT_CARD_ADD_ADJUST
)
def handle_check_report_card_add_just(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （检查成绩单用）有未查看的新成绩单时输出那一份并清除成绩单flag，否则输出该女儿本学期截至目前的各科成长与出勤；按成绩档位加好感与亲密
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    from Script.System.Education_System import (
        education_constant,
        semester_handle,
    )

    target_id = activity.target(character_id)
    if target_id == character_id or not identity.exists(target_id):
        return
    target_data: identity.Identity = identity.of(target_id)
    with growth.editing(target_id) as growth_data:
        assert growth_data is not None
        # 两条路径：有还没看过的新成绩单（学期结算时**冻结**的那一份，report_card_flag 置着）就发那份；
        #    否则现算一份本学期「截至目前」的（Plan 27 §3.6，用户拍板）。此前以「有没有历史」判：有过一份成绩单之后，
        #    学期中途再查永远只给上一份，看不到本学期的情况，分档口上夸的也是上学期。
        # 不能因为还没有成绩单就什么都不显示：指令本身没有「有成绩单」这条前提，
        #    玩家学期中途照样能用，那时也该给他看到东西
        report_data = semester_handle.get_last_report_card(target_id)
        finished = growth_data.report_card_flag and bool(report_data)
        if not finished:
            report_data = semester_handle.build_report_card(target_id)
        now_draw = draw.NormalDraw()
        now_draw.width = normal_config.config_normal.text_width
        now_draw.text = semester_handle.get_report_card_text(
            target_id, report_data, finished
        )
        # 更早的学期不在这里翻——指令是一段式的打印，翻页要有面板才做得了。
        #    发的是冻结那一份时它自己就是历史里最新的一份；给的是本学期截至目前时，历史里的每一份都更早（Plan 27 §3.6）
        history_count = len(semester_handle.get_report_card_history(target_id))
        earlier_count = history_count - 1 if finished else history_count
        if earlier_count > 0:
            now_draw.text += _(
                "（更早的 {0} 个学期可以在教育管理系统的养成总览里翻看）\n"
            ).format(earlier_count)
        now_draw.draw()

        # 成绩档位越高，检查成绩单时的反馈越正面
        # 档位已经把「出勤率 + 有没有真学出东西」并进一个口径了，
        #    这里再单写一遍出勤率阈值，会与成绩单正文里的评定对不上
        base_chara_favorability_and_trust_common_settle(
            character_id,
            add_time,
            True,
            0,
            abilities.ability(target_id)[32],
            change_data,
            target_data.cid,
        )
        if report_data.get("grade", education_constant.REPORT_GRADE_POOR) in {
            education_constant.REPORT_GRADE_EXCELLENT,
            education_constant.REPORT_GRADE_GOOD,
        }:
            base_chara_state_common_settle(
                target_id,
                add_time,
                13,
                change_data_to_target_change=change_data,
            )
        if finished:
            growth_data.report_card_flag = False


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.BAGGING_AND_MOVING_ADD_ADJUST
)
def handle_bagging_and_moving_add_just(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （装袋搬走用）交互对象获得装袋搬走flag，玩家增加搬运人id，对方离线
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    # 获取角色数据
    target_data: identity.Identity = identity.of(activity.target(character_id))
    # 玩家数据结算
    flags.set(character_id, bagging_chara_id=activity.target(character_id))
    # 对方数据结算
    flags.set(target_data.cid, be_bagged=True)
    handle_chara_off_line(
        activity.target(character_id), add_time, change_data, now_time
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.RELEASE_FROM_BAG_ADD_ADJUST
)
def handle_release_from_bag_add_just(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （从袋中放出来）交互对象失去装袋搬走flag，玩家失去搬运人id，对方上线
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    # 获取角色数据
    target_data: identity.Identity = identity.of(activity.target(character_id))
    # 玩家数据结算
    flags.set(character_id, bagging_chara_id=0)
    # 对方数据结算
    flags.set(target_data.cid, be_bagged=False)
    handle_chara_on_line(
        activity.target(character_id), add_time, change_data, now_time
    )
    # 如果当时是时间停止H中，则刷新时停状态
    if handle_premise.handle_time_stop_on(character_id):
        flags.set(target_data.cid, unconscious_h=3)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PUT_INTO_PRISON_ADD_ADJUST
)
def handle_put_into_prison_add_just(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （投入监牢用）被搬运对象上线，成为囚犯并结算，玩家失去搬运人id
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    from Script.UI.Panel import confinement_and_training

    if not add_time:
        return
    # 获取角色数据
    target_id = flags.get(0, "bagging_chara_id")
    # 玩家数据结算
    flags.set(0, bagging_chara_id=0)
    # 对方位置结算
    activity.set_position(target_id, activity.position(0))
    activity.update_behavior(
        target_id,
        move_src=activity.position(0),
        move_target=activity.position(0),
    )
    # 对方数据结算
    confinement_and_training.chara_become_prisoner(target_id)
    # 角色上线
    handle_chara_on_line(target_id, add_time, change_data, now_time)
    # 如果当时是时间停止H中，则刷新时停状态
    if handle_premise.handle_time_stop_on(character_id):
        flags.set(target_id, unconscious_h=3)
    # 囚犯成就
    achievement_panel.achievement_flow(_("囚犯"))


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SET_FREE_ADD_ADJUST
)
def handle_set_free_add_just(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （解除囚禁）交互对象失去监禁flag，从囚犯数据中删除
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    # 获取角色数据
    target_data: identity.Identity = identity.of(activity.target(character_id))
    flags.set(target_data.cid, imprisonment=False)
    from Script.System.Dormitory_System import common as dormitory_common

    # 回到旧宿舍
    dormitory_common.restore_character_dormitory(activity.target(character_id))
    # 从囚犯数据中删除
    prison.release(activity.target(character_id))
    # 刷新衣服
    clothing.get_cloth_from_dormitory_locker(activity.target(character_id))


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.EAT_ADD_ADJUST
)
def handle_eat_add_just(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （进食）食物结算。会根据有无交互目标，食物的调味来自动判别食用对象和结算内容
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    from Script.System.Cooking_System.food_bag_panel import (
        calculate_food_effects,
    )
    from Script.System.Sex_System.drunk_sex_common import add_drunk_point

    # 获取角色数据

    # 获取食物数据
    now_food = activity.behavior(character_id).target_food
    food_seasoning = now_food.special_seasoning if now_food is not None else 0
    food_quality = now_food.quality if now_food is not None else 1
    food_maker = now_food.maker if now_food is not None else ""
    recipe_id = now_food.recipe if now_food is not None else 0
    if recipe_id not in game_config.config_recipes:
        return
    recipe_data = game_config.config_recipes[recipe_id]
    if recipe_data.type in {0, 1, 5}:
        eat_flag = True
    else:
        eat_flag = False
    # 判断是谁要吃食物
    eat_food_chara_id_list = []
    if food_seasoning == 0:
        eat_food_chara_id_list.append(character_id)
        if activity.target(character_id) != character_id:
            eat_food_chara_id_list.append(activity.target(character_id))
    else:
        eat_food_chara_id_list.append(activity.target(character_id))
    # 判断是否是玩家制作的
    pl_make_flag = False
    if food_maker == identity.of(0).name:
        pl_make_flag = True

    # 计算食物效果
    state_add, hpmp_add = calculate_food_effects(character_id, add_time)

    # 删除该食物
    handle_delete_food(
        character_id,
        add_time=add_time,
        change_data=change_data,
        now_time=now_time,
    )
    # 对要吃食物的人进行结算
    for chara_id in eat_food_chara_id_list:
        target_data: identity.Identity = identity.of(chara_id)
        change_data.target_change.setdefault(
            target_data.cid, game_type.TargetChange()
        )
        target_change = change_data.target_change[target_data.cid]

        # NPC吃的时候
        if chara_id:
            # 加好感
            base_chara_favorability_and_trust_common_settle(
                character_id, state_add, True, 0, 0, change_data, chara_id
            )
            # 加好意
            base_chara_state_common_settle(
                chara_id,
                state_add * 4,
                11,
                0,
                change_data_to_target_change=change_data,
            )
            # 玩家做的饭的情况下，额外加信赖
            if pl_make_flag:
                base_chara_favorability_and_trust_common_settle(
                    character_id, state_add, False, 0, 0, change_data, chara_id
                )
            # 高品质食物
            if food_quality >= 7:
                # 变为好心情
                handle_mood_to_good(chara_id, add_time, change_data, now_time)
                # 增加口喉快感
                base_chara_state_common_settle(
                    chara_id,
                    state_add * 3,
                    21,
                    0,
                    change_data_to_target_change=change_data,
                )
                # 增加心理快感
                base_chara_state_common_settle(
                    chara_id,
                    state_add * 2,
                    23,
                    0,
                    change_data_to_target_change=change_data,
                )

        # 仅食物加体力
        if eat_flag:
            handle_add_small_hit_point(
                chara_id,
                add_time=hpmp_add,
                change_data=target_change,
                now_time=now_time,
            )
        # 都加气力
        handle_add_small_mana_point(
            chara_id,
            add_time=hpmp_add,
            change_data=target_change,
            now_time=now_time,
        )
        # 食物结算饥饿值，饮品结算尿意值
        if eat_flag:
            handle_hunger_point_zero(
                chara_id,
                add_time=add_time,
                change_data=target_change,
                now_time=now_time,
            )
        else:
            handle_add_small_urinate_point(
                chara_id,
                add_time=add_time,
                change_data=target_change,
                now_time=now_time,
            )
        # 清除进食状态
        handle_eat_food_flag_to_0(
            chara_id,
            add_time=add_time,
            change_data=target_change,
            now_time=now_time,
        )

        # 酒类食物
        if recipe_data.type == 3:
            # 增加醉酒值
            add_drunk_point(chara_id, food=now_food)
            # 增加饮酒经验
            base_chara_experience_common_settle(
                chara_id, 94, change_data=target_change
            )

        # 精液食物则将精液加到口腔污浊，并加精液经验
        if food_seasoning in {11, 12}:
            # 加精液经验和饮精经验
            base_chara_experience_common_settle(
                chara_id, 24, change_data=target_change
            )
            base_chara_experience_common_settle(
                chara_id, 25, change_data=target_change
            )
            # 获取精液量
            semen_ml = (
                now_food.special_seasoning_amount if now_food is not None else 0
            )
            # 加精液到口腔
            temp_position = h_meters.shoot_position()
            h_meters.set_shoot_position(2)  # 口腔
            ejaculation_panel.update_semen_dirty(
                chara_id, 2, 0, semen_ml, update_shoot_position_flag=False
            )
            h_meters.set_shoot_position(temp_position)
            # 登记精液进入口腔，使本次进食若因高品质快感而绝顶时，
            # 由二段绝顶结算联动饮精绝顶（素质31）与饮精绝顶经验（111）
            if semen_ml > 0:
                h_state.set(target_data.cid, shoot_position_body=2)
        # 药物食物则获得对应药物效果
        elif food_seasoning == 102:  # 事后避孕药
            handle_target_no_pregnancy_from_last_h(
                0, add_time=add_time, change_data=change_data, now_time=now_time
            )
        elif food_seasoning == 103:  # 媚药
            handle_target_add_huge_desire_and_submit(
                0, add_time=add_time, change_data=change_data, now_time=now_time
            )
        elif food_seasoning == 105:  # 一次性利尿剂
            handle_target_add_urinate(
                0, add_time=add_time, change_data=change_data, now_time=now_time
            )
        elif food_seasoning == 106:  # 持续性利尿剂
            handle_target_diuretics_on(
                0, add_time=add_time, change_data=change_data, now_time=now_time
            )
        elif food_seasoning == 107:  # 安眠药
            handle_target_add_tired_tosleep(
                0, add_time=add_time, change_data=change_data, now_time=now_time
            )
        elif food_seasoning == 108:  # 排卵促进药
            handle_target_add_pregnancy_chance(
                0, add_time=add_time, change_data=change_data, now_time=now_time
            )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ADD_HPMP_MAX
)
def handle_add_hpmp_max(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （锻炼身体用）增加体力气力上限
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    character_data: identity.Identity = identity.of(character_id)
    if activity.dead(character_id):
        return
    # 设施效率
    facility_adjust = basement.calc_facility_efficiency(9)

    # 指数曲线，x = [1000, 2000, 4000, 5000, 10000]， y = [50, 25, 15, 10, 5]
    add_hp = 128.961 * math.exp(
        -0.0016 * needs.of(character_id)["hit_max"]
    ) + 28.578 * math.exp(-1.8453e-04 * needs.of(character_id)["hit_max"])
    add_mp = 128.961 * math.exp(
        -0.0016 * needs.of(character_id)["mana_max"]
    ) + 28.578 * math.exp(-1.8453e-04 * needs.of(character_id)["mana_max"])

    # 最终增加值
    add_hp = int(add_hp * facility_adjust * random.uniform(0.8, 1.2))
    add_mp = int(add_mp * facility_adjust * random.uniform(0.8, 1.5))
    # 增加上限
    needs.add(character_id, "hit_max", add_hp)
    needs.add(character_id, "mana_max", add_mp)
    # 如果和玩家位于同一地点，则输出提示信息
    if activity.position(character_id) == activity.position(0):
        now_draw = draw.NormalDraw()
        now_draw.text = _("\n{0}的体力上限增加{1},气力上限增加{2}").format(
            character_data.name, str(add_hp), str(add_mp)
        )
        now_draw.width = width
        now_draw.draw()
    # 交互对象也同样#
    if activity.target(character_id) != character_id:
        target_data: identity.Identity = identity.of(
            activity.target(character_id)
        )
        add_hp = 128.961 * math.exp(
            -0.0016 * needs.of(target_data.cid)["hit_max"]
        ) + 28.578 * math.exp(
            -1.8453e-04 * needs.of(target_data.cid)["hit_max"] * 2
        )
        add_mp = 128.961 * math.exp(
            -0.0016 * needs.of(target_data.cid)["mana_max"]
        ) + 28.578 * math.exp(
            -1.8453e-04 * needs.of(target_data.cid)["mana_max"] * 2
        )
        add_hp = int(add_hp * facility_adjust * random.uniform(0.8, 1.2))
        add_mp = int(add_mp * facility_adjust * random.uniform(0.8, 1.5))
        needs.add(target_data.cid, "hit_max", add_hp)
        needs.add(target_data.cid, "mana_max", add_mp)
        # 如果和玩家位于同一地点，则输出提示信息
        if activity.position(character_id) == activity.position(0):
            now_draw = draw.NormalDraw()
            now_draw.text = _(
                "\n{0}的体力上限增加{1},气力上限增加{2}\n"
            ).format(target_data.name, str(add_hp), str(add_mp))
            now_draw.width = width
            now_draw.draw()
    else:
        now_draw = draw.NormalDraw()
        now_draw.text = "\n"
        now_draw.width = 1
        now_draw.draw()
    # 结算成就
    if character_id == 0:
        achievement_panel.achievement_flow(_("锻炼"))


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SING_ADD_ADJUST
)
def handle_sing_add_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （唱歌用）根据自己的音乐技能进行好感度、信赖、好意、恐怖、抑郁、反感调整
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    ability = abilities.ability(character_id)
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))

    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if character_id != 0 and activity.target(character_id) != 0:
            return
        # 获取调整值#
        ability.setdefault(44, 0)
        # 如果水平在2级及以下则扣好感信赖，如果是NPC执行则跳过
        good_flag = True
        if ability[44] <= 2 and character_id == 0:
            good_flag = False
        adjust = handle_ability.get_ability_adjust(ability[44])

        # 对在场的全部角色起效
        for chara_id in cache.scene_data[
            map_handle.get_map_system_path_str_for_list(
                activity.position(character_id)
            )
        ].character_list:
            # 跳过玩家自己
            if chara_id == character_id:
                continue
            # 跳过无意识的角色
            if handle_premise.handle_unconscious_flag_ge_1(chara_id):
                continue
            # 跳过睡觉中的角色
            if handle_premise.handle_action_sleep(chara_id):
                continue
            target_data = identity.of(chara_id)

            change_data.target_change.setdefault(
                target_data.cid, game_type.TargetChange()
            )
            target_change: game_type.TargetChange = change_data.target_change[
                target_data.cid
            ]
            # 好感与信赖变化#
            if good_flag:
                base_chara_favorability_and_trust_common_settle(
                    character_id,
                    add_time,
                    True,
                    0,
                    adjust,
                    change_data,
                    chara_id,
                )
                base_chara_favorability_and_trust_common_settle(
                    character_id,
                    add_time,
                    False,
                    0,
                    adjust,
                    change_data,
                    chara_id,
                )
            else:
                base_chara_favorability_and_trust_common_settle(
                    character_id,
                    add_time,
                    True,
                    0,
                    adjust - 1.3,
                    change_data,
                    chara_id,
                )
                base_chara_favorability_and_trust_common_settle(
                    character_id,
                    add_time,
                    False,
                    0,
                    adjust - 1.3,
                    change_data,
                    chara_id,
                )

            # 好意变化#
            status.setdefault(target_data.cid, 11, 0)
            now_lust = status.of(target_data.cid)[11]
            now_lust_multiple = 30
            now_add_lust: float = add_time + now_lust_multiple
            if good_flag:
                now_add_lust *= adjust
                now_add_lust += now_lust / 10
            else:
                now_add_lust *= adjust - 1
            now_add_lust = int(now_add_lust)
            status.add(target_data.cid, 11, now_add_lust, max=99999)
            change_data.target_change.setdefault(
                target_data.cid, game_type.TargetChange()
            )
            target_change = change_data.target_change[target_data.cid]
            target_change.status_data.setdefault(11, 0)
            target_change.status_data[11] += now_add_lust

            # 恐怖、抑郁、反感变化
            if not good_flag:
                for i in {18, 19, 20}:
                    now_lust = status.of(target_data.cid)[i]
                    now_lust_multiple = 100
                    now_add_lust = add_time + now_lust_multiple
                    if good_flag:
                        now_add_lust *= 1.5 - adjust
                    else:
                        now_add_lust *= 5 - adjust
                        now_add_lust += now_lust / 10
                    now_add_lust = int(now_add_lust)
                    status.add(target_data.cid, i, now_add_lust, max=99999)
                    change_data.target_change.setdefault(
                        target_data.cid, game_type.TargetChange()
                    )
                    target_change = change_data.target_change[target_data.cid]
                    target_change.status_data.setdefault(i, 0)
                    target_change.status_data[i] += now_add_lust


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PLAY_INSTRUMENT_ADD_ADJUST
)
def handle_play_instrument_add_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （演奏乐器用）根据自己的音乐技能进行好感度、信赖、好意、恐怖、抑郁、反感调整
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    ability = abilities.ability(character_id)
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    # print(f"debug 演奏，角色 = {character_data.name}，目标= {target_data.name}")
    # 对着自己演奏乐器不进行该结算
    if activity.target(character_id) == character_id:
        return
    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if character_id != 0 and activity.target(character_id) != 0:
            return
        # 获取调整值#
        ability.setdefault(44, 0)
        # 如果水平在2级及以下则扣好感信赖，如果是NPC执行则跳过
        good_flag = True
        if ability[44] <= 2 and character_id == 0:
            good_flag = False
        adjust = handle_ability.get_ability_adjust(ability[44])

        # 对在场的全部角色起效
        for chara_id in cache.scene_data[
            map_handle.get_map_system_path_str_for_list(
                activity.position(character_id)
            )
        ].character_list:
            # 跳过玩家自己
            if chara_id == character_id:
                continue
            # 跳过无意识的角色
            if handle_premise.handle_unconscious_flag_ge_1(chara_id):
                continue
            # 跳过睡觉中的角色
            if handle_premise.handle_action_sleep(chara_id):
                continue
            target_data = identity.of(chara_id)

            change_data.target_change.setdefault(
                target_data.cid, game_type.TargetChange()
            )
            target_change: game_type.TargetChange = change_data.target_change[
                target_data.cid
            ]

            # 好感与信赖变化#
            if good_flag:
                base_chara_favorability_and_trust_common_settle(
                    character_id,
                    add_time,
                    True,
                    0,
                    adjust * 2,
                    change_data,
                    chara_id,
                )
                base_chara_favorability_and_trust_common_settle(
                    character_id,
                    add_time,
                    False,
                    0,
                    adjust * 2,
                    change_data,
                    chara_id,
                )
            else:
                base_chara_favorability_and_trust_common_settle(
                    character_id,
                    add_time,
                    True,
                    0,
                    (adjust - 1.3) * 2,
                    change_data,
                    chara_id,
                )
                base_chara_favorability_and_trust_common_settle(
                    character_id,
                    add_time,
                    False,
                    0,
                    (adjust - 1.3) * 2,
                    change_data,
                    chara_id,
                )

            # 好意变化#
            status.setdefault(target_data.cid, 11, 0)
            now_lust = status.of(target_data.cid)[11]
            now_lust_multiple = 30
            now_add_lust: float = add_time + now_lust_multiple
            if good_flag:
                now_add_lust *= adjust
                now_add_lust += now_lust / 8
            else:
                now_add_lust *= adjust - 1
            now_add_lust = int(now_add_lust)
            status.add(target_data.cid, 11, now_add_lust, max=99999)
            change_data.target_change.setdefault(
                target_data.cid, game_type.TargetChange()
            )
            target_change = change_data.target_change[target_data.cid]
            target_change.status_data.setdefault(11, 0)
            target_change.status_data[11] += now_add_lust

            # 恐怖、抑郁、反感变化
            if not good_flag:
                for i in {18, 19, 20}:
                    now_lust = status.of(target_data.cid)[i]
                    now_lust_multiple = 150
                    now_add_lust = add_time + now_lust_multiple
                    if good_flag:
                        now_add_lust *= 1.5 - adjust
                    else:
                        now_add_lust *= 5 - adjust
                        now_add_lust += now_lust / 8
                    now_add_lust = int(now_add_lust)
                    status.add(target_data.cid, i, now_add_lust, max=99999)
                    change_data.target_change.setdefault(
                        target_data.cid, game_type.TargetChange()
                    )
                    target_change = change_data.target_change[target_data.cid]
                    target_change.status_data.setdefault(i, 0)
                    target_change.status_data[i] += now_add_lust


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TECH_ADD_S_ADJUST
)
def handle_tech_add_s_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    根据发起者的技巧技能和交互对象的感度，和交互对象的感度，对交互对象进行S快、欲情调整
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if activity.dead(target_data.cid):
            return
        # 快感
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            0,
            50,
            ability_level=abilities.ability(character_id)[30],
            change_data_to_target_change=change_data,
        )
        # 欲情
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            12,
            50,
            ability_level=abilities.ability(target_data.cid)[0],
            change_data_to_target_change=change_data,
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TECH_ADD_B_ADJUST
)
def handle_tech_add_b_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    根据发起者的技巧技能和交互对象的感度，对交互对象进行B快、欲情调整
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if activity.dead(target_data.cid):
            return
        # 快感
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            1,
            50,
            ability_level=abilities.ability(character_id)[30],
            change_data_to_target_change=change_data,
        )
        # 欲情
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            12,
            50,
            ability_level=abilities.ability(target_data.cid)[1],
            change_data_to_target_change=change_data,
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TECH_ADD_C_ADJUST
)
def handle_tech_add_c_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    根据发起者的技巧技能和交互对象的感度，对交互对象进行C快、欲情调整
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if activity.dead(target_data.cid):
            return
        # 快感
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            2,
            50,
            ability_level=abilities.ability(character_id)[30],
            change_data_to_target_change=change_data,
        )
        # 欲情
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            12,
            50,
            ability_level=abilities.ability(target_data.cid)[2],
            change_data_to_target_change=change_data,
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TECH_ADD_P_ADJUST
)
def handle_tech_add_p_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    根据发起者的技巧技能和交互对象的感度，对交互对象进行P快、欲情调整
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    ability = abilities.ability(character_id)
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if activity.dead(target_data.cid):
            return
        # 获取调整值#
        ability.setdefault(19, 0)
        abi_adjust = handle_ability.get_ability_adjust(ability[30])
        feel_adjust = handle_ability.get_ability_adjust(ability[3])
        adjust = math.sqrt(abi_adjust * feel_adjust)
        # P快变化#
        status.setdefault(target_data.cid, 3, 0)
        now_lust = status.of(target_data.cid)[3]
        now_lust_multiple = 50
        now_add_lust: float = add_time + now_lust_multiple
        now_add_lust *= adjust
        now_add_lust += now_lust / 8
        now_add_lust = int(now_add_lust)
        h_meters.add(target_data.cid, "eja", now_add_lust)
        # change_data.target_change.setdefault(target_data.cid, game_type.TargetChange())
        # target_change: game_type.TargetChange = change_data.target_change[target_data.cid]
        # target_change.status_data.setdefault(3, 0)
        # target_change.status_data[3] += now_add_lust
        action_info.set(target_data.cid, "last_eaj_add_time", now_time)
        # 欲情变化#
        status.setdefault(target_data.cid, 12, 0)
        now_lust = status.of(target_data.cid)[12]
        now_lust_multiple = 50
        now_add_lust = add_time + now_lust_multiple
        now_add_lust *= adjust
        now_add_lust += now_lust / 6
        now_add_lust = int(now_add_lust)
        status.add(target_data.cid, 12, now_add_lust, max=99999)
        change_data.target_change.setdefault(
            target_data.cid, game_type.TargetChange()
        )
        target_change: game_type.TargetChange = change_data.target_change[
            target_data.cid
        ]
        target_change.status_data.setdefault(12, 0)
        target_change.status_data[12] += now_add_lust


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TECH_ADD_V_ADJUST
)
def handle_tech_add_v_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    根据发起者的技巧技能和交互对象的感度，对交互对象进行V快、欲情调整
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if activity.dead(target_data.cid):
            return
        # 快感
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            4,
            50,
            ability_level=abilities.ability(character_id)[30],
            change_data_to_target_change=change_data,
        )
        # 欲情
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            12,
            50,
            ability_level=abilities.ability(target_data.cid)[4],
            change_data_to_target_change=change_data,
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TECH_ADD_A_ADJUST
)
def handle_tech_add_a_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    根据发起者的技巧技能和交互对象的感度，对交互对象进行A快、欲情调整
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if activity.dead(target_data.cid):
            return
        # 快感
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            5,
            50,
            ability_level=abilities.ability(character_id)[30],
            change_data_to_target_change=change_data,
        )
        # 欲情
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            12,
            50,
            ability_level=abilities.ability(target_data.cid)[5],
            change_data_to_target_change=change_data,
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TECH_ADD_U_ADJUST
)
def handle_tech_add_u_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    根据发起者的技巧技能和交互对象的感度，对交互对象进行U快、欲情调整
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if activity.dead(target_data.cid):
            return
        # 快感
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            6,
            50,
            ability_level=abilities.ability(character_id)[30],
            change_data_to_target_change=change_data,
        )
        # 欲情
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            12,
            50,
            ability_level=abilities.ability(target_data.cid)[6],
            change_data_to_target_change=change_data,
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TECH_ADD_W_ADJUST
)
def handle_tech_add_w_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    根据发起者的技巧技能和交互对象的感度，对交互对象进行W快、欲情调整
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if activity.dead(target_data.cid):
            return
        # 快感
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            7,
            50,
            ability_level=abilities.ability(character_id)[30],
            change_data_to_target_change=change_data,
        )
        # 欲情
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            12,
            50,
            ability_level=abilities.ability(target_data.cid)[7],
            change_data_to_target_change=change_data,
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TECH_ADD_M_ADJUST
)
def handle_tech_add_m_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    根据发起者的技巧技能和交互对象的感度，对交互对象进行M快、欲情调整
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if activity.dead(target_data.cid):
            return
        # 快感
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            21,
            50,
            ability_level=abilities.ability(character_id)[30],
            change_data_to_target_change=change_data,
        )
        # 欲情
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            12,
            50,
            ability_level=abilities.ability(target_data.cid)[7],
            change_data_to_target_change=change_data,
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TECH_ADD_F_ADJUST
)
def handle_tech_add_f_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    根据发起者的技巧技能和交互对象的感度，对交互对象进行F快、欲情调整
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if activity.dead(target_data.cid):
            return
        # 快感
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            22,
            50,
            ability_level=abilities.ability(character_id)[30],
            change_data_to_target_change=change_data,
        )
        # 欲情
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            12,
            50,
            ability_level=abilities.ability(target_data.cid)[7],
            change_data_to_target_change=change_data,
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TECH_ADD_PL_P_ADJUST
)
def handle_tech_add_pl_p_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    根据对交互对象的技巧技能对发起者进行P快调整
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    ability = abilities.ability(target_data.cid)
    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if activity.dead(target_data.cid):
            return
        # 获取调整值#
        ability.setdefault(19, 0)
        adjust = handle_ability.get_ability_adjust(ability[30])
        # P快变化#
        status.setdefault(character_id, 3, 0)
        now_lust = status.of(character_id)[3]
        now_lust_multiple = 50
        now_add_lust: float = add_time + now_lust_multiple
        now_add_lust *= adjust
        now_add_lust += now_lust / 8
        now_add_lust = int(now_add_lust)
        h_meters.add(character_id, "eja", now_add_lust)
        change_data.eja_point += now_add_lust
        action_info.set(character_id, "last_eaj_add_time", now_time)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_LUBRICATION_ADJUST_ADD_PAIN
)
def handle_target_lubrication_adjust_add_pain(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    根据交互对象的润滑情况对其进行苦痛调整
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if activity.dead(target_data.cid):
            return
        # 获取调整值#
        status.setdefault(target_data.cid, 8, 0)
        pain_adjust = attr_calculation.get_pain_adjust(
            num.whole(status.of(target_data.cid)[8])
        )
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            17,
            ability_level=abilities.ability(target_data.cid)[15],
            extra_adjust=pain_adjust,
            change_data_to_target_change=change_data,
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_V_ADJUST_ADD_PAIN
)
def handle_target_v_adjust_add_pain(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    根据交互对象的V属性(润滑+腰技+扩张+阴茎大小)对其进行苦痛调整
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if activity.dead(target_data.cid):
            return
        # 润滑调整
        status.setdefault(target_data.cid, 8, 0)
        pain_adjust = attr_calculation.get_pain_adjust(
            num.whole(status.of(target_data.cid)[8])
        )
        # 腰技的调整
        waist_tech = abilities.ability(character_id)[76]
        waist_adjust = handle_ability.get_ability_adjust(waist_tech) - 1

        # 扩长等级相对于阴茎等级的调整，因为阴茎等级默认为1，所以再加1
        jj_size = player_ability.get(character_id, "jj_size")
        dilate_level = abilities.ability(target_data.cid)[9]
        final_level = dilate_level - jj_size + 1
        size_adjust = attr_calculation.get_pain_adjust(
            final_level, level_flag=True
        )

        # 最终调整值
        final_adjust = max(pain_adjust - waist_adjust, 0) * size_adjust

        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            17,
            ability_level=abilities.ability(target_data.cid)[15],
            extra_adjust=final_adjust,
            change_data_to_target_change=change_data,
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_A_ADJUST_ADD_PAIN
)
def handle_target_a_adjust_add_pain(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    根据交互对象的A属性(润滑+腰技+扩张+阴茎大小)对其进行苦痛调整
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if activity.dead(target_data.cid):
            return
        # 润滑调整
        status.setdefault(target_data.cid, 8, 0)
        pain_adjust = attr_calculation.get_pain_adjust(
            num.whole(status.of(target_data.cid)[8])
        )
        # 腰技的调整
        waist_tech = abilities.ability(character_id)[76]
        waist_adjust = handle_ability.get_ability_adjust(waist_tech) - 1

        # 扩长等级相对于阴茎等级的调整，因为阴茎等级默认为1，所以再加1
        jj_size = player_ability.get(character_id, "jj_size")
        dilate_level = abilities.ability(target_data.cid)[10]
        final_level = dilate_level - jj_size + 1
        size_adjust = attr_calculation.get_pain_adjust(
            final_level, level_flag=True
        )

        # 最终调整值
        final_adjust = max(pain_adjust - waist_adjust, 0) * size_adjust

        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            17,
            ability_level=abilities.ability(target_data.cid)[15],
            extra_adjust=final_adjust,
            change_data_to_target_change=change_data,
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_U_ADJUST_ADD_PAIN
)
def handle_target_u_adjust_add_pain(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    根据交互对象的U属性(润滑+腰技+扩张+阴茎大小)对其进行苦痛调整
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if activity.dead(target_data.cid):
            return
        # 润滑调整
        status.setdefault(target_data.cid, 8, 0)
        pain_adjust = attr_calculation.get_pain_adjust(
            num.whole(status.of(target_data.cid)[8])
        )
        # 腰技的调整
        waist_tech = abilities.ability(character_id)[76]
        waist_adjust = handle_ability.get_ability_adjust(waist_tech) - 1

        # 扩长等级相对于阴茎等级的调整，因为尿道非常小，所以相对于V和A，初始+1-4 = -3
        jj_size = player_ability.get(character_id, "jj_size")
        dilate_level = abilities.ability(target_data.cid)[11]
        final_level = dilate_level - jj_size - 3
        size_adjust = attr_calculation.get_pain_adjust(
            final_level, level_flag=True
        )

        # 最终调整值
        final_adjust = max(pain_adjust - waist_adjust, 0) * size_adjust

        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            17,
            base_value=1000,
            ability_level=abilities.ability(target_data.cid)[15],
            extra_adjust=final_adjust,
            change_data_to_target_change=change_data,
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_W_ADJUST_ADD_PAIN
)
def handle_target_w_adjust_add_pain(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    根据交互对象的W属性(润滑+腰技+扩张+阴茎大小)对其进行苦痛调整
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if activity.dead(target_data.cid):
            return
        # 润滑调整
        status.setdefault(target_data.cid, 8, 0)
        pain_adjust = attr_calculation.get_pain_adjust(
            num.whole(status.of(target_data.cid)[8])
        )
        # 腰技的调整
        waist_tech = abilities.ability(character_id)[76]
        waist_adjust = handle_ability.get_ability_adjust(waist_tech) - 1

        # 扩长等级相对于阴茎等级的调整，因为子宫较小，所以相对于V和A，初始+1-2=-1
        jj_size = player_ability.get(character_id, "jj_size")
        dilate_level = abilities.ability(target_data.cid)[12]
        final_level = dilate_level - jj_size - 1
        size_adjust = attr_calculation.get_pain_adjust(
            final_level, level_flag=True
        )

        # 如果是子宫奸，则进一步调整
        if h_state.get(character_id, "current_womb_sex_position") == 2:
            size_adjust *= 3

        # 最终调整值
        final_adjust = max(pain_adjust - waist_adjust, 0) * size_adjust

        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            17,
            base_value=100,
            ability_level=abilities.ability(target_data.cid)[15],
            extra_adjust=final_adjust,
            change_data_to_target_change=change_data,
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_V_ADJUST_ADD_BY_SEX
)
def handle_target_v_adjust_add_by_sex(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    根据发起者的技巧+腰技+阴茎大小对交互目标进行V快、欲情调整
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if activity.dead(target_data.cid):
            return

        # 阴茎大小的调整
        jj_size = player_ability.get(character_id, "jj_size")
        size_adjust = handle_ability.get_ability_adjust(jj_size) / 2
        # 腰技的调整
        waist_tech = abilities.ability(character_id)[76]
        waist_adjust = handle_ability.get_ability_adjust(waist_tech) / 2
        # 最终调整值
        extra_adjust = size_adjust + waist_adjust

        # 快感
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            4,
            50,
            ability_level=abilities.ability(character_id)[30],
            extra_adjust=extra_adjust,
            change_data_to_target_change=change_data,
        )
        # 欲情
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            12,
            50,
            ability_level=abilities.ability(target_data.cid)[4],
            extra_adjust=extra_adjust,
            change_data_to_target_change=change_data,
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_A_ADJUST_ADD_BY_SEX
)
def handle_target_a_adjust_add_by_sex(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    根据发起者的技巧+腰技+阴茎大小对交互目标进行A快、欲情调整
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if activity.dead(target_data.cid):
            return

        # 阴茎大小的调整
        jj_size = player_ability.get(character_id, "jj_size")
        size_adjust = handle_ability.get_ability_adjust(jj_size) / 2
        # 腰技的调整
        waist_tech = abilities.ability(character_id)[76]
        waist_adjust = handle_ability.get_ability_adjust(waist_tech) / 2
        # 最终调整值
        extra_adjust = size_adjust + waist_adjust

        # 快感
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            5,
            50,
            ability_level=abilities.ability(character_id)[30],
            extra_adjust=extra_adjust,
            change_data_to_target_change=change_data,
        )
        # 欲情
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            12,
            50,
            ability_level=abilities.ability(target_data.cid)[5],
            extra_adjust=size_adjust,
            change_data_to_target_change=change_data,
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_U_ADJUST_ADD_BY_SEX
)
def handle_target_u_adjust_add_by_sex(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    根据发起者的技巧+腰技+阴茎大小对交互目标进行U快、欲情调整
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if activity.dead(target_data.cid):
            return

        # 阴茎大小的调整
        jj_size = player_ability.get(character_id, "jj_size")
        size_adjust = handle_ability.get_ability_adjust(jj_size) / 2
        # 腰技的调整
        waist_tech = abilities.ability(character_id)[76]
        waist_adjust = handle_ability.get_ability_adjust(waist_tech) / 2
        # 最终调整值
        extra_adjust = size_adjust + waist_adjust

        # 快感
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            6,
            50,
            ability_level=abilities.ability(character_id)[30],
            extra_adjust=extra_adjust,
            change_data_to_target_change=change_data,
        )
        # 欲情
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            12,
            50,
            ability_level=abilities.ability(target_data.cid)[6],
            extra_adjust=extra_adjust,
            change_data_to_target_change=change_data,
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_W_ADJUST_ADD_BY_SEX
)
def handle_target_w_adjust_add_by_sex(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    根据发起者的技巧+腰技+阴茎大小对交互目标进行W快、欲情调整
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if activity.dead(target_data.cid):
            return

        # 阴茎大小的调整
        jj_size = player_ability.get(character_id, "jj_size")
        size_adjust = handle_ability.get_ability_adjust(jj_size) / 2
        # 腰技的调整
        waist_tech = abilities.ability(character_id)[76]
        waist_adjust = handle_ability.get_ability_adjust(waist_tech) / 2
        # 最终调整值
        extra_adjust = size_adjust + waist_adjust

        # 快感
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            7,
            50,
            ability_level=abilities.ability(character_id)[30],
            extra_adjust=extra_adjust,
            change_data_to_target_change=change_data,
        )
        # 欲情
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            12,
            50,
            ability_level=abilities.ability(target_data.cid)[7],
            extra_adjust=extra_adjust,
            change_data_to_target_change=change_data,
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_PAIN_TO_H_ADJUST
)
def handle_target_pain_to_h_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    根据发起者的技巧、交互对象的受虐对其进行H快、欲情、苦痛调整
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if activity.dead(target_data.cid):
            return

        # 技巧大小的调整
        tech_lv = abilities.ability(character_id)[30]
        tech_adjust = handle_ability.get_ability_adjust(tech_lv)
        # 受虐的调整
        masochism_lv = abilities.ability(target_data.cid)[36]
        masochism_adjust = handle_ability.get_ability_adjust(masochism_lv)
        # 最终调整值
        extra_adjust = tech_adjust + masochism_adjust

        # 快感
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            23,
            50,
            ability_level=abilities.ability(character_id)[30],
            extra_adjust=masochism_adjust,
            change_data_to_target_change=change_data,
        )
        # 欲情
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            12,
            50,
            ability_level=abilities.ability(target_data.cid)[33],
            extra_adjust=extra_adjust,
            change_data_to_target_change=change_data,
        )
        # 苦痛
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            17,
            50,
            ability_level=abilities.ability(target_data.cid)[15],
            extra_adjust=extra_adjust,
            change_data_to_target_change=change_data,
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.FINGER_TECH_ADD_PL_P_ADJUST
)
def handle_finger_tech_add_pl_p_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    根据交互对象的技巧+指技对发起者进行P快调整
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    ability = abilities.ability(target_data.cid)
    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if activity.dead(target_data.cid):
            return
        # 获取调整值#
        ability.setdefault(19, 0)
        adjust_1 = handle_ability.get_ability_adjust(ability[30])
        adjust_2 = handle_ability.get_ability_adjust(ability[70])
        adjust = adjust_1 / 2 + adjust_2
        # P快变化#
        status.setdefault(character_id, 3, 0)
        now_lust = status.of(character_id)[3]
        now_lust_multiple = 50
        now_add_lust: float = add_time + now_lust_multiple
        now_add_lust *= adjust
        now_add_lust += now_lust / 8
        now_add_lust = int(now_add_lust)
        h_meters.add(character_id, "eja", now_add_lust)
        change_data.eja_point += now_add_lust
        action_info.set(character_id, "last_eaj_add_time", now_time)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TONGUE_TECH_ADD_PL_P_ADJUST
)
def handle_tongue_tech_add_pl_p_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    根据交互对象的技巧+舌技对发起者进行P快调整
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    ability = abilities.ability(target_data.cid)
    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if activity.dead(target_data.cid):
            return
        # 获取调整值#
        ability.setdefault(19, 0)
        adjust_1 = handle_ability.get_ability_adjust(ability[30])
        adjust_2 = handle_ability.get_ability_adjust(ability[71])
        adjust = adjust_1 / 2 + adjust_2
        # P快变化#
        status.setdefault(character_id, 3, 0)
        now_lust = status.of(character_id)[3]
        now_lust_multiple = 50
        now_add_lust: float = add_time + now_lust_multiple
        now_add_lust *= adjust
        now_add_lust += now_lust / 8
        now_add_lust = int(now_add_lust)
        h_meters.add(character_id, "eja", now_add_lust)
        change_data.eja_point += now_add_lust
        action_info.set(character_id, "last_eaj_add_time", now_time)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.FEET_TECH_ADD_PL_P_ADJUST
)
def handle_feet_tech_add_pl_p_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    根据交互对象的技巧+足技对发起者进行P快调整
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    ability = abilities.ability(target_data.cid)
    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if activity.dead(target_data.cid):
            return
        # 获取调整值#
        ability.setdefault(19, 0)
        adjust_1 = handle_ability.get_ability_adjust(ability[30])
        adjust_2 = handle_ability.get_ability_adjust(ability[72])
        adjust = adjust_1 / 2 + adjust_2
        # P快变化#
        status.setdefault(character_id, 3, 0)
        now_lust = status.of(character_id)[3]
        now_lust_multiple = 50
        now_add_lust: float = add_time + now_lust_multiple
        now_add_lust *= adjust
        now_add_lust += now_lust / 8
        now_add_lust = int(now_add_lust)
        h_meters.add(character_id, "eja", now_add_lust)
        change_data.eja_point += now_add_lust
        action_info.set(character_id, "last_eaj_add_time", now_time)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.BREAST_TECH_ADD_PL_P_ADJUST
)
def handle_breast_tech_add_pl_p_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    根据交互对象的技巧+胸技对发起者进行P快调整
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    ability = abilities.ability(target_data.cid)
    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if activity.dead(target_data.cid):
            return
        # 获取调整值#
        ability.setdefault(19, 0)
        adjust_1 = handle_ability.get_ability_adjust(ability[30])
        adjust_2 = handle_ability.get_ability_adjust(ability[73])
        adjust = adjust_1 / 2 + adjust_2
        # P快变化#
        status.setdefault(character_id, 3, 0)
        now_lust = status.of(character_id)[3]
        now_lust_multiple = 50
        now_add_lust: float = add_time + now_lust_multiple
        now_add_lust *= adjust
        now_add_lust += now_lust / 8
        now_add_lust = int(now_add_lust)
        h_meters.add(character_id, "eja", now_add_lust)
        change_data.eja_point += now_add_lust
        action_info.set(character_id, "last_eaj_add_time", now_time)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.VAGINA_TECH_ADD_PL_P_ADJUST
)
def handle_vagina_tech_add_pl_p_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    根据交互对象的技巧+膣技对发起者进行P快调整
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    ability = abilities.ability(target_data.cid)
    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if activity.dead(target_data.cid):
            return
        # 获取调整值#
        ability.setdefault(19, 0)
        adjust_1 = handle_ability.get_ability_adjust(ability[30])
        adjust_2 = handle_ability.get_ability_adjust(ability[74])
        adjust = adjust_1 / 2 + adjust_2
        # P快变化#
        status.setdefault(character_id, 3, 0)
        now_lust = status.of(character_id)[3]
        now_lust_multiple = 50
        now_add_lust: float = add_time + now_lust_multiple
        now_add_lust *= adjust
        now_add_lust += now_lust / 8
        now_add_lust = int(now_add_lust)
        h_meters.add(character_id, "eja", now_add_lust)
        change_data.eja_point += now_add_lust
        action_info.set(character_id, "last_eaj_add_time", now_time)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ANUS_TECH_ADD_PL_P_ADJUST
)
def handle_anus_tech_add_pl_p_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    根据交互对象的技巧+肛技对发起者进行P快调整
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    ability = abilities.ability(target_data.cid)
    if activity.target(character_id) != character_id and (
        not character_id or not activity.target(character_id)
    ):

        if activity.dead(character_id):
            return
        if activity.dead(target_data.cid):
            return
        # 获取调整值#
        ability.setdefault(19, 0)
        adjust_1 = handle_ability.get_ability_adjust(ability[30])
        adjust_2 = handle_ability.get_ability_adjust(ability[75])
        adjust = adjust_1 / 2 + adjust_2
        # P快变化#
        status.setdefault(character_id, 3, 0)
        now_lust = status.of(character_id)[3]
        now_lust_multiple = 50
        now_add_lust: float = add_time + now_lust_multiple
        now_add_lust *= adjust
        now_add_lust += now_lust / 8
        now_add_lust = int(now_add_lust)
        h_meters.add(character_id, "eja", now_add_lust)
        change_data.eja_point += now_add_lust
        action_info.set(character_id, "last_eaj_add_time", now_time)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.LOW_OBSCENITY_FAILED_ADJUST
)
def handle_low_obscenity_failed_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    轻度性骚扰失败的加反感、加愤怒、降好感度修正
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.target(character_id):
        target_data: identity.Identity = identity.of(
            activity.target(character_id)
        )

        # 不需要再进行该判断
        # if not character.calculation_instuct_judege(0,character_data.target_character_id,"初级骚扰"):

        change_data.target_change.setdefault(
            target_data.cid, game_type.TargetChange()
        )
        # 加反感
        base_chara_state_common_settle(
            activity.target(character_id),
            add_time,
            20,
            200,
            ability_level=abilities.ability(target_data.cid)[18],
            change_data_to_target_change=change_data,
        )
        # 加愤怒
        needs.add(target_data.cid, "angry", 50)
        flags.set(target_data.cid, angry_with_player=True)
        # 降好感
        base_chara_favorability_and_trust_common_settle(
            character_id, add_time, True, 0, -1, change_data
        )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.HIGH_OBSCENITY_FAILED_ADJUST
)
def handle_high_obscenity_failed_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    重度性骚扰失败的加反感、加愤怒、降好感度修正
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.target(character_id):
        target_data: identity.Identity = identity.of(
            activity.target(character_id)
        )

        # 不需要再进行该判断
        # if not character.calculation_instuct_judege(0,character_data.target_character_id,"严重骚扰"):

        change_data.target_change.setdefault(
            target_data.cid, game_type.TargetChange()
        )
        target_change = change_data.target_change[target_data.cid]
        # 加反感
        status.setdefault(target_data.cid, 20, 0)
        now_lust = status.of(target_data.cid)[20]
        now_lust_multiple: float = 10000
        now_add_lust: float = add_time + now_lust_multiple
        adjust = handle_ability.get_ability_adjust(
            abilities.ability(target_data.cid)[18]
        )
        now_add_lust *= adjust
        now_add_lust += now_lust / 2
        now_add_lust = int(now_add_lust)
        status.add(target_data.cid, 20, now_add_lust, max=99999)
        change_data.target_change.setdefault(
            target_data.cid, game_type.TargetChange()
        )
        target_change.status_data.setdefault(20, 0)
        target_change.status_data[20] = now_add_lust
        # 加愤怒
        needs.add(target_data.cid, "angry", 100)
        flags.set(target_data.cid, angry_with_player=True)
        # 降好感
        base_chara_favorability_and_trust_common_settle(
            character_id, add_time, True, 0, -3, change_data
        )
        # 降信赖
        now_lust_multiple = relations.trust(target_data.cid) * 0.2 + 2
        if now_lust_multiple < 0:
            now_lust_multiple *= -1
        relations.trust.set(
            target_data.cid,
            relations.trust(target_data.cid) - now_lust_multiple,
        )
        change_data.target_change.setdefault(
            target_data.cid, game_type.TargetChange()
        )
        target_change = change_data.target_change[target_data.cid]
        target_change.trust -= now_lust_multiple


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DO_H_FAILED_ADJUST
)
def handle_do_h_failed_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    邀请H失败的加反感、加愤怒、降好感度、降信赖修正
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if activity.target(character_id):
        target_data: identity.Identity = identity.of(
            activity.target(character_id)
        )

        # 高陷落不进行该判断
        chara_fall = attr_calculation.get_character_fall_level(
            activity.target(character_id)
        )
        if chara_fall >= 4:
            return

        change_data.target_change.setdefault(
            target_data.cid, game_type.TargetChange()
        )
        target_change = change_data.target_change[target_data.cid]
        # 加反感
        status.setdefault(target_data.cid, 20, 0)
        now_lust = status.of(target_data.cid)[20]
        now_lust_multiple: float = 20000
        now_add_lust: float = add_time + now_lust_multiple
        adjust = handle_ability.get_ability_adjust(
            abilities.ability(target_data.cid)[18]
        )
        now_add_lust *= adjust
        now_add_lust += now_lust / 2
        now_add_lust = int(now_add_lust)
        status.add(target_data.cid, 20, now_add_lust, max=99999)
        change_data.target_change.setdefault(
            target_data.cid, game_type.TargetChange()
        )
        target_change.status_data.setdefault(20, 0)
        target_change.status_data[20] = now_add_lust
        # 加愤怒
        needs.add(target_data.cid, "angry", 100)
        flags.set(target_data.cid, angry_with_player=True)
        # 降好感
        base_chara_favorability_and_trust_common_settle(
            character_id, add_time, True, 0, -15, change_data
        )
        # 降信赖
        now_lust_multiple = relations.trust(target_data.cid) * 0.4 + 5
        if now_lust_multiple < 0:
            now_lust_multiple *= -1
        relations.trust.set(
            target_data.cid,
            relations.trust(target_data.cid) - now_lust_multiple,
        )
        change_data.target_change.setdefault(
            target_data.cid, game_type.TargetChange()
        )
        target_change = change_data.target_change[target_data.cid]
        target_change.trust -= now_lust_multiple


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SLEEP_ADD_ADJUST
)
def handle_sleep_add_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （睡觉用）如果在自己宿舍，则换睡衣并有一定几率关门
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if handle_premise.handle_in_dormitory(character_id):
        # 换睡衣
        clothing.get_sleep_cloth(character_id)
        # 被要求不关门则不关门
        if handle_premise.handle_ask_not_lock_door_bedore_sleeping(
            character_id
        ):
            pass
        # 否则判定是否关门
        elif random.random() < 0.5:
            handle_door_close(character_id, add_time, change_data, now_time)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.URINATE_POINT_ZERO
)
def handle_urinate_point_zero(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    尿意值归零
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    needs.set(character_id, urine=0)
    # 尿道的精液一起归零
    with dirty.editing(character_id) as d:
        d.body_semen[9][1] = 0
        d.body_semen[9][2] = 0


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_URINATE_POINT_ZERO
)
def handle_target_urinate_point_zero(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象尿意值归零
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    handle_urinate_point_zero(
        activity.target(character_id), add_time, change_data, now_time
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.HUNGER_POINT_ZERO
)
def handle_hunger_point_zero(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange | game_type.TargetChange,
    now_time: datetime.datetime,
) -> None:
    """
    饥饿值归零
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    needs.set(character_id, hunger=0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_HUNGER_POINT_ZERO
)
def handle_target_hunger_point_zero(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象饥饿值归零
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    needs.set(activity.target(character_id), hunger=0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SLEEP_POINT_ZERO
)
def handle_sleep_point_zero(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    熟睡值归零
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    needs.set(character_id, sleep=0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_SLEEP_POINT_ZERO
)
def handle_target_sleep_point_zero(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象熟睡值归零
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    needs.set(target_data.cid, sleep=0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ADD_SMALL_URINATE_POINT
)
def handle_add_small_urinate_point(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange | game_type.TargetChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己增加少量尿意值
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    needs.set(
        character_id, urine=min(needs.of(character_id)["urine"] + 60, 300)
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_ADD_SMALL_URINATE_POINT
)
def handle_target_add_small_urinate_point(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象增加少量尿意值
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_id = activity.target(character_id)
    needs.set(target_id, urine=min(needs.of(target_id)["urine"] + 60, 300))


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_DESIRE_POINT_ZERO
)
def handle_target_desire_point_zero(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象欲望值归零
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    needs.set(target_data.cid, desire=0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DESIRE_POINT_TO_79
)
def handle_desire_point_to_79(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己欲望值调为79
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    needs.set(character_id, desire=79)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TARGET_DESIRE_POINT_TO_79
)
def handle_target_desire_point_to_79(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    交互对象欲望值调为79
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    needs.set(target_data.cid, desire=79)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DESIRE_POINT_TO_0
)
def handle_desire_point_to_0(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    自己欲望值归零
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    needs.set(character_id, desire=0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ADD_SMALL_SANITY_POINT
)
def handle_add_small_sanity_point(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    增加少量理智值(15%/h)
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    add_sanity_point = int(
        add_time / 60 * 0.15 * needs.of(character_id)["sanity_max"]
    )
    needs.add(character_id, "sanity", add_sanity_point)
    # 如果超过最大值则=最大值
    if needs.of(character_id)["sanity"] >= needs.of(character_id)["sanity_max"]:
        needs.set(character_id, sanity=needs.of(character_id)["sanity_max"])


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.ADD_SMALL_SEMEN_POINT
)
def handle_add_small_semen_point(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    增加少量精液值(15%/h)
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    if character_id > 0:
        return
    semen_max = h_meters.of(character_id)["semen_max"]
    add_semen_point = int(add_time / 60 * 0.15 * semen_max)
    h_meters.add(character_id, "semen", add_semen_point, max=semen_max)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.RECORD_TRAINING_TIME
)
def handle_record_training_time(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    记录当前训练时间
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    action_info.set(character_id, "last_training_time", now_time)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.RECORD_SHOWER_TIME
)
def handle_record_shower_time(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    记录当前淋浴时间
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    action_info.set(character_id, "last_shower_time", now_time)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.RECORD_WAKE_TIME
)
def handle_record_wake_time(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    角色记录并刷新起床时间
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    action_info.set(character_id, "wake_time", now_time)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.RECORD_CONSCIOUS_H_TIME
)
def handle_record_conscious_h_time(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    角色记录并刷新有意识H时间
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    action_info.set(character_id, "last_conscious_h_time", now_time)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.RECORD_UNCONSCIOUS_H_TIME
)
def handle_record_unconscious_h_time(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    角色记录并刷新无意识H时间
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    action_info.set(character_id, "last_unconscious_h_time", now_time)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PENIS_IN_T_RESET
)
def handle_penis_in_t_reset(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    当前阴茎位置为交互对象_双方归零
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    h_state.set(target_data.cid, insert_position=-1)
    h_state.set(character_id, insert_position=-1)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.SCENE_ALL_CHARACTERS_PENIS_IN_RESET
)
def handle_scene_all_characters_penis_in_reset(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    场景内所有角色的当前阴茎位置归零
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    scene_path_str = map_handle.get_map_system_path_str_for_list(
        activity.position(character_id)
    )
    scene_data: game_type.Scene = cache.scene_data[scene_path_str]
    for chara_id in scene_data.character_list:
        h_state.set(chara_id, insert_position=-1)


def record_first_part_sex(
    character_id: int, target_data: identity.Identity, item: int = -1
) -> None:
    """
    部位交初体验记录（键取自insert_position，未记录才写入；破处handler的完整写入会覆盖本条目）\n
    Keyword arguments:
    character_id -- 行为发起者id（记为对象）\n
    target_data -- 被交部位所属角色数据\n
    item -- 道具编号，-1无/0手指/1振动棒/2采尿器
    """
    # 玩家不做部位交记录（部位交的身体部位恒属于NPC）
    if not target_data.cid:
        return
    part_id = h_state.get(target_data.cid, "insert_position")
    # 身体部位以外（未插入或服装部位）不记录
    if part_id == -1 or part_id >= 20:
        return
    if first_record.has_part_sex(target_data.cid, part_id):
        return
    # 姿势取行为发起者当前行为的中文名
    behavior_name = ""
    behavior_id = activity.behavior(character_id).behavior_id
    if behavior_id in game_config.config_behavior:
        behavior_name = game_config.config_behavior[behavior_id].name
    with first_record.editing(target_data.cid) as fr:
        fr.first_part_sex_dict[part_id] = {
            "id": character_id,
            "time": game_time.now(),
            "place": list(activity.position(target_data.cid)),
            "posture": behavior_name,
            "item": item,
        }


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PENIS_IN_T_HAIR
)
def handle_penis_in_t_hair(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    当前阴茎位置为交互对象_发交中
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    h_state.set(target_data.cid, insert_position=0)
    record_first_part_sex(character_id, target_data)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PENIS_IN_T_FACE
)
def handle_penis_in_t_face(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    当前阴茎位置为交互对象_阴茎蹭脸中
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    h_state.set(target_data.cid, insert_position=1)
    record_first_part_sex(character_id, target_data)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PENIS_IN_T_MOUSE
)
def handle_penis_in_t_mouse(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    当前阴茎位置为交互对象_口交中
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    h_state.set(target_data.cid, insert_position=2)
    record_first_part_sex(character_id, target_data)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PENIS_IN_T_BREAST
)
def handle_penis_in_t_breast(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    当前阴茎位置为交互对象_乳交中
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    h_state.set(target_data.cid, insert_position=3)
    record_first_part_sex(character_id, target_data)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PENIS_IN_T_AXILLA
)
def handle_penis_in_t_axilla(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    当前阴茎位置为交互对象_腋交中
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    h_state.set(target_data.cid, insert_position=4)
    record_first_part_sex(character_id, target_data)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PENIS_IN_T_HAND
)
def handle_penis_in_t_hand(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    当前阴茎位置为交互对象_手交中
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    h_state.set(target_data.cid, insert_position=5)
    record_first_part_sex(character_id, target_data)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PENIS_IN_T_VAGINA
)
def handle_penis_in_t_vagina(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    当前阴茎位置为交互对象_V插入中
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    h_state.set(target_data.cid, insert_position=6)
    record_first_part_sex(character_id, target_data)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PENIS_IN_T_WOMB
)
def handle_penis_in_t_womb(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    当前阴茎位置为交互对象_W插入中
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    h_state.set(target_data.cid, insert_position=7)
    record_first_part_sex(character_id, target_data)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PENIS_IN_T_ANAL
)
def handle_penis_in_t_anal(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    当前阴茎位置为交互对象_A插入中
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    h_state.set(target_data.cid, insert_position=8)
    record_first_part_sex(character_id, target_data)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PENIS_IN_T_URETHRAL
)
def handle_penis_in_t_urethral(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    当前阴茎位置为交互对象_U插入中
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    h_state.set(target_data.cid, insert_position=9)
    record_first_part_sex(character_id, target_data)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PENIS_IN_T_LEG
)
def handle_penis_in_t_leg(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    当前阴茎位置为交互对象_腿交中
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    h_state.set(target_data.cid, insert_position=10)
    record_first_part_sex(character_id, target_data)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PENIS_IN_T_FOOT
)
def handle_penis_in_t_foot(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    当前阴茎位置为交互对象_足交中
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    h_state.set(target_data.cid, insert_position=11)
    record_first_part_sex(character_id, target_data)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PENIS_IN_T_TAIL
)
def handle_penis_in_t_tail(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    当前阴茎位置为交互对象_尾交中
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    h_state.set(target_data.cid, insert_position=12)
    record_first_part_sex(character_id, target_data)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PENIS_IN_T_HORN
)
def handle_penis_in_t_horn(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    当前阴茎位置为交互对象_阴茎蹭角中
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    h_state.set(target_data.cid, insert_position=13)
    record_first_part_sex(character_id, target_data)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PENIS_IN_T_EARS
)
def handle_penis_in_t_ears(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    当前阴茎位置为交互对象_阴茎蹭耳朵中
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    h_state.set(target_data.cid, insert_position=14)
    record_first_part_sex(character_id, target_data)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PENIS_IN_T_DEEP_THROAT
)
def handle_penis_in_t_deep_throat(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    改变当前阴茎位置为交互对象_深喉中
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    h_state.set(target_data.cid, insert_position=15)
    record_first_part_sex(character_id, target_data)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PENIS_IN_T_HAT
)
def handle_penis_in_t_hat(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    改变当前阴茎位置为交互对象_帽子交中
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    h_state.set(target_data.cid, insert_position=20)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PENIS_IN_T_GLASSES
)
def handle_penis_in_t_classes(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    改变当前阴茎位置为交互对象_眼镜交中
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    h_state.set(target_data.cid, insert_position=21)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PENIS_IN_T_EAR_ORNAMENT
)
def handle_penis_in_t_ear_ornament(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    改变当前阴茎位置为交互对象_耳饰交中
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    h_state.set(target_data.cid, insert_position=22)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PENIS_IN_T_NECK_ORNAMENT
)
def handle_penis_in_t_neck_ornament(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    改变当前阴茎位置为交互对象_脖饰交中
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    h_state.set(target_data.cid, insert_position=23)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PENIS_IN_T_MOUTH_ORNAMENT
)
def handle_penis_in_t_mouth_ornament(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    改变当前阴茎位置为交互对象_口罩交中
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    h_state.set(target_data.cid, insert_position=24)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PENIS_IN_T_TOP
)
def handle_penis_in_t_top(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    改变当前阴茎位置为交互对象_上衣交中
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    h_state.set(target_data.cid, insert_position=25)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PENIS_IN_T_CORSET
)
def handle_penis_in_t_corset(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    改变当前阴茎位置为交互对象_胸衣交中
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    h_state.set(target_data.cid, insert_position=26)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PENIS_IN_T_GLOVES
)
def handle_penis_in_t_gloves(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    改变当前阴茎位置为交互对象_手套交中
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    h_state.set(target_data.cid, insert_position=27)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PENIS_IN_T_SKIRT
)
def handle_penis_in_t_skirt(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    改变当前阴茎位置为交互对象_裙子交中
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    h_state.set(target_data.cid, insert_position=28)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PENIS_IN_T_UNDERWEAR
)
def handle_penis_in_t_underwear(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    改变当前阴茎位置为交互对象_内裤交中
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    h_state.set(target_data.cid, insert_position=29)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PENIS_IN_T_SOCKS
)
def handle_penis_in_t_socks(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    改变当前阴茎位置为交互对象_袜子交中
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    h_state.set(target_data.cid, insert_position=30)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PENIS_IN_T_SHOES
)
def handle_penis_in_t_shoes(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    改变当前阴茎位置为交互对象_鞋子交中
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    h_state.set(target_data.cid, insert_position=31)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PENIS_IN_T_WEAPONS
)
def handle_penis_in_t_weapoms(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    改变当前阴茎位置为交互对象_武器交中
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    h_state.set(target_data.cid, insert_position=32)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PENIS_IN_T_TROUSERS
)
def handle_penis_in_t_trousers(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    改变当前阴茎位置为交互对象_裤子交中
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    h_state.set(target_data.cid, insert_position=28)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.CANCEL_PENIS_IN_FACE_OR_MOUSE
)
def handle_cancel_penis_in_face_or_mouse(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    取消为阴茎位置交互对象_阴茎蹭脸中和口交中
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if h_state.get(target_data.cid, "insert_position") in {1, 2}:
        h_state.set(target_data.cid, insert_position=-1)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DR_POSITION_NULL
)
def handle_dr_position_null(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    博士体位数据变成无
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    h_state.set(0, current_sex_position=-1)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DR_POSITION_NORMAL
)
def handle_dr_position_normal(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    博士体位数据变成正常体位
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    h_state.set(0, current_sex_position=1)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DR_POSITION_BACK
)
def handle_dr_position_back(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    博士体位数据变成后背体位
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    h_state.set(0, current_sex_position=2)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DR_POSITION_FACE_RIDE
)
def handle_dr_position_face_ride(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    博士体位数据变成对面骑乘体位
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    h_state.set(0, current_sex_position=3)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DR_POSITION_BACK_RIDE
)
def handle_dr_position_back_ride(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    博士体位数据变成背面骑乘体位
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    h_state.set(0, current_sex_position=4)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DR_POSITION_FACE_SEAT
)
def handle_dr_position_face_seat(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    博士体位数据变成对面座体位
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    h_state.set(0, current_sex_position=5)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DR_POSITION_BACK_SEAT
)
def handle_dr_position_back_seat(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    博士体位数据变成背面座体位
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    h_state.set(0, current_sex_position=6)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DR_POSITION_FACE_STAND
)
def handle_dr_position_face_stand(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    博士体位数据变成对面立体位
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    h_state.set(0, current_sex_position=7)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DR_POSITION_BACK_STAND
)
def handle_dr_position_back_stand(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    博士体位数据变成背面立体位
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    h_state.set(0, current_sex_position=8)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DR_POSITION_FACE_HUG
)
def handle_dr_position_face_hug(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    博士体位数据变成对面抱体位
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    h_state.set(0, current_sex_position=9)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DR_POSITION_BACK_HUG
)
def handle_dr_position_back_hug(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    博士体位数据变成背面抱体位
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    h_state.set(0, current_sex_position=10)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DR_POSITION_FACE_LIE
)
def handle_dr_position_face_lie(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    博士体位数据变成对面卧体位
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    h_state.set(0, current_sex_position=11)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DR_POSITION_BACK_LIE
)
def handle_dr_position_back_lie(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    博士体位数据变成背面卧体位
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    h_state.set(0, current_sex_position=12)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DR_POSITION_WOMB_NULL
)
def handle_dr_position_womb_null(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    博士子宫性交位置变成无
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    h_state.set(0, current_womb_sex_position=0)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DR_POSITION_WOMB_INSERT
)
def handle_dr_position_womb_insert(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    博士子宫性交位置变成子宫口插入
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    h_state.set(0, current_womb_sex_position=1)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.DR_POSITION_WOMB_SEX
)
def handle_dr_position_womb_sex(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    博士子宫性交位置变成子宫奸
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    h_state.set(0, current_womb_sex_position=2)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.H_IN_LOVE_HOTEL_TO_FALSE
)
def handle_h_in_love_hotel_to_false(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    取消自己和交互对象正在爱情旅馆中H的状态
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    target_data: identity.Identity = identity.of(activity.target(character_id))
    h_state.set(character_id, h_in_love_hotel=False)
    h_state.set(target_data.cid, h_in_love_hotel=False)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.TAKE_CHARA_EGGS_SETTLE
)
def handle_take_chara_eggs_settle(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （拿走产下的卵用）拿走交互对象的全部未鉴定卵，卵数据留原处标记被拿走并写入玩家临时持有索引
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    from Script.System.Pregnancy_System import egg_handle

    target_character_id = activity.target(character_id)
    # 无有效交互对象时不结算
    if target_character_id == character_id or not identity.exists(
        target_character_id
    ):
        return
    egg_handle.take_eggs_from_chara(target_character_id)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.IDENTIFY_HELD_EGGS_SETTLE
)
def handle_identify_held_eggs_settle(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （鉴定持有的卵用）鉴定玩家临时持有的全部卵并经索引回写原角色卵数据，无精删卵、受精进入孵化
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    # 玩家临时持有的卵仅由玩家鉴定
    if character_id != 0:
        return
    from Script.System.Pregnancy_System import egg_handle

    egg_handle.identify_held_eggs_settle()


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.EAT_LAST_TWO_FOOD
)
def handle_eat_last_two_food(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    吃掉背包里的最后两个食物，助理送饭时用
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return
    for __ in range(2):
        handle_set_target_food_from_bag_last(
            character_id, add_time, change_data, now_time
        )
        handle_eat_add_just(character_id, add_time, change_data, now_time)
        handle_delete_last_food(character_id, add_time, change_data, now_time)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.OFFICIAL_EVENT_ACCEPT_RECRUIT
)
def handle_official_event_accept_recruit(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    公务事件用：接收一名待确认的招募干员（Plan 23）

    这类效果没法用数值 token 表达（要建角色、分宿舍、发成就），所以走纯数字结算id这条路。
    直接复用招募面板的 recruit_new_chara：宿舍已满或没有待确认干员时它自己会给提示并返回，
       不要在这里另写一套判定，否则两处的门槛迟早会对不上
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    Return arguments:
    无
    """
    if not add_time:
        return
    from Script.UI.Panel import recruit_panel

    recruit_panel.recruit_new_chara()


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.OFFICIAL_EVENT_TEMP_COMMISSION
)
def handle_official_event_temp_commission(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    公务事件用：生成一条突发的临时外勤委托（Plan 23）

    复用外勤委托系统的 create_temp_commission：委托的需求与奖励用的是外勤自己的前缀语法
       （r_资源id_数量、声望_势力id_值），与 CVE token 是两套，别混着写
    该函数会把新委托**追加写进 data/csv/Commission.csv**（不是只改内存），所以
       描述里的换行必须写成两个字符的 \\n 转义、且不能出现英文逗号，
       否则写出去的那一行会把 CSV 撑断，下次构建直接报错
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    Return arguments:
    无
    """
    if not add_time:
        return
    from Script.System.Field_Commission_System import field_commission_function

    field_commission_function.create_temp_commission(
        name=_("突发：受灾点的紧急支援"),
        level=2,
        type=_("资源"),
        people=2,
        time=2,
        demand="a_42_2&a_46_2",
        reward="r_1_2000&声望_0_10",
        description=_(
            "公务里递上来的急件：附近的定居点遭了灾，请求罗德岛派人支援。\\n博士已经答应下来，需要尽快组队出发。"
        ),
    )


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.PRENATAL_ADD_ADJUST
)
def handle_prenatal_add_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （胎教用）给交互对象（孕妇）的妊娠期胎教累积值 +0.5（Plan 22 四期 §3.27）

    只累积不转写：孩子此时还不存在，出生时由 born_event_panel 逐个全额转写给每个新生儿。
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    Return arguments:
    无
    """
    if not add_time:
        return
    from Script.System.Education_System import baby_growth_handle

    target_id = activity.target(character_id)
    if target_id == character_id or not identity.exists(target_id):
        return
    baby_growth_handle.add_prenatal_point(target_id)


@settle_behavior.add_settle_behavior_effect(
    constant_effect.BehaviorEffect.NUIRSE_CHILD_ADD_ADJUST
)
def handle_nuirse_child_add_adjust(
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> None:
    """
    （喂奶用）婴儿的体力与气力上限微增；发起者是玩家时额外给婴儿加好感与好意（Plan 22 四期 §3.20）

    照料值本身走效果串里的 CVE_A2_Growth|20，这里只做 CVE 表达不了的两件事：
    体质（上限值不是养成数值）与"玩家亲自照料才有"的加成（CVE 没有发起者判定）。
    保育员喂奶同样给体质，只是没有玩家那份额外的好感——差异化对 NPC 照料同样生效（方案 §2.2）
    Keyword arguments:
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    Return arguments:
    无
    """
    if not add_time:
        return
    from Script.System.Education_System import education_constant

    target_id = activity.target(character_id)
    if target_id == character_id or not identity.exists(target_id):
        return
    # 只对婴儿生效
    if not abilities.talent(target_id).get(101, 0):
        return
    needs.add(target_id, "hit_max", education_constant.NUIRSE_CHILD_HP_MAX_ADD)
    needs.add(target_id, "mana_max", education_constant.NUIRSE_CHILD_MP_MAX_ADD)
    if character_id != 0:
        return
    base_chara_favorability_and_trust_common_settle(
        character_id,
        add_time,
        True,
        base_value=education_constant.NUIRSE_CHILD_FAVOR_BASE,
        change_data=change_data,
    )
    base_chara_state_common_settle(
        target_id,
        add_time,
        11,
        base_value=education_constant.NUIRSE_CHILD_FRIENDLY_BASE,
        ability_level=abilities.ability(target_id).get(32, 0),
        change_data_to_target_change=change_data,
    )
