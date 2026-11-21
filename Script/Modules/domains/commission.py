"""
外勤委托与载具的全局键 base.commission 与 base.vehicles
=======================================================
base.commission 是 {"ongoing": {委托id的字符串: 委托}, "finished": [委托id, ...], "shut_down": [委托id, ...]}。
委托是 {"team": [角色id, ...], "end": 返回时刻, "vehicles": [载具id, ...]}。队伍的第一人是队长。
返回时刻是内核时钟的分钟数。ongoing 按派出的顺序排列。结算外勤委托时按这个顺序处理到期的委托。
finished 是已完成的委托id。shut_down 是不可进行的委托id。两者都升序排列。
base.vehicles 是 {载具id的字符串: [拥有数, 外勤中数]}，按记下的顺序排列。
没有 base.vehicles 时读出配置里每种载具各一行 (0, 0)，按配置的顺序排列。
两个键都整值替换。新值与旧值相同时不写。
"""

import datetime
from collections.abc import Collection, Iterable, Mapping
from typing import Any, NamedTuple, cast

from Script.Config import game_config
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

KEY = "base.commission"
""" 外勤委托在全局数据里的键 """
VEHICLES = "base.vehicles"
""" 载具表在全局数据里的键 """

working.register(KEY, {"ongoing": {}, "finished": (), "shut_down": ()})
working.register(VEHICLES, None)


class Ongoing(NamedTuple):
    """进行中的一项委托，由 ongoing 交回"""

    team: tuple[int, ...]
    """ 派出的角色id，第一人是队长 """
    end: datetime.datetime
    """ 返回时刻 """
    vehicles: tuple[int, ...]
    """ 派出的载具id，派出几辆就有几项 """


def _stored(game: core.GameState | None = None) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], working.get(None, KEY, game))


def _put(**parts: core.JSON) -> None:
    old = _stored()
    new = {**old, **parts}
    if new != old:
        working.put(None, KEY, new)


def ongoing(game: core.GameState | None = None) -> dict[int, Ongoing]:
    """
    进行中的委托
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    dict -- 委托id到 Ongoing，按派出的顺序
    """
    return {
        int(cid): Ongoing(
            tuple(one["team"]), game_time.at(one["end"]), tuple(one["vehicles"])
        )
        for cid, one in _stored(game)["ongoing"].items()
    }


def _entry(team: Iterable[int], end: int, vehicles: Iterable[int]) -> core.JSON:
    return {"team": tuple(team), "end": end, "vehicles": tuple(vehicles)}


def start(
    cid: int,
    team: Iterable[int],
    end: datetime.datetime,
    vehicles: Iterable[int],
) -> None:
    """
    派出一项委托，写进当前缓冲区。委托id是新的时，这项委托排在最后。
    委托id已在进行中时，这一项整项换掉，位置不变
    Keyword arguments:
    cid -- 委托id
    team -- 派出的角色id，第一人是队长
    end -- 返回时刻
    vehicles -- 派出的载具id，派出几辆就有几项
    """
    table = dict(_stored()["ongoing"])
    table[str(cid)] = _entry(team, game_time.minutes(end), vehicles)
    _put(ongoing=table)


def set_team(cid: int, team: Iterable[int]) -> None:
    """
    换掉一项进行中的委托的队伍，写进当前缓冲区。返回时刻、载具与委托的位置不变。没有这项委托时报 KeyError
    Keyword arguments:
    cid -- 委托id
    team -- 新队伍的角色id，第一人是队长
    """
    table = dict(_stored()["ongoing"])
    one = table[str(cid)]
    table[str(cid)] = _entry(team, one["end"], one["vehicles"])
    _put(ongoing=table)


def finish(cid: int) -> None:
    """
    把一项委托从进行中的委托里删掉，写进当前缓冲区。它不记已完成，也不收回载具。没有这项委托时报 KeyError
    Keyword arguments:
    cid -- 委托id
    """
    table = dict(_stored()["ongoing"])
    del table[str(cid)]
    _put(ongoing=table)


def finished(game: core.GameState | None = None) -> frozenset[int]:
    """
    已完成的委托
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    frozenset -- 委托id
    """
    return frozenset(_stored(game)["finished"])


def shut_down(game: core.GameState | None = None) -> frozenset[int]:
    """
    不可进行的委托
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    frozenset -- 委托id
    """
    return frozenset(_stored(game)["shut_down"])


def mark(cid: int, state: float) -> None:
    """
    按委托奖励 m 的值改一项委托的记录，写进当前缓冲区。state 为 -1 时记为不可进行。state 为 1 时记为已完成。
    state 为 0 时，委托记为不可进行的就去掉这一记，不然委托记为已完成的就去掉那一记
    Keyword arguments:
    cid -- 委托id
    state -- 奖励 m 的值，-1、0 与 1 以外的值什么也不改
    """
    shut, done = set(shut_down()), set(finished())
    if state == -1:
        shut.add(cid)
    elif state == 0:
        if cid in shut:
            shut.remove(cid)
        elif cid in done:
            done.remove(cid)
    elif state == 1:
        done.add(cid)
    _put(finished=tuple(sorted(done)), shut_down=tuple(sorted(shut)))


