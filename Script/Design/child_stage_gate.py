"""
幼年阶段的H闸
幼年阶段指年龄素质 101 婴儿与 102 幼儿。本模块判断角色是否处于幼年阶段、指令与行为是否属于H类，
指令的列表与执行、NPC状态机选出的行为据此避开幼年阶段的角色
"""
from typing import Set

from Script.Core import cache_control, constant, game_type
from Script.Config import game_config

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """

CHILD_STAGE_TALENTS = (101, 102)
""" 幼年阶段的年龄素质：101 婴儿、102 幼儿 """
H_INSTRUCT_TYPES = {"SEX", "OBSCENITY"}
""" 属于H类的指令类型（InstructConfig.csv 的 instruct_type 列） """
H_WEB_MINOR_TYPES = {"hand_touch", "arts_hypnosis", "arts_time_stop", "tool_item", "arts_xray", "arts_hormone"}
""" 属于H类的Web小类（InstructConfig.csv 的 web_minor_type 列） """
H_BEHAVIOR_TAGS = {"性爱", "猥亵"}
""" 属于H类的行为标签（Behavior_Data.csv 的 tag 列，该列不翻译） """

_h_instruct_ids: Set[str] = set()
""" H类指令id集合，首次使用时由指令配置建立 """
_h_behavior_ids: Set[str] = set()
""" H类行为id集合，首次使用时由指令配置与行为配置建立 """


def is_child_stage(character_id: int) -> bool:
    """
    判断角色是否处于幼年阶段
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    bool -- 拥有素质101或102时为True；玩家与不存在的角色为False
    """
    if character_id == 0:
        return False
    character_data: game_type.Character = cache.character_data.get(character_id)
    if character_data is None:
        return False
    return any(character_data.talent.get(talent_id, 0) for talent_id in CHILD_STAGE_TALENTS)


def _build_h_sets():
    """
    由指令配置与行为配置建立H类指令id集合与H类行为id集合
    Keyword arguments:
    无
    Return arguments:
    无
    """
    non_h_instruct_behavior_ids = set()
    for instruct_config in game_config.config_instruct.values():
        instruct_type = getattr(instruct_config, "instruct_type", "")
        minor_type = getattr(instruct_config, "web_minor_type", "")
        # 配置里写的是 constant.Behavior 的属性名，同 handle_instruct.add_instruct 换成行为id，空值为发呆
        behavior_name = getattr(instruct_config, "behavior_id", "") or "SHARE_BLANKLY"
        behavior_id = getattr(constant.Behavior, behavior_name, behavior_name)
        if instruct_type in H_INSTRUCT_TYPES or minor_type in H_WEB_MINOR_TYPES:
            _h_instruct_ids.add(instruct_config.instruct_id)
            _h_behavior_ids.add(behavior_id)
        else:
            non_h_instruct_behavior_ids.add(behavior_id)
    # 非H类指令也用的行为（等待、发呆）不算H类行为
    _h_behavior_ids.difference_update(non_h_instruct_behavior_ids)
    for behavior_id, behavior_config in game_config.config_behavior.items():
        if H_BEHAVIOR_TAGS & set(behavior_config.tag.split("|")):
            _h_behavior_ids.add(behavior_id)


def is_h_instruct(instruct_id: str) -> bool:
    """
    判断指令是否属于H类
    Keyword arguments:
    instruct_id -- 指令id
    Return arguments:
    bool -- 指令类型为SEX或OBSCENITY，或Web小类属于H_WEB_MINOR_TYPES时为True
    """
    if not _h_instruct_ids:
        _build_h_sets()
    return instruct_id in _h_instruct_ids


def is_h_behavior(behavior_id: str) -> bool:
    """
    判断行为是否属于H类
    Keyword arguments:
    behavior_id -- 行为id
    Return arguments:
    bool -- 行为只由H类指令使用，或行为标签含性爱、猥亵时为True
    """
    if not _h_behavior_ids:
        _build_h_sets()
    return behavior_id in _h_behavior_ids


def involves_child_stage(character_id: int) -> bool:
    """
    判断角色自己或其交互对象是否处于幼年阶段
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    bool -- 任一方处于幼年阶段时为True
    """
    character_data: game_type.Character = cache.character_data[character_id]
    return is_child_stage(character_id) or is_child_stage(character_data.target_character_id)


def blocks_instruct(instruct_id: str) -> bool:
    """
    判断玩家当前是否不能列出或执行该指令
    Keyword arguments:
    instruct_id -- 指令id
    Return arguments:
    bool -- 指令属于H类且玩家的交互对象处于幼年阶段时为True
    """
    return is_h_instruct(instruct_id) and is_child_stage(cache.character_data[0].target_character_id)


def blocks_behavior(character_id: int) -> bool:
    """
    判断角色当前的行为是否不能进行
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    bool -- 行为属于H类，且角色自己或其交互对象处于幼年阶段时为True
    """
    character_data: game_type.Character = cache.character_data[character_id]
    return is_h_behavior(character_data.behavior.behavior_id) and involves_child_stage(character_id)


def reset_to_idle(character_id: int):
    """
    把NPC的行为换成1分钟的发呆，交互对象改回自己
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    无
    """
    character_data: game_type.Character = cache.character_data[character_id]
    start_time = character_data.behavior.start_time
    character_data.behavior = game_type.Behavior()
    character_data.behavior.start_time = start_time
    character_data.behavior.duration = 1
    character_data.state = constant.CharacterStatus.STATUS_ARDER
    character_data.target_character_id = character_id
