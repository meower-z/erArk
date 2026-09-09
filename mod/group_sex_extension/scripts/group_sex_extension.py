# -*- coding: UTF-8 -*-
"""
群交功能扩展Mod

功能：
1. 在群交模式的“技艺”类别中增加“全员寸止”指令。
2. 在群交模式的“技艺”类别中增加“全员戴上玩具”指令。
3. 在群交模式的“技艺”类别中增加“全员催眠增强”指令。
"""

from typing import Callable, Optional


INSTRUCT_EDGE_ALL_ID = "group_sex_extension_edge_all"
"""全员寸止指令ID"""

INSTRUCT_EQUIP_TOYS_ALL_ID = "group_sex_extension_equip_toys_all"
"""全员戴上玩具指令ID"""

INSTRUCT_HYPNOSIS_BOOST_ALL_ID = "group_sex_extension_hypnosis_boost_all"
"""全员催眠增强指令ID"""

PREMISE_GROUP_SEX_COMPLETE_HYPNOSIS_GE_2 = "group_sex_extension_complete_hypnosis_ge_2"
"""群交上下文中至少两名干员已完全催眠的前提ID"""

INSTRUCT_EDGE_ALL_CID = 4901
"""全员寸止指令数字ID"""

INSTRUCT_EQUIP_TOYS_ALL_CID = 4902
"""全员戴上玩具指令数字ID"""

INSTRUCT_HYPNOSIS_BOOST_ALL_CID = 4903
"""全员催眠增强指令数字ID"""

_TOY_BODY_ITEM_IDS = (0, 1, 2, 3)
"""一键装备的身体道具ID：乳头夹、阴蒂夹、V震动棒、A震动棒"""

_ACTIVE_HYPNOSIS_FLAGS = {4, 5, 6, 7}
"""正在生效的催眠无意识标记"""


def _get_cache():
    """
    输入：无
    返回值类型：Cache
    功能：获取当前游戏缓存对象
    """
    from Script.Core import cache_control

    return cache_control.cache


def _get_group_sex_character_ids() -> list:
    """
    输入：无
    返回值类型：list[int]
    功能：获取当前群交上下文中的NPC角色ID列表
    """
    from Script.Design import map_handle
    from Script.System.Sex_System import group_sex_panel

    cache_obj = _get_cache()
    character_id_set = set()

    try:
        for character_id in group_sex_panel.count_group_sex_character_list():
            if not character_id or character_id not in cache_obj.character_data:
                continue
            character_data = cache_obj.character_data[character_id]
            if character_data.sp_flag.is_h:
                character_id_set.add(character_id)
    except Exception:
        pass

    pl_character_data = cache_obj.character_data.get(0)
    if pl_character_data is None:
        return sorted(character_id_set)

    try:
        scene_path_str = map_handle.get_map_system_path_str_for_list(pl_character_data.position)
        scene_data = cache_obj.scene_data.get(scene_path_str)
        if scene_data is not None:
            for character_id in scene_data.character_list:
                if not character_id or character_id not in cache_obj.character_data:
                    continue
                character_data = cache_obj.character_data[character_id]
                if character_data.sp_flag.is_h:
                    character_id_set.add(character_id)
    except Exception:
        pass

    return sorted(character_id_set)


def _is_complete_hypnosis(character_data) -> bool:
    """
    输入：
        character_data: Character，角色数据
    返回值类型：bool
    功能：判断角色是否已经达到完全催眠
    """
    if character_data.talent.get(73, 0):
        return True
    return character_data.hypnosis.hypnosis_degree >= 200


def _is_active_hypnosis(character_data) -> bool:
    """
    输入：
        character_data: Character，角色数据
    返回值类型：bool
    功能：判断角色当前是否处于正在生效的催眠状态
    """
    return getattr(getattr(character_data, "sp_flag", None), "unconscious_h", 0) in _ACTIVE_HYPNOSIS_FLAGS


def _get_complete_hypnosis_character_ids() -> list:
    """
    输入：无
    返回值类型：list[int]
    功能：获取当前群交上下文中达到完全催眠的NPC角色ID列表
    """
    cache_obj = _get_cache()
    complete_character_ids = []

    for character_id in _get_group_sex_character_ids():
        character_data = cache_obj.character_data[character_id]
        if _is_complete_hypnosis(character_data):
            complete_character_ids.append(character_id)
    return complete_character_ids


