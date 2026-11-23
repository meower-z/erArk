"""
玩家收藏品：角色的键 player.collection
======================================
值只存偏离默认值的项：{字段名: JSON 值}，没有这一项时各项均取 PLAYER_COLLECTION() 的默认值。
字典里的角色id、奖励id、卵id 键在 JSON 中存为字符串，读出时还原为 int。
held_eggs 的值为 (角色id, 卵编号) 二元组；soft_eggs 里的 lay_time 存为内核时钟分钟数（公元 1 年存 None）。
写入整值替换这个键，值没变时不写；恢复默认值的项从表里删去。
"""

import datetime
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, cast

from Script.Config import game_config
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import npc_template
from Script.Modules.gameplay_resolution import working

KEY = "player.collection"
""" 玩家收藏品在角色数据里的键 """

SENTINEL = datetime.datetime(1, 1, 1)
""" 未设置时间戳的占位值 """

_DEFAULTS: Mapping[str, core.JSON] = {
    "collection_bonus": {},
    "token_list": {},
    "first_panties": {},
    "npc_panties": {},
    "npc_panties_tem": {},
    "npc_socks": {},
    "npc_socks_tem": {},
    "eqip_token": (1, ()),
    "milk_total": {},
    "urine_total": {},
    "used_condoms": (),
    "held_eggs": {},
    "next_held_egg_id": 0,
    "soft_eggs": {},
    "next_soft_egg_id": 0,
}
FIELDS: frozenset[str] = frozenset(_DEFAULTS)

_LIST_MAP_STR = frozenset({"npc_panties", "npc_socks"})
_LIST_MAP_INT = frozenset({"npc_panties_tem", "npc_socks_tem"})
_SCALAR_MAP_BOOL = frozenset({"collection_bonus", "token_list"})
_SCALAR_MAP_INT = frozenset({"milk_total", "urine_total"})
_NPC_KEYED_MAPS = (
    "token_list",
    "first_panties",
    "npc_panties",
    "npc_socks",
    "npc_panties_tem",
    "npc_socks_tem",
    "milk_total",
    "urine_total",
)

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


def _encode_soft_egg(egg: Mapping[str, Any]) -> dict[str, core.JSON]:
    semen = egg.get("semen_count", 0.0)
    return {
        "mother_id": int(egg["mother_id"]),
        "lay_time": _encode_dt(egg.get("lay_time")),
        "position": tuple(str(p) for p in egg.get("position", ())),
        "semen_count": (
            semen
            if isinstance(semen, (int, float)) and not isinstance(semen, bool)
            else float(semen)
        ),
    }


def _decode_soft_egg(raw: Mapping[str, core.JSON]) -> dict[str, Any]:
    return {
        "mother_id": cast(int, raw["mother_id"]),
        "lay_time": _decode_dt(raw.get("lay_time")),
        "position": list(cast(Sequence[str], raw.get("position", ()))),
        "semen_count": raw.get("semen_count", 0.0),
    }


def _encode(name: str, value: Any) -> core.JSON:
    if name not in _DEFAULTS:
        raise KeyError(f"unknown player_collection field {name!r}")
    if name in _SCALAR_MAP_BOOL:
        return {str(int(k)): bool(v) for k, v in value.items()}
    if name == "first_panties":
        return {str(int(k)): str(v) for k, v in value.items()}
    if name in _LIST_MAP_STR:
        return {str(int(k)): tuple(str(x) for x in v) for k, v in value.items()}
    if name in _LIST_MAP_INT:
        return {str(int(k)): tuple(int(x) for x in v) for k, v in value.items()}
    if name == "eqip_token":
        return (int(value[0]), tuple(int(x) for x in value[1]))
    if name in _SCALAR_MAP_INT:
        return {str(int(k)): int(v) for k, v in value.items()}
    if name == "used_condoms":
        return tuple(int(x) for x in value)
    if name == "held_eggs":
        return {str(int(k)): (int(v[0]), int(v[1])) for k, v in value.items()}
    if name == "soft_eggs":
        return {str(int(k)): _encode_soft_egg(v) for k, v in value.items()}
    return int(value)


