"""
角色的妊娠数据：角色的键 body.pregnancy
=======================================
值是稀疏映射：至少含 {"milk_max": 乳汁上限}，其余 15 项妊娠字段仅在偏离默认值时写入。
缺省时乳汁上限为 200，其余字段取 game_type.PREGNANCY() 的默认值，兼容版本 1 至 17 的存档。
这个键没有规则，写入整值替换它（working.put），值未变时不写。
"""

import copy
import datetime
import math
from collections.abc import Collection, Iterator, Mapping
from contextlib import contextmanager
from typing import Any, cast

from Script.Core import game_type
from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

KEY = "body.pregnancy"
""" 妊娠数据在角色数据里的键 """
DEFAULT: Mapping[str, core.JSON] = {"milk_max": 200}
""" 角色没有 body.pregnancy 时读到的值 """
UNSET_TIME = datetime.datetime(1, 1, 1)
""" 受精时间与出生时间未设置时的占位时间 """

_DEFAULTS: Mapping[str, Any] = {
    "fertilization_rate": 0,
    "reproduction_period": 0,
    "ovulation_flag": False,
    "fertilization_time": UNSET_TIME,
    "born_time": UNSET_TIME,
    "unconscious_fertilization": True,
    "lactation_flag": False,
    "eggs": {},
    "next_egg_id": 0,
    "acceleration_days": 0.0,
    "growth_acceleration_days": 0.0,
    "fetus_count": 0,
    "identical_twins": False,
    "external_ovulation_chance": False,
    "prenatal_point": 0.0,
}
""" game_type.PREGNANCY 的 15 项字段与默认值 """

_NON_NEGATIVE_INTS = ("fetus_count", "next_egg_id")
_NON_NEGATIVE_FLOATS = (
    "acceleration_days",
    "growth_acceleration_days",
    "prenatal_point",
)
_DT_FIELDS = ("fertilization_time", "born_time")
_BOOL_FIELDS = (
    "ovulation_flag",
    "unconscious_fertilization",
    "lactation_flag",
    "identical_twins",
    "external_ovulation_chance",
)

_open: dict[int, game_type.PREGNANCY] = {}
""" 可重入 editing(cid) 当前正在编辑的实例 """

working.register(KEY, cast(core.JSON, DEFAULT))


def _is_unset_time(dt: datetime.datetime) -> bool:
    return (
        dt.year == 1
        and dt.month == 1
        and dt.day == 1
        and dt.hour == 0
        and dt.minute == 0
        and dt.second == 0
        and dt.microsecond == 0
    )


def _encode_dt(
    value: datetime.datetime | None, *, unset_as_none: bool
) -> int | str | None:
    if value is None:
        return None
    if not isinstance(value, datetime.datetime):
        raise ValueError(f"非法的妊娠时间值：{value!r}")
    if unset_as_none and _is_unset_time(value):
        return None
    from Script.Design import game_time

    mins = game_time.minutes(value)
    if game_time.at(mins) == value:
        return mins
    return value.isoformat()


def _decode_dt(
    raw: core.JSON, *, default: datetime.datetime | None
) -> datetime.datetime | None:
    if raw is None:
        return default
    if type(raw) is int:
        from Script.Design import game_time

        return game_time.at(raw)
    if isinstance(raw, str):
        return datetime.datetime.fromisoformat(raw)
    raise ValueError(f"无法解码妊娠时间：{raw!r}")


def _encode_eggs(eggs: Mapping[int, Mapping[str, Any]]) -> dict[str, core.JSON]:
    out: dict[str, core.JSON] = {}
    for egg_id, egg in eggs.items():
        if type(egg_id) is not int or egg_id < 0:
            raise ValueError(f"非法的卵编号：{egg_id!r}")
        encoded: dict[str, core.JSON] = {}
        for k, v in egg.items():
            if k in ("lay_time", "identify_time"):
                encoded[k] = _encode_dt(v, unset_as_none=False)
            elif isinstance(v, list):
                encoded[k] = tuple(v)
            else:
                encoded[k] = cast(core.JSON, v)
        out[str(egg_id)] = encoded
    return out


def _decode_eggs(raw: core.JSON) -> dict[int, dict[str, Any]]:
    if not isinstance(raw, Mapping):
        return {}
    out: dict[int, dict[str, Any]] = {}
    for k, entry in raw.items():
        if not isinstance(entry, Mapping):
            continue
        egg: dict[str, Any] = {}
        for ek, ev in entry.items():
            if ek in ("lay_time", "identify_time"):
                egg[ek] = _decode_dt(ev, default=None)
            elif isinstance(ev, tuple):
                egg[ek] = list(ev)
            else:
                egg[ek] = ev
        out[int(k)] = egg
    return out


