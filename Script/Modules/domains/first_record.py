"""
角色的初次记录（history.first_record）与历史周目履历（history.first_record_history）
================================================================================
两个键均稀疏存储，默认空表。占位时间 datetime(1, 1, 1)（year <= 1）编码为 None，
解码还原为 datetime(1, 1, 1)；真实时间按内核时钟分钟数编解码。
写整份记录可在 editing(cid) 块里修改 FIRST_RECORD，退出最外层块时有变动才写回。
"""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
import datetime
from typing import Any, cast

from Script.Core import game_type
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

KEY = "history.first_record"
""" 当前周目初次记录在角色数据里的键 """
HISTORY = "history.first_record_history"
""" 历史周目初次记录在角色数据里的键 """

_SENTINEL = datetime.datetime(1, 1, 1)
_SCALAR_DEFAULTS: Mapping[str, Any] = {
    "first_meet": 1,
    "day_first_meet": 1,
    "first_hand_in_hand": -1,
    "first_kiss_id": -1,
    "first_kiss_body_part": -1,
    "first_kiss_time": None,
    "first_kiss_place": ("0",),
    "first_sex_id": -1,
    "first_sex_time": None,
    "first_sex_place": ("0",),
    "first_sex_posture": "",
    "first_sex_item": -1,
}
_TIME_FIELDS = frozenset({"first_kiss_time", "first_sex_time"})
_PLACE_FIELDS = frozenset({"first_kiss_place", "first_sex_place"})
_INT_KEY_DICTS = (
    "first_part_sex_dict",
    "first_shoot_body_dict",
    "first_strong_orgasm_dict",
    "first_super_orgasm_dict",
    "first_plural_orgasm_dict",
    "fall_talent_time_dict",
    "first_special_record_dict",
)
_STR_KEY_DICTS = ("first_mark_dict", "first_h_mode_dict")
_ALL_DICTS = _INT_KEY_DICTS + _STR_KEY_DICTS

working.register(KEY, {})
working.register(HISTORY, {})
_open: dict[int, game_type.FIRST_RECORD] = {}


def _encode_time(value: Any) -> int | None:
    if not isinstance(value, datetime.datetime) or value.year <= 1:
        return None
    return game_time.minutes(value)


def _decode_time(value: Any) -> datetime.datetime:
    if value is None:
        return _SENTINEL
    if isinstance(value, datetime.datetime):
        return value
    return game_time.at(int(value))


def _freeze(value: Any) -> core.JSON:
    if isinstance(value, datetime.datetime):
        return _encode_time(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(x) for x in value)
    if isinstance(value, dict):
        return {str(k): _freeze(v) for k, v in value.items()}
    return cast(core.JSON, value)


def _thaw_list(seq: Any) -> list[Any]:
    return [_thaw_list(x) if isinstance(x, (list, tuple)) else x for x in seq]


def _encode_entry(dict_name: str, entry: Any) -> core.JSON:
    if dict_name == "first_part_sex_dict" and isinstance(entry, Mapping):
        return {
            "id": entry.get("id", -1),
            "time": _encode_time(entry.get("time")),
            "place": tuple(entry.get("place", ("0",))),
            "posture": entry.get("posture", ""),
            "item": entry.get("item", -1),
        }
    if isinstance(entry, (list, tuple)):
        return tuple(
            _encode_time(e) if i == 0 else _freeze(e)
            for i, e in enumerate(entry)
        )
    return _freeze(entry)


def _decode_entry(dict_name: str, entry: Any) -> Any:
    if dict_name == "first_part_sex_dict" and isinstance(entry, Mapping):
        return {
            "id": entry.get("id", -1),
            "time": _decode_time(entry.get("time")),
            "place": list(entry.get("place", ("0",))),
            "posture": entry.get("posture", ""),
            "item": entry.get("item", -1),
        }
    if isinstance(entry, (list, tuple)):
        return [
            (
                _decode_time(e)
                if i == 0
                else _thaw_list(e) if isinstance(e, (list, tuple)) else e
            )
            for i, e in enumerate(entry)
        ]
    return entry