def vehicles(game: core.GameState | None = None) -> dict[int, tuple[int, int]]:
    """
    载具表
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    dict -- 载具id到 (拥有数, 外勤中数)，按表里的顺序。没有 base.vehicles 时为配置里每种载具一行 (0, 0)
    """
    stored = cast(
        Mapping[str, tuple[int, int]] | None,
        working.get(None, VEHICLES, game),
    )
    if stored is None:
        return {vid: (0, 0) for vid in game_config.config_vehicle}
    return {int(vid): (row[0], row[1]) for vid, row in stored.items()}


def _put_vehicles(table: Mapping[int, tuple[int, int]]) -> None:
    new = {str(vid): tuple(row) for vid, row in table.items()}
    if working.get(None, VEHICLES) != new:
        working.put(None, VEHICLES, cast(core.JSON, new))


def add_vehicle(vid: int, owned: int = 0, out: int = 0) -> None:
    """
    给一种载具的拥有数与外勤中数各加上给出的增量，写进当前缓冲区。表里没有这种载具时报 KeyError
    Keyword arguments:
    vid -- 载具id
    owned -- 拥有数的增量
    out -- 外勤中数的增量
    """
    table = vehicles()
    had, away = table[vid]
    table[vid] = (had + owned, away + out)
    _put_vehicles(table)


def fill_vehicles() -> None:
    """表里缺了配置里的载具时，按配置的顺序在最后补上 (0, 0)，写进当前缓冲区。不缺时不写"""
    table = vehicles()
    missing = [vid for vid in game_config.config_vehicle if vid not in table]
    if missing:
        _put_vehicles({**table, **dict.fromkeys(missing, (0, 0))})


def remap(old_to_new: Mapping[int, int]) -> None:
    """
    角色换id时，把进行中的委托的队伍里的旧id换成新id，写进当前缓冲区。队伍里的顺序与委托的顺序都不变
    Keyword arguments:
    old_to_new -- 旧id到新id，表里没有的id不变
    """
    for cid, one in ongoing().items():
        set_team(cid, [old_to_new.get(oid, oid) for oid in one.team])


PICKLED_TYPES = {
    "ongoing_field_commissions": dict,
    "vehicles": dict,
    "finished_field_commissions_set": set,
    "shut_down_field_commissions_set": set,
}
""" 版本 10 之前的存档里，罗德岛对象上外勤委托与载具的属性名到应有的类型 """


def _pickled_ongoing(raw: Mapping[Any, Any]) -> dict[str, core.JSON]:
    table: dict[str, core.JSON] = {}
    for cid, one in raw.items():
        team = one[0] if len(one) > 0 else []
        end = one[1] if len(one) > 1 else None
        if not isinstance(end, datetime.datetime):
            continue
        sent = one[2] if len(one) > 2 else []
        table[str(cid)] = _entry(team, game_time.minutes(end), sent)
    return table


def adopt_old_save(loaded_dict: dict[str, Any], version: int) -> int:
    """
    读档时调用。从罗德岛对象上删掉 PICKLED_TYPES 里的属性。载具表类型相符时写进当前缓冲区的 base.vehicles。
    对象带着其中任何一个属性时，base.commission 整值写进当前缓冲区，缺了或类型不符的部分取空值。
    进行中委托的返回时刻换成分钟数。返回时刻不是时间的委托不留。缺了载具一项的委托记为没有派出载具。
    两个集合换成升序的列表。对象上没有这些属性时什么也不写
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    version -- 存档的版本，旧存档为 0
    Return arguments:
    int -- 版本 10 之前的存档里缺了或类型不符的属性个数，计法同 save_handle.update_dict_with_default，其余为 0
    """
    attrs = vars(loaded_dict["rhodes_island"])
    found = {name: attrs.pop(name) for name in PICKLED_TYPES if name in attrs}
    kept = {n: v for n, v in found.items() if type(v) is PICKLED_TYPES[n]}
    if "vehicles" in kept:
        rows = kept["vehicles"].items()
        _put_vehicles({vid: (row[0], row[1]) for vid, row in rows})
    if found:
        sets: dict[str, Collection[int]] = {
            "finished": kept.get("finished_field_commissions_set", ()),
            "shut_down": kept.get("shut_down_field_commissions_set", ()),
        }
        raw = kept.get("ongoing_field_commissions", {})
        parts = {name: tuple(sorted(ids)) for name, ids in sets.items()}
        _put(ongoing=_pickled_ongoing(raw), **parts)
    return len(PICKLED_TYPES) - len(kept) if version < 10 else 0
