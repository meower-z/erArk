# -*- coding: UTF-8 -*-
"""
测试里读写角色的活动
====================
behave、stand、status、aim 与 place 经 kernel_data.put 写：在一步、一次挑选或一个缓冲区里时写进当前缓冲区，
不在这些里时经 kernel_data.written 套用到内核状态上。doing 与 scene_of 读当前缓冲区。
"""

from tests import kernel_data
from tests.kernel_project import activity


def behave(cid: int, behavior_id: str | None = None, **fields: object) -> None:
    """
    改角色当前行为的给出字段（activity.update_behavior）
    Keyword arguments:
    cid -- 角色id
    behavior_id -- 给出时改行为id
    fields -- 其余字段名到新值
    """
    if behavior_id is not None:
        fields["behavior_id"] = behavior_id
    kernel_data.put(activity.update_behavior, cid, **fields)


def doing(cid: int) -> str:
    """
    角色当前行为的行为id
    Keyword arguments:
    cid -- 角色id
    Return arguments:
    str -- 行为id
    """
    return str(activity.behavior(cid).behavior_id)


def aim(cid: int, target: int) -> None:
    """
    把角色的交互对象换成 target（activity.set_target）
    Keyword arguments:
    cid -- 角色id
    target -- 交互对象id
    """
    kernel_data.put(activity.set_target, cid, target)


def stand(cid: int, behavior_id: str, **fields: object) -> None:
    """
    把角色当前行为改成原地的 behavior_id：时长 0，移动目标与最终目标清空，再改给出的字段
    Keyword arguments:
    cid -- 角色id
    behavior_id -- 行为id
    fields -- 其余字段名到新值，盖过上面的默认
    """
    still = {"duration": 0, "move_target": [], "move_final_target": []}
    behave(cid, behavior_id, **{**still, **fields})


def status(cid: int, value: int | str) -> None:
    """
    把角色当前状态换成 value（activity.set_state）
    Keyword arguments:
    cid -- 角色id
    value -- 状态
    """
    kernel_data.put(activity.set_state, cid, value)


def place(cid: int, position: list[str], **fields: object) -> None:
    """
    把角色放到 position（activity.set_position），再改当前行为的给出字段
    Keyword arguments:
    cid -- 角色id
    position -- 场景路径列表
    fields -- 当前行为的字段名到新值
    """
    kernel_data.put(activity.set_position, cid, position)
    kernel_data.put(activity.update_behavior, cid, **fields)


def scene_of(cid: int) -> str:
    """
    角色所在场景的路径字符串（map_handle.get_map_system_path_str_for_list）
    Keyword arguments:
    cid -- 角色id
    Return arguments:
    str -- 场景路径字符串
    """
    from Script.Design import map_handle

    return map_handle.get_map_system_path_str_for_list(activity.position(cid))
