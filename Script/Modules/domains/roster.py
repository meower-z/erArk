"""
在编名册、禁用名单与已用干员姓名：全局键 roster.active、roster.forbidden 与 roster.names
=====================================================================================
roster.active 存按角色 id 升序排列的在编干员元组（原 Cache.npc_id_got）。
roster.forbidden 存按角色 id 升序排列的禁用角色元组（原 Cache.forbidden_npc_id），新周目沿用。
roster.names 存按字典序排列的已用干员姓名元组（原 Cache.npc_name_data），新周目沿用。
三个键缺省时均读空元组，写入整值替换对应键，值未变时不写。
101（婴儿）与 102（幼女）阶段的角色禁止进入在编名册，由 require_eligible 统一把关。
"""

from collections.abc import Collection, Iterable, Mapping
from typing import Any, NewType, cast

from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

ActiveNpcId = NewType("ActiveNpcId", int)
""" 通过成长阶段边界校验、允许进入在编名册的角色 id """

ACTIVE = "roster.active"
""" 在编干员名单在全局数据里的键 """
FORBIDDEN = "roster.forbidden"
""" 禁用干员名单在全局数据里的键 """
NAMES = "roster.names"
""" 已用干员姓名在全局数据里的键 """
KEYS = (ACTIVE, FORBIDDEN, NAMES)
""" 本模块拥有的全部键 """

PICKLED_TYPES: Mapping[str, type] = {
    "npc_id_got": set,
    "forbidden_npc_id": set,
    "npc_name_data": set,
}
""" 版本 18 之前的存档里，旧缓存上三项名册属性名与应有类型 """

working.register(ACTIVE, ())
working.register(FORBIDDEN, ())
working.register(NAMES, ())


def require_eligible(
    cid: int, characters: Mapping[int, Any] | None = None
) -> ActiveNpcId:
    """
    校验角色是否允许进入在编名册与内核角色表，101/102 阶段角色或非法 id 报 ValueError
    Keyword arguments:
    cid -- 角色 id
    characters -- 给出时按这份角色表检查 101/102 阶段（读档未覆盖缓存时使用），缺省查当前缓存
    Return arguments:
    ActiveNpcId -- 通过校验的角色 id
    """
    if type(cid) is not int or cid < 0:
        raise ValueError(f"非法的名册角色 id：{cid!r}")
    if cid != 0:
        from Script.Design import child_stage_gate

        if characters is not None:
            chara = characters.get(cid)
            if chara is not None:
                from Script.Modules.domains import abilities

                talent: Any = getattr(chara, "talent", None)
                if not isinstance(talent, Mapping):
                    talent = abilities.talent(cid)
                if any(
                    talent.get(tid, 0)
                    for tid in child_stage_gate.CHILD_STAGE_TALENTS
                ):
                    raise ValueError(f"101/102 阶段角色 {cid} 不能进入在编名册")
        elif child_stage_gate.is_child_stage(cid):
            raise ValueError(f"101/102 阶段角色 {cid} 不能进入在编名册")
    return ActiveNpcId(cid)


def active_sorted(game: core.GameState | None = None) -> tuple[int, ...]:
    """
    按角色 id 升序排列的在编名单只读元组
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    tuple[int, ...] -- 升序唯一的角色 id 元组
    """
    return cast(tuple[int, ...], working.get(None, ACTIVE, game))


def active(game: core.GameState | None = None) -> set[int]:
    """
    在编名单的集合副本
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    set[int] -- 在编角色 id 集合
    """
    return set(active_sorted(game))


def has(cid: int, game: core.GameState | None = None) -> bool:
    """
    角色是否在在编名单里
    Keyword arguments:
    cid -- 角色 id
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    bool -- 在编为 True
    """
    return cid in active_sorted(game)


def count(game: core.GameState | None = None) -> int:
    """
    在编名单人数
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    int -- 人数
    """
    return len(active_sorted(game))


def set_active(
    cids: Iterable[int], *, characters: Mapping[int, Any] | None = None
) -> None:
    """
    整表替换在编名单，逐项校验 101/102 禁入边界，按升序去重后写入
    Keyword arguments:
    cids -- 新的角色 id 序列
    characters -- 给出时按这份角色表检查 101/102 阶段
    """
    validated = tuple(
        sorted({int(require_eligible(cid, characters)) for cid in cids})
    )
    if validated != active_sorted():
        working.put(None, ACTIVE, cast(core.JSON, validated))


def add(cid: int) -> None:
    """
    把一名通过边界校验的角色加入在编名单
    Keyword arguments:
    cid -- 角色 id
    """
    checked = int(require_eligible(cid))
    current = active_sorted()
    if checked in current:
        return
    working.put(
        None, ACTIVE, cast(core.JSON, tuple(sorted((*current, checked))))
    )


def remove(cid: int) -> None:
    """
    从在编名单移除角色，不在名单里时报 KeyError
    Keyword arguments:
    cid -- 角色 id
    """
    current = active_sorted()
    if cid not in current:
        raise KeyError(cid)
    updated = tuple(item for item in current if item != cid)
    working.put(None, ACTIVE, cast(core.JSON, updated))


def discard(cid: int) -> None:
    """
    若角色在在编名单里则移除，不在时什么也不做
    Keyword arguments:
    cid -- 角色 id
    """
    current = active_sorted()
    if cid not in current:
        return
    updated = tuple(item for item in current if item != cid)
    working.put(None, ACTIVE, cast(core.JSON, updated))


