# -*- coding: UTF-8 -*-
"""
Local bugfix mod for movement/H-state edge cases.

The mod system replaces whole functions, so this file prefers wrappers around
upstream functions and only copies function bodies where the fix must alter
mid-function control flow.
"""
import datetime
import random


HN_AI = "Script.Design.handle_npc_ai"
HN_AI_H = "Script.Design.handle_npc_ai_in_h"
CHAR_MOVE = "Script.Design.character_move"
STATE_DEFAULT = "Script.StateMachine.default"

BEHAVIOR_EFFECT_HYPNOSIS_CANCEL = 1213
BEHAVIOR_EFFECT_HYPNOSIS_ONE = 1211
BEHAVIOR_EFFECT_END_H_ADD_HPMP_MAX = 528
BEHAVIOR_EFFECT_GROUP_SEX_END_H_ADD_HPMP_MAX = 529
SECOND_EFFECT_ADD_SMALL_PAIN = 270
SECOND_EFFECT_ADD_MIDDLE_PAIN = 283
SECOND_EFFECT_ADD_LARGE_PAIN = 296
SECOND_EFFECT_EXTRA_ORGASM = 408
ORGASM_PART_PREFIX = {0: "s", 1: "b", 2: "c", 4: "v", 5: "a", 6: "u", 7: "w", 21: "m", 22: "f", 23: "h"}
ORGASM_DEGREE_ID_TO_NAME = {2: "strong", 3: "super"}
HYPNOSIS_UNCONSCIOUS_FLAGS = {4, 5, 6, 7}

_ORIGINAL_GENERAL_MOVEMENT_MODULE = None
_ORIGINAL_CHARACTER_CONTINUE_MOVE = None
_ORIGINAL_BASE_STATE_COMMON_SETTLE = None
_ORIGINAL_HYPNOSIS_ONE_EFFECT = None
_ORIGINAL_HYPNOSIS_CANCEL_EFFECT = None
_ORIGINAL_END_H_ADD_HPMP_MAX = None
_ORIGINAL_GROUP_SEX_END_H_ADD_HPMP_MAX = None
_ORIGINAL_GET_WEIGHT_FROM_PREMISE_DICT = None
_ORIGINAL_SEX_BE_DISCOVERED_DRAW = None
_ORIGINAL_CHANGE_HYPNOSIS_TYPE = None
_ORIGINAL_SECOND_EFFECTS = {}
_GROUP_SEX_MASTURBATION_ACTION_KEYS = {}
_GROUP_SEX_MASTURBATION_ACTION_SERIAL = 0
_GROUP_SEX_MASTURBATION_OVER_OBJECT = None


def _cache():
    from Script.Core import cache_control

    return cache_control.cache


def _is_orgasm_batch_settling(character_id: int) -> bool:
    """判断角色是否正在进行本地修复的绝顶批处理"""
    try:
        from Script.Design import second_behavior

        checker = getattr(second_behavior, "local_bugfix_is_orgasm_batch_settling", None)
        return bool(checker and checker(character_id))
    except Exception:
        return False


def _stable_dedupe_character_ids(character_ids):
    """按首次出现顺序去重角色ID"""
    result = []
    seen = set()
    for character_id in character_ids:
        if not character_id or character_id in seen:
            continue
        seen.add(character_id)
        result.append(character_id)
    return result


def _ordered_character_ids(character_ids):
    """返回可稳定遍历的角色ID列表"""
    if isinstance(character_ids, set):
        return sorted(character_ids)
    return list(character_ids)


def _collect_group_template_character_ids():
    """收集群交模板中的角色ID"""
    try:
        from Script.System.Sex_System import group_sex_panel

        return [character_id for character_id in _ordered_character_ids(group_sex_panel.count_group_sex_character_list()) if character_id]
    except Exception:
        return []


def _collect_scene_h_character_ids():
    """收集玩家当前场景中处于H状态的角色ID"""
    try:
        from Script.Design import map_handle

        cache_obj = _cache()
        pl_character_data = cache_obj.character_data.get(0)
        if pl_character_data is None:
            return []

        scene_path_str = map_handle.get_map_system_path_str_for_list(pl_character_data.position)
        scene_data = cache_obj.scene_data.get(scene_path_str)
        if scene_data is None:
            return []

        character_ids = []
        for character_id in _ordered_character_ids(scene_data.character_list):
            if not character_id or character_id not in cache_obj.character_data:
                continue
            character_data = cache_obj.character_data[character_id]
            if getattr(character_data.sp_flag, "is_h", False):
                character_ids.append(character_id)
        return character_ids
    except Exception:
        return []


def _collect_group_sex_participant_ids():
    """按群交扩展的语义收集群交上下文角色ID"""
    return _stable_dedupe_character_ids(_collect_group_template_character_ids() + _collect_scene_h_character_ids())


def _has_pending_edge_count(character_data) -> bool:
    """判断角色是否存在未释放的寸止计数"""
    edge_count = getattr(character_data.h_state, "orgasm_edge_count", {})
    return any(value != 0 for value in edge_count.values())


def _character_can_release_group_edge(character_id: int, group_context_ids) -> bool:
    """判断角色是否满足群交寸止释放条件"""
    cache_obj = _cache()
    if character_id == 0 or character_id not in cache_obj.character_data:
        return False

    character_data = cache_obj.character_data[character_id]
    if getattr(character_data.h_state, "orgasm_edge", 0) != 1 or not _has_pending_edge_count(character_data):
        return False

    in_group_context = character_id in set(group_context_ids)
    in_h_state = bool(getattr(character_data.sp_flag, "is_h", False))
    return in_h_state or in_group_context


def _new_character_status_change():
    """创建角色状态变化记录"""
    from Script.Core import game_type

    return game_type.CharacterStatusChange()


def _get_release_change_data(character_id: int, owner_character_id: int, change_data):
    """获取本次释放应写入的变化记录对象"""
    if character_id == owner_character_id:
        return change_data

    target_change_dict = getattr(change_data, "target_change", None)
    if target_change_dict is None:
        return change_data

    if character_id not in target_change_dict:
        try:
            from Script.Core import game_type

            target_change_dict[character_id] = game_type.TargetChange()
        except Exception:
            target_change_dict[character_id] = change_data
    return target_change_dict[character_id]


def _get_pending_edge_count_snapshot(character_data) -> dict:
    """复制当前未释放的寸止计数字典"""
    return {state_id: count for state_id, count in getattr(character_data.h_state, "orgasm_edge_count", {}).items() if count != 0}


def _clear_orgasm_edge_count(character_data) -> None:
    """清空角色寸止计数"""
    edge_count = getattr(character_data.h_state, "orgasm_edge_count", {})
    state_ids = set(edge_count.keys())
    try:
        from Script.Config import game_config

        for state_id, state_data in game_config.config_character_state.items():
            if getattr(state_data, "type", None) == 0:
                state_ids.add(state_id)
    except Exception:
        pass

    for state_id in state_ids:
        edge_count[state_id] = 0


def _is_release_second_behavior(second_behavior_id: str) -> bool:
    """判断二段行为是否属于本次寸止释放产生的绝顶行为"""
    return "orgasm" in second_behavior_id


def _collect_new_release_second_behaviors(character_data, before_second_behavior: dict):
    """收集释放后新增且仍待结算的绝顶二段行为"""
    result = []
    for second_behavior_id, behavior_value in getattr(character_data, "second_behavior", {}).items():
        if behavior_value == 0:
            continue
        if before_second_behavior.get(second_behavior_id, 0) != 0:
            continue
        if _is_release_second_behavior(second_behavior_id):
            result.append(second_behavior_id)
    return result


