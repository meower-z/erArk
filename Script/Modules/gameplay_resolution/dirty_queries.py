"""
污秽与身体状态查询（dirty_queries）
===================================
提供角色身体部位 6 与 7 的当前精液量合计，以及同场景内指定状态角色的只读查询。
不直接导入界面模块，供 handle_premise_dirty 与 hidden_sex_panel 调用。
"""

from Script.Core import num
from Script.Design import map_handle
from Script.Modules.domains import activity, dirty, h_state, scene_state


def get_v_and_w_semen_count(character_id: int) -> num.Num:
    """
    计算指定角色身体部位 6 与 7 的当前精液量之和。
    两项数值均从 dirty.body_semen_amount 读取，返回精确数值。
    Keyword arguments:
    character_id -- int，角色编号
    Return arguments:
    num.Num -- 身体部位 6 与 7 的当前精液量合计（int 或 Fraction）
    """
    all_semen_count = dirty.body_semen_amount(
        character_id, 6
    ) + dirty.body_semen_amount(character_id, 7)
    return all_semen_count


def get_inserted_character_id() -> int:
    """
    只读查询玩家交互对象或同场景角色中 h_state 的 insert_position 不为 -1 的角色编号。
    玩家当前交互对象不为 0 且其 insert_position 不为 -1 时，优先返回该对象编号。
    否则遍历玩家所在场景的 scene_state.occupants（跳过玩家与交互对象），返回首个满足条件的角色编号。
    Return arguments:
    int -- 满足条件的角色编号，无匹配角色时返回 0
    """
    target_id: int = activity.target(0)
    if target_id != 0 and h_state.get(target_id, "insert_position") != -1:
        return target_id

    scene_path_str = map_handle.get_map_system_path_str_for_list(
        activity.position(0)
    )
    for character_id in scene_state.occupants(scene_path_str):
        if character_id == 0 or character_id == target_id:
            continue
        if h_state.get(character_id, "insert_position") != -1:
            return character_id

    return 0
