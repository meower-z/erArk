"""
公务的全局键 base.office_work、base.official_queue 与 base.official_history
==========================================================================
base.office_work 是待处理的公务量，没有这个键时读 200（新游戏的公务量）。
base.official_queue 是待处理的公务事件队列，队首在前。每项是 {"uid", "department", "chara_id", "partner_id",
"add_time"}，add_time 存成内核时钟的分钟数，读出时换回游戏时间。没有这个键时读空队列。
base.official_history 是不记在角色养成数据里的公务事件履历：{履历键: {"time", "choice"}}，time 同样存成分钟数。
写入整值替换键。新值与旧值相同时不写。
"""

import datetime
from collections.abc import Iterable, Mapping
from typing import Any, cast

from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

WORK = "base.office_work"
""" 待处理的公务量在全局数据里的键 """
QUEUE = "base.official_queue"
""" 公务事件队列在全局数据里的键 """
HISTORY = "base.official_history"
""" 公务事件履历在全局数据里的键 """
TIMES = ("add_time", "time")
""" 队列项与履历里存成分钟数的项 """

working.register(WORK, 200)
working.register(QUEUE, ())
working.register(HISTORY, {})


def _put(key: str, new: core.JSON) -> None:
    if new != working.get(None, key):
        working.put(None, key, new)


def _encoded(entry: Mapping[str, Any]) -> dict[str, core.JSON]:
    return {
        k: (
            game_time.minutes(v)
            if k in TIMES and isinstance(v, datetime.datetime)
            else v
        )
        for k, v in entry.items()
    }


def _decoded(entry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        k: game_time.at(v) if k in TIMES and isinstance(v, int) else v
        for k, v in entry.items()
    }


def office_work(game: core.GameState | None = None) -> float:
    """
    待处理的公务量
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    float -- 公务量（int 或 float，按存下的）
    """
    return cast(float, working.get(None, WORK, game))


def set_office_work(value: float) -> None:
    """
    换掉待处理的公务量
    Keyword arguments:
    value -- 新的公务量
    """
    _put(WORK, value)


def queue(game: core.GameState | None = None) -> list[dict[str, Any]]:
    """
    公务事件队列。返回新建的 list 与 dict，改它们不改存的值
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    list -- 队列项，队首在前，add_time 为游戏时间
    """
    stored = cast(Iterable[Mapping[str, Any]], working.get(None, QUEUE, game))
    return [_decoded(entry) for entry in stored]


def set_queue(entries: Iterable[Mapping[str, Any]]) -> None:
    """
    换掉公务事件队列
    Keyword arguments:
    entries -- 队列项，队首在前
    """
    _put(QUEUE, tuple(_encoded(entry) for entry in entries))


def history(game: core.GameState | None = None) -> dict[str, dict[str, Any]]:
    """
    公务事件履历。返回新建的 dict
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    dict -- 履历键到 {"time": 游戏时间, "choice": 选项序号}，按记下的顺序
    """
    stored = cast(Mapping[str, Mapping], working.get(None, HISTORY, game))
    return {key: _decoded(record) for key, record in stored.items()}


def done(key: str, game: core.GameState | None = None) -> bool:
    """
    履历里有没有这个键
    Keyword arguments:
    key -- 履历键
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    bool -- 有时为 True
    """
    return key in cast(Mapping[str, Any], working.get(None, HISTORY, game))


def record(key: str, entry: Mapping[str, Any]) -> None:
    """
    在履历里记下一条，键已有时换掉它的记录，位置不变
    Keyword arguments:
    key -- 履历键
    entry -- {"time": 游戏时间, "choice": 选项序号}
    """
    stored = cast(Mapping[str, core.JSON], working.get(None, HISTORY))
    _put(HISTORY, {**stored, key: _encoded(entry)})


def set_history(records: Mapping[str, Mapping[str, Any]]) -> None:
    """
    换掉公务事件履历
    Keyword arguments:
    records -- 履历键到记录，按要存的顺序
    """
    _put(HISTORY, {key: _encoded(r) for key, r in records.items()})


PICKLED = {
    "official_event_queue": list,
    "official_event_history": dict,
    "office_work": None,
}
""" 版本 11 之前的存档里，罗德岛对象上这三项的属性名与应有的类型。类型不是这一种的值不导入，None 为不查类型 """


def adopt_old_save(loaded_dict: dict[str, Any], version: int) -> int:
    """
    读档时调用。从罗德岛对象上删掉 PICKLED 里的属性，把类型相符的值写进当前缓冲区。
    公务量不查类型，同 save_handle.update_dict_with_default 对 int 默认值的处理。队列里不是 dict 的项不导入
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    version -- 存档的版本，旧存档为 0
    Return arguments:
    int -- 版本 11 之前的存档里缺了或类型不符的属性个数，计法同 save_handle.update_dict_with_default
    """
    attrs = vars(loaded_dict["rhodes_island"])
    found = {name: attrs.pop(name) for name in PICKLED if name in attrs}
    kept = {
        n: v
        for n, v in found.items()
        if PICKLED[n] is None or type(v) is PICKLED[n]
    }
    if "official_event_queue" in kept:
        raw = kept["official_event_queue"]
        set_queue(entry for entry in raw if isinstance(entry, dict))
    if "official_event_history" in kept:
        set_history(kept["official_event_history"])
    if "office_work" in kept:
        set_office_work(kept["office_work"])
    return len(PICKLED) - len(kept) if version < 11 else 0
