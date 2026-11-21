"""
角色特殊状态标记：角色的键 chara.flags
====================================
值只存偏离默认值 DEFAULTS 的项：{标记名: bool 或 int}，没有这一项时各项均取默认值。
40 个标记分为 19 个布尔标记（默认 False）与 21 个整数标记（默认 0）。
写入整值替换这个键，值没变时不写；把标记设回默认值时从表里删去。
"""

from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Any, Literal, cast, overload

from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

KEY = "chara.flags"
""" 角色特殊状态标记在角色数据里的键 """

BoolFlag = Literal[
    "is_h",
    "sleep_h_awake",
    "wait_flag",
    "tired",
    "angry_with_player",
    "move_stop",
    "be_bagged",
    "imprisonment",
    "escaping",
    "sleep",
    "rest",
    "pee",
    "milk",
    "npc_masturebate_for_player",
    "find_food_weird",
    "work_maintenance",
    "go_to_join_group_sex",
    "see_pl_h",
    "see_h_reaction_settled",
]
""" 布尔型特殊标记名 """

IntFlag = Literal[
    "unconscious_h",
    "hidden_sex_mode",
    "condom_cloth_flag",
    "exhibitionism_sex_mode",
    "is_follow",
    "bagging_chara_id",
    "masturebate",
    "masturebate_before_sleep",
    "shower",
    "eat_food",
    "swim",
    "bathhouse_entertainment",
    "help_buy_food",
    "help_make_food",
    "morning_salutation",
    "night_salutation",
    "vistor",
    "aromatherapy",
    "field_commission",
    "in_diplomatic_visit",
    "sex_toy_level",
]
""" 整数型特殊标记名 """

BOOL_FLAGS: frozenset[str] = frozenset(
    {
        "is_h",
        "sleep_h_awake",
        "wait_flag",
        "tired",
        "angry_with_player",
        "move_stop",
        "be_bagged",
        "imprisonment",
        "escaping",
        "sleep",
        "rest",
        "pee",
        "milk",
        "npc_masturebate_for_player",
        "find_food_weird",
        "work_maintenance",
        "go_to_join_group_sex",
        "see_pl_h",
        "see_h_reaction_settled",
    }
)
""" 全部布尔型特殊标记集合 """

DEFAULTS: Mapping[str, bool | int] = {
    "is_h": False,
    "unconscious_h": 0,
    "hidden_sex_mode": 0,
    "condom_cloth_flag": 0,
    "exhibitionism_sex_mode": 0,
    "sleep_h_awake": False,
    "wait_flag": False,
    "is_follow": 0,
    "tired": False,
    "angry_with_player": False,
    "move_stop": False,
    "be_bagged": False,
    "bagging_chara_id": 0,
    "imprisonment": False,
    "escaping": False,
    "sleep": False,
    "rest": False,
    "pee": False,
    "milk": False,
    "masturebate": 0,
    "masturebate_before_sleep": 0,
    "npc_masturebate_for_player": False,
    "shower": 0,
    "eat_food": 0,
    "find_food_weird": False,
    "swim": 0,
    "bathhouse_entertainment": 0,
    "work_maintenance": False,
    "help_buy_food": 0,
    "help_make_food": 0,
    "morning_salutation": 0,
    "night_salutation": 0,
    "vistor": 0,
    "aromatherapy": 0,
    "field_commission": 0,
    "in_diplomatic_visit": 0,
    "go_to_join_group_sex": False,
    "see_pl_h": False,
    "see_h_reaction_settled": False,
    "sex_toy_level": 0,
}
""" 全部 40 项特殊标记与默认值 """

_EMPTY: Mapping[str, bool | int] = MappingProxyType({})
""" 空标记映射 """

working.register(KEY, {})


def of(
    cid: int, game: core.GameState | None = None
) -> Mapping[str, bool | int]:
    """
    返回角色已写入的非默认特殊标记映射（未出现的键均取 DEFAULTS 中的 False 或 0），不做拷贝，供热路径单次读取多项标记
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    Mapping -- 标记名到非默认值的只读映射
    """
    if game is not None:
        character = game.characters.get(str(cid))
        if character is not None:
            stored = character.data.get(KEY)
            if stored is None:
                return _EMPTY
            return cast(Mapping[str, bool | int], stored)
    return cast(Mapping[str, bool | int], working.get(str(cid), KEY, game))