def _decode(name: str, raw: core.JSON) -> Any:
    if (
        name in _SCALAR_MAP_BOOL
        or name in _SCALAR_MAP_INT
        or name == "first_panties"
    ):
        return {int(k): v for k, v in cast(Mapping[str, Any], raw).items()}
    if name in _LIST_MAP_STR or name in _LIST_MAP_INT:
        return {
            int(k): list(v)
            for k, v in cast(Mapping[str, Sequence[Any]], raw).items()
        }
    if name == "eqip_token":
        seq = cast(Sequence[Any], raw)
        return [int(seq[0]), list(cast(Sequence[int], seq[1]))]
    if name == "used_condoms":
        return list(cast(Sequence[int], raw))
    if name == "held_eggs":
        return {
            int(k): (int(v[0]), int(v[1]))
            for k, v in cast(Mapping[str, Sequence[int]], raw).items()
        }
    if name == "soft_eggs":
        return {
            int(k): _decode_soft_egg(v)
            for k, v in cast(Mapping[str, Mapping[str, core.JSON]], raw).items()
        }
    return raw


def _raw(
    cid: int = 0, game: core.GameState | None = None
) -> Mapping[str, core.JSON]:
    return cast(Mapping[str, core.JSON], working.get(str(cid), KEY, game))


def get(name: str, cid: int = 0, game: core.GameState | None = None) -> Any:
    """读收藏品的一项，容器返回新副本"""
    default = _DEFAULTS[name]
    return _decode(name, _raw(cid, game).get(name, default))


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


def update(cid: int = 0, **values: Any) -> None:
    """更新收藏品的一项或多项，写进当前缓冲区。值未变时不写"""
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


def put(name: str, value: Any, cid: int = 0) -> None:
    """替换收藏品的一项，写进当前缓冲区"""
    update(cid, **{name: value})


def bonus(bonus_id: int, cid: int = 0) -> bool:
    """一项收集解锁奖励是否已获得"""
    raw = cast(Mapping[str, bool], _raw(cid).get("collection_bonus", {}))
    return bool(raw.get(str(bonus_id), False))


def set_bonus(bonus_id: int, value: bool = True, cid: int = 0) -> None:
    """设置一项收集解锁奖励"""
    table = cast(dict[int, bool], get("collection_bonus", cid))
    table[bonus_id] = value
    put("collection_bonus", table, cid)


def has_soft_eggs(cid: int = 0) -> bool:
    """当前是否存在体外无壳卵"""
    return bool(_raw(cid).get("soft_eggs"))


def init_zero(cid: int = 0) -> None:
    """按当前配置与角色模板初始化收藏品"""
    npcs = tuple(npc_template.ids())
    sparse: dict[str, core.JSON] = {}
    for name, val in (
        (
            "collection_bonus",
            {bid: False for bid in game_config.config_collection_bonus_data},
        ),
        ("token_list", {adv: False for adv in npcs}),
        ("first_panties", {adv: "" for adv in npcs}),
        ("npc_panties", {adv: [] for adv in npcs}),
        ("npc_socks", {adv: [] for adv in npcs}),
    ):
        encoded = _encode(name, val)
        if encoded != _DEFAULTS[name]:
            sparse[name] = encoded
    if dict(_raw(cid)) != sparse:
        working.put(str(cid), KEY, cast(core.JSON, sparse))


def ensure_npc(npc_id: int, cid: int = 0) -> bool:
    """确认 npc_id 已在四张干员藏品表里；缺失时补空条目并返回 True"""
    raw_tokens = _raw(cid).get("token_list")
    if isinstance(raw_tokens, Mapping) and str(npc_id) in raw_tokens:
        return False
    set_npc_entries(npc_id, cid)
    return True


