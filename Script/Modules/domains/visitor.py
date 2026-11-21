"""
访客的全局键 base.visitor
=========================
值是 {"visitors": {角色id的字符串: 离开时刻}, "last_arrival": 时刻或 None,
"invite": {"target": 角色id, "progress": 进度}, "moved": 布尔值}。时刻都是内核时钟的分钟数。
visitors 是在罗德岛的访客，按抵达的顺序排列。
last_arrival 是上次随机来访的时刻。开新游戏与新周目时它记为当时的时刻。它为 None 时读到开局时刻。
invite 是邀请的目标与进度。目标为 0 时没有邀请。
moved 记下罗德岛在上次结算访客之后是否抵达过别处。
写入整值替换这个键。新值与旧值相同时不写。
访客上限不存下。capacity 每次读时按已开放的客房算出。
"""

import datetime
from collections.abc import Mapping
from typing import Any, cast

from Script.Config import game_config
from Script.Core import get_text
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import facility
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import kernel_state

KEY = "base.visitor"
""" 访客在全局数据里的键 """

working.register(
    KEY,
    {
        "visitors": {},
        "last_arrival": None,
        "invite": {"target": 0, "progress": 0},
        "moved": False,
    },
)


def _stored(game: core.GameState | None = None) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], working.get(None, KEY, game))


def _put(**parts: core.JSON) -> None:
    old = _stored()
    new = {**old, **parts}
    if new != old:
        working.put(None, KEY, new)


def visitors(
    game: core.GameState | None = None,
) -> dict[int, datetime.datetime]:
    """
    在罗德岛的访客
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    dict -- 角色id到离开时刻，按抵达的顺序
    """
    stored = _stored(game)["visitors"]
    return {int(cid): game_time.at(m) for cid, m in stored.items()}


def is_visitor(cid: int, game: core.GameState | None = None) -> bool:
    """
    角色是不是在罗德岛的访客
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    bool -- 是访客时为 True
    """
    return str(cid) in _stored(game)["visitors"]


def arrive(cid: int, leave: datetime.datetime) -> None:
    """
    记下一名访客，写进当前缓冲区。角色已是访客时只换离开时刻，位置不变
    Keyword arguments:
    cid -- 角色id
    leave -- 离开时刻
    """
    table = {**_stored()["visitors"], str(cid): game_time.minutes(leave)}
    _put(visitors=table)


def leave(cid: int) -> None:
    """
    删掉一名访客，写进当前缓冲区。角色不是访客时报 KeyError
    Keyword arguments:
    cid -- 角色id
    """
    table = dict(_stored()["visitors"])
    del table[str(cid)]
    _put(visitors=table)


def last_arrival(game: core.GameState | None = None) -> datetime.datetime:
    """
    上次随机来访的时刻
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    datetime.datetime -- 时刻。没有记下时为开局时刻（kernel_state.first_clock）
    """
    stored = _stored(game)["last_arrival"]
    if stored is None:
        return game_time.at(kernel_state.first_clock())
    return game_time.at(stored)


def set_last_arrival(at: datetime.datetime) -> None:
    """
    记下随机来访的时刻，写进当前缓冲区
    Keyword arguments:
    at -- 时刻
    """
    _put(last_arrival=game_time.minutes(at))


def invite(game: core.GameState | None = None) -> tuple[int, float]:
    """
    邀请的目标与进度
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    tuple -- (目标角色id, 进度)。目标为 0 时没有邀请
    """
    stored = _stored(game)["invite"]
    return stored["target"], stored["progress"]


def set_invite(target: int, progress: float = 0) -> None:
    """
    换掉邀请的目标与进度，写进当前缓冲区
    Keyword arguments:
    target -- 目标角色id，0 为没有邀请
    progress -- 进度
    """
    _put(invite={"target": target, "progress": progress})


def moved(game: core.GameState | None = None) -> bool:
    """
    罗德岛在上次结算访客之后是否抵达过别处
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    bool -- 抵达过时为 True
    """
    return cast(bool, _stored(game)["moved"])


def set_moved(flag: bool) -> None:
    """
    记下罗德岛是否抵达过别处，写进当前缓冲区
    Keyword arguments:
    flag -- 抵达过时为 True
    """
    _put(moved=flag)


def capacity(game: core.GameState | None = None) -> int:
    """
    访客上限：名字含「客房」（按当前语言翻译）的待开放设施里已开放的个数
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    int -- 人数
    """
    word = get_text._("客房")
    return sum(
        1
        for room_id, room in game_config.config_facility_open.items()
        if word in room.name and facility.is_open(room_id, False, game)
    )


def remap(old_to_new: Mapping[int, int]) -> None:
    """
    角色换id时，把访客与邀请目标里的旧id换成新id，写进当前缓冲区。访客的顺序不变。
    两个旧id换成同一个新id时，留后一个的离开时刻
    Keyword arguments:
    old_to_new -- 旧id到新id，表里没有的id不变
    """
    table: dict[str, core.JSON] = {}
    for oid, m in _stored()["visitors"].items():
        table[str(old_to_new.get(int(oid), int(oid)))] = m
    target, progress = invite()
    _put(visitors=table)
    set_invite(old_to_new.get(target, target), progress)


PICKLED_TYPES = {
    "visitor_info": dict,
    "last_visitor_time": datetime.datetime,
    "invite_visitor": list,
    "base_move_visitor_flag": bool,
}
""" 版本 10 之前的存档里，罗德岛对象上访客、上次来访时刻、邀请与移动标记的属性名到应有的类型 """


def _kept(name: str, value: object) -> bool:
    if name == "last_visitor_time":
        return isinstance(value, datetime.datetime)
    return type(value) is PICKLED_TYPES[name]


def adopt_old_save(loaded_dict: dict[str, Any], version: int) -> int:
    """
    读档时调用。从罗德岛对象上删掉 PICKLED_TYPES 里的属性。对象带着其中任何一个属性时，base.visitor 整值写进当前缓冲区。
    缺了或类型不符的访客、邀请与移动标记取新游戏的值。缺了或类型不符的上次来访时刻取读档时的游戏时间。
    时刻换成分钟数。邀请取列表的前两项，列表短时缺的项为 0。对象上没有这些属性时什么也不写
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    version -- 存档的版本，旧存档为 0
    Return arguments:
    int -- 版本 10 之前的存档里缺了或类型不符的属性个数，计法同 save_handle.update_dict_with_default，其余为 0
    """
    attrs = vars(loaded_dict["rhodes_island"])
    found = {name: attrs.pop(name) for name in PICKLED_TYPES if name in attrs}
    kept = {n: v for n, v in found.items() if _kept(n, v)}
    if found:
        stays = kept.get("visitor_info", {}).items()
        invited = [*kept.get("invite_visitor", []), 0, 0]
        _put(
            visitors={str(cid): game_time.minutes(m) for cid, m in stays},
            last_arrival=game_time.minutes(
                kept.get("last_visitor_time", game_time.now())
            ),
            invite={"target": invited[0], "progress": invited[1]},
            moved=kept.get("base_move_visitor_flag", False),
        )
    return len(PICKLED_TYPES) - len(kept) if version < 10 else 0