def _check_finite_number(name: str, value: Any, *, non_negative: bool) -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} 须为数值：{value!r}")
    if not math.isfinite(value) or (non_negative and value < 0):
        raise ValueError(f"{name} 超出合法范围：{value!r}")
    return value


def _encode_fields(
    value: game_type.PREGNANCY, milk_max_val: int
) -> dict[str, core.JSON]:
    if type(milk_max_val) is not int:
        raise ValueError(f"milk_max 须为整数：{milk_max_val!r}")
    if type(value.reproduction_period) is not int:
        raise ValueError(
            f"reproduction_period 须为整数：{value.reproduction_period!r}"
        )
    for name in _NON_NEGATIVE_INTS:
        v = getattr(value, name)
        if type(v) is not int or v < 0:
            raise ValueError(f"{name} 须为非负整数：{v!r}")
    for name in _NON_NEGATIVE_FLOATS:
        _check_finite_number(name, getattr(value, name), non_negative=True)
    _check_finite_number(
        "fertilization_rate", value.fertilization_rate, non_negative=False
    )

    out: dict[str, core.JSON] = {"milk_max": milk_max_val}
    if value.fertilization_rate != 0:
        out["fertilization_rate"] = value.fertilization_rate
    if value.reproduction_period != 0:
        out["reproduction_period"] = value.reproduction_period
    for name in _BOOL_FIELDS:
        bv = bool(getattr(value, name))
        if bv != _DEFAULTS[name]:
            out[name] = bv
    for name in _DT_FIELDS:
        enc_dt = _encode_dt(getattr(value, name), unset_as_none=True)
        if enc_dt is not None:
            out[name] = enc_dt
    if value.eggs:
        out["eggs"] = _encode_eggs(value.eggs)
    if value.next_egg_id != 0:
        out["next_egg_id"] = value.next_egg_id
    if value.acceleration_days != 0.0:
        out["acceleration_days"] = float(value.acceleration_days)
    if value.growth_acceleration_days != 0.0:
        out["growth_acceleration_days"] = float(value.growth_acceleration_days)
    if value.fetus_count != 0:
        out["fetus_count"] = value.fetus_count
    if value.prenatal_point != 0.0:
        out["prenatal_point"] = float(value.prenatal_point)
    return out


def _decode_fields(stored: Mapping[str, core.JSON]) -> game_type.PREGNANCY:
    p = game_type.PREGNANCY()
    if "fertilization_rate" in stored:
        p.fertilization_rate = cast(float, stored["fertilization_rate"])
    if "reproduction_period" in stored:
        p.reproduction_period = cast(int, stored["reproduction_period"])
    for name in _BOOL_FIELDS:
        if name in stored:
            setattr(p, name, bool(stored[name]))
    for name in _DT_FIELDS:
        if name in stored:
            dt = _decode_dt(stored[name], default=UNSET_TIME)
            setattr(p, name, UNSET_TIME if dt is None else dt)
    if "eggs" in stored:
        p.eggs = _decode_eggs(stored["eggs"])
    if "next_egg_id" in stored:
        p.next_egg_id = cast(int, stored["next_egg_id"])
    if "acceleration_days" in stored:
        p.acceleration_days = float(cast(float, stored["acceleration_days"]))
    if "growth_acceleration_days" in stored:
        p.growth_acceleration_days = float(
            cast(float, stored["growth_acceleration_days"])
        )
    if "fetus_count" in stored:
        p.fetus_count = cast(int, stored["fetus_count"])
    if "prenatal_point" in stored:
        p.prenatal_point = float(cast(float, stored["prenatal_point"]))
    return p


def _raw(
    cid: int, game: core.GameState | None = None
) -> Mapping[str, core.JSON]:
    return cast(Mapping[str, core.JSON], working.get(str(cid), KEY, game))


def milk_max(cid: int, game: core.GameState | None = None) -> int:
    """
    角色的乳汁上限
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读这个状态，没有时读当前缓冲区，含还没套用的写入
    Return arguments:
    int -- 乳汁上限
    """
    return cast(int, _raw(cid, game).get("milk_max", 200))


def set_milk_max(cid: int, value: int) -> None:
    """
    把角色的乳汁上限换成 value：整值替换 body.pregnancy，写进当前缓冲区
    Keyword arguments:
    cid -- 角色id
    value -- 乳汁上限
    """
    if type(value) is not int:
        raise ValueError(f"milk_max 须为整数：{value!r}")
    current = _raw(cid)
    if current.get("milk_max", 200) == value:
        return
    working.put(str(cid), KEY, cast(core.JSON, {**current, "milk_max": value}))


def of(cid: int, game: core.GameState | None = None) -> game_type.PREGNANCY:
    """
    读取角色的妊娠数据副本（含 15 项字段，改动返回值不影响内核状态）
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    game_type.PREGNANCY -- 妊娠数据副本
    """
    if game is None and cid in _open:
        return copy.deepcopy(_open[cid])
    return _decode_fields(_raw(cid, game))