def _remove_second_behavior_from_must_lists(character_data, second_behavior_id: str) -> None:
    """从必须结算/显示列表中移除已经处理的二段行为"""
    for list_name in ("must_settle_second_behavior_id_list", "must_show_second_behavior_id_list"):
        behavior_list = getattr(character_data, list_name, [])
        while second_behavior_id in behavior_list:
            behavior_list.remove(second_behavior_id)


def _clear_queued_orgasm_edge_second_behaviors(character_data) -> None:
    """清除已经释放后的旧寸止二段行为队列"""
    second_behavior = getattr(character_data, "second_behavior", {})
    for part_prefix in ORGASM_PART_PREFIX.values():
        second_behavior_id = f"{part_prefix}_orgasm_edge"
        if second_behavior_id in second_behavior:
            second_behavior[second_behavior_id] = 0
        _remove_second_behavior_from_must_lists(character_data, second_behavior_id)


def _flush_release_second_behavior(character_id: int, change_data, second_behavior_id: str) -> None:
    """同步结算一个释放产生的二段行为"""
    from Script.Config import game_config
    from Script.Core import constant
    from Script.Design import settle_behavior, talk

    cache_obj = _cache()
    character_data = cache_obj.character_data[character_id]
    if character_data.second_behavior.get(second_behavior_id, 0) == 0:
        _remove_second_behavior_from_must_lists(character_data, second_behavior_id)
        return

    talk.handle_second_talk(character_id, second_behavior_id)
    if second_behavior_id in game_config.config_behavior_effect_data:
        for effect_id in game_config.config_behavior_effect_data[second_behavior_id]:
            if isinstance(effect_id, str) and "CVE" in effect_id:
                effect_all_value_list = effect_id.split("_")[1:]
                settle_behavior.handle_comprehensive_value_effect(character_id, effect_all_value_list, change_data)
            elif effect_id in constant.settle_second_behavior_effect_data:
                constant.settle_second_behavior_effect_data[effect_id](character_id, change_data)

    character_data.second_behavior[second_behavior_id] = 0
    _remove_second_behavior_from_must_lists(character_data, second_behavior_id)


def _flush_release_second_behaviors(character_id: int, change_data, second_behavior_ids) -> None:
    """同步结算释放产生的二段行为列表"""
    for second_behavior_id in second_behavior_ids:
        _flush_release_second_behavior(character_id, change_data, second_behavior_id)


def _get_edge_count_waves(pending_edge_count: dict):
    """把多次寸止计数拆为每部位每轮一次的结算波次"""
    remaining_count = {state_id: int(count) for state_id, count in pending_edge_count.items() if count > 0}
    first_wave = {state_id: 1 for state_id in remaining_count}
    if first_wave:
        yield first_wave

    for state_id, count in remaining_count.items():
        for _release_index in range(count - 1):
            yield {state_id: 1}


def _stable_dedupe_second_behavior_ids(second_behavior_ids):
    """按首次出现顺序去重二段行为ID"""
    result = []
    seen = set()
    for second_behavior_id in second_behavior_ids:
        if not second_behavior_id or second_behavior_id in seen:
            continue
        seen.add(second_behavior_id)
        result.append(second_behavior_id)
    return result


def _restore_preexisting_second_behavior(character_data, second_behavior_id: str, before_second_behavior: dict, before_must_settle: list, before_must_show: list) -> None:
    """恢复释放前已经存在的同名二段行为标记"""
    if before_second_behavior.get(second_behavior_id, 0) == 0:
        return

    character_data.second_behavior[second_behavior_id] = before_second_behavior[second_behavior_id]
    character_data.must_settle_second_behavior_id_list = before_must_settle.copy()
    character_data.must_show_second_behavior_id_list = before_must_show.copy()


def _flush_release_second_behavior_with_restore(character_id: int, change_data, second_behavior_id: str, before_second_behavior: dict, before_must_settle: list, before_must_show: list) -> None:
    """结算释放二段行为并恢复释放前已有的同名标记"""
    character_data = _cache().character_data[character_id]
    _flush_release_second_behavior(character_id, change_data, second_behavior_id)
    _restore_preexisting_second_behavior(character_data, second_behavior_id, before_second_behavior, before_must_settle, before_must_show)


def _settle_edge_count_wave(character_id: int, change_data, wave_count: dict) -> None:
    """结算一轮每部位一次的寸止释放"""
    from Script.Design import second_behavior

    cache_obj = _cache()
    character_data = cache_obj.character_data[character_id]
    before_second_behavior = dict(getattr(character_data, "second_behavior", {}))
    before_must_settle = list(getattr(character_data, "must_settle_second_behavior_id_list", []))
    before_must_show = list(getattr(character_data, "must_show_second_behavior_id_list", []))
    generated_second_behavior_ids = []
    original_get_second_behavior = getattr(second_behavior, "character_get_second_behavior", None)

    if original_get_second_behavior is not None:

        def record_release_second_behavior(record_character_id: int, second_behavior_id: str, reset: bool = False):
            if record_character_id == character_id and not reset and _is_release_second_behavior(second_behavior_id):
                generated_second_behavior_ids.append(second_behavior_id)
            return original_get_second_behavior(record_character_id, second_behavior_id, reset=reset)

        second_behavior.character_get_second_behavior = record_release_second_behavior

    try:
        second_behavior.orgasm_settle(character_id, change_data, un_count_orgasm_dict=wave_count)
    finally:
        if original_get_second_behavior is not None:
            second_behavior.character_get_second_behavior = original_get_second_behavior

    if generated_second_behavior_ids:
        release_second_behavior_ids = _stable_dedupe_second_behavior_ids(generated_second_behavior_ids)
    else:
        release_second_behavior_ids = _collect_new_release_second_behaviors(character_data, before_second_behavior)

    for second_behavior_id in release_second_behavior_ids:
        _flush_release_second_behavior_with_restore(character_id, change_data, second_behavior_id, before_second_behavior, before_must_settle, before_must_show)


def _get_release_bonus_second_behavior_id(character_data, state_id: int, release_count: int) -> str:
    """获取寸止解放三次以上时追加的绝顶二段行为ID"""
    if release_count < 3 or state_id not in ORGASM_PART_PREFIX:
        return ""

    ability_id = state_id if state_id <= 7 else state_id + 79
    now_degree = 3
    if character_data.ability[ability_id] < 6:
        now_degree = 2
    return f"{ORGASM_PART_PREFIX[state_id]}_orgasm_{ORGASM_DEGREE_ID_TO_NAME[now_degree]}"


def _settle_release_bonus_second_behaviors(character_id: int, change_data, pending_edge_count: dict) -> None:
    """结算聚合寸止次数触发的追加绝顶二段行为"""
    from Script.Design import second_behavior

    cache_obj = _cache()
    character_data = cache_obj.character_data[character_id]
    before_second_behavior = dict(getattr(character_data, "second_behavior", {}))
    before_must_settle = list(getattr(character_data, "must_settle_second_behavior_id_list", []))
    before_must_show = list(getattr(character_data, "must_show_second_behavior_id_list", []))

    for state_id, release_count in pending_edge_count.items():
        second_behavior_id = _get_release_bonus_second_behavior_id(character_data, state_id, release_count)
        if not second_behavior_id:
            continue
        second_behavior.character_get_second_behavior(character_id, second_behavior_id)
        _flush_release_second_behavior_with_restore(character_id, change_data, second_behavior_id, before_second_behavior, before_must_settle, before_must_show)


