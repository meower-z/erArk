"""
基地娱乐的全局键 base.party_days 与 base.hotel_room
===================================================
base.party_days 是一周的派对排期 {星期（周一 0 到周日 6）的字符串: 娱乐id}，0 表示这天没有派对。
没有这个键时七天都读 0。
base.hotel_room 是玩家预订的旅馆房间档次，0 表示没有预订，1 到 3 依次是三种房间。没有这个键时读 0。
两个键都整值替换，值不变时不写。
"""

from collections.abc import Mapping
from typing import Any, cast

from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

PARTY = "base.party_days"
""" 一周派对排期在全局数据里的键 """
HOTEL = "base.hotel_room"
""" 预订的旅馆房间档次在全局数据里的键 """
NO_PARTY: Mapping[str, int] = {str(day): 0 for day in range(7)}
""" 没有 base.party_days 时读到的排期：七天都没有派对 """
PICKLED_PARTY = "party_day_of_week"
""" 版本 13 之前的存档里，派对排期在罗德岛对象上的属性名 """
PICKLED_HOTEL = "love_hotel_room_lv"
""" 版本 13 之前的存档里，旅馆房间档次在罗德岛对象上的属性名 """

working.register(PARTY, cast(core.JSON, NO_PARTY))
working.register(HOTEL, 0)


def _days(game: core.GameState | None) -> Mapping[str, int]:
    return cast(Mapping[str, int], working.get(None, PARTY, game))


def party_days(game: core.GameState | None = None) -> dict[int, int]:
    """
    一周的派对排期
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    dict -- 星期到娱乐id，按存下的先后排列。改它不改排期
    """
    return {int(day): eid for day, eid in _days(game).items()}


def party_day(week_day: int, game: core.GameState | None = None) -> int:
    """
    一天的派对娱乐
    Keyword arguments:
    week_day -- 星期，周一为 0
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    int -- 娱乐id，0 表示没有派对。排期里没有这一天时报 KeyError
    """
    return _days(game)[str(week_day)]


def set_party_day(week_day: int, entertainment_id: int) -> None:
    """
    把一天的派对娱乐换成 entertainment_id，写进当前缓冲区。值不变时不写
    Keyword arguments:
    week_day -- 星期，周一为 0
    entertainment_id -- 娱乐id，0 表示这天没有派对
    """
    days = _days(None)
    if days.get(str(week_day)) != entertainment_id:
        new = {**days, str(week_day): entertainment_id}
        working.put(None, PARTY, cast(core.JSON, new))


def hotel_room(game: core.GameState | None = None) -> int:
    """
    预订的旅馆房间档次
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    int -- 0 表示没有预订，1 到 3 是三种房间
    """
    return cast(int, working.get(None, HOTEL, game))


def set_hotel_room(level: int) -> None:
    """
    把预订的旅馆房间档次换成 level，写进当前缓冲区。值不变时不写
    Keyword arguments:
    level -- 0 表示没有预订，1 到 3 是三种房间
    """
    if hotel_room() != level:
        working.put(None, HOTEL, level)


def adopt_old_save(loaded_dict: dict[str, Any], version: int) -> int:
    """
    读档时调用。从罗德岛对象上删掉派对排期与旅馆房间档次两个属性，把与默认值不同的值写进当前缓冲区。
    派对排期不是 dict 时按七天都没有派对读
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    version -- 存档的版本，旧存档为 0
    Return arguments:
    int -- 计入跨版本更新的条数：版本 13 之前的存档里缺一个属性记 1，派对排期不是 dict 时记 1
    """
    attrs = vars(loaded_dict["rhodes_island"])
    missing = [n for n in (PICKLED_PARTY, PICKLED_HOTEL) if n not in attrs]
    count = len(missing) if version < 13 else 0
    days = attrs.pop(PICKLED_PARTY, NO_PARTY)
    if type(days) is not dict:
        count += 1
    elif (stored := {str(d): eid for d, eid in days.items()}) != NO_PARTY:
        working.put(None, PARTY, cast(core.JSON, stored))
    room = attrs.pop(PICKLED_HOTEL, 0)
    if room != 0:
        working.put(None, HOTEL, room)
    return count