def set_npc_entries(npc_id: int, cid: int = 0) -> None:
    """把 npc_id 在四张干员藏品表里的条目设为初始空值"""
    tokens = cast(dict[int, bool], get("token_list", cid))
    first = cast(dict[int, str], get("first_panties", cid))
    panties = cast(dict[int, list[str]], get("npc_panties", cid))
    socks = cast(dict[int, list[str]], get("npc_socks", cid))
    tokens[npc_id], first[npc_id] = False, ""
    panties[npc_id], socks[npc_id] = [], []
    update(
        cid,
        token_list=tokens,
        first_panties=first,
        npc_panties=panties,
        npc_socks=socks,
    )


def set_token(npc_id: int, value: bool = True, cid: int = 0) -> None:
    """记录获得或取消一名干员的信物"""
    tokens = cast(dict[int, bool], get("token_list", cid))
    tokens[npc_id] = value
    put("token_list", tokens, cid)


def set_first_panty(npc_id: int, text: str, cid: int = 0) -> None:
    """记录一名干员的处子血内裤文本"""
    first = cast(dict[int, str], get("first_panties", cid))
    first[npc_id] = text
    put("first_panties", first, cid)


def append_list_map(name: str, npc_id: int, item: Any, cid: int = 0) -> None:
    """向内裤或袜子映射表的 npc_id 列表末尾追加一项"""
    extend_list_map(name, ((npc_id, item),), cid)


def extend_list_map(
    name: str, items: Iterable[tuple[int, Any]], cid: int = 0
) -> None:
    """
    批量向内裤或袜子映射表追加条目，只读表一次并调用 put 写回一次
    Keyword arguments:
    name -- 收藏品列表映射字段名（内裤或袜子映射表）
    items -- (干员id, 追加项) 二元组的可迭代对象，干员键不存在时先建空列表再按顺序追加
    cid -- 收藏品所属角色id，默认 0
    """
    table = cast(dict[int, list[Any]], get(name, cid))
    for npc_id, item in items:
        table.setdefault(npc_id, []).append(item)
    put(name, table, cid)


def set_list_map_entry(
    name: str, npc_id: int, items: Sequence[Any], cid: int = 0
) -> None:
    """替换内裤或袜子映射表里 npc_id 的列表"""
    table = cast(dict[int, list[Any]], get(name, cid))
    table[npc_id] = list(items)
    put(name, table, cid)


def add_total(name: str, npc_id: int, amount: int, cid: int = 0) -> None:
    """累加 milk_total 或 urine_total 中指定干员的收集量"""
    table = cast(dict[int, int], get(name, cid))
    table[npc_id] = table.get(npc_id, 0) + amount
    put(name, table, cid)


def set_eqip_token(limit: int, equipped: Sequence[int], cid: int = 0) -> None:
    """设置信物装备上限与已装备干员id列表"""
    put("eqip_token", [limit, list(equipped)], cid)


def append_used_condom(amount: int, cid: int = 0) -> None:
    """向用过的避孕套池追加一份精液量"""
    items = cast(list[int], get("used_condoms", cid))
    items.append(amount)
    put("used_condoms", items, cid)


def clear_used_condoms(cid: int = 0) -> None:
    """清空用过的避孕套池"""
    put("used_condoms", [], cid)


def add_held_egg(mother_id: int, egg_id: int, cid: int = 0) -> int:
    """登记一枚玩家临时持有的未鉴定卵索引，返回分配的持有编号"""
    held = cast(dict[int, tuple[int, int]], get("held_eggs", cid))
    held_id = cast(int, get("next_held_egg_id", cid))
    held[held_id] = (mother_id, egg_id)
    update(cid, held_eggs=held, next_held_egg_id=held_id + 1)
    return held_id


def add_soft_egg(
    mother_id: int,
    lay_time: datetime.datetime,
    position: Sequence[str],
    semen_count: float,
    cid: int = 0,
) -> int:
    """登记一枚体外无壳卵，返回分配的卵编号"""
    eggs = cast(dict[int, dict[str, Any]], get("soft_eggs", cid))
    egg_id = cast(int, get("next_soft_egg_id", cid))
    eggs[egg_id] = {
        "mother_id": mother_id,
        "lay_time": lay_time,
        "position": list(position),
        "semen_count": float(semen_count),
    }
    update(cid, soft_eggs=eggs, next_soft_egg_id=egg_id + 1)
    return egg_id


