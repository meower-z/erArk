"""
角色的生长养成数据：角色的键 growth.child
========================================
保持惰性创建：角色未曾写入时键值为 None，读操作（has、of、editing(create=False)）不写入键。
写入时将 game_type.CHILD_GROWTH 的全部 25 项字段编码为不可变 JSON 映射，整值替换（working.put），
值未变时不写。
"""

import copy
import datetime
import math
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from typing import Any, Literal, cast, overload

from Script.Core import game_type
from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

KEY = "growth.child"
""" 角色生长养成数据在角色数据里的键 """

_NON_NEGATIVE_INTS = (
    "attend_class_count",
    "absent_count",
    "skip_count",
    "sex_class_count",
)
_NON_NEGATIVE_FLOATS = ("care_point", "prenatal_point")
_INT_KEY_DICTS = (
    "personality_point",
    "show_off_ability",
    "schedule_override",
    "semester_base_ability",
)
_LIST_FIELDS = ("last_absent_period", "last_attend_period", "semester_id")

_open: dict[int, game_type.CHILD_GROWTH] = {}
""" 可重入 editing(cid) 当前正在编辑的实例 """

working.register(KEY, None)


def _encode_dt(value: Any) -> core.JSON:
    if not isinstance(value, datetime.datetime):
        return cast(core.JSON, value)
    from Script.Design import game_time

    mins = game_time.minutes(value)
    if game_time.at(mins) == value:
        return mins
    return value.isoformat()


def _decode_dt(raw: core.JSON) -> Any:
    if type(raw) is int:
        from Script.Design import game_time

        return game_time.at(raw)
    if isinstance(raw, str):
        try:
            return datetime.datetime.fromisoformat(raw)
        except ValueError:
            return raw
    return raw


def _freeze_value(value: Any) -> core.JSON:
    if isinstance(value, list):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, Mapping):
        return {str(k): _freeze_value(v) for k, v in value.items()}
    return cast(core.JSON, value)


def _thaw_value(value: core.JSON) -> Any:
    if isinstance(value, tuple):
        return [_thaw_value(item) for item in value]
    if isinstance(value, Mapping):
        return {k: _thaw_value(v) for k, v in value.items()}
    return value


def _encode_report_card(card: Mapping[str, Any]) -> dict[str, core.JSON]:
    out: dict[str, core.JSON] = {}
    for k, v in card.items():
        if k == "level_change" and isinstance(v, Mapping):
            out[k] = {
                str(aid): (
                    tuple(pair)
                    if isinstance(pair, (list, tuple))
                    else cast(core.JSON, pair)
                )
                for aid, pair in v.items()
            }
        else:
            out[k] = _freeze_value(v)
    return out