def _release_group_edge_for_character(character_id: int, change_data, owner_character_id: int = 0, group_context_ids=None) -> bool:
    """释放单个群交参与者的寸止计数"""
    group_context_ids = group_context_ids or []
    if not _character_can_release_group_edge(character_id, group_context_ids):
        return False

    cache_obj = _cache()
    character_data = cache_obj.character_data[character_id]
    pending_edge_count = _get_pending_edge_count_snapshot(character_data)
    if not pending_edge_count:
        return False

    release_change_data = _get_release_change_data(character_id, owner_character_id, change_data)

    character_data.h_state.orgasm_edge = 2
    try:
        for wave_count in _get_edge_count_waves(pending_edge_count):
            _settle_edge_count_wave(character_id, release_change_data, wave_count)
        _settle_release_bonus_second_behaviors(character_id, release_change_data, pending_edge_count)
    finally:
        _clear_orgasm_edge_count(character_data)
        _clear_queued_orgasm_edge_second_behaviors(character_data)
        if getattr(character_data.h_state, "orgasm_edge", 0) == 2:
            character_data.h_state.orgasm_edge = 0

    return True


def _release_group_edge_for_characters(character_ids, change_data=None, owner_character_id: int = 0, group_context_ids=None):
    """释放一组角色的群交寸止计数并返回实际释放的角色ID"""
    if change_data is None:
        change_data = _new_character_status_change()

    group_context_ids = group_context_ids or character_ids
    released_character_ids = []
    for character_id in _stable_dedupe_character_ids(character_ids):
        if _release_group_edge_for_character(character_id, change_data, owner_character_id, group_context_ids):
            released_character_ids.append(character_id)
    return released_character_ids


def _is_group_sex_npc_hp_0_end(character_id: int) -> bool:
    """判断当前角色是否正在结算群交NPC体力耗尽退出"""
    from Script.Core import constant

    cache_obj = _cache()
    if character_id not in cache_obj.character_data:
        return False
    behavior_id = cache_obj.character_data[character_id].behavior.behavior_id
    return behavior_id == getattr(constant.Behavior, "GROUP_SEX_NPC_HP_0_END", "group_sex_npc_hp_0_end")


def _release_group_sex_to_h_leavers(pre_transition_character_ids, owner_character_id: int = 0):
    """释放群交转单人H时离开群交上下文的角色"""
    from Script.Core import constant

    cache_obj = _cache()
    pl_character_data = cache_obj.character_data.get(0)
    if pl_character_data is None:
        return []

    if pl_character_data.behavior.behavior_id != getattr(constant.Behavior, "GROUP_SEX_TO_H", "group_sex_to_h"):
        return []

    continuing_target_id = pl_character_data.target_character_id
    leaver_ids = [character_id for character_id in pre_transition_character_ids if character_id != continuing_target_id]
    return _release_group_edge_for_characters(
        leaver_ids,
        _new_character_status_change(),
        owner_character_id=owner_character_id,
        group_context_ids=pre_transition_character_ids,
    )


def _group_sex_mode_is_on(character_id: int) -> bool:
    """判断指定角色视角下是否处于群交模式"""
    try:
        from Script.Design import handle_premise

        return bool(handle_premise.handle_group_sex_mode_on(character_id))
    except Exception:
        return bool(getattr(_cache(), "group_sex_mode", False))


def _should_release_before_unconscious_recovery(character_id: int) -> bool:
    """判断无意识恢复流程是否需要提前释放群交寸止"""
    cache_obj = _cache()
    character_data = cache_obj.character_data.get(character_id)
    if character_data is None:
        return False

    target_character_id = getattr(character_data, "target_character_id", character_id)
    target_data = cache_obj.character_data.get(target_character_id)
    if target_data is None or getattr(target_data.sp_flag, "unconscious_h", 0) == 0:
        return False

    return _group_sex_mode_is_on(character_id)


def _stop_player_move_if_interrupted(character_data) -> bool:
    cache_obj = _cache()
    if character_data.sp_flag.move_stop or character_data.sp_flag.is_h or cache_obj.group_sex_mode:
        character_data.sp_flag.move_stop = False
        character_data.behavior.move_target = []
        character_data.behavior.move_final_target = []
        return True
    return False


def _stop_player_move_on_h_interrupt() -> None:
    from Script.Core import constant

    cache_obj = _cache()
    pl_character_data = cache_obj.character_data[0]
    if pl_character_data.behavior.behavior_id == constant.Behavior.MOVE and pl_character_data.behavior.move_final_target != []:
        pl_character_data.sp_flag.move_stop = True
        pl_character_data.behavior.move_final_target = []


def _stop_group_sex_h_move(character_id: int) -> bool:
    if not character_id:
        return False

    from Script.Core import constant
    from Script.Design import handle_premise

    cache_obj = _cache()
    character_data = cache_obj.character_data[character_id]
    if character_data.sp_flag.is_h and handle_premise.handle_group_sex_mode_on(character_id):
        character_data.target_character_id = character_id
        character_data.behavior.behavior_id = constant.Behavior.WAIT
        character_data.behavior.duration = 1
        character_data.behavior.start_time = cache_obj.game_time
        character_data.behavior.move_target = []
        character_data.behavior.move_src = []
        character_data.behavior.move_final_target = []
        character_data.state = constant.CharacterStatus.STATUS_WAIT
        return True
    return False


def _clear_group_sex_masturbation_flag(character_id: int) -> None:
    from Script.Design import handle_premise

    cache_obj = _cache()
    if handle_premise.handle_masturebate_flag_3(character_id):
        character_data = cache_obj.character_data[character_id]
        character_data.sp_flag.masturebate = 0
        handle_premise.settle_chara_unnormal_flag(character_id, 1)


def _clear_group_template_masturbation_flags() -> None:
    try:
        from Script.System.Sex_System import group_sex_panel

        for character_id in group_sex_panel.count_group_sex_character_list():
            if character_id:
                _clear_group_sex_masturbation_flag(character_id)
    except Exception:
        return


def _get_group_sex_masturbation_action_key():
    """获取当前玩家行动切片的群交自慰消费标识"""
    global _GROUP_SEX_MASTURBATION_ACTION_SERIAL, _GROUP_SEX_MASTURBATION_OVER_OBJECT

    cache_obj = _cache()
    over_behavior_character = getattr(cache_obj, "over_behavior_character", None)
    if over_behavior_character is not _GROUP_SEX_MASTURBATION_OVER_OBJECT:
        _GROUP_SEX_MASTURBATION_OVER_OBJECT = over_behavior_character
        _GROUP_SEX_MASTURBATION_ACTION_SERIAL += 1
        _GROUP_SEX_MASTURBATION_ACTION_KEYS.clear()
    return _GROUP_SEX_MASTURBATION_ACTION_SERIAL


def _has_consumed_group_sex_masturbation_action(character_id: int) -> bool:
    """判断该角色本次玩家行动是否已经执行过群交自慰"""
    return _GROUP_SEX_MASTURBATION_ACTION_KEYS.get(character_id) == _get_group_sex_masturbation_action_key()


def _mark_group_sex_masturbation_action_consumed(character_id: int) -> None:
    """记录该角色本次玩家行动已经执行过群交自慰"""
    _GROUP_SEX_MASTURBATION_ACTION_KEYS[character_id] = _get_group_sex_masturbation_action_key()


def _call_with_preserved_player_target(func):
    """调用群交AI时保护玩家当前交互对象"""
    cache_obj = _cache()
    if 0 not in cache_obj.character_data:
        return func()

    player_character_data = cache_obj.character_data[0]
    old_target_character_id = player_character_data.target_character_id
    try:
        return func()
    finally:
        if 0 in cache_obj.character_data:
            cache_obj.character_data[0].target_character_id = old_target_character_id


def _has_pain_as_pleasure(character_id: int) -> bool:
    cache_obj = _cache()
    if character_id not in cache_obj.character_data:
        return False
    return bool(cache_obj.character_data[character_id].hypnosis.pain_as_pleasure)