def add_soft_egg_semen(egg_id: int, amount: int, cid: int = 0) -> None:
    """向体外无壳卵追加精液量"""
    eggs = cast(dict[int, dict[str, Any]], get("soft_eggs", cid))
    if egg_id not in eggs:
        return
    eggs[egg_id]["semen_count"] = max(eggs[egg_id]["semen_count"] + amount, 0)
    put("soft_eggs", eggs, cid)


def remove_soft_egg(egg_id: int, cid: int = 0) -> None:
    """删去一枚体外无壳卵"""
    eggs = cast(dict[int, dict[str, Any]], get("soft_eggs", cid))
    if egg_id in eggs:
        del eggs[egg_id]
        put("soft_eggs", eggs, cid)


def carry_for_new_round(game: core.GameState) -> dict[str, core.JSON]:
    """读出新周目继承所需的玩家内裤与袜子收藏（已编码为 JSON）"""
    stored = _raw(0, game)
    return {
        "npc_panties": stored.get("npc_panties", {}),
        "npc_socks": stored.get("npc_socks", {}),
    }


def snapshot(cid: int, game: core.GameState | None = None) -> dict[str, Any]:
    """全部 15 项收藏品的完整字典，供快照投影使用"""
    stored = _raw(cid, game)
    return {
        name: _decode(name, stored.get(name, default))
        for name, default in _DEFAULTS.items()
    }


def copy_to(old_id: int, new_id: int) -> None:
    """角色替换时把 old_id 的收藏品整份写到 new_id"""
    stored = dict(_raw(old_id))
    if stored != dict(_raw(new_id)):
        working.put(str(new_id), KEY, cast(core.JSON, stored))


def remap(cids: Iterable[int], mapping: Mapping[int, int]) -> None:
    """角色换 id 时把收藏品里引用的干员 id 按 mapping 改写"""
    moved = {k: v for k, v in mapping.items() if k != v}
    if not moved:
        return
    for cid in cids:
        if not _raw(cid):
            continue
        updates: dict[str, Any] = {}
        for field in _NPC_KEYED_MAPS:
            table = cast(dict[int, Any], get(field, cid))
            if not table or not any(k in moved for k in table):
                continue
            new_table = {k: v for k, v in table.items() if k not in moved}
            for old_id, new_id in moved.items():
                if old_id in table:
                    new_table[new_id] = table[old_id]
            updates[field] = new_table
        eqip = cast(list[Any], get("eqip_token", cid))
        if len(eqip) > 1 and eqip[1]:
            new_list = [moved.get(oid, oid) for oid in eqip[1]]
            if new_list != eqip[1]:
                updates["eqip_token"] = [eqip[0], new_list]
        held = cast(dict[int, tuple[int, int]], get("held_eggs", cid))
        if held:
            new_held = {h: (moved.get(m, m), e) for h, (m, e) in held.items()}
            if new_held != held:
                updates["held_eggs"] = new_held
        soft = cast(dict[int, dict[str, Any]], get("soft_eggs", cid))
        if soft and any(egg["mother_id"] in moved for egg in soft.values()):
            for egg in soft.values():
                egg["mother_id"] = moved.get(egg["mother_id"], egg["mother_id"])
            updates["soft_eggs"] = soft
        if updates:
            update(cid, **updates)


def adopt_old_save(loaded_dict: dict[str, Any]) -> None:
    """读档时把角色对象上携带的 pl_collection 写入 player.collection，随后删掉该属性"""
    for cid, character in loaded_dict.get("character_data", {}).items():
        if "pl_collection" not in vars(character):
            continue
        pc = vars(character)["pl_collection"]
        if pc is not None:
            sparse: dict[str, core.JSON] = {}
            for name, default in _DEFAULTS.items():
                if hasattr(pc, name):
                    encoded = _encode(name, getattr(pc, name))
                    if not (
                        type(encoded) is type(default) and encoded == default
                    ):
                        sparse[name] = encoded
            if sparse or _raw(cid):
                working.put(str(cid), KEY, cast(core.JSON, sparse))
        vars(character).pop("pl_collection", None)