def _ensure_body_item_slot(character_data, body_item_id: int) -> None:
    """
    输入：
        character_data: Character，角色数据
        body_item_id: int，身体道具ID
    返回值类型：None
    功能：确保角色H状态中存在指定身体道具槽位
    """
    from Script.Config import game_config

    if body_item_id in character_data.h_state.body_item and len(character_data.h_state.body_item[body_item_id]) >= 3:
        return

    item_name = f"身体道具{body_item_id}"
    if body_item_id in game_config.config_body_item:
        item_id = game_config.config_body_item[body_item_id].item_id
        if item_id in game_config.config_item:
            item_name = game_config.config_item[item_id].name
        else:
            item_name = game_config.config_body_item[body_item_id].name
    character_data.h_state.body_item[body_item_id] = [item_name, False, None]


def _set_orgasm_edge(character_data) -> bool:
    """
    输入：
        character_data: Character，角色数据
    返回值类型：bool
    功能：如果角色尚未处于寸止模式，则开启寸止模式
    """
    from Script.Config import game_config

    if character_data.h_state.orgasm_edge != 0:
        return False

    character_data.h_state.orgasm_edge = 1
    for state_id in game_config.config_character_state:
        if game_config.config_character_state[state_id].type == 0:
            character_data.h_state.orgasm_edge_count[state_id] = 0
    return True


def _equip_group_sex_toys(character_data) -> int:
    """
    输入：
        character_data: Character，角色数据
    返回值类型：int
    功能：给角色戴上群交扩展的一组身体玩具，并返回新增装备数量
    """
    changed_count = 0
    for body_item_id in _TOY_BODY_ITEM_IDS:
        _ensure_body_item_slot(character_data, body_item_id)
        if not character_data.h_state.body_item[body_item_id][1]:
            character_data.h_state.body_item[body_item_id][1] = True
            character_data.h_state.body_item[body_item_id][2] = None
            changed_count += 1
    return changed_count


def _set_hypnosis_boost(character_data) -> tuple:
    """
    输入：
        character_data: Character，角色数据
    返回值类型：tuple[bool, bool]
    功能：为完全催眠角色开启敏感度上升与苦痛快感化，不改变当前催眠状态
    """
    sensitivity_changed = False
    pain_as_pleasure_changed = False

    if not character_data.hypnosis.increase_body_sensitivity:
        character_data.hypnosis.increase_body_sensitivity = True
        sensitivity_changed = True
    if not character_data.hypnosis.pain_as_pleasure:
        character_data.hypnosis.pain_as_pleasure = True
        pain_as_pleasure_changed = True
    return sensitivity_changed, pain_as_pleasure_changed


def _draw_result(text: str) -> None:
    """
    输入：
        text: str，提示文本
    返回值类型：None
    功能：绘制操作结果提示
    """
    from Script.Config import normal_config
    from Script.UI.Moudle import draw

    info_draw = draw.NormalDraw()
    info_draw.text = text
    info_draw.width = normal_config.config_normal.text_width
    info_draw.draw()


def group_sex_extension_edge_all() -> None:
    """
    输入：无
    返回值类型：None
    功能：为当前群交上下文中的所有干员开启寸止模式
    """
    cache_obj = _get_cache()
    character_id_list = _get_group_sex_character_ids()
    changed_count = 0

    for character_id in character_id_list:
        character_data = cache_obj.character_data[character_id]
        if _set_orgasm_edge(character_data):
            changed_count += 1

    _draw_result(f"\n已为{changed_count}/{len(character_id_list)}名干员开启寸止模式\n")


def group_sex_extension_equip_toys_all() -> None:
    """
    输入：无
    返回值类型：None
    功能：为当前群交上下文中的所有干员戴上指定身体玩具
    """
    cache_obj = _get_cache()
    character_id_list = _get_group_sex_character_ids()
    changed_character_count = 0
    changed_item_count = 0

    for character_id in character_id_list:
        character_data = cache_obj.character_data[character_id]
        now_changed_count = _equip_group_sex_toys(character_data)
        if now_changed_count:
            changed_character_count += 1
            changed_item_count += now_changed_count

    _draw_result(f"\n已为{changed_character_count}/{len(character_id_list)}名干员戴上玩具，共新增{changed_item_count}件\n")