def _call_with_disabled_pain_as_pleasure(character_id: int, func):
    cache_obj = _cache()
    character_data = cache_obj.character_data[character_id]
    old_flag = character_data.hypnosis.pain_as_pleasure
    character_data.hypnosis.pain_as_pleasure = False
    try:
        return func()
    finally:
        character_data.hypnosis.pain_as_pleasure = old_flag


def _is_character_tired_for_group_sex(character_id: int) -> bool:
    """判断角色是否已不适合继续参与或打扰群交"""
    from Script.Design import attr_calculation

    cache_obj = _cache()
    if character_id not in cache_obj.character_data:
        return False

    character_data = cache_obj.character_data[character_id]
    return (
        getattr(character_data, "hit_point", 0) <= 1
        or bool(getattr(character_data.sp_flag, "tired", False))
        or attr_calculation.get_tired_level(getattr(character_data, "tired_point", 0)) >= 2
    )


def _should_auto_leave_group_sex_discovery(character_id: int) -> bool:
    """判断疲劳发现者是否应直接离开当前群交发现事件"""
    if not character_id:
        return False

    from Script.Design import handle_premise

    return handle_premise.handle_group_sex_mode_on(0) and _is_character_tired_for_group_sex(character_id)


def _prepare_h_discovery_common_state(panel) -> None:
    """复用被发现面板进入时的通用状态设置"""
    from Script.Core import game_type
    from Script.Settle import default

    cache_obj = _cache()
    panel.pl_chara_data.behavior.h_interrupt_chara_name = panel.find_chara_data.name
    default.handle_masturebate_to_pl_flag_0(panel.character_id, 1, game_type.CharacterStatusChange(), cache_obj.game_time)
    default.handle_target_to_player(panel.character_id, 1, game_type.CharacterStatusChange(), cache_obj.game_time)
    default.handle_see_pl_h(panel.character_id, 1, game_type.CharacterStatusChange(), cache_obj.game_time)
    panel.find_chara_data.behavior.duration = 1


def _auto_leave_group_sex_discovery(panel):
    """疲劳角色发现群交时不弹按钮，直接按既有离开行为处理"""
    from Script.Config import game_config
    from Script.Core import constant

    cache_obj = _cache()
    _prepare_h_discovery_common_state(panel)
    panel.find_chara_data.behavior.behavior_id = constant.Behavior.SEE_H_AND_LEAVE
    panel.find_chara_data.behavior.duration = game_config.config_behavior[panel.find_chara_data.behavior.behavior_id].duration
    if hasattr(cache_obj, "now_panel_id"):
        cache_obj.now_panel_id = constant.Panel.IN_SCENE
    return None


def _get_mark_debuff_adjust(ability_level: int):
    from Script.Design import attr_calculation

    return attr_calculation.get_mark_debuff_adjust(ability_level)


def _settle_direct_pain_increase(character_id: int, pain_value: int, change_data, change_data_to_target_change=None) -> bool:
    """把绕过通用结算的正向苦痛转为心理快感"""
    if pain_value <= 0 or not _has_pain_as_pleasure(character_id):
        return False

    character_data = _cache().character_data[character_id]
    _ORIGINAL_BASE_STATE_COMMON_SETTLE(
        character_id,
        pain_value,
        23,
        0,
        ability_level=character_data.ability[36],
        tenths_add=False,
        change_data=change_data,
        change_data_to_target_change=change_data_to_target_change,
    )
    return True


def _call_original_second_effect(effect_id: int, character_id: int, change_data):
    return _ORIGINAL_SECOND_EFFECTS[effect_id](character_id, change_data)


def patched_base_chara_state_common_settle(
    character_id: int,
    add_time: int,
    state_id: int,
    base_value: int = 30,
    ability_level: int = -1,
    extra_adjust: float = 0,
    tenths_add: bool = True,
    change_data=None,
    change_data_to_target_change=None,
):
    def call_original_base():
        return _ORIGINAL_BASE_STATE_COMMON_SETTLE(
            character_id,
            add_time,
            state_id,
            base_value=base_value,
            ability_level=ability_level,
            extra_adjust=extra_adjust,
            tenths_add=tenths_add,
            change_data=change_data,
            change_data_to_target_change=change_data_to_target_change,
        )

    # 苦痛快感化只转换苦痛上升；苦痛下降时临时关闭开关，复用上游原结算。
    if state_id == 17 and _has_pain_as_pleasure(character_id) and add_time + base_value <= 0:
        return _call_with_disabled_pain_as_pleasure(character_id, call_original_base)
    return call_original_base()


def patched_handle_hypnosis_cancel(character_id: int, add_time: int, change_data, now_time):
    result = _ORIGINAL_HYPNOSIS_CANCEL_EFFECT(character_id, add_time, change_data, now_time)
    if not add_time:
        return result

    cache_obj = _cache()
    if character_id in cache_obj.character_data:
        target_character_id = cache_obj.character_data[character_id].target_character_id
        if target_character_id in cache_obj.character_data:
            cache_obj.character_data[target_character_id].hypnosis.pain_as_pleasure = False
    return result


def _manual_hypnosis_type_degree_threshold(hypnosis_panel) -> int:
    """取得手动催眠类型选择的最低催眠度阈值"""
    try:
        return hypnosis_panel.game_config.config_hypnosis_type[0].hypnosis_degree
    except Exception:
        return 50


def _hypnosis_degree_need_for_current_type(hypnosis_panel, hypnosis_type: int) -> int:
    """取得当前催眠类型需要的催眠度"""
    try:
        return hypnosis_panel.game_config.config_hypnosis_type[hypnosis_type].hypnosis_degree
    except Exception:
        return _manual_hypnosis_type_degree_threshold(hypnosis_panel)


def _apply_current_hypnosis_state(target_character_id: int) -> int:
    """按博士当前催眠类型把目标修正到对应催眠状态"""
    from Script.Design import handle_premise, map_handle
    from Script.UI.Panel import hypnosis_panel

    cache_obj = _cache()
    pl_character_data = cache_obj.character_data.get(0)
    target_character_data = cache_obj.character_data.get(target_character_id)
    if pl_character_data is None or target_character_data is None or target_character_id == 0:
        return 0

    hypnosis_type = getattr(getattr(pl_character_data, "pl_ability", None), "hypnosis_type", 0)
    if hypnosis_type == 0 or hypnosis_type not in hypnosis_panel.game_config.config_hypnosis_type:
        return 0

    hypnosis_degree = getattr(getattr(target_character_data, "hypnosis", None), "hypnosis_degree", 0)
    hypnosis_degree_need = _hypnosis_degree_need_for_current_type(hypnosis_panel, hypnosis_type)
    if hypnosis_degree < hypnosis_degree_need:
        return 0

    if hypnosis_type == 2:
        scene_path = map_handle.get_map_system_path_str_for_list(pl_character_data.position)
        scene_data = cache_obj.scene_data.get(scene_path)
        if scene_data is None or scene_data.close_type != 1:
            return 0
        if scene_data.close_flag == 0:
            scene_data.close_flag = scene_data.close_type
        pl_character_data.pl_ability.air_hypnosis_position = pl_character_data.position

    target_character_data.sp_flag.unconscious_h = hypnosis_type + 3
    handle_premise.settle_chara_unnormal_flag(target_character_id, 5)
    handle_premise.settle_chara_unnormal_flag(target_character_id, 6)
    return 1


