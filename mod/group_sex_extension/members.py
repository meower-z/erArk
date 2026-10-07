# -*- coding: UTF-8 -*-
"""
群交参与者

参与者 = 群交模板里的角色 ∪ 玩家所在场景里的角色，只取处于 H 状态的 NPC。
两个来源都要：先进入单人 H 的角色、之后直接邀请加入的角色不一定在模板里。
"""

from Script.Core import cache_control
from Script.Design import map_handle
from Script.System.Sex_System import group_sex_panel

COMPLETE_HYPNOSIS_TALENT = 73
""" 完全催眠素质id """
COMPLETE_HYPNOSIS_DEGREE = 200
""" 催眠度达到此值即视为完全催眠 """


def member_ids() -> list:
    """
    当前群交的 NPC 参与者
    Keyword arguments:
    无
    Return arguments:
    list -- 按id升序的角色id列表
    """
    cache = cache_control.cache
    scene_path_str = map_handle.get_map_system_path_str_for_list(cache.character_data[0].position)
    candidate_ids = set(group_sex_panel.count_group_sex_character_list()) | set(cache.scene_data[scene_path_str].character_list)
    # 模板里可能留着已不在 character_data 里的旧id，先滤掉再读角色数据
    return sorted(cid for cid in candidate_ids if cid and cid in cache.character_data and cache.character_data[cid].sp_flag.is_h)


def is_complete_hypnosis(character_data) -> bool:
    """
    角色是否已完全催眠（有完全催眠素质，或催眠度达到上限）；与当前是否处于催眠状态无关
    Keyword arguments:
    character_data -- 角色数据
    Return arguments:
    bool -- 是否完全催眠
    """
    return bool(character_data.talent.get(COMPLETE_HYPNOSIS_TALENT, 0)) or character_data.hypnosis.hypnosis_degree >= COMPLETE_HYPNOSIS_DEGREE


def complete_hypnosis_member_ids() -> list:
    """
    当前群交参与者中已完全催眠的那些
    Keyword arguments:
    无
    Return arguments:
    list -- 按id升序的角色id列表
    """
    character_data = cache_control.cache.character_data
    return [cid for cid in member_ids() if is_complete_hypnosis(character_data[cid])]
