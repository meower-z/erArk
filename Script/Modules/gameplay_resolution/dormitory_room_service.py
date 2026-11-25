"""
宿舍房间服务（dormitory_room_service）
======================================
提供宿舍入住统计、房间选择、临时空白位、自动排序与超员重分配逻辑。
本模块不导入 Script.UI 与 Script.Settle。
"""

import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from types import FunctionType

from Script.Core import constant, constant_promise, get_text
from Script.Design import basement, handle_premise
from Script.Modules.domains import chara_life, facility, identity, roster
from Script.System.Dormitory_System import common

_: FunctionType = get_text._
""" 翻译api """

ROOM_SIZE = 2
""" 单间宿舍的设计容量上限（2人）。 """


@dataclass(frozen=True, slots=True)
class Notice:
    """服务操作返回给面板的提示内容，含普通文本行与等待确认文本。"""

    lines: tuple[str, ...]
    wait: str | None


@dataclass(frozen=True, slots=True)
class RoomChoice:
    """可迁入目标宿舍的展示条目，含房间名、场景路径与按钮标签。"""

    room_name: str
    room_path: str
    label: str


@dataclass(slots=True)
class TempBlank:
    """面板持有的临时空白位干员编号列表。"""

    ids: list[int] = field(default_factory=list)

    def current(self) -> list[int]:
        """
        过滤不存在与重复的角色编号，回写并返回清理后的列表。
        Return arguments:
        list[int] -- 清理后的临时空白位角色编号列表
        """
        valid: list[int] = []
        for chara_id in self.ids:
            if identity.exists(chara_id) and chara_id not in valid:
                valid.append(chara_id)
        self.ids = valid
        return valid


def _by_adv(ids: Iterable[int]) -> list[int]:
    """按角色 adv 升序排列给定角色编号。"""
    return sorted(ids, key=lambda chara_id: identity.of(chara_id).adv)


def _open_room_paths() -> list[tuple[int, str, str]]:
    """按层号与房间顺序展开已开放宿舍的 (层号, 房名, 路径) 列表。"""
    rooms = common.get_open_dormitory_rooms_by_layer()
    return [
        (layer, room_name, room_path)
        for layer in sorted(rooms)
        for room_name, room_path in rooms[layer]
    ]


def occupancy() -> dict[str, int]:
    """
    统计已分配宿舍的住户人数，含离岛角色并忽略空宿舍路径。
    Return arguments:
    dict[str, int] -- 宿舍场景路径到当前入住人数的映射
    """
    counts: dict[str, int] = {}
    for chara_id in common.get_dormitory_resident_id_set():
        path = chara_life.dormitory(chara_id)
        if path:
            counts[path] = counts.get(path, 0) + 1
    return counts


def capacity(room_path: str, counts: dict[str, int]) -> int:
    """
    计算指定宿舍的有效容量，取设计容量与当前人数的较大值。
    Keyword arguments:
    room_path -- str，宿舍场景路径
    counts -- dict[str, int]，宿舍路径到入住人数的映射
    Return arguments:
    int -- 该宿舍的有效容量上限
    """
    return max(ROOM_SIZE, int(counts.get(room_path, 0)))


def room_name(room_path: str) -> str:
    """
    将宿舍场景路径转为可读名称，空路径返回暂无。
    Keyword arguments:
    room_path -- str，宿舍场景路径
    Return arguments:
    str -- 场景名称，未登记路径取末段名，空路径返回暂无
    """
    if room_path == "":
        return _("暂无")
    if room_path not in constant.scene_data:
        return room_path.split(os.sep)[-1]
    return constant.scene_data[room_path].scene_name