def put(cid: int, value: game_type.PREGNANCY) -> None:
    """
    写入角色的妊娠数据（保留已有 milk_max），值未变时不写
    Keyword arguments:
    cid -- 角色id
    value -- 妊娠数据结构体
    """
    current = _raw(cid)
    cur_milk_max = cast(int, current.get("milk_max", 200))
    encoded = _encode_fields(value, cur_milk_max)
    if cid in _open and value is not _open[cid]:
        vars(_open[cid]).update(copy.deepcopy(vars(value)))
    if dict(current) != encoded:
        working.put(str(cid), KEY, cast(core.JSON, encoded))


def update(cid: int, **fields: Any) -> None:
    """
    按字段名更新角色的妊娠数据，遇到未知字段或非法值时报错
    Keyword arguments:
    cid -- 角色id
    fields -- PREGNANCY 字段名与新值
    """
    unknown = set(fields) - set(_DEFAULTS)
    if unknown:
        raise ValueError(f"未知的妊娠字段：{sorted(unknown)}")
    with editing(cid) as p:
        for name, val in fields.items():
            setattr(p, name, val)


@contextmanager
def editing(cid: int) -> Iterator[game_type.PREGNANCY]:
    """
    可重入的妊娠数据编辑块：嵌套块共用同一实例，最外层退出时写回缓冲区。
    块里抛出 Exception 时回滚不写；抛出别的 BaseException（如 Chosen）时照常写回
    Keyword arguments:
    cid -- 角色id
    Return arguments:
    Iterator[game_type.PREGNANCY] -- 可编辑的妊娠数据实例
    """
    if cid in _open:
        yield _open[cid]
        return
    obj = of(cid)
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


def reset_except(cid: int, keep: Collection[str]) -> int:
    """
    把除 keep 外偏离默认值的妊娠字段重置为默认值，返回改动的字段个数
    Keyword arguments:
    cid -- 角色id
    keep -- 要保留的字段名集合
    Return arguments:
    int -- 实际改动的字段数
    """
    defaults = game_type.PREGNANCY()
    keep_set = set(keep)
    changed = 0
    with editing(cid) as p:
        for name, default_val in vars(defaults).items():
            if name in keep_set:
                continue
            if getattr(p, name) != default_val:
                setattr(p, name, copy.deepcopy(default_val))
                changed += 1
    return changed


def copy_character(old_id: int, new_id: int) -> None:
    """
    把旧角色编号的完整妊娠数据（含 milk_max）复制到新角色编号
    Keyword arguments:
    old_id -- 旧角色 id
    new_id -- 新角色 id
    """
    source = dict(_raw(old_id))
    if source != dict(_raw(new_id)):
        working.put(str(new_id), KEY, cast(core.JSON, source))


def adopt_old_save(loaded_dict: dict[str, Any], version: int) -> None:
    """
    读档时调用。把旧存档角色对象上的 pregnancy 属性补齐、截断加速天数并写进 body.pregnancy，
    保留此前由 adopt_pickled 写入的 milk_max，再从角色对象上删掉 pregnancy 属性
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    version -- 存档版本，旧存档为 0
    """
    from Script.System.Pregnancy_System import pregnancy_constant

    del version
    characters = loaded_dict.get("character_data")
    if not isinstance(characters, Mapping):
        return
    for cid, chara in characters.items():
        attrs = chara.__dict__
        if "pregnancy" not in attrs:
            continue
        raw = attrs.pop("pregnancy")
        if raw is None or not hasattr(raw, "__dict__"):
            continue
        normalized = game_type.PREGNANCY()
        for name in vars(normalized):
            if hasattr(raw, name):
                setattr(normalized, name, getattr(raw, name))
        normalized.acceleration_days = min(
            max(0.0, float(normalized.acceleration_days)),
            float(pregnancy_constant.ACCELERATION_MAX_DAY),
        )
        normalized.growth_acceleration_days = min(
            max(0.0, float(normalized.growth_acceleration_days)),
            float(pregnancy_constant.GROW_TO_GIRL_DAY - 1),
        )
        normalized.prenatal_point = max(0.0, float(normalized.prenatal_point))
        normalized.fetus_count = max(0, int(normalized.fetus_count))
        normalized.next_egg_id = max(0, int(normalized.next_egg_id))
        eggs_raw: Any = normalized.eggs
        if isinstance(eggs_raw, dict):
            for egg_data in eggs_raw.values():
                if (
                    isinstance(egg_data, dict)
                    and "acceleration_days" in egg_data
                ):
                    egg_data["acceleration_days"] = min(
                        max(0.0, float(egg_data["acceleration_days"])),
                        float(pregnancy_constant.ACCELERATION_MAX_DAY),
                    )
        else:
            normalized.eggs = {}
        put(cid, normalized)
