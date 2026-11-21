"""
角色行动记录与时间戳：角色的键 chara.action_info
================================================
值只存偏离默认值的项：{字段名: JSON 值}，没有这一项时各项均取 ACTION_INFO() 的默认值。
13 项时间戳与 interacting_character_end_info[1]、两张社交时间字典里的时刻存成内核时钟分钟数；
公元 1 年占位时间（year <= 1）存成 None，读出时还原为 datetime.datetime(1, 1, 1)。
写入整值替换这个键，值没变时不写；恢复默认值的项从表里删去。
"""

import datetime
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Literal, cast, overload

from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

KEY = "chara.action_info"
""" 角色行动记录在角色数据里的键 """

SENTINEL = datetime.datetime(1, 1, 1)
""" 未设置时间戳的占位值 """

TimeField = Literal[
    "talk_time",
    "last_move_time",
    "last_training_time",
    "last_shower_time",
    "last_conscious_h_time",
    "last_unconscious_h_time",
    "sleep_time",
    "sleep_disturbed_end_time",
    "wake_time",
    "last_eaj_add_time",
    "check_out_time",
    "move_talk_time",
    "last_gift_time",
]
IntField = Literal[
    "talk_count",
    "h_interrupt",
    "follow_wait_time",
    "eat_food_restaurant",
    "health_check_today",
    "carry_chara_id",
]
BoolField = Literal[
    "ask_close_door_flag",
    "have_shown_waiting_in_now_instruct",
    "day_first_shoot_semen",
]

TIME_FIELDS: frozenset[str] = frozenset(
    {
        "talk_time",
        "last_move_time",
        "last_training_time",
        "last_shower_time",
        "last_conscious_h_time",
        "last_unconscious_h_time",
        "sleep_time",
        "sleep_disturbed_end_time",
        "wake_time",
        "last_eaj_add_time",
        "check_out_time",
        "move_talk_time",
        "last_gift_time",
    }
)
TIME_DICT_FIELDS: frozenset[str] = frozenset(
    {"social_contact_last_time", "social_contact_last_cut_down_time"}
)
_LIST_FIELDS: frozenset[str] = frozenset(
    {
        "plan_to_wake_time",
        "plan_to_sleep_time",
        "ask_group_sex_refuse_chara_id_list",
        "find_another_toilet",
    }
)

_DEFAULTS: Mapping[str, core.JSON] = {
    "talk_count": 0,
    "talk_time": None,
    "last_move_time": None,
    "last_training_time": None,
    "last_shower_time": None,
    "last_conscious_h_time": None,
    "last_unconscious_h_time": None,
    "social_contact_last_time": {},
    "sleep_time": None,
    "sleep_disturbed_end_time": None,
    "plan_to_wake_time": (6, 0),
    "plan_to_sleep_time": (18, 0),
    "wake_time": None,
    "social_contact_last_cut_down_time": {},
    "h_interrupt": 0,
    "follow_wait_time": 0,
    "last_eaj_add_time": None,
    "check_out_time": None,
    "eat_food_restaurant": -1,
    "ask_group_sex_refuse_chara_id_list": (),
    "ask_close_door_flag": False,
    "move_talk_time": None,
    "have_shown_waiting_in_now_instruct": False,
    "health_check_today": 0,
    "interacting_character_end_info": (-1, None),
    "past_move_position_list": (),
    "last_gift_time": None,
    "day_first_shoot_semen": True,
    "find_another_toilet": (),
    "carry_chara_id": 0,
}
""" 全部 30 项字段的编码默认值 """

FIELDS: frozenset[str] = frozenset(_DEFAULTS)
working.register(KEY, {})


