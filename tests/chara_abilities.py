# -*- coding: UTF-8 -*-
"""
测试读写角色的能力、经验、宝珠与素质表
====================================
- ability、experience、juel、talent 按角色id或角色对象交回角色的一张表。
  在一步、玩家选择或缓冲区里写时，写入记进当前缓冲区。不在这些里时，写入经 kernel_data.writing 套用到内核状态上。
- zero_tables 把角色的四张表换成置零函数给的整表。
- auto_commit_outside_step 让游戏代码在一步之外对这四个键的写入同样套用到内核状态上，
  tests/education/_bootstrap.py 调用它，教育区测试因此能在一步之外直接调用结算。
- project 在快照里用 abilities.PICKLED 的属性名记下这四张表，名字为 chara.<id>.ability.<编号> 等。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any
from tests.kernel_project import identity

if TYPE_CHECKING:
    from Script.Core import game_type
    from Script.Kernel import core
    from Script.Modules.domains.abilities import Table

_committing: type[Table] | None = None
""" 写入在一步之外时自动套用的表类，第一次取表时建 """
_memo: dict[tuple[int, str], tuple[object, dict[str, object]]] = {}
""" 快照里每张表上一次展开的结果，working.get 交回同一个对象时沿用 """


def _outside_step(write: Callable[[], None]) -> None:
    """跑 write。它因为不在一步、玩家选择或缓冲区里而报 RuntimeError 时，在 kernel_data.writing 里再跑一次"""
    from tests import kernel_data

    try:
        write()
    except RuntimeError as error:
        if "outside a step" not in str(error):
            raise
        with kernel_data.writing():
            write()


def _table_class() -> type[Table]:
    global _committing
    if _committing is None:
        from Script.Modules.domains.abilities import Table as base

        class Committing(base):
            """写入在一步之外时经 kernel_data.writing 套用到内核状态上的表"""

            __slots__ = ()

            def __setitem__(self, tid: int, value: int) -> None:
                _outside_step(lambda: base.__setitem__(self, tid, value))

            def __delitem__(self, tid: int) -> None:
                _outside_step(lambda: base.__delitem__(self, tid))

            def merge(self, values: Mapping[int, int]) -> None:
                _outside_step(lambda: base.merge(self, values))

            def replace(self, values: Mapping[int, int]) -> None:
                _outside_step(lambda: base.replace(self, values))

        _committing = Committing
    return _committing


def _table(who: int | identity.Identity, name: str) -> Table:
    from Script.Modules.domains import abilities

    cid = who if isinstance(who, int) else who.cid
    return _table_class()(cid, abilities.PICKLED[name])


def ability(who: int | identity.Identity) -> Table:
    """角色的能力表"""
    return _table(who, "ability")


def experience(who: int | identity.Identity) -> Table:
    """角色的经验表"""
    return _table(who, "experience")


def juel(who: int | identity.Identity) -> Table:
    """角色的宝珠表"""
    return _table(who, "juel")


def talent(who: int | identity.Identity) -> Table:
    """角色的素质表"""
    return _table(who, "talent")


def zero_tables(cid: int) -> None:
    """把角色的四张表换成置零函数给的整表，每个配置编号都为 0"""
    from Script.Design import attr_calculation

    talent(cid).replace(attr_calculation.get_talent_zero({}))
    ability(cid).replace(attr_calculation.get_ability_zero({}))
    juel(cid).replace(attr_calculation.get_juel_zero({}))
    experience(cid).replace(attr_calculation.get_experience_zero({}))


def auto_commit_outside_step() -> None:
    """
    换掉 working.change。对这四个键的写入不在一步、玩家选择或缓冲区里时，经 kernel_data.writing 套用到内核状态上。
    别的键原样走 working.change
    """
    from Script.Modules.domains import abilities
    from Script.Modules.gameplay_resolution import working

    keys = frozenset(abilities.PICKLED.values())
    raw_change = working.change

    def change(who: str | None, key: str, op: str, operand: core.JSON) -> None:
        if key not in keys:
            raw_change(who, key, op, operand)
            return
        _outside_step(lambda: raw_change(who, key, op, operand))

    working.change = change


def project(cache: game_type.Cache, state: dict[str, object]) -> None:
    """
    在快照里用 abilities.PICKLED 的属性名记下每个角色的四张表，名字为 chara.<id>.<属性名>.<编号>
    Keyword arguments:
    cache -- 游戏缓存
    state -- 快照，原地补上
    """
    from Script.Modules.domains import abilities
    from Script.Modules.gameplay_resolution import working
    from tests.snapshot import flatten

    for cid in identity.table():
        for name, key in abilities.PICKLED.items():
            raw: Any = working.get(str(cid), key)
            hit = _memo.get((cid, key))
            if hit is None or hit[0] is not raw:
                rows: dict[str, object] = {}
                table = {int(tid): value for tid, value in raw.items()}
                flatten(f"chara.{cid}.{name}", table, rows)
                hit = _memo[(cid, key)] = (raw, rows)
            state.update(hit[1])