def _should_prompt_manual_hypnosis_type(character_id: int) -> bool:
    """判断单人催眠后是否需要让玩家手动选择本次催眠类型"""
    cache_obj = _cache()
    character_data = cache_obj.character_data.get(character_id)
    if character_data is None or getattr(character_data, "dead", False):
        return False

    pl_ability = getattr(character_data, "pl_ability", None)
    if getattr(pl_ability, "hypnosis_type", 0) != 0:
        return False

    if getattr(character_data, "sanity_point", 1) == 0:
        return False

    target_character_id = getattr(character_data, "target_character_id", 0)
    if not target_character_id or target_character_id not in cache_obj.character_data:
        return False

    target_character_data = cache_obj.character_data[target_character_id]
    if getattr(getattr(target_character_data, "sp_flag", None), "unconscious_h", 0):
        return False

    from Script.UI.Panel import hypnosis_panel

    hypnosis_degree = getattr(getattr(target_character_data, "hypnosis", None), "hypnosis_degree", 0)
    return hypnosis_degree >= _manual_hypnosis_type_degree_threshold(hypnosis_panel)


def _draw_manual_hypnosis_type_selector(character_id: int) -> None:
    """绘制单人催眠完成后的手动类型选择面板，并保持默认类型仍为无"""
    from Script.UI.Panel import hypnosis_panel

    cache_obj = _cache()
    character_data = cache_obj.character_data[character_id]
    old_hypnosis_type = character_data.pl_ability.hypnosis_type
    now_panel = hypnosis_panel.Chose_Hypnosis_Type_Panel(hypnosis_panel.window_width, True)
    now_panel.draw()
    if old_hypnosis_type == 0:
        character_data.pl_ability.hypnosis_type = old_hypnosis_type


def _target_is_in_hypnosis_unconscious_state(character_id: int) -> bool:
    """判断交互目标是否处于催眠类无意识状态"""
    try:
        cache_obj = _cache()
        character_data = cache_obj.character_data.get(character_id)
        if character_data is None:
            return False

        target_character_id = getattr(character_data, "target_character_id", 0)
        target_data = cache_obj.character_data.get(target_character_id)
        if target_data is None:
            return False

        return getattr(getattr(target_data, "sp_flag", None), "unconscious_h", 0) in HYPNOSIS_UNCONSCIOUS_FLAGS
    except Exception:
        return False


def patched_get_weight_from_premise_dict(talk_premise_dict: set, character_id: int, calculated_premise_dict: dict, weight_all_to_1_flag: bool = False, unconscious_pass_flag: bool = False):
    """催眠态口上不应被通用睡眠/醉酒/时停门禁吞掉"""
    if not unconscious_pass_flag and _target_is_in_hypnosis_unconscious_state(character_id):
        unconscious_pass_flag = True
    return _ORIGINAL_GET_WEIGHT_FROM_PREMISE_DICT(
        talk_premise_dict,
        character_id,
        calculated_premise_dict,
        weight_all_to_1_flag=weight_all_to_1_flag,
        unconscious_pass_flag=unconscious_pass_flag,
    )


def patched_handle_hypnosis_one(character_id: int, add_time: int, change_data, now_time):
    """单人催眠结算后，幂等校正当前目标的催眠状态"""
    result = _ORIGINAL_HYPNOSIS_ONE_EFFECT(character_id, add_time, change_data, now_time)
    if not add_time:
        return result

    cache_obj = _cache()
    character_data = cache_obj.character_data.get(character_id)
    if character_data is None:
        return result

    target_character_id = getattr(character_data, "target_character_id", 0)
    if _apply_current_hypnosis_state(target_character_id):
        return result

    if _should_prompt_manual_hypnosis_type(character_id):
        _draw_manual_hypnosis_type_selector(character_id)
    return result


def patched_handle_group_sex_end_h_add_hpmp_max(character_id: int, add_time: int, change_data, now_time):
    """在群交结束上限结算前释放群交寸止计数"""
    if add_time:
        participant_ids = _collect_group_sex_participant_ids()
        _release_group_edge_for_characters(participant_ids, change_data, owner_character_id=character_id, group_context_ids=participant_ids)
    return _ORIGINAL_GROUP_SEX_END_H_ADD_HPMP_MAX(character_id, add_time, change_data, now_time)


def patched_handle_end_h_add_hpmp_max(character_id: int, add_time: int, change_data, now_time):
    """在群交NPC单人退出上限结算前释放该NPC寸止计数"""
    if add_time and _is_group_sex_npc_hp_0_end(character_id):
        participant_ids = _stable_dedupe_character_ids(_collect_group_sex_participant_ids() + [character_id])
        _release_group_edge_for_character(character_id, change_data, owner_character_id=character_id, group_context_ids=participant_ids)
    return _ORIGINAL_END_H_ADD_HPMP_MAX(character_id, add_time, change_data, now_time)


def patched_recover_from_unconscious_h(character_id: int, info_text: str = ""):
    """在无意识恢复清空群交模板前释放群交寸止计数"""
    participant_ids = []
    if _should_release_before_unconscious_recovery(character_id):
        participant_ids = _collect_group_sex_participant_ids()
        _release_group_edge_for_characters(
            participant_ids,
            _new_character_status_change(),
            owner_character_id=character_id,
            group_context_ids=participant_ids,
        )
    return call_original(HN_AI_H, "recover_from_unconscious_h", character_id, info_text)


def patched_handle_add_small_pain(character_id: int, change_data):
    character_data = _cache().character_data[character_id]
    now_lust = character_data.status_data[17]
    now_add_lust = 20
    now_add_lust *= _get_mark_debuff_adjust(character_data.ability[15])
    now_add_lust += now_lust / 20
    now_add_lust = int(now_add_lust)

    if _settle_direct_pain_increase(character_id, now_add_lust, change_data):
        return
    return _call_original_second_effect(SECOND_EFFECT_ADD_SMALL_PAIN, character_id, change_data)


def patched_handle_add_middle_pain(character_id: int, change_data):
    character_data = _cache().character_data[character_id]
    now_lust = character_data.status_data[17]
    now_add_lust = 100
    now_add_lust *= _get_mark_debuff_adjust(character_data.ability[15])
    now_add_lust += now_lust / 10
    now_add_lust = int(now_add_lust)

    if _settle_direct_pain_increase(character_id, now_add_lust, change_data):
        return
    return _call_original_second_effect(SECOND_EFFECT_ADD_MIDDLE_PAIN, character_id, change_data)


def patched_handle_add_large_pain(character_id: int, change_data):
    character_data = _cache().character_data[character_id]
    now_add_lust = 1000
    now_add_lust *= _get_mark_debuff_adjust(character_data.ability[15])
    now_add_lust = int(now_add_lust)

    if _settle_direct_pain_increase(character_id, now_add_lust, change_data):
        return
    return _call_original_second_effect(SECOND_EFFECT_ADD_LARGE_PAIN, character_id, change_data)


def patched_handle_extra_orgasm(character_id: int, change_data):
    if not _has_pain_as_pleasure(character_id):
        return _call_original_second_effect(SECOND_EFFECT_EXTRA_ORGASM, character_id, change_data)

    from Script.Config import normal_config
    from Script.Core import get_text
    from Script.UI.Moudle import draw

    _ = get_text._
    character_data = _cache().character_data[character_id]
    if character_data.dead:
        return

    all_extra_count = character_data.h_state.extra_orgasm_count
    if all_extra_count > 0:
        extra_pain = 100 * (1.2 ** all_extra_count)
        extra_terror = 100 * (1.2 ** all_extra_count)
        extra_pain *= _get_mark_debuff_adjust(character_data.ability[15])
        extra_pain = int(extra_pain)
        extra_terror *= _get_mark_debuff_adjust(character_data.ability[17])
        extra_terror = int(extra_terror)

        _settle_direct_pain_increase(character_id, extra_pain, change_data)
        character_data.status_data[18] += extra_terror
        character_data.status_data[18] = min(99999, character_data.status_data[18])
        change_data.status_data.setdefault(18, 0)
        change_data.status_data[18] += extra_terror

        now_draw = draw.NormalDraw()
        now_draw.text = _("\n{0}因为第{1}次的连续额外绝顶而被迫感受到了更多的心理快感和恐怖\n").format(character_data.name, all_extra_count)
        now_draw.width = normal_config.config_normal.text_width
        now_draw.draw()
        character_data.h_state.extra_orgasm_count = 0