def _decode_report_card(card: Mapping[str, core.JSON]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in card.items():
        if k == "level_change" and isinstance(v, Mapping):
            out[k] = {
                int(aid): list(pair) if isinstance(pair, tuple) else pair
                for aid, pair in v.items()
            }
        else:
            out[k] = _thaw_value(v)
    return out


def _encode_event_history(
    history: Mapping[str, Any],
) -> dict[str, core.JSON]:
    out: dict[str, core.JSON] = {}
    for uid, entry in history.items():
        if isinstance(entry, Mapping):
            frozen_entry: dict[str, core.JSON] = {}
            for k, v in entry.items():
                if k == "time":
                    frozen_entry[k] = _encode_dt(v)
                else:
                    frozen_entry[k] = _freeze_value(v)
            out[str(uid)] = frozen_entry
        else:
            out[str(uid)] = _freeze_value(entry)
    return out


def _decode_event_history(raw: core.JSON) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        return {}
    out: dict[str, Any] = {}
    for uid, entry in raw.items():
        if isinstance(entry, Mapping):
            thawed: dict[str, Any] = {}
            for k, v in entry.items():
                if k == "time":
                    thawed[k] = _decode_dt(v)
                else:
                    thawed[k] = _thaw_value(v)
            out[str(uid)] = thawed
        else:
            out[str(uid)] = _thaw_value(entry)
    return out


def _encode(value: game_type.CHILD_GROWTH) -> dict[str, core.JSON]:
    for name in _NON_NEGATIVE_INTS:
        v = getattr(value, name)
        if type(v) is not int or v < 0:
            raise ValueError(f"{name} 须为非负整数：{v!r}")
    for name in _NON_NEGATIVE_FLOATS:
        v = getattr(value, name)
        if (
            isinstance(v, bool)
            or not isinstance(v, (int, float))
            or not math.isfinite(v)
            or v < 0
        ):
            raise ValueError(f"{name} 须为有限非负数：{v!r}")

    selected: dict[str, core.JSON] = {}
    for day, periods in value.selected_course.items():
        selected[str(day)] = {
            str(period): (
                tuple(cell)
                if isinstance(cell, (list, tuple))
                else cast(core.JSON, cell)
            )
            for period, cell in periods.items()
        }

    out: dict[str, core.JSON] = {
        "personality_point": {
            str(k): v for k, v in value.personality_point.items()
        },
        "prenatal_point": float(value.prenatal_point),
        "care_point": float(value.care_point),
        "selected_course": selected,
        "attend_class_count": value.attend_class_count,
        "absent_count": value.absent_count,
        "last_absent_period": tuple(value.last_absent_period),
        "last_attend_period": tuple(value.last_attend_period),
        "skip_count": value.skip_count,
        "skip_caught_day": value.skip_caught_day,
        "sex_class_count": value.sex_class_count,
        "event_history": _encode_event_history(value.event_history),
        "show_off_ability": {
            str(k): v for k, v in value.show_off_ability.items()
        },
        "report_card_flag": bool(value.report_card_flag),
        "skip_class_flag": bool(value.skip_class_flag),
        "skip_class_day": value.skip_class_day,
        "schedule_template_id": value.schedule_template_id,
        "schedule_override": {
            str(k): v for k, v in value.schedule_override.items()
        },
        "follow_mother_flag": bool(value.follow_mother_flag),
        "semester_id": tuple(value.semester_id),
        "semester_base_attend": value.semester_base_attend,
        "semester_base_absent": value.semester_base_absent,
        "semester_base_ability": {
            str(k): v for k, v in value.semester_base_ability.items()
        },
        "semester_base_work_type": value.semester_base_work_type,
        "report_card_history": tuple(
            (
                _encode_report_card(card)
                if isinstance(card, Mapping)
                else _freeze_value(card)
            )
            for card in value.report_card_history
        ),
    }
    return out


def _decode(stored: Mapping[str, core.JSON]) -> game_type.CHILD_GROWTH:
    g = game_type.CHILD_GROWTH()
    for name in _INT_KEY_DICTS:
        raw_map = stored.get(name)
        if isinstance(raw_map, Mapping):
            setattr(g, name, {int(k): v for k, v in raw_map.items()})
    raw_selected = stored.get("selected_course")
    if isinstance(raw_selected, Mapping):
        g.selected_course = {
            int(day): {
                int(period): list(cell) if isinstance(cell, tuple) else cell
                for period, cell in periods.items()
            }
            for day, periods in raw_selected.items()
            if isinstance(periods, Mapping)
        }
    g.prenatal_point = float(cast(float, stored.get("prenatal_point", 0.0)))
    g.care_point = float(cast(float, stored.get("care_point", 0.0)))
    g.attend_class_count = cast(int, stored.get("attend_class_count", 0))
    g.absent_count = cast(int, stored.get("absent_count", 0))
    for name in _LIST_FIELDS:
        raw_list = stored.get(name)
        if isinstance(raw_list, tuple):
            setattr(g, name, list(raw_list))
    g.skip_count = cast(int, stored.get("skip_count", 0))
    g.skip_caught_day = cast(int, stored.get("skip_caught_day", 0))
    g.sex_class_count = cast(int, stored.get("sex_class_count", 0))
    g.event_history = _decode_event_history(stored.get("event_history"))
    g.report_card_flag = bool(stored.get("report_card_flag", False))
    g.skip_class_flag = bool(stored.get("skip_class_flag", False))
    g.skip_class_day = cast(int, stored.get("skip_class_day", 0))
    g.schedule_template_id = cast(int, stored.get("schedule_template_id", 0))
    g.follow_mother_flag = bool(stored.get("follow_mother_flag", False))
    g.semester_base_attend = cast(int, stored.get("semester_base_attend", 0))
    g.semester_base_absent = cast(int, stored.get("semester_base_absent", 0))
    g.semester_base_work_type = cast(
        int, stored.get("semester_base_work_type", -1)
    )
    raw_cards = stored.get("report_card_history")
    if isinstance(raw_cards, tuple):
        g.report_card_history = [
            (
                _decode_report_card(card)
                if isinstance(card, Mapping)
                else _thaw_value(card)
            )
            for card in raw_cards
        ]
    return g


def has(cid: int, game: core.GameState | None = None) -> bool:
    """
    角色是否已创建生长养成数据（只读不写）
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    bool -- 已创建为 True
    """
    if game is None and cid in _open:
        return True
    return working.get(str(cid), KEY, game) is not None


def of(
    cid: int, game: core.GameState | None = None
) -> game_type.CHILD_GROWTH | None:
    """
    读取角色的生长养成数据副本；未创建时返回 None 且不写入键
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    game_type.CHILD_GROWTH | None -- 养成数据副本或 None
    """
    if game is None and cid in _open:
        return copy.deepcopy(_open[cid])
    stored = working.get(str(cid), KEY, game)
    if stored is None:
        return None
    return _decode(cast(Mapping[str, core.JSON], stored))


def put(cid: int, value: game_type.CHILD_GROWTH | None) -> None:
    """
    写入或清空角色的生长养成数据，值未变时不写
    Keyword arguments:
    cid -- 角色id
    value -- 养成数据结构体，None 表示清空
    """
    current = working.get(str(cid), KEY)
    if value is None:
        if current is not None:
            working.put(str(cid), KEY, None)
        return
    encoded = _encode(value)
    if cid in _open and value is not _open[cid]:
        vars(_open[cid]).update(copy.deepcopy(vars(value)))
    if (
        current is None
        or dict(cast(Mapping[str, core.JSON], current)) != encoded
    ):
        working.put(str(cid), KEY, cast(core.JSON, encoded))


@contextmanager
def _editing(cid: int, create: bool) -> Iterator[game_type.CHILD_GROWTH | None]:
    if cid in _open:
        yield _open[cid]
        return
    obj = of(cid)
    if obj is None:
        if not create:
            yield None
            return
        obj = game_type.CHILD_GROWTH()
    _open[cid] = obj
    try:
        yield obj
    except Exception:
        raise
    except BaseException:
        put(cid, obj)
        raise
    else:
        put(cid, obj)
    finally:
        _open.pop(cid, None)


@overload
def editing(
    cid: int, *, create: Literal[True] = True
) -> AbstractContextManager[game_type.CHILD_GROWTH]: ...


@overload
def editing(
    cid: int, *, create: Literal[False]
) -> AbstractContextManager[game_type.CHILD_GROWTH | None]: ...


@overload
def editing(
    cid: int, *, create: bool
) -> AbstractContextManager[game_type.CHILD_GROWTH | None]: ...


def editing(cid: int, *, create: bool = True) -> AbstractContextManager[Any]:
    """
    可重入的养成数据编辑块：create=True 时不存在则惰性创建；create=False 且不存在时交回 None 且不写入。
    嵌套块共用最外层实例，最外层正常退出或抛出非 Exception 的 BaseException 时写回缓冲区
    Keyword arguments:
    cid -- 角色id
    create -- 尚无养成数据时是否惰性创建
    Return arguments:
    AbstractContextManager -- 可编辑的养成数据实例或 None
    """
    return _editing(cid, create)


def copy_character(old_id: int, new_id: int) -> None:
    """
    把旧角色编号的生长养成数据复制到新角色编号（源为空时不动目标）
    Keyword arguments:
    old_id -- 旧角色 id
    new_id -- 新角色 id
    """
    source = working.get(str(old_id), KEY)
    if source is not None and source != working.get(str(new_id), KEY):
        working.put(str(new_id), KEY, source)


def normalize_legacy(
    raw: game_type.CHILD_GROWTH,
    *,
    migrate_ent: Callable[[Any], Any] | None = None,
    migrate_events: Callable[[dict[str, Any]], int] | None = None,
) -> game_type.CHILD_GROWTH:
    """
    补齐旧版 CHILD_GROWTH 缺失字段，并入旧版单份成绩单，并迁移娱乐编号与事件 uid
    Keyword arguments:
    raw -- 旧版养成数据对象（原地规范后交回）
    migrate_ent -- 娱乐编号迁移函数，缺省用 save_handle._migrate_entertainment_cid
    migrate_events -- 事件履历 uid 迁移函数，缺省用 save_handle._migrate_official_event_history
    Return arguments:
    game_type.CHILD_GROWTH -- 规范化后的养成数据对象
    """
    from Script.Core import save_handle

    ent_fn = (
        migrate_ent
        if migrate_ent is not None
        else save_handle._migrate_entertainment_cid
    )
    evt_fn = (
        migrate_events
        if migrate_events is not None
        else save_handle._migrate_official_event_history
    )
    defaults = game_type.CHILD_GROWTH()
    for attr_name in vars(defaults):
        if not hasattr(raw, attr_name):
            setattr(raw, attr_name, getattr(defaults, attr_name))
    old_card = getattr(raw, "last_report_card", None)
    if old_card and not raw.report_card_history:
        raw.report_card_history = [old_card]
    if hasattr(raw, "last_report_card"):
        delattr(raw, "last_report_card")
    for slot in list(raw.schedule_override):
        raw.schedule_override[slot] = ent_fn(raw.schedule_override[slot])
    evt_fn(raw.event_history)
    return raw


def adopt_old_save(loaded_dict: dict[str, Any], version: int) -> None:
    """
    读档时调用。从旧存档角色对象上删掉 child_growth 属性，非空条目经规范化后写进 growth.child
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    version -- 存档版本，旧存档为 0
    """
    del version
    characters = loaded_dict.get("character_data")
    if not isinstance(characters, Mapping):
        return
    for cid, chara in characters.items():
        attrs = chara.__dict__
        if "child_growth" not in attrs:
            continue
        raw = attrs.pop("child_growth")
        if raw is None or not hasattr(raw, "__dict__"):
            continue
        put(cid, normalize_legacy(raw))
