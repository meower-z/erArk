"""
事件与输入记录：全局键 events.triggered、events.triggered_today、log.instructions 与 log.inputs
===============================================================================================
events.triggered 与 events.triggered_today 是 {事件id: true}，按触发先后记录触发过的事件与今日触发过的事件。
log.instructions 是 {"recent": 玩家最近的行为id（至多 RECENT_MAX 个，旧的在前）,
"daily": 每日指令输入记录的文本}。
log.inputs 是玩家最近的原始输入字符串元组，旧的在前，至多 INPUTS_MAX 条。
没有某一项时为空。写入整值替换一个键，值没变时不写。
"""

from collections.abc import Mapping, Sequence
from typing import Any, cast

from Script.Kernel import core
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import pickled

TRIGGERED = "events.triggered"
""" 触发过的事件的全局键 """
TODAY = "events.triggered_today"
""" 今日触发过的事件的全局键 """
LOG = "log.instructions"
""" 玩家指令记录的全局键 """
RECENT_MAX = 10
""" 最近的行为id 至多记几个 """
INPUTS = "log.inputs"
""" 玩家最近的输入的全局键 """
INPUTS_MAX = 21
""" 最近的输入至多记几条 """

working.register(TRIGGERED, {})
working.register(TODAY, {})
working.register(LOG, {"recent": (), "daily": ""})
working.register(INPUTS, ())


def _ids(key: str) -> Mapping[str, bool]:
    return cast(Mapping[str, bool], working.get(None, key))


def triggered(event_id: str) -> bool:
    """
    事件触发过时为 True
    Keyword arguments:
    event_id -- 事件id
    """
    return event_id in _ids(TRIGGERED)


def triggered_today(event_id: str) -> bool:
    """
    事件今天触发过时为 True
    Keyword arguments:
    event_id -- 事件id
    """
    return event_id in _ids(TODAY)


def _add(key: str, event_id: str) -> None:
    ids = _ids(key)
    if event_id not in ids:
        working.put(None, key, {**ids, event_id: True})


def trigger(event_id: str) -> None:
    """
    记下事件触发过，写进当前缓冲区
    Keyword arguments:
    event_id -- 事件id
    """
    _add(TRIGGERED, event_id)


def trigger_today(event_id: str) -> None:
    """
    记下事件今天触发过，写进当前缓冲区
    Keyword arguments:
    event_id -- 事件id
    """
    _add(TODAY, event_id)


def clear_today() -> None:
    """清空今日触发过的事件，写进当前缓冲区"""
    if _ids(TODAY):
        working.put(None, TODAY, {})


def triggered_ids() -> set[str]:
    """触发过的全部事件id"""
    return set(_ids(TRIGGERED))


def today_ids() -> set[str]:
    """今日触发过的全部事件id"""
    return set(_ids(TODAY))


def today_count() -> int:
    """今日触发过的事件数"""
    return len(_ids(TODAY))


def _log() -> Mapping[str, Any]:
    return cast(Mapping[str, Any], working.get(None, LOG))


def recent() -> list[str]:
    """
    玩家最近的行为id，旧的在前
    Return arguments:
    list -- 新的列表
    """
    return list(cast(Sequence[str], _log()["recent"]))


def daily() -> str:
    """
    每日指令输入记录的文本
    Return arguments:
    str -- 文本
    """
    return cast(str, _log()["daily"])


def _put_log(recent_ids: Sequence[str], daily_text: str) -> None:
    old = _log()
    new: dict[str, core.JSON] = {
        "recent": tuple(recent_ids),
        "daily": daily_text,
    }
    if tuple(old["recent"]) != new["recent"] or old["daily"] != new["daily"]:
        working.put(None, LOG, new)


def note_instruction(record: str, behavior_id: str) -> None:
    """
    玩家的一个行为结算时：record 接到每日记录后面，behavior_id 接到最近的行为后面，超出 RECENT_MAX 个时去掉最旧的一个
    Keyword arguments:
    record -- 这次的指令输入记录文本
    behavior_id -- 行为id
    """
    ids = [*recent(), behavior_id]
    if len(ids) > RECENT_MAX:
        ids.pop(0)
    _put_log(ids, daily() + record)


def set_recent(behavior_ids: Sequence[str]) -> None:
    """
    换掉最近的行为id
    Keyword arguments:
    behavior_ids -- 行为id，旧的在前
    """
    _put_log(behavior_ids, daily())


def add_daily(text: str) -> None:
    """
    每日记录后面接一段文本
    Keyword arguments:
    text -- 文本
    """
    _put_log(recent(), daily() + text)


def clear_daily() -> None:
    """清空每日记录"""
    _put_log(recent(), "")


def inputs(game: core.GameState | None = None) -> list[str]:
    """
    玩家最近的输入，旧的在前
    Keyword arguments:
    game -- 给出时只读这个 GameState，没有时读当前缓冲区
    Return arguments:
    list -- 新的列表
    """
    return list(cast(Sequence[str], working.get(None, INPUTS, game)))


def _appended(old: Sequence[str], orders: Sequence[str]) -> tuple[str, ...]:
    return (*old, *orders)[-INPUTS_MAX:]


def add_inputs(orders: Sequence[str]) -> None:
    """
    将 orders 依次接到最近的输入后面，只保留最新的 INPUTS_MAX 条，值有变化时写进当前缓冲区
    Keyword arguments:
    orders -- 要追加的输入序列，旧的在前
    """
    new = _appended(inputs(), orders)
    if new != tuple(inputs()):
        working.put(None, INPUTS, new)


def with_inputs(game: core.GameState, orders: Sequence[str]) -> core.GameState:
    """
    返回在 game 的 log.inputs 后面依次接上 orders 的 GameState，只保留最新的 INPUTS_MAX 条
    Keyword arguments:
    game -- 起点状态
    orders -- 要追加的输入序列，旧的在前
    Return arguments:
    GameState -- 更新后的状态，orders 为空时原样返回 game
    """
    if not orders:
        return game
    new = _appended(inputs(game), orders)
    return core.with_value(game, None, INPUTS, new)


def adopt_old_save(loaded_dict: dict[str, Any], version: int) -> int:
    """
    读档时调用，从存档缓存取出 input_cache、两个事件记录与两个指令记录并写进当前缓冲区。
    事件记录按 sorted 的顺序记下，取出的字段会从 loaded_dict 中删掉
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表，原地修改
    version -- 存档的版本，旧存档为 0
    Return arguments:
    int -- 补上或换掉的项数，计法同 save_handle.update_dict_with_default
    """
    default: dict[str, Any] = {
        "taiggered_event_record": set(),
        "today_taiggered_event_record": set(),
        "pl_pre_behavior_instruce": [],
        "daily_intsruce": [],
    }
    typed, typed_count = pickled.take(loaded_dict, {"input_cache": []}, version)
    if typed:
        new = tuple(typed["input_cache"])
        if new != tuple(inputs()):
            working.put(None, INPUTS, new)
    found, count = pickled.take(loaded_dict, default, version)
    if not found:
        return typed_count
    for key, name in (
        (TRIGGERED, "taiggered_event_record"),
        (TODAY, "today_taiggered_event_record"),
    ):
        new_ids = {eid: True for eid in sorted(found[name])}
        if dict(_ids(key)) != new_ids:
            working.put(None, key, new_ids)
    daily_raw = found["daily_intsruce"]
    daily_text = daily_raw if isinstance(daily_raw, str) else "".join(daily_raw)
    _put_log(found["pl_pre_behavior_instruce"], daily_text)
    return count + typed_count