def _encode_record(fr: game_type.FIRST_RECORD) -> dict[str, core.JSON]:
    out: dict[str, core.JSON] = {}
    for name, default in _SCALAR_DEFAULTS.items():
        val = getattr(fr, name, default)
        if name in _TIME_FIELDS:
            enc: Any = _encode_time(val)
        elif name in _PLACE_FIELDS:
            enc = tuple(val) if isinstance(val, (list, tuple)) else ("0",)
        else:
            enc = val
        if enc != default or type(enc) is not type(default):
            out[name] = cast(core.JSON, enc)
    for dname in _ALL_DICTS:
        raw_d = getattr(fr, dname, None)
        if isinstance(raw_d, Mapping) and raw_d:
            out[dname] = {
                str(k): _encode_entry(dname, v) for k, v in raw_d.items()
            }
    return out


def _decode_record(raw: Mapping[str, Any]) -> game_type.FIRST_RECORD:
    fr = game_type.FIRST_RECORD()
    if not raw:
        return fr
    for name in _SCALAR_DEFAULTS:
        if name not in raw:
            continue
        val = raw[name]
        if name in _TIME_FIELDS:
            setattr(fr, name, _decode_time(val))
        elif name in _PLACE_FIELDS:
            setattr(fr, name, list(val))
        else:
            setattr(fr, name, val)
    for dname in _INT_KEY_DICTS:
        raw_d = raw.get(dname)
        if isinstance(raw_d, Mapping) and raw_d:
            setattr(
                fr,
                dname,
                {int(k): _decode_entry(dname, v) for k, v in raw_d.items()},
            )
    for dname in _STR_KEY_DICTS:
        raw_d = raw.get(dname)
        if isinstance(raw_d, Mapping) and raw_d:
            setattr(
                fr,
                dname,
                {str(k): _decode_entry(dname, v) for k, v in raw_d.items()},
            )
    return fr


def _raw_has_any(raw: Mapping[str, Any]) -> bool:
    return (
        raw.get("first_kiss_id", -1) != -1
        or raw.get("first_sex_id", -1) != -1
        or any(bool(raw.get(dname)) for dname in _ALL_DICTS)
    )


def get(cid: int, field: str, game: core.GameState | None = None) -> Any:
    """快速读取单个标量字段"""
    if game is None and cid in _open:
        return getattr(_open[cid], field)
    stored = cast(Mapping[str, Any], working.get(str(cid), KEY, game))
    if field in _TIME_FIELDS:
        return _decode_time(stored.get(field))
    if field in _PLACE_FIELDS:
        return list(stored.get(field, ("0",)))
    if field in _SCALAR_DEFAULTS:
        return stored.get(field, _SCALAR_DEFAULTS[field])
    raise KeyError(f"{KEY} has no scalar field {field}")


def part_sex(
    cid: int, part_id: int, game: core.GameState | None = None
) -> dict[str, Any] | None:
    """读取单个部位的破处/部位交初体验记录，无记录时返回 None"""
    if game is None and cid in _open:
        rec = _open[cid].first_part_sex_dict.get(part_id)
        return dict(rec) if rec is not None else None
    parts = cast(Mapping[str, Any], working.get(str(cid), KEY, game)).get(
        "first_part_sex_dict"
    )
    entry = parts.get(str(part_id)) if isinstance(parts, Mapping) else None
    if entry is None:
        return None
    return cast(dict[str, Any], _decode_entry("first_part_sex_dict", entry))


def has_any_record(cid: int, game: core.GameState | None = None) -> bool:
    """判断当前周目是否存在任何一条性行为履历"""
    if game is None and cid in _open:
        return _open[cid].has_any_record()
    return _raw_has_any(
        cast(Mapping[str, Any], working.get(str(cid), KEY, game))
    )