def patched_judge_character_tired_sleep(character_id: int):
    cache_obj = _cache()
    pre_group_sex_character_ids = []
    if character_id and character_id in cache_obj.character_data and _group_sex_mode_is_on(character_id):
        pre_group_sex_character_ids = _collect_group_sex_participant_ids()

    if character_id in cache_obj.character_data:
        character_data = cache_obj.character_data[character_id]
        if _is_orgasm_batch_settling(character_id) or (character_id == 0 and _is_orgasm_batch_settling(character_data.target_character_id)):
            return

    from Script.Design import attr_calculation, character_behavior, handle_premise

    should_rejudge_status = False
    if character_id and character_id in cache_obj.character_data:
        character_data = cache_obj.character_data[character_id]
        if (character_data.sp_flag.is_h or character_data.sp_flag.is_follow) and handle_premise.handle_group_sex_mode_on(character_id):
            should_rejudge_status = (
                character_data.hit_point <= 1
                or character_data.sp_flag.tired
                or attr_calculation.get_tired_level(character_data.tired_point) >= 2
            )

    result = call_original(HN_AI, "judge_character_tired_sleep", character_id)
    if pre_group_sex_character_ids:
        _release_group_sex_to_h_leavers(pre_group_sex_character_ids, owner_character_id=0)
    if should_rejudge_status and character_id in cache_obj.character_data:
        character_behavior.judge_character_status(character_id)
    return result


def patched_find_character_target(character_id: int, now_time: datetime.datetime):
    from Script.Config import game_config
    from Script.Core import constant
    from Script.Design import handle_npc_ai, handle_premise

    cache_obj = _cache()
    character_data = cache_obj.character_data[character_id]

    if (
        character_data.sp_flag.is_h
        and handle_premise.handle_group_sex_mode_on(character_id)
        and handle_premise.handle_masturebate_flag_3(character_id)
    ):
        if _has_consumed_group_sex_masturbation_action(character_id):
            _clear_group_sex_masturbation_flag(character_id)
            cache_obj.over_behavior_character.add(character_id)
            return

        target, weight, judge, new_premise_data = handle_npc_ai.search_target(
            character_id,
            ["default91"],
            set(),
            {},
            {},
            get_first_only=True,
        )
        if judge:
            target_config = game_config.config_target[target]
            constant.handle_state_machine_data[target_config.state_machine_id](character_id)
            _mark_group_sex_masturbation_action_consumed(character_id)
        else:
            _clear_group_sex_masturbation_flag(character_id)
            cache_obj.over_behavior_character.add(character_id)
        return

    return call_original(HN_AI, "find_character_target", character_id, now_time)


def patched_sex_be_discovered_draw(self):
    if _should_auto_leave_group_sex_discovery(self.character_id):
        return _auto_leave_group_sex_discovery(self)
    return _ORIGINAL_SEX_BE_DISCOVERED_DRAW(self)


def patched_own_charcter_move(target_scene: list):
    from Script.Core import constant
    from Script.Design import character_move as character_move_module

    cache_obj = _cache()
    move_now = "end"
    while True:
        character_data = cache_obj.character_data[0]
        move_now = "end"
        if _stop_player_move_if_interrupted(character_data):
            break

        if character_data.position != target_scene:
            move_now, now_path_list, now_target_position, now_need_time = character_move_module.character_move(0, target_scene)
            if move_now in ["null", "wait_open", "door_lock"]:
                break
            character_data.behavior.behavior_id = constant.Behavior.MOVE
            character_data.behavior.move_target = now_target_position
            character_data.behavior.move_src = character_data.position
            character_data.behavior.move_final_target = target_scene
            character_data.behavior.duration = now_need_time
            character_data.behavior.start_time = cache_obj.game_time
            character_data.state = constant.CharacterStatus.STATUS_MOVE
            character_data.action_info.ask_close_door_flag = False
            character_move_module.update.game_update_flow(now_need_time)
            character_data = cache_obj.character_data[0]
            if _stop_player_move_if_interrupted(character_data):
                break
        else:
            break

    cache_obj.character_data[0].target_character_id = 0
    if move_now in ["Null", "null", "wait_open", "door_lock"]:
        cache_obj.now_panel_id = constant.Panel.SEE_MAP
    else:
        cache_obj.now_panel_id = constant.Panel.IN_SCENE


def patched_judge_character_h_obscenity_unconscious(character_id: int, pl_start_time: datetime.datetime) -> int:
    from Script.Core import constant, game_type
    from Script.Design import character_behavior, handle_npc_ai_in_h, handle_premise, map_handle
    from Script.Settle import default

    cache_obj = _cache()
    character_data = cache_obj.character_data[character_id]
    pl_character_data = cache_obj.character_data[0]

    if character_id == 0:
        if character_data.position != character_data.pl_ability.air_hypnosis_position:
            character_data.pl_ability.air_hypnosis_position = ""
        if handle_premise.handle_last_cmd_blowjob_type(0):
            for dirty_key in character_data.dirty.penis_dirty_dict:
                character_data.dirty.penis_dirty_dict[dirty_key] = False
        if handle_premise.handle_dr_have_sex_position(0):
            if handle_premise.handle_last_cmd_handjob_type(0) or handle_premise.handle_last_cmd_blowjob_type(0) or handle_premise.handle_last_cmd_paizuri_type(0):
                character_data.h_state.current_sex_position = -1
        if handle_premise.handle_dr_have_sex_position(0):
            if character_data.h_state.insert_position not in [6, 7]:
                character_data.h_state.current_womb_sex_position = 0
        if character_data.h_state.just_shoot == 1:
            character_data.h_state.just_shoot = 2
        else:
            character_data.h_state.just_shoot = 0
        special_end_list = constant.special_end_H_list
        if len(cache_obj.pl_pre_behavior_instruce) and cache_obj.pl_pre_behavior_instruce[-1] in special_end_list and character_data.behavior.behavior_id not in special_end_list:
            default.handle_both_h_state_reset(0, 1, change_data=game_type.CharacterStatusChange(), now_time=datetime.datetime(1, 1, 1))
        if handle_premise.handle_time_stop_on(character_id) and handle_premise.handle_carry_somebody_in_time_stop(character_id):
            now_carry_chara_id = pl_character_data.pl_ability.carry_chara_id_in_time_stop
            now_carry_character_data = cache_obj.character_data[now_carry_chara_id]
            map_handle.character_move_scene(now_carry_character_data.position, pl_character_data.position, now_carry_chara_id)

    if character_id == 0:
        return 1

    if handle_premise.handle_self_orgasm_edge_relase(character_id):
        default.handle_self_orgasm_edge_off(character_id, 1, change_data=game_type.CharacterStatusChange(), now_time=datetime.datetime(1, 1, 1))
    if handle_premise.handle_self_time_stop_orgasm_relase(character_id):
        character_data.h_state.time_stop_release = False

    if handle_premise.handle_not_in_player_scene(character_id):
        if handle_premise.handle_self_is_h(character_id):
            character_data.sp_flag.is_h = False
            character_data.sp_flag.unconscious_h = 0
            character_data.behavior.behavior_id = constant.Behavior.END_H
            character_data.state = constant.CharacterStatus.STATUS_END_H
            character_data.behavior.start_time = pl_start_time
            character_data.behavior.duration = 1
            character_data.target_character_id = character_id
        if handle_premise.handle_unconscious_flag_1(character_id):
            character_data.sp_flag.unconscious_h = 0
        if handle_premise.handle_unconscious_flag_5(character_id) and character_data.position != pl_character_data.pl_ability.air_hypnosis_position:
            character_data.sp_flag.unconscious_h = 0
        if handle_premise.handle_hidden_sex_mode_ge_1(character_id):
            character_data.sp_flag.hidden_sex_mode = 0
        if handle_premise.handle_exhibitionism_sex_mode_ge_1(character_id):
            character_data.sp_flag.exhibitionism_sex_mode = 0
        handle_premise.settle_chara_unnormal_flag(character_id, 5)
        handle_premise.settle_chara_unnormal_flag(character_id, 6)

    if character_data.sp_flag.is_h or character_data.hypnosis.blockhead:
        if character_data.behavior.behavior_id == constant.Behavior.SLEEP:
            return 1
        if not handle_premise.handle_normal_6(character_id):
            return 1
        if handle_premise.handle_group_sex_mode_on(character_id):
            if handle_premise.handle_npc_ai_type_1_in_group_sex(character_id) or handle_premise.handle_npc_ai_type_2_in_group_sex(character_id):
                handle_npc_ai_in_h.npc_ai_in_group_sex(character_id)
                if handle_premise.handle_masturebate_flag_3(character_id):
                    return 1
            elif character_data.h_state.sex_assist:
                character_behavior.judge_character_status(character_id)
                character_data.h_state.sex_assist = False
        character_data.behavior.behavior_id = constant.Behavior.WAIT
        character_data.state = constant.CharacterStatus.STATUS_WAIT
        character_data.behavior.start_time = pl_start_time
        character_data.behavior.duration = pl_character_data.behavior.duration
        character_data.target_character_id = character_id
        if character_data.behavior.duration == 0:
            past_time = int((cache_obj.game_time.timestamp() - pl_start_time.timestamp()) / 60)
            character_data.behavior.duration = max(1, past_time)

    return 1