def group_sex_extension_hypnosis_boost_all() -> None:
    """
    输入：无
    返回值类型：None
    功能：为当前群交上下文中完全催眠的所有干员开启敏感度上升与苦痛快感化
    """
    cache_obj = _get_cache()
    character_id_list = _get_complete_hypnosis_character_ids()
    sensitivity_changed_count = 0
    pain_as_pleasure_changed_count = 0

    if len(character_id_list) < 2:
        _draw_result("\n当前完全催眠的群交干员不足2人，无法执行全员催眠增强\n")
        return

    for character_id in character_id_list:
        character_data = cache_obj.character_data[character_id]
        sensitivity_changed, pain_as_pleasure_changed = _set_hypnosis_boost(character_data)
        if sensitivity_changed:
            sensitivity_changed_count += 1
        if pain_as_pleasure_changed:
            pain_as_pleasure_changed_count += 1

    _draw_result(
        f"\n已为{len(character_id_list)}名完全催眠干员设置敏感度上升与苦痛快感化"
        f"（新增敏感度上升{sensitivity_changed_count}人，新增苦痛快感化{pain_as_pleasure_changed_count}人）\n"
    )


def _handle_complete_hypnosis_ge_2(_character_id: int) -> int:
    """
    输入：
        _character_id: int，角色ID
    返回值类型：int
    功能：判断当前群交上下文中是否至少有两名完全催眠干员
    """
    return 1 if len(_get_complete_hypnosis_character_ids()) >= 2 else 0


def _register_instruction(instruct_id: str, cid: int, name: str, func: Callable[[], None], extra_premises: Optional[set] = None) -> None:
    """
    输入：
        instruct_id: str，指令ID
        cid: int，指令数字ID
        name: str，指令显示名
        func: Callable[[], None]，指令处理函数
        extra_premises: set | None，额外前提集合
    返回值类型：None
    功能：把扩展指令注册到群交模式下的技艺类别中
    """
    from Script.Core import constant, constant_promise

    constant.handle_instruct_data[instruct_id] = func
    constant.instruct_premise_data[instruct_id] = {constant_promise.Premise.GROUP_SEX_MODE_ON}
    if extra_premises:
        constant.instruct_premise_data[instruct_id].update(extra_premises)
    constant.instruct_type_data.setdefault(constant.InstructType.ARTS, set()).add(instruct_id)
    constant.instruct_sub_type_data[instruct_id] = constant.SexInstructSubType.ARTS
    constant.handle_instruct_name_data[instruct_id] = name
    constant.instruct_id_to_cid[instruct_id] = cid
    constant.cid_to_instruct_id[cid] = instruct_id
    constant.behavior_id_to_instruct_id[instruct_id] = instruct_id
    constant.instruct_category_data[instruct_id] = constant.InstructCategory.CHARACTER
    constant.instruct_major_type_data[instruct_id] = "arts"
    constant.instruct_minor_type_data[instruct_id] = "arts_hypnosis"
    constant.instruct_body_parts_data[instruct_id] = ["head"]


def _install_patch() -> None:
    """
    输入：无
    返回值类型：None
    功能：注册群交功能扩展指令
    """
    from Script.Core import constant

    if getattr(constant, "_group_sex_extension_installed", False):
        return

    constant.handle_premise_data[PREMISE_GROUP_SEX_COMPLETE_HYPNOSIS_GE_2] = _handle_complete_hypnosis_ge_2
    _register_instruction(INSTRUCT_EDGE_ALL_ID, INSTRUCT_EDGE_ALL_CID, "全员寸止", group_sex_extension_edge_all)
    _register_instruction(INSTRUCT_EQUIP_TOYS_ALL_ID, INSTRUCT_EQUIP_TOYS_ALL_CID, "全员戴上玩具", group_sex_extension_equip_toys_all)
    _register_instruction(
        INSTRUCT_HYPNOSIS_BOOST_ALL_ID,
        INSTRUCT_HYPNOSIS_BOOST_ALL_CID,
        "全员催眠增强",
        group_sex_extension_hypnosis_boost_all,
        {PREMISE_GROUP_SEX_COMPLETE_HYPNOSIS_GE_2},
    )
    constant._group_sex_extension_installed = True
    print("[群交功能扩展] 已加载：群交模式技艺类别新增全员寸止、全员戴上玩具与全员催眠增强指令")


_install_patch()