def overview_text(
    blank_ids: list[int], layers: list[tuple[int, str | None]]
) -> str:
    """
    组装宿舍总览页文本，含等级、开放规模、空白位与各层管理员。
    Keyword arguments:
    blank_ids -- list[int]，当前临时空白位角色编号列表
    layers -- list[tuple[int, str | None]]，各层 (层号, 管理员名)
    Return arguments:
    str -- 供面板绘制的宿舍总览文本
    """
    level = facility.level(4, 1)
    rooms = common.get_open_dormitory_rooms_by_layer()
    efficiency = basement.calc_facility_efficiency(4)
    max_layer = common.get_dormitory_max_open_layer()
    names = [identity.of(c).name for c in blank_ids if identity.exists(c)]
    text = _("\n 当前宿舍区块等级：{0}\n").format(level)
    text += _(" 干员总数/宿舍容量：{0}/{1}\n").format(
        str(roster.count()), facility.people_max()
    )
    text += _(" 按等级已开放至：{0}层，").format(max_layer)
    text += _("当前开放层数：{0} 层\n").format(len(rooms))
    text += _(" 当前开放房间数：{0} 间\n").format(
        sum(len(room_list) for room_list in rooms.values())
    )
    text += _(" 当前基础恢复效率：{0:.0f}%\n").format(efficiency * 100)
    if names:
        text += _(" 临时空白位：{0}人（{1}）\n").format(
            len(names), "、".join(names)
        )
    else:
        text += _(" 临时空白位：0人\n")
    text += _("\n\n 各层管理员状态：\n")
    for layer, name in layers:
        if name is not None:
            text += _("  {0}层：{1}\n").format(layer, name)
        else:
            text += _("  {0}层：未任命\n").format(layer)
    if not layers:
        text += _("  暂无开放层\n")
    return text


def selectable_ids() -> list[int]:
    """
    返回可调整宿舍的在编干员编号，排除玩家并按 adv 升序排列。
    Return arguments:
    list[int] -- 排序后的在编干员角色编号列表
    """
    return _by_adv([chara_id for chara_id in roster.active() if chara_id != 0])


def can_change_room(chara_id: int) -> bool:
    """
    按前提 CAN_MANUAL_CHANGE_DORMITORY 判断角色能否手动换宿舍。
    Keyword arguments:
    chara_id -- int，角色编号
    Return arguments:
    bool -- 允许手动更换宿舍时返回 True，否则返回 False
    """
    return bool(
        handle_premise.handle_premise(
            constant_promise.Premise.CAN_MANUAL_CHANGE_DORMITORY, chara_id
        )
    )


def change_header(chara_id: int, blank_ids: list[int]) -> tuple[str, str]:
    """
    生成调整单名干员宿舍子页的标题与当前状态说明。
    Keyword arguments:
    chara_id -- int，角色编号
    blank_ids -- list[int]，当前临时空白位角色编号列表
    Return arguments:
    tuple[str, str] -- (标题文本, 当前宿舍与状态提示文本)
    """
    name = identity.of(chara_id).name
    text = _("\n 当前宿舍：{0}\n").format(
        room_name(chara_life.dormitory(chara_id))
    )
    if chara_id in blank_ids:
        text += _(" 当前状态：临时空白位\n")
    text += _(" 请选择目标宿舍（仅显示已开放且未满员）：\n\n")
    return _("调整宿舍：{0}").format(name), text


def room_choices(chara_id: int) -> list[RoomChoice]:
    """
    列出角色可迁入的已开放未满员宿舍，排除当前所住宿舍。
    Keyword arguments:
    chara_id -- int，角色编号
    Return arguments:
    list[RoomChoice] -- 按层与房间顺序排列的可选宿舍条目
    """
    counts = occupancy()
    choices: list[RoomChoice] = []
    for layer, name, path in _open_room_paths():
        count = counts.get(path, 0)
        size = capacity(path, counts)
        if path == chara_life.dormitory(chara_id) or count >= size:
            continue
        label = _("[{0}层] {1} ({2}/{3})").format(layer, name, count, size)
        if path in counts and counts[path] > 0:
            residents = common.get_dormitory_resident_id_set()
            label += " - " + "、".join(
                identity.of(c).name
                for c in residents
                if chara_life.dormitory(c) == path
            )
        choices.append(RoomChoice(name, path, label))
    return choices


