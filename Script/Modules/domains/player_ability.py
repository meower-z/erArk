"""
玩家特殊能力：角色的键 player.ability
=====================================
值只存偏离默认值 DEFAULTS 的项：{字段名: 值}，没有这一项时各项均取 PLAYER_ABILITY() 的默认值。
today_sanity_point_cost 保留精确数值类型（int 或 Fraction）。
air_hypnosis_position 存成空串或场景路径元组，读出时元组换回列表。
写入整值替换这个键，值与类型都未变时不写；恢复默认值的项从表里删去。
"""

from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Literal, cast, overload

from Script.Core import num
from Script.Core.num import Num
from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

KEY = "player.ability"
""" 玩家特殊能力在角色数据里的键 """

IntField = Literal[
    "follow_count",
    "jj_size",
    "hypnosis_type",
    "carry_chara_id_in_time_stop",
    "free_in_time_stop_chara_id",
]
""" 整数字段名 """

BoolField = Literal["hormone", "visual", "tactile"]
""" 布尔字段名 """

_DEFAULTS: Mapping[str, core.JSON] = {
    "follow_count": 1,
    "jj_size": 1,
    "hormone": False,
    "visual": False,
    "tactile": False,
    "today_sanity_point_cost": 0,
    "hypnosis_type": 0,
    "air_hypnosis_position": "",
    "carry_chara_id_in_time_stop": 0,
    "free_in_time_stop_chara_id": 0,
}
""" 全部 10 项字段的编码默认值 """

FIELDS: frozenset[str] = frozenset(_DEFAULTS)
""" 全部合法字段名 """

working.register(KEY, {})


def _same(a: object, b: object) -> bool:
    return type(a) is type(b) and a == b


def _encode(name: str, value: Any) -> core.JSON:
    if name not in _DEFAULTS:
        raise KeyError(f"unknown player_ability field {name!r}")
    if name == "today_sanity_point_cost":
        return cast(core.JSON, value)
    if name == "air_hypnosis_position":
        if isinstance(value, str):
            return value
        if isinstance(value, Sequence):
            return tuple(str(part) for part in value)
        raise TypeError(f"bad air_hypnosis_position: {value!r}")
    if isinstance(_DEFAULTS[name], bool):
        return bool(value)
    return int(value)


def _decode(name: str, raw: core.JSON) -> Any:
    if name == "air_hypnosis_position" and isinstance(raw, tuple):
        return list(raw)
    return raw


def _raw(
    cid: int, game: core.GameState | None = None
) -> Mapping[str, core.JSON]:
    return cast(Mapping[str, core.JSON], working.get(str(cid), KEY, game))


@overload
def get(
    cid: int, name: IntField, game: core.GameState | None = None
) -> int: ...


@overload
def get(
    cid: int, name: BoolField, game: core.GameState | None = None
) -> bool: ...


@overload
def get(
    cid: int,
    name: Literal["today_sanity_point_cost"],
    game: core.GameState | None = None,
) -> Num: ...


@overload
def get(
    cid: int,
    name: Literal["air_hypnosis_position"],
    game: core.GameState | None = None,
) -> list[str] | str: ...


@overload
def get(cid: int, name: str, game: core.GameState | None = None) -> Any: ...


def get(cid: int, name: str, game: core.GameState | None = None) -> Any:
    """
    读玩家特殊能力的一项
    Keyword arguments:
    cid -- 角色id
    name -- 字段名，不在 FIELDS 里报 KeyError
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    Any -- 解码后的值
    """
    default = _DEFAULTS[name]
    return _decode(name, _raw(cid, game).get(name, default))


def set(cid: int, **values: Any) -> None:
    """
    更新玩家特殊能力的一项或多项，写进当前缓冲区。值与类型都未变时不写
    Keyword arguments:
    cid -- 角色id
    values -- 字段名到新值
    """
    if not values:
        return
    old = _raw(cid)
    new = dict(old)
    changed = False
    for name, val in values.items():
        encoded = _encode(name, val)
        default = _DEFAULTS[name]
        cur = old.get(name, default)
        if _same(cur, encoded):
            continue
        changed = True
        if _same(encoded, default):
            new.pop(name, None)
        else:
            new[name] = encoded
    if changed:
        working.put(str(cid), KEY, cast(core.JSON, new))


def add_sanity_cost(cid: int, by: Num) -> None:
    """
    累加今日理智消耗（保留 int/Fraction 精确类型），写进当前缓冲区
    Keyword arguments:
    cid -- 角色id
    by -- 增加的理智消耗
    """
    current = get(cid, "today_sanity_point_cost")
    set(cid, today_sanity_point_cost=current + by)


def reset(cid: int) -> None:
    """
    将玩家特殊能力全部恢复为默认值，写进当前缓冲区
    Keyword arguments:
    cid -- 角色id
    """
    if _raw(cid):
        working.put(str(cid), KEY, {})


def snapshot(cid: int, game: core.GameState | None = None) -> dict[str, Any]:
    """
    全部 10 项能力的完整字典，供快照投影使用
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    dict -- 字段名到值
    """
    stored = _raw(cid, game)
    return {
        name: _decode(name, stored.get(name, default))
        for name, default in _DEFAULTS.items()
    }


def copy_to(old_id: int, new_id: int) -> None:
    """
    角色替换时把 old_id 的能力数据整份写到 new_id
    Keyword arguments:
    old_id -- 原角色id
    new_id -- 新角色id
    """
    stored = dict(_raw(old_id))
    if stored != dict(_raw(new_id)):
        working.put(str(new_id), KEY, cast(core.JSON, stored))


def remap(cids: Iterable[int], mapping: Mapping[int, int]) -> None:
    """
    角色换 id 时把能力数据里引用的角色 id 按 mapping 改写
    Keyword arguments:
    cids -- 要检查的角色id集合
    mapping -- 原角色id到新角色id
    """
    for cid in cids:
        stored = _raw(cid)
        if not stored:
            continue
        updates: dict[str, int] = {}
        for field in (
            "carry_chara_id_in_time_stop",
            "free_in_time_stop_chara_id",
        ):
            val = get(cid, field)
            if val and val in mapping:
                updates[field] = mapping[val]
        if updates:
            set(cid, **updates)


def adopt_old_save(loaded_dict: dict[str, Any]) -> None:
    """
    读档时调用。把角色对象上携带的 pl_ability 写入 player.ability，
    today_sanity_point_cost 经 num.exact 转为精确数值，随后删掉该属性
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    """
    for cid, character in loaded_dict.get("character_data", {}).items():
        if "pl_ability" not in vars(character):
            continue
        pa = vars(character)["pl_ability"]
        if pa is not None:
            sparse: dict[str, core.JSON] = {}
            for name, default in _DEFAULTS.items():
                if hasattr(pa, name):
                    raw_val = getattr(pa, name)
                    if name == "today_sanity_point_cost":
                        raw_val = num.exact(raw_val)
                    encoded = _encode(name, raw_val)
                    if not _same(encoded, default):
                        sparse[name] = encoded
            if sparse or _raw(cid):
                working.put(str(cid), KEY, cast(core.JSON, sparse))
        vars(character).pop("pl_ability", None)
