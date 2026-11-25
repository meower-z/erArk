"""
宿舍管理员服务（dormitory_manager_service）
===========================================
提供各层宿舍管理员查询、候选列表、任命、撤换与未分配岗位重置逻辑。
本模块不导入 Script.UI 与 Script.Settle。
"""

import re
from types import FunctionType

from Script.Core import constant, get_text
from Script.Design import basement, map_handle
from Script.Modules.domains import activity, chara_life, dormitory, identity
from Script.Modules.domains import inventory, roster, work
from Script.Modules.gameplay_resolution.dormitory_room_service import Notice
from Script.System.Dormitory_System import common

_: FunctionType = get_text._
""" 翻译api """

MANAGER_WORK = 31
""" 宿舍管理员岗位的工作类型编号（31）。 """
KEY_ITEM_BASE = 300
""" 各层宿舍钥匙物品编号的基准值（300 加层号）。 """
MANAGER_ROOM = "Dormitory_Manager_Room"
""" 宿舍管理员房间的地点与场景标签名。 """


def _pool() -> list[int]:
    """返回宿舍管理员岗位名册中的角色编号，按 adv 升序排列。"""
    return sorted(
        work.roster(MANAGER_WORK),
        key=lambda chara_id: identity.of(chara_id).adv,
    )


def layer_managers() -> list[tuple[int, str | None]]:
    """
    按层号顺序返回各开放层及其当前宿舍管理员姓名。
    Return arguments:
    list[tuple[int, str | None]] -- (层号, 管理员姓名或 None)
    """
    rows: list[tuple[int, str | None]] = []
    for layer in sorted(common.get_open_dormitory_rooms_by_layer()):
        manager_id = dormitory.managers().get(layer, 0)
        name = None
        if manager_id and identity.exists(manager_id):
            name = identity.of(manager_id).name
        rows.append((layer, name))
    return rows


def unassigned_manager_names() -> list[str]:
    """
    返回处于宿舍管理员岗位但未分配管理层级的干员姓名列表。
    Return arguments:
    list[str] -- 按 adv 升序排列的未分配层级管理员姓名
    """
    assigned = dormitory.managers().values()
    return [
        identity.of(chara_id).name
        for chara_id in _pool()
        if chara_id not in assigned
    ]


def manager_candidates() -> list[tuple[int, str, str]]:
    """
    先刷新各岗位名册，再返回宿舍管理员岗位的候选干员展示条目。
    Return arguments:
    list[tuple[int, str, str]] -- (角色编号, 姓名, 带 adv 的标签)
    """
    basement.update_work_people()
    rows = []
    for chara_id in _pool():
        data = identity.of(chara_id)
        rows.append(
            (
                chara_id,
                data.name,
                f"[{str(data.adv).rjust(4, '0')}] {data.name}",
            )
        )
    return rows


def _take_key(layer: int, manager_id: int) -> str | None:
    """若玩家持有该层宿舍钥匙则收回并返回提示行，否则返回 None。"""
    key_item_id = KEY_ITEM_BASE + layer
    if inventory.items(0)[key_item_id] <= 0:
        return None
    inventory.set_item(0, key_item_id, 0)
    return _(
        "\n○{0}的{1}层管理员任命已被撤销，博士持有的该层钥匙已被收回\n"
    ).format(identity.of(manager_id).name, layer)


def _manager_room(layer: int) -> str:
    """查找指定楼层的宿舍管理员房间路径，未找到时返回空字符串。"""
    for office_path in constant.place_data.get(MANAGER_ROOM, []):
        match = re.search(r"[\\/](\d)区[\\/]", office_path)
        if match and int(match.group(1)) == layer:
            return office_path
    return ""


def _is_manager_room(room_path: str) -> bool:
    """判断场景路径是否属于宿舍管理员房间。"""
    if room_path == "":
        return False
    if room_path in constant.place_data.get(MANAGER_ROOM, []):
        return True
    if room_path in constant.scene_data:
        return MANAGER_ROOM in constant.scene_data[room_path].scene_tag
    return False


def _move_in(layer: int, chara_id: int) -> None:
    """登记永久宿舍，将角色宿舍与位置迁入指定层的管理员房间。"""
    room_path = _manager_room(layer)
    if room_path == "":
        return
    common.register_permanent_dormitory(chara_id)
    chara_life.dormitory.set(chara_id, room_path)
    target = map_handle.get_map_system_path_for_str(room_path)
    if target:
        map_handle.character_move_scene(
            activity.position(chara_id), target, chara_id
        )


def _move_out(chara_id: int) -> None:
    """当角色住在管理员房间时按登记宿舍优先恢复普通宿舍并移动位置。"""
    if not _is_manager_room(chara_life.dormitory(chara_id)):
        return
    restore_path = common.restore_character_dormitory(chara_id)
    target = map_handle.get_map_system_path_for_str(restore_path)
    map_handle.character_move_scene(
        activity.position(chara_id), target, chara_id
    )


def appoint(layer: int, chara_id: int) -> Notice:
    """
    任命干员为指定层管理员，处理跨层卸任、收钥匙、搬房与刷新名册。
    Keyword arguments:
    layer -- int，目标宿舍楼层号
    chara_id -- int，被任命干员的角色编号
    Return arguments:
    Notice -- 含跨层收回钥匙提示行与任命完成等待消息
    """
    old_manager_id = dormitory.managers().get(layer, 0)
    lines: list[str] = []
    for other_layer, other_id in dormitory.managers().items():
        if other_layer != layer and other_id == chara_id:
            dormitory.set_manager(other_layer, 0)
            line = _take_key(other_layer, chara_id)
            if line is not None:
                lines.append(line)
    dormitory.set_manager(layer, chara_id)
    chara_life.work_type.set(chara_id, MANAGER_WORK)
    _move_in(layer, chara_id)
    if old_manager_id and old_manager_id != chara_id:
        if old_manager_id not in dormitory.managers().values():
            _move_out(old_manager_id)
    basement.update_work_people()
    text = _("\n○已任命 {0} 为 {1}层宿舍管理员\n").format(
        identity.of(chara_id).name, layer
    )
    return Notice(tuple(lines), text)


def dismiss(layer: int) -> Notice:
    """
    撤换指定层管理员，迁出管理员房间、刷新名册并在持钥匙时收回。
    Keyword arguments:
    layer -- int，目标宿舍楼层号
    Return arguments:
    Notice -- 含收回钥匙提示行与撤换完成等待消息
    """
    manager_id = dormitory.managers().get(layer, 0)
    if not manager_id:
        return Notice((), _("\n○该层当前没有已任命管理员\n"))
    dormitory.set_manager(layer, 0)
    _move_out(manager_id)
    basement.update_work_people()
    line = _take_key(layer, manager_id)
    lines = () if line is None else (line,)
    return Notice(lines, _("\n○已撤换 {0}层宿舍管理员\n").format(layer))


def reset_unassigned_managers() -> int:
    """
    将未分配楼层的在编宿舍管理员重置为无岗位，有变更时刷新名册。
    Return arguments:
    int -- 被重置为无岗位的干员人数
    """
    assigned = set(dormitory.managers().values())
    assigned.discard(0)
    count = 0
    for chara_id in roster.active():
        data = identity.get(chara_id)
        if chara_id == 0 or data is None or chara_id in assigned:
            continue
        if chara_life.work_type(data.cid) == MANAGER_WORK:
            chara_life.work_type.set(data.cid, 0)
            count += 1
    if count:
        basement.update_work_people()
    return count