def set_room(chara_id: int, room_path: str, blank: TempBlank) -> Notice:
    """
    将角色宿舍设为指定路径，并从临时空白位列表去除。
    Keyword arguments:
    chara_id -- int，角色编号
    room_path -- str，目标宿舍场景路径
    blank -- TempBlank，面板持有的临时空白位对象
    Return arguments:
    Notice -- 含宿舍调整完成提示的等待确认消息
    """
    old_text = room_name(chara_life.dormitory(chara_id))
    new_text = room_name(room_path)
    chara_life.dormitory.set(chara_id, room_path)
    ids = blank.current()
    if chara_id in ids:
        ids.remove(chara_id)
    text = _("\n○{0} 的宿舍已从 {1} 调整为 {2}\n").format(
        identity.of(chara_id).name, old_text, new_text
    )
    return Notice((), text)


def move_to_blank(chara_id: int, blank: TempBlank) -> Notice:
    """
    将角色加入临时空白位列表，并清空其当前宿舍路径。
    Keyword arguments:
    chara_id -- int，角色编号
    blank -- TempBlank，面板持有的临时空白位对象
    Return arguments:
    Notice -- 含移入临时空白位提示的等待确认消息
    """
    ids = blank.current()
    if chara_id not in ids:
        ids.append(chara_id)
    old_text = room_name(chara_life.dormitory(chara_id))
    chara_life.dormitory.set(chara_id, "")
    text = _("\n○{0} 已从 {1} 移入临时空白位\n").format(
        identity.of(chara_id).name, old_text
    )
    return Notice((), text)


def auto_sort(blank: TempBlank) -> Notice | None:
    """
    按开放房间空位顺序安置临时空白位干员，空列表返回 None。
    Keyword arguments:
    blank -- TempBlank，面板持有的临时空白位对象
    Return arguments:
    Notice | None -- 安置结果提示消息，空白位为空时返回 None
    """
    ids = blank.current()
    if not ids:
        return None
    counts = occupancy()
    free_slots: list[str] = []
    for *__, path in _open_room_paths():
        free = max(0, capacity(path, counts) - counts.get(path, 0))
        free_slots.extend([path] * free)
    assigned = 0
    while ids and free_slots:
        target = free_slots.pop(0)
        if identity.exists(ids[0]):
            chara_life.dormitory.set(ids[0], target)
            assigned += 1
        ids.pop(0)
    if not assigned:
        return Notice((), _("\n○当前没有可用宿舍位置，无法进行自动排序\n"))
    text = _("\n○已自动安置{0}名干员进入宿舍\n").format(assigned)
    if ids:
        text += _("○仍有{0}名干员留在临时空白位（宿舍可用位置不足）\n").format(
            len(ids)
        )
    return Notice((), text)


def has_overcrowded_room() -> bool:
    """
    判断是否存在当前入住人数超过设计容量的已开放宿舍。
    Return arguments:
    bool -- 有已开放宿舍入住超过 2 人时返回 True，否则返回 False
    """
    counts = occupancy()
    return any(
        counts.get(path, 0) > ROOM_SIZE for *__, path in _open_room_paths()
    )


def redistribute() -> Notice | None:
    """
    将超员开放宿舍超出 2 人的住户按空位重分配，空位不足不改动。
    Return arguments:
    Notice | None -- 重分配结果或空位不足提示，无超员住户返回 None
    """
    paths = [path for *__, path in _open_room_paths()]
    residents: dict[str, list[int]] = {path: [] for path in paths}
    living = common.get_dormitory_resident_id_set()
    for chara_id in _by_adv(c for c in living if identity.exists(c)):
        path = chara_life.dormitory(chara_id)
        if path in residents:
            residents[path].append(chara_id)
    moving = [c for path in paths for c in residents[path][ROOM_SIZE:]]
    if not moving:
        return None
    free_slots: list[str] = []
    for path in paths:
        free_slots.extend(
            [path] * (ROOM_SIZE - len(residents[path][:ROOM_SIZE]))
        )
    if len(free_slots) < len(moving):
        return Notice(
            (), _("\n○当前剩余宿舍空位不足以重新分配，请升级宿舍后重试。\n")
        )
    for index, chara_id in enumerate(moving):
        chara_life.dormitory.set(chara_id, free_slots[index])
    return Notice(
        (),
        _("\n○已完成重新分配，共分配了{0}名角色。\n").format(len(moving)),
    )