def _encode_dt(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        return None if value.year <= 1 else game_time.minutes(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise TypeError(f"expected datetime, got {value!r}")


def _decode_dt(value: core.JSON) -> datetime.datetime:
    return SENTINEL if value is None else game_time.at(cast(int, value))


def _encode_field(name: str, value: Any) -> core.JSON:
    if name not in _DEFAULTS:
        raise KeyError(f"unknown action_info field {name!r}")
    if name in TIME_FIELDS:
        return _encode_dt(value)
    if name in TIME_DICT_FIELDS:
        return {
            str(int(k)): _encode_dt(v)
            for k, v in cast(Mapping[Any, Any], value).items()
        }
    if name == "interacting_character_end_info":
        seq = cast(Sequence[Any], value)
        return (int(seq[0]), _encode_dt(seq[1]))
    if name == "past_move_position_list":
        return tuple(
            tuple(str(part) for part in scene)
            for scene in cast(Sequence[Sequence[Any]], value)
        )
    if name in ("plan_to_wake_time", "plan_to_sleep_time"):
        seq = cast(Sequence[Any], value)
        return (int(seq[0]), int(seq[1]))
    if name == "ask_group_sex_refuse_chara_id_list":
        return tuple(int(x) for x in cast(Sequence[Any], value))
    if name == "find_another_toilet":
        return tuple(str(x) for x in cast(Sequence[Any], value))
    if isinstance(_DEFAULTS[name], bool):
        return bool(value)
    return int(value)


def _decode_field(name: str, raw: core.JSON) -> Any:
    if name in TIME_FIELDS:
        return _decode_dt(raw)
    if name in TIME_DICT_FIELDS:
        return {
            int(k): _decode_dt(v)
            for k, v in cast(Mapping[str, core.JSON], raw).items()
        }
    if name == "interacting_character_end_info":
        seq = cast(Sequence[core.JSON], raw)
        return [cast(int, seq[0]), _decode_dt(seq[1])]
    if name == "past_move_position_list":
        return [list(scene) for scene in cast(Sequence[Sequence[str]], raw)]
    if name in _LIST_FIELDS:
        return list(cast(Sequence[Any], raw))
    return raw


def _raw(
    cid: int, game: core.GameState | None = None
) -> Mapping[str, core.JSON]:
    return cast(Mapping[str, core.JSON], working.get(str(cid), KEY, game))


@overload
def get(
    cid: int, name: TimeField, game: core.GameState | None = None
) -> datetime.datetime: ...


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
    name: Literal[
        "plan_to_wake_time",
        "plan_to_sleep_time",
        "ask_group_sex_refuse_chara_id_list",
    ],
    game: core.GameState | None = None,
) -> list[int]: ...


@overload
def get(
    cid: int,
    name: Literal["find_another_toilet"],
    game: core.GameState | None = None,
) -> list[str]: ...


@overload
def get(
    cid: int,
    name: Literal["past_move_position_list"],
    game: core.GameState | None = None,
) -> list[list[str]]: ...


@overload
def get(
    cid: int,
    name: Literal["interacting_character_end_info"],
    game: core.GameState | None = None,
) -> list[Any]: ...


@overload
def get(
    cid: int,
    name: Literal[
        "social_contact_last_time", "social_contact_last_cut_down_time"
    ],
    game: core.GameState | None = None,
) -> dict[int, datetime.datetime]: ...


@overload
def get(cid: int, name: str, game: core.GameState | None = None) -> Any: ...


def get(cid: int, name: str, game: core.GameState | None = None) -> Any:
    """读角色行动记录的一项，容器交回新副本"""
    default = _DEFAULTS[name]
    return _decode_field(name, _raw(cid, game).get(name, default))


def _same(a: core.JSON, b: core.JSON) -> bool:
    if isinstance(a, Mapping) and isinstance(b, Mapping):
        return len(a) == len(b) and all(
            k in b and _same(v, b[k]) for k, v in a.items()
        )
    if isinstance(a, tuple) and isinstance(b, tuple):
        return len(a) == len(b) and all(
            _same(x, y) for x, y in zip(a, b, strict=True)
        )
    return type(a) is type(b) and a == b


def update(cid: int, **values: Any) -> None:
    """更新角色行动记录的一项或多项，写进当前缓冲区。值未变时不写"""
    if not values:
        return
    old = _raw(cid)
    new = dict(old)
    changed = False
    for name, val in values.items():
        encoded = _encode_field(name, val)
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


def set(cid: int, name: str, value: Any) -> None:
    """把角色行动记录的 name 项设为 value，写进当前缓冲区"""
    update(cid, **{name: value})


def add(cid: int, name: str, by: int) -> None:
    """给整数字段加 by，写进当前缓冲区"""
    set(cid, name, int(get(cid, name)) + by)


def set_plan_time(cid: int, name: str, index: int, value: int) -> None:
    """修改计划起床或睡觉时间的时或分，写进当前缓冲区"""
    pair = list(cast(Sequence[int], get(cid, name)))
    pair[index] = value
    set(cid, name, pair)


def record_move(cid: int, scene: Sequence[str], limit: int = 10) -> None:
    """把离开的场景记到移动历史末尾；与末条相同时不记，超过 limit 条时删去最早一条"""
    history = get(cid, "past_move_position_list")
    entry = list(scene)
    if history and history[-1] == entry:
        return
    history.append(entry)
    if len(history) > limit:
        history.pop(0)
    set(cid, "past_move_position_list", history)


def pop_past_move(cid: int, index: int = -1) -> list[str]:
    """弹出移动历史里指定下标的一条并返回它"""
    history = get(cid, "past_move_position_list")
    item = history.pop(index)
    set(cid, "past_move_position_list", history)
    return item


def init_zero(cid: int) -> None:
    """按开局时间初始化角色的行动记录"""
    now = game_time.now()
    prev = game_time.get_sub_date(day=-1) if now.day != 1 else now
    raw_map: dict[str, int | None] = {
        "talk_time": _encode_dt(now),
        "last_move_time": _encode_dt(now),
        "last_training_time": _encode_dt(prev),
        "last_shower_time": _encode_dt(prev),
        "wake_time": _encode_dt(now),
        "sleep_time": _encode_dt(now),
    }
    sparse: dict[str, core.JSON] = {
        k: v for k, v in raw_map.items() if v is not None
    }
    if dict(_raw(cid)) != sparse:
        working.put(str(cid), KEY, cast(core.JSON, sparse))


def snapshot(cid: int, game: core.GameState | None = None) -> dict[str, Any]:
    """角色全部 30 项行动记录的完整字典，供快照投影使用"""
    stored = _raw(cid, game)
    return {
        name: _decode_field(name, stored.get(name, default))
        for name, default in _DEFAULTS.items()
    }


def copy_to(old_id: int, new_id: int) -> None:
    """角色替换时把 old_id 的行动记录整份写到 new_id"""
    stored = dict(_raw(old_id))
    if stored != dict(_raw(new_id)):
        working.put(str(new_id), KEY, cast(core.JSON, stored))


def remap(cids: Iterable[int], mapping: Mapping[int, int]) -> None:
    """角色换 id 时把行动记录里引用的角色 id 按 mapping 改写"""
    moved = {k: v for k, v in mapping.items() if k != v}
    if not moved:
        return
    for cid in cids:
        if not _raw(cid):
            continue
        updates: dict[str, Any] = {}
        refuse = get(cid, "ask_group_sex_refuse_chara_id_list")
        if refuse:
            new_refuse = [moved.get(oid, oid) for oid in refuse]
            if new_refuse != refuse:
                updates["ask_group_sex_refuse_chara_id_list"] = new_refuse
        for field in TIME_DICT_FIELDS:
            table = cast(dict[int, datetime.datetime], get(cid, field))
            if table and any(k in moved for k in table):
                new_table = {k: v for k, v in table.items() if k not in moved}
                for old_id, new_id in moved.items():
                    if old_id in table:
                        new_table[new_id] = table[old_id]
                updates[field] = new_table
        end_info = get(cid, "interacting_character_end_info")
        if end_info[0] != -1 and end_info[0] in moved:
            updates["interacting_character_end_info"] = [
                moved[end_info[0]],
                end_info[1],
            ]
        if updates:
            update(cid, **updates)


def adopt_old_save(loaded_dict: dict[str, Any]) -> None:
    """读档时把角色对象上携带的 action_info 写入 chara.action_info，随后删掉该属性"""
    for cid, character in loaded_dict.get("character_data", {}).items():
        if "action_info" not in vars(character):
            continue
        info = vars(character)["action_info"]
        if info is not None:
            sparse: dict[str, core.JSON] = {}
            for name, default in _DEFAULTS.items():
                if hasattr(info, name):
                    encoded = _encode_field(name, getattr(info, name))
                    if not (
                        type(encoded) is type(default) and encoded == default
                    ):
                        sparse[name] = encoded
            if sparse or _raw(cid):
                working.put(str(cid), KEY, cast(core.JSON, sparse))
        vars(character).pop("action_info", None)
