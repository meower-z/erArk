"""
罗德岛所在位置的全局键 base.location
====================================
值是 {"country": 国家id, "move": 移动}。国家id 是 game_config.config_birthplace 的键。
move 为 None 时罗德岛停着。罗德岛移动中时，move 是 {"to": 目标国家id, "at": 抵达时刻}。
抵达时刻是内核时钟的分钟数。没有这个键时读到新游戏的值：国家 START，停着。
写入整值替换这个键。新值与旧值相同时不写。
"""

import datetime
from collections.abc import Mapping
from typing import Any, cast

from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

KEY = "base.location"
""" 罗德岛所在位置在全局数据里的键 """
START = 17
""" 新游戏时罗德岛所在的国家id """

working.register(KEY, {"country": START, "move": None})


def _stored(game: core.GameState | None = None) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], working.get(None, KEY, game))


def _put(**parts: core.JSON) -> None:
    old = _stored()
    new = {**old, **parts}
    if new != old:
        working.put(None, KEY, new)


def country(game: core.GameState | None = None) -> int:
    """
    罗德岛所在的国家
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    int -- 国家id
    """
    return cast(int, _stored(game)["country"])


def move(
    game: core.GameState | None = None,
) -> tuple[int, datetime.datetime] | None:
    """
    罗德岛正在进行的移动
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    tuple | None -- (目标国家id, 抵达时刻)，停着时为 None
    """
    going = _stored(game)["move"]
    if going is None:
        return None
    return going["to"], game_time.at(going["at"])


def set_move(to: int, at: datetime.datetime) -> None:
    """
    让罗德岛开始移动，写进当前缓冲区。已在移动时换掉目标与抵达时刻
    Keyword arguments:
    to -- 目标国家id
    at -- 抵达时刻
    """
    _put(move={"to": to, "at": game_time.minutes(at)})


def arrive() -> None:
    """罗德岛抵达移动的目标，写进当前缓冲区。所在国家换成目标，移动清掉。停着时报 TypeError"""
    _put(country=_stored()["move"]["to"], move=None)


PICKLED_TYPES = {"current_location": list, "move_target_and_time": list}
""" 版本 10 之前的存档里，罗德岛对象上所在位置与移动的属性名到应有的类型 """


def adopt_old_save(loaded_dict: dict[str, Any], version: int) -> int:
    """
    读档时调用。从罗德岛对象上删掉 PICKLED_TYPES 里的属性。
    对象带着其中任何一个属性时，所在国家写进当前缓冲区，并记为停着。所在国家取位置列表的第一项。
    位置列表空、缺了或类型不符时取 START。移动列表有三项、目标不为 0 且第三项是时间时，再记为移动。
    对象上没有这些属性时什么也不写
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    version -- 存档的版本，旧存档为 0
    Return arguments:
    int -- 版本 10 之前的存档里缺了或类型不符的属性个数，计法同 save_handle.update_dict_with_default，其余为 0
    """
    attrs = vars(loaded_dict["rhodes_island"])
    found = {name: attrs.pop(name) for name in PICKLED_TYPES if name in attrs}
    kept = {n: v for n, v in found.items() if type(v) is PICKLED_TYPES[n]}
    place = kept.get("current_location", [START])
    target = kept.get("move_target_and_time", [0, 0, 0])
    if found:
        _put(country=place[0] if place else START, move=None)
    going = len(target) > 2 and target[0] != 0
    if going and isinstance(target[2], datetime.datetime):
        set_move(target[0], target[2])
    return len(PICKLED_TYPES) - len(kept) if version < 10 else 0