def drop_active(cids: Collection[int]) -> int:
    """
    从在编名单批量移除 cids 中的角色，返回实际移除人数
    Keyword arguments:
    cids -- 要移除的角色 id 集合
    Return arguments:
    int -- 实际移除人数
    """
    if not cids:
        return 0
    current = active_sorted()
    drop = set(cids)
    updated = tuple(item for item in current if item not in drop)
    removed = len(current) - len(updated)
    if removed:
        working.put(None, ACTIVE, cast(core.JSON, updated))
    return removed


def clear_active() -> None:
    """清空在编名单"""
    if active_sorted():
        working.put(None, ACTIVE, ())


def forbidden(game: core.GameState | None = None) -> set[int]:
    """
    禁用角色 id 集合副本
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    set[int] -- 禁用角色 id 集合
    """
    return set(cast(tuple[int, ...], working.get(None, FORBIDDEN, game)))


def is_forbidden(cid: int, game: core.GameState | None = None) -> bool:
    """
    角色是否在禁用名单里
    Keyword arguments:
    cid -- 角色 id
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    bool -- 禁用为 True
    """
    return cid in cast(tuple[int, ...], working.get(None, FORBIDDEN, game))


def set_forbidden(cids: Iterable[int]) -> None:
    """
    整表替换禁用名单
    Keyword arguments:
    cids -- 新的禁用角色 id 序列
    """
    normalized = tuple(sorted({int(cid) for cid in cids}))
    if normalized != cast(tuple[int, ...], working.get(None, FORBIDDEN)):
        working.put(None, FORBIDDEN, cast(core.JSON, normalized))


def forbid(cid: int) -> None:
    """把角色加入禁用名单"""
    current = cast(tuple[int, ...], working.get(None, FORBIDDEN))
    if cid in current:
        return
    working.put(
        None, FORBIDDEN, cast(core.JSON, tuple(sorted((*current, cid))))
    )


def unforbid(cid: int) -> None:
    """从禁用名单移除角色"""
    current = cast(tuple[int, ...], working.get(None, FORBIDDEN))
    if cid not in current:
        return
    updated = tuple(item for item in current if item != cid)
    working.put(None, FORBIDDEN, cast(core.JSON, updated))


def names(game: core.GameState | None = None) -> set[str]:
    """
    已用干员姓名集合副本
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    set[str] -- 已用姓名集合
    """
    return set(cast(tuple[str, ...], working.get(None, NAMES, game)))


def has_name(name: str, game: core.GameState | None = None) -> bool:
    """
    姓名是否已被使用
    Keyword arguments:
    name -- 角色名
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    bool -- 已用为 True
    """
    return name in cast(tuple[str, ...], working.get(None, NAMES, game))


def set_names(values: Iterable[str]) -> None:
    """
    整表替换已用干员姓名
    Keyword arguments:
    values -- 姓名序列
    """
    normalized = tuple(sorted({str(name) for name in values}))
    if normalized != cast(tuple[str, ...], working.get(None, NAMES)):
        working.put(None, NAMES, cast(core.JSON, normalized))


def add_name(name: str) -> None:
    """登记一个已用干员姓名"""
    current = cast(tuple[str, ...], working.get(None, NAMES))
    if name in current:
        return
    working.put(None, NAMES, cast(core.JSON, tuple(sorted((*current, name)))))


def remap(
    old_to_new: Mapping[int, int],
    *,
    characters: Mapping[int, Any] | None = None,
) -> None:
    """
    角色换号时重映射在编名单与禁用名单里的角色 id
    Keyword arguments:
    old_to_new -- 旧 id 到新 id 的映射
    characters -- 给出时按这份角色表检查 101/102 阶段
    """
    if not old_to_new:
        return
    cur_active = active_sorted()
    if any(cid in old_to_new for cid in cur_active):
        set_active(
            (old_to_new.get(cid, cid) for cid in cur_active),
            characters=characters,
        )
    cur_forbidden = cast(tuple[int, ...], working.get(None, FORBIDDEN))
    if any(cid in old_to_new for cid in cur_forbidden):
        set_forbidden(old_to_new.get(cid, cid) for cid in cur_forbidden)


def adopt_old_save(loaded_dict: dict[str, Any], version: int) -> int:
    """
    读档时调用。从旧缓存字典里删掉 PICKLED_TYPES 中的三项属性，类型相符的值写进当前缓冲区。
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    version -- 存档版本，旧存档为 0
    Return arguments:
    int -- 版本 18 之前的存档里缺了或类型不符的属性个数，版本 18 及以后为 0
    """
    found: dict[str, Any] = {
        name: loaded_dict.pop(name)
        for name in PICKLED_TYPES
        if name in loaded_dict
    }
    kept: dict[str, Any] = {
        name: val
        for name, val in found.items()
        if type(val) is PICKLED_TYPES[name]
    }
    if "npc_id_got" in kept:
        chars = loaded_dict.get("character_data")
        set_active(
            kept["npc_id_got"],
            characters=chars if isinstance(chars, Mapping) else None,
        )
    if "forbidden_npc_id" in kept:
        set_forbidden(kept["forbidden_npc_id"])
    if "npc_name_data" in kept:
        set_names(kept["npc_name_data"])
    return len(PICKLED_TYPES) - len(kept) if version < 18 else 0