def patched_npc_active_h():
    """保留原版逆推流程，仅在进入流程前清理被H中断的移动目标"""
    _stop_player_move_on_h_interrupt()
    return call_original(HN_AI_H, "npc_active_h")


def patched_npc_ai_in_group_sex(character_id: int):
    result = _call_with_preserved_player_target(lambda: call_original(HN_AI_H, "npc_ai_in_group_sex", character_id))
    # 群交自慰标记会被后续AI目标default91消费，并由正式结算清理
    return result


def patched_npc_ai_in_group_sex_type_3():
    result = _call_with_preserved_player_target(lambda: call_original(HN_AI_H, "npc_ai_in_group_sex_type_3"))
    # 群交自慰标记会被后续AI目标default91消费，并由正式结算清理
    return result


def patched_general_movement_module(character_id: int, target_scene: list, show_info_flag=True):
    if _stop_group_sex_h_move(character_id):
        return False
    return _ORIGINAL_GENERAL_MOVEMENT_MODULE(character_id, target_scene, show_info_flag=show_info_flag)


def patched_character_continue_move(character_id: int):
    if _stop_group_sex_h_move(character_id):
        return
    return _ORIGINAL_CHARACTER_CONTINUE_MOVE(character_id)


def _patch_base_state_common_settle() -> None:
    global _ORIGINAL_BASE_STATE_COMMON_SETTLE

    from Script.Settle import common_default

    current_base = common_default.base_chara_state_common_settle
    if _ORIGINAL_BASE_STATE_COMMON_SETTLE is None:
        _ORIGINAL_BASE_STATE_COMMON_SETTLE = getattr(current_base, "_local_bugfix_original", current_base)
    patched_base_chara_state_common_settle._local_bugfix_original = _ORIGINAL_BASE_STATE_COMMON_SETTLE
    common_default.base_chara_state_common_settle = patched_base_chara_state_common_settle

    for module_name in ["Script.Settle.default", "Script.Settle.Second_effect", "Script.Settle.realtime_settle", "Script.Settle.item_effect"]:
        try:
            module = __import__(module_name, fromlist=["base_chara_state_common_settle"])
        except Exception:
            continue
        if hasattr(module, "base_chara_state_common_settle"):
            setattr(module, "base_chara_state_common_settle", patched_base_chara_state_common_settle)


def _patch_hypnosis_cancel_effect() -> None:
    global _ORIGINAL_HYPNOSIS_CANCEL_EFFECT

    from Script.Core import constant
    from Script.Settle import default as settle_default

    current_effect = constant.settle_behavior_effect_data.get(BEHAVIOR_EFFECT_HYPNOSIS_CANCEL, settle_default.handle_hypnosis_cancel)
    if _ORIGINAL_HYPNOSIS_CANCEL_EFFECT is None:
        _ORIGINAL_HYPNOSIS_CANCEL_EFFECT = getattr(current_effect, "_local_bugfix_original", current_effect)
    patched_handle_hypnosis_cancel._local_bugfix_original = _ORIGINAL_HYPNOSIS_CANCEL_EFFECT
    constant.settle_behavior_effect_data[BEHAVIOR_EFFECT_HYPNOSIS_CANCEL] = patched_handle_hypnosis_cancel
    settle_default.handle_hypnosis_cancel = patched_handle_hypnosis_cancel


def _patch_hypnosis_one_effect() -> None:
    """安装单人催眠默认手动类型选择补丁"""
    global _ORIGINAL_HYPNOSIS_ONE_EFFECT

    from Script.Core import constant
    from Script.Settle import default as settle_default

    current_effect = constant.settle_behavior_effect_data.get(BEHAVIOR_EFFECT_HYPNOSIS_ONE, settle_default.handle_hypnosis_one)
    if _ORIGINAL_HYPNOSIS_ONE_EFFECT is None:
        _ORIGINAL_HYPNOSIS_ONE_EFFECT = getattr(current_effect, "_local_bugfix_original", current_effect)
    patched_handle_hypnosis_one._local_bugfix_original = _ORIGINAL_HYPNOSIS_ONE_EFFECT
    constant.settle_behavior_effect_data[BEHAVIOR_EFFECT_HYPNOSIS_ONE] = patched_handle_hypnosis_one
    settle_default.handle_hypnosis_one = patched_handle_hypnosis_one


def _patch_get_weight_from_premise_dict() -> None:
    """安装心控逆推口上的前提权重包装"""
    global _ORIGINAL_GET_WEIGHT_FROM_PREMISE_DICT

    from Script.Design import handle_premise

    current_func = handle_premise.get_weight_from_premise_dict
    if _ORIGINAL_GET_WEIGHT_FROM_PREMISE_DICT is None:
        _ORIGINAL_GET_WEIGHT_FROM_PREMISE_DICT = getattr(current_func, "_local_bugfix_original", current_func)
    patched_get_weight_from_premise_dict._local_bugfix_original = _ORIGINAL_GET_WEIGHT_FROM_PREMISE_DICT
    handle_premise.get_weight_from_premise_dict = patched_get_weight_from_premise_dict