def has_part_sex(
    cid: int, part_id: int, game: core.GameState | None = None
) -> bool:
    """零拷贝判断是否存在指定部位的初次性交记录"""
    if game is None and cid in _open:
        return part_id in _open[cid].first_part_sex_dict
    parts = cast(Mapping[str, Any], working.get(str(cid), KEY, game)).get(
        "first_part_sex_dict"
    )
    return isinstance(parts, Mapping) and str(part_id) in parts


def has_special(
    cid: int, special_id: int, game: core.GameState | None = None
) -> bool:
    """零拷贝判断是否存在指定特殊履历"""
    if game is None and cid in _open:
        return special_id in _open[cid].first_special_record_dict
    spec = cast(Mapping[str, Any], working.get(str(cid), KEY, game)).get(
        "first_special_record_dict"
    )
    return isinstance(spec, Mapping) and str(special_id) in spec


def has_shoot_body(
    cid: int, part_id: int, game: core.GameState | None = None
) -> bool:
    """零拷贝判断是否存在指定身体部位的初次射精记录"""
    if game is None and cid in _open:
        return part_id in _open[cid].first_shoot_body_dict
    shoot = cast(Mapping[str, Any], working.get(str(cid), KEY, game)).get(
        "first_shoot_body_dict"
    )
    return isinstance(shoot, Mapping) and str(part_id) in shoot


def view(
    cid: int, game: core.GameState | None = None
) -> game_type.FIRST_RECORD:
    """按当前状态构造 FIRST_RECORD；editing 块内返回正在编辑的对象"""
    if game is None and cid in _open:
        return _open[cid]
    return _decode_record(
        cast(Mapping[str, Any], working.get(str(cid), KEY, game))
    )


def history(
    cid: int, game: core.GameState | None = None
) -> dict[int, game_type.FIRST_RECORD]:
    """读取全部历史周目履历，返回 {周目号int: FIRST_RECORD}"""
    stored = cast(Mapping[str, Any], working.get(str(cid), HISTORY, game))
    if not stored:
        return {}
    return {
        int(r): _decode_record(cast(Mapping[str, Any], rec))
        for r, rec in stored.items()
    }


def set(cid: int, **fields: Any) -> None:
    """更新一个或多个标量字段，值未变时不写"""
    if cid in _open:
        for name, val in fields.items():
            setattr(_open[cid], name, val)
        return
    stored = cast(Mapping[str, core.JSON], working.get(str(cid), KEY))
    new = dict(stored)
    for name, val in fields.items():
        if name not in _SCALAR_DEFAULTS:
            raise KeyError(f"{KEY} has no scalar field {name}")
        default = _SCALAR_DEFAULTS[name]
        enc: Any = (
            _encode_time(val)
            if name in _TIME_FIELDS
            else tuple(val) if name in _PLACE_FIELDS else val
        )
        if enc == default and type(enc) is type(default):
            new.pop(name, None)
        else:
            new[name] = cast(core.JSON, enc)
    if dict(stored) != new:
        working.put(str(cid), KEY, cast(core.JSON, new))


@contextmanager
def editing(cid: int) -> Iterator[game_type.FIRST_RECORD]:
    """修改角色初次记录的上下文块；离开最外层块时有变动才写回"""
    if cid in _open:
        yield _open[cid]
        return
    record = view(cid)
    _open[cid] = record
    try:
        yield record
    except Exception:
        raise
    except BaseException:
        _commit(cid, record)
        raise
    else:
        _commit(cid, record)
    finally:
        _open.pop(cid, None)


def _commit(cid: int, record: game_type.FIRST_RECORD) -> None:
    new = _encode_record(record)
    old = cast(Mapping[str, core.JSON], working.get(str(cid), KEY))
    if dict(old) != new:
        working.put(str(cid), KEY, cast(core.JSON, new))


def clear(cid: int) -> None:
    """清空角色当前周目的初次记录"""
    if cid in _open:
        vars(_open[cid]).update(vars(game_type.FIRST_RECORD()))
        return
    if working.get(str(cid), KEY):
        working.put(str(cid), KEY, {})