def _raw(
    cid: int, game: core.GameState | None = None
) -> Mapping[str, bool | int]:
    return of(cid, game)


def _coerce(name: str, value: int) -> bool | int:
    if name not in DEFAULTS:
        raise KeyError(f"unknown flag {name!r}")
    return bool(value) if name in BOOL_FLAGS else int(value)


@overload
def get(
    cid: int, name: BoolFlag, game: core.GameState | None = None
) -> bool: ...


@overload
def get(cid: int, name: IntFlag, game: core.GameState | None = None) -> int: ...


@overload
def get(cid: int, name: str, game: core.GameState | None = None) -> int: ...


def get(cid: int, name: str, game: core.GameState | None = None) -> bool | int:
    """
    读角色的一项特殊标记
    Keyword arguments:
    cid -- 角色id
    name -- 标记名，不在 DEFAULTS 里报 KeyError
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    bool | int -- 标记值
    """
    default = DEFAULTS[name]
    return _raw(cid, game).get(name, default)


def set(cid: int, **values: int) -> None:
    """
    更新角色的一项或多项特殊标记，写进当前缓冲区。值未变时不写
    Keyword arguments:
    cid -- 角色id
    values -- 标记名到新值
    """
    if not values:
        return
    old = _raw(cid)
    new = dict(old)
    changed = False
    for name, raw_val in values.items():
        val = _coerce(name, raw_val)
        default = DEFAULTS[name]
        cur = old.get(name, default)
        if type(cur) is type(val) and cur == val:
            continue
        changed = True
        if val == default:
            new.pop(name, None)
        else:
            new[name] = val
    if changed:
        working.put(str(cid), KEY, cast(core.JSON, new))


def reset(cid: int) -> None:
    """
    把角色的全部特殊标记恢复为默认值，写进当前缓冲区
    Keyword arguments:
    cid -- 角色id
    """
    if _raw(cid):
        working.put(str(cid), KEY, {})


def snapshot(
    cid: int, game: core.GameState | None = None
) -> dict[str, bool | int]:
    """
    角色全部 40 项特殊标记的完整字典，供快照投影使用
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    dict -- 标记名到值
    """
    stored = _raw(cid, game)
    return {
        name: stored.get(name, default) for name, default in DEFAULTS.items()
    }


def copy_to(old_id: int, new_id: int) -> None:
    """
    角色替换时把 old_id 的特殊标记整份写到 new_id
    Keyword arguments:
    old_id -- 原角色id
    new_id -- 新角色id
    """
    stored = dict(_raw(old_id))
    if stored != dict(_raw(new_id)):
        working.put(str(new_id), KEY, cast(core.JSON, stored))


def remap(cids: Iterable[int], mapping: Mapping[int, int]) -> None:
    """
    角色换 id 时把所有角色标记里引用的 bagging_chara_id 按 mapping 改写
    Keyword arguments:
    cids -- 要检查的角色id集合
    mapping -- 原角色id到新角色id
    """
    for cid in cids:
        bagged = get(cid, "bagging_chara_id")
        if bagged and bagged in mapping:
            set(cid, bagging_chara_id=mapping[bagged])


def adopt_old_save(loaded_dict: dict[str, Any]) -> None:
    """
    读档时调用。把角色对象上携带的 sp_flag 写入 chara.flags（忽略 unnormal_flag），随后删掉该属性
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    """
    for cid, character in loaded_dict.get("character_data", {}).items():
        if "sp_flag" not in vars(character):
            continue
        sp = vars(character)["sp_flag"]
        if sp is not None:
            sparse: dict[str, bool | int] = {}
            for name, default in DEFAULTS.items():
                if hasattr(sp, name):
                    val = _coerce(name, getattr(sp, name))
                    if val != default:
                        sparse[name] = val
            if sparse or _raw(cid):
                working.put(str(cid), KEY, cast(core.JSON, sparse))
        vars(character).pop("sp_flag", None)