def _patch_group_sex_edge_release_effects() -> None:
    """安装群交寸止释放相关的行为效果包装"""
    global _ORIGINAL_END_H_ADD_HPMP_MAX, _ORIGINAL_GROUP_SEX_END_H_ADD_HPMP_MAX

    from Script.Core import constant
    from Script.Settle import default as settle_default

    current_group_end_effect = constant.settle_behavior_effect_data.get(
        BEHAVIOR_EFFECT_GROUP_SEX_END_H_ADD_HPMP_MAX,
        settle_default.handle_group_sex_end_h_add_hpmp_max,
    )
    if _ORIGINAL_GROUP_SEX_END_H_ADD_HPMP_MAX is None:
        _ORIGINAL_GROUP_SEX_END_H_ADD_HPMP_MAX = getattr(current_group_end_effect, "_local_bugfix_original", current_group_end_effect)
    patched_handle_group_sex_end_h_add_hpmp_max._local_bugfix_original = _ORIGINAL_GROUP_SEX_END_H_ADD_HPMP_MAX
    constant.settle_behavior_effect_data[BEHAVIOR_EFFECT_GROUP_SEX_END_H_ADD_HPMP_MAX] = patched_handle_group_sex_end_h_add_hpmp_max
    settle_default.handle_group_sex_end_h_add_hpmp_max = patched_handle_group_sex_end_h_add_hpmp_max

    current_end_h_effect = constant.settle_behavior_effect_data.get(BEHAVIOR_EFFECT_END_H_ADD_HPMP_MAX, settle_default.handle_end_h_add_hpmp_max)
    if _ORIGINAL_END_H_ADD_HPMP_MAX is None:
        _ORIGINAL_END_H_ADD_HPMP_MAX = getattr(current_end_h_effect, "_local_bugfix_original", current_end_h_effect)
    patched_handle_end_h_add_hpmp_max._local_bugfix_original = _ORIGINAL_END_H_ADD_HPMP_MAX
    constant.settle_behavior_effect_data[BEHAVIOR_EFFECT_END_H_ADD_HPMP_MAX] = patched_handle_end_h_add_hpmp_max
    settle_default.handle_end_h_add_hpmp_max = patched_handle_end_h_add_hpmp_max


def _patch_second_effect(effect_id: int, patched_func, function_name: str) -> None:
    from Script.Core import constant
    from Script.Settle import Second_effect

    current_effect = constant.settle_second_behavior_effect_data.get(effect_id)
    if current_effect is not None:
        _ORIGINAL_SECOND_EFFECTS[effect_id] = getattr(current_effect, "_local_bugfix_original", current_effect)
        patched_func._local_bugfix_original = _ORIGINAL_SECOND_EFFECTS[effect_id]
        constant.settle_second_behavior_effect_data[effect_id] = patched_func
    setattr(Second_effect, function_name, patched_func)


def _patch_pain_second_effects() -> None:
    _patch_second_effect(SECOND_EFFECT_ADD_SMALL_PAIN, patched_handle_add_small_pain, "handle_add_small_pain")
    _patch_second_effect(SECOND_EFFECT_ADD_MIDDLE_PAIN, patched_handle_add_middle_pain, "handle_add_middle_pain")
    _patch_second_effect(SECOND_EFFECT_ADD_LARGE_PAIN, patched_handle_add_large_pain, "handle_add_large_pain")
    _patch_second_effect(SECOND_EFFECT_EXTRA_ORGASM, patched_handle_extra_orgasm, "handle_extra_orgasm")


def _patch_sex_be_discovered_panel() -> None:
    global _ORIGINAL_SEX_BE_DISCOVERED_DRAW

    from Script.System.Sex_System import sex_be_discovered_panel

    current_draw = sex_be_discovered_panel.Sex_Be_Discovered_Panel.draw
    if _ORIGINAL_SEX_BE_DISCOVERED_DRAW is None:
        _ORIGINAL_SEX_BE_DISCOVERED_DRAW = getattr(current_draw, "_local_bugfix_original", current_draw)
    patched_sex_be_discovered_draw._local_bugfix_original = _ORIGINAL_SEX_BE_DISCOVERED_DRAW
    sex_be_discovered_panel.Sex_Be_Discovered_Panel.draw = patched_sex_be_discovered_draw


def patched_change_hypnosis_type(self, hypnosis_type_cid):
    """切换催眠模式时，在指令模式下立即把当前目标套用到对应催眠状态"""
    from Script.UI.Panel import hypnosis_panel

    pl_character_data = hypnosis_panel.cache.character_data[0]
    pl_character_data.pl_ability.hypnosis_type = hypnosis_type_cid
    target_data = hypnosis_panel.cache.character_data[pl_character_data.target_character_id]
    line_draw = hypnosis_panel.draw.LineDraw("-", self.width)
    line_draw.draw()

    if hypnosis_type_cid > 0:
        hypnosis_type_name = hypnosis_panel.game_config.config_hypnosis_type[hypnosis_type_cid].name
        now_draw = hypnosis_panel.draw.WaitDraw()
        draw_text = hypnosis_panel._("\n已切换为{0}催眠模式\n\n").format(hypnosis_type_name)
        now_draw.style = "pink"
        now_draw.text = draw_text
        now_draw.draw()
        if self.instruct_flag and pl_character_data.target_character_id:
            # H状态中无法再通过单人催眠补套状态，因此切换模式指令需要立即生效
            if _apply_current_hypnosis_state(pl_character_data.target_character_id) == 0:
                return
            now_draw = hypnosis_panel.draw.WaitDraw()
            now_draw.style = "pink"
            if hypnosis_type_cid == 1:
                draw_text = hypnosis_panel._("\n{0}会理所当然地接受{1}的不合理行为了\n\n").format(target_data.name, pl_character_data.name)
                now_draw.text = draw_text
                now_draw.draw()
            elif hypnosis_type_cid == 2:
                draw_text = hypnosis_panel._("\n{0}会把{1}视为空气了\n\n").format(target_data.name, pl_character_data.name)
                now_draw.text = draw_text
                now_draw.draw()
            elif hypnosis_type_cid == 3:
                draw_text = hypnosis_panel._("\n{0}可以随意地操纵{1}的身体了\n\n").format(pl_character_data.name, target_data.name)
                now_draw.text = draw_text
                now_draw.draw()
                self.body_or_mind_control_option(0)
            elif hypnosis_type_cid == 4:
                draw_text = hypnosis_panel._("\n{0}可以向{1}的潜意识灌输指令了\n\n").format(pl_character_data.name, target_data.name)
                now_draw.text = draw_text
                now_draw.draw()
                self.body_or_mind_control_option(1)


def _patch_hypnosis_panel() -> None:
    """安装切换催眠模式面板补丁"""
    global _ORIGINAL_CHANGE_HYPNOSIS_TYPE

    from Script.UI.Panel import hypnosis_panel

    current_method = hypnosis_panel.Chose_Hypnosis_Type_Panel.change_hypnosis_type
    if _ORIGINAL_CHANGE_HYPNOSIS_TYPE is None:
        _ORIGINAL_CHANGE_HYPNOSIS_TYPE = getattr(current_method, "_local_bugfix_original", current_method)
    patched_change_hypnosis_type._local_bugfix_original = _ORIGINAL_CHANGE_HYPNOSIS_TYPE
    hypnosis_panel.Chose_Hypnosis_Type_Panel.change_hypnosis_type = patched_change_hypnosis_type


def _install_registry_patches() -> None:
    global _ORIGINAL_CHARACTER_CONTINUE_MOVE, _ORIGINAL_GENERAL_MOVEMENT_MODULE

    from Script.Core import constant
    from Script.StateMachine import default as state_default

    _patch_base_state_common_settle()
    _patch_hypnosis_cancel_effect()
    _patch_group_sex_edge_release_effects()
    _patch_pain_second_effects()
    _patch_sex_be_discovered_panel()
    _patch_hypnosis_panel()
    _patch_hypnosis_one_effect()
    _patch_get_weight_from_premise_dict()

    if _ORIGINAL_GENERAL_MOVEMENT_MODULE is None:
        _ORIGINAL_GENERAL_MOVEMENT_MODULE = state_default.general_movement_module
    if _ORIGINAL_CHARACTER_CONTINUE_MOVE is None:
        _ORIGINAL_CHARACTER_CONTINUE_MOVE = state_default.character_continue_move

    state_default.general_movement_module = patched_general_movement_module
    state_default.character_continue_move = patched_character_continue_move
    constant.handle_state_machine_data[constant.StateMachine.CONTINUE_MOVE] = patched_character_continue_move


_install_registry_patches()