def carry_for_new_round(
    character_data: Mapping[int, Any], game: core.GameState | None = None
) -> dict[str, core.JSON]:
    """新周目重置前导出所有角色的当前履历与历史周目履历（只导非空项）"""
    out: dict[str, core.JSON] = {}
    for cid in character_data:
        cur = cast(Mapping[str, core.JSON], working.get(str(cid), KEY, game))
        hist = cast(
            Mapping[str, core.JSON], working.get(str(cid), HISTORY, game)
        )
        if _raw_has_any(cur) or hist:
            out[str(cid)] = {
                "current": dict(cur) if _raw_has_any(cur) else {},
                "history": dict(hist),
            }
    return out


def restore_for_new_round(
    cid: int, old_round: int, carried: Mapping[str, Any]
) -> None:
    """新周目里恢复历史周目履历，并把旧周目有记录的当前履历归档到 old_round"""
    entry = carried.get(str(cid))
    if not isinstance(entry, Mapping):
        return
    hist = dict(cast(Mapping[str, core.JSON], entry.get("history", {})))
    cur = cast(Mapping[str, core.JSON], entry.get("current", {}))
    if cur and _raw_has_any(cur):
        hist[str(old_round)] = dict(cur)
    if hist:
        working.put(str(cid), HISTORY, cast(core.JSON, hist))


def _remap_raw(
    raw: Mapping[str, Any], id_map: Mapping[int, int]
) -> dict[str, core.JSON]:
    if not raw:
        return {}
    out: dict[str, Any] = dict(raw)
    for attr in ("first_hand_in_hand", "first_kiss_id", "first_sex_id"):
        val = out.get(attr, -1)
        if isinstance(val, int) and val > 0:
            out[attr] = id_map.get(val, val)
    parts = out.get("first_part_sex_dict")
    if isinstance(parts, Mapping) and parts:
        new_parts: dict[str, core.JSON] = {}
        for k, rec in parts.items():
            if isinstance(rec, Mapping):
                copy_rec = dict(rec)
                rid = copy_rec.get("id", -1)
                if isinstance(rid, int) and rid > 0:
                    copy_rec["id"] = id_map.get(rid, rid)
                new_parts[str(k)] = cast(core.JSON, copy_rec)
            else:
                new_parts[str(k)] = cast(core.JSON, rec)
        out["first_part_sex_dict"] = new_parts
    return cast(dict[str, core.JSON], out)


def remap_ids(cid: int, id_map: Mapping[int, int]) -> None:
    """重映射角色当前记录与全部历史周目记录里引用的角色id"""
    cur = cast(Mapping[str, core.JSON], working.get(str(cid), KEY))
    if cur:
        new_cur = _remap_raw(cur, id_map)
        if dict(cur) != new_cur:
            working.put(str(cid), KEY, cast(core.JSON, new_cur))
    hist = cast(Mapping[str, core.JSON], working.get(str(cid), HISTORY))
    if hist:
        new_hist = {
            str(r): _remap_raw(cast(Mapping[str, Any], rec), id_map)
            for r, rec in hist.items()
        }
        if dict(hist) != new_hist:
            working.put(str(cid), HISTORY, cast(core.JSON, new_hist))


def adopt_old_save(loaded_dict: dict[str, Any]) -> int:
    """读档重建角色后，把旧角色对象上的 first_record 与 first_record_history 迁入内核键"""
    for cid, character in loaded_dict["character_data"].items():
        attrs = vars(character)
        if "first_record" in attrs:
            old_fr = attrs.pop("first_record")
            if old_fr is not None:
                enc = _encode_record(old_fr)
                if enc:
                    working.put(str(cid), KEY, cast(core.JSON, enc))
        if "first_record_history" in attrs:
            old_hist = attrs.pop("first_record_history")
            if isinstance(old_hist, Mapping) and old_hist:
                enc_hist = {
                    str(r): _encode_record(rec)
                    for r, rec in old_hist.items()
                    if rec is not None
                }
                if enc_hist:
                    working.put(str(cid), HISTORY, cast(core.JSON, enc_hist))
    return 0
