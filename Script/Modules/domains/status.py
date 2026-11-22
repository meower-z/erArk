"""
角色的状态值：角色键 body.status
================================
值是 {状态id的字符串: 状态值}，状态值是 int 或 Fraction。角色没有这一项时读空表。
新角色由 character.init_attr 补上 CharacterState.csv 里缺的状态，值为 0。
这个键归本模块的规则 apply 所有。代码用 add、set、setdefault、replace 记一次操作，规则按顺序把操作套到当前值上。
操作见 counts.fold。套用后值不变的操作不记。
"""

from collections.abc import Mapping
from typing import Any, cast

from Script.Core import num
from Script.Core.num import Num
from Script.Kernel import core
from Script.Modules.domains import counts
from Script.Modules.gameplay_resolution import working

KEY = "body.status"
""" 状态值在角色数据里的键 """
PICKLED = "status_data"
""" 版本 19 之前的存档里，角色对象上状态值的属性名 """

working.register(KEY, {}, counts.fold)


@core.rule(KEY)
def apply(game: core.GameState, change: core.Change) -> core.GameState:
    """
    body.status 的规则：用 working.fold_all 把 Change 带的一串操作依次套到角色当前的状态值上
    Keyword arguments:
    game -- 状态
    change -- working.flush 给的 Change，operand 为 (操作名, 操作数) 的序列
    Return arguments:
    GameState -- 新状态
    """
    old = core.value(game, change.who, KEY)
    ops = cast(tuple[core.JSON, ...], change.operand)
    return core.with_value(
        game, change.who, KEY, working.fold_all(KEY, old, ops)
    )


def of(cid: int, game: core.GameState | None = None) -> counts.Table[Num]:
    """
    角色的状态值
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读这个状态，没有时读当前缓冲区，含还没套用的写入
    Return arguments:
    counts.Table -- 状态id到状态值的只读表
    """
    return counts.Table(
        cast(Mapping[str, Num], working.get(str(cid), KEY, game))
    )


def add(
    cid: int,
    status_id: int,
    by: Num,
    *,
    max: Num | None = None,
    min: Num | None = None,
) -> None:
    """
    给一个状态加 by，再先按给出的 max、后按给出的 min 夹住，写进当前缓冲区。角色没有这个状态时报 KeyError
    Keyword arguments:
    cid -- 角色id
    status_id -- 状态id
    by -- 加的量，可以为负
    max -- 上限，None 时不夹
    min -- 下限，None 时不夹
    """
    operand = counts.add_operand(status_id, by, max, min)
    counts.record(str(cid), KEY, "add", operand)


def set(cid: int, status_id: int, value: Num) -> None:
    """
    把一个状态换成 value，写进当前缓冲区。角色没有这个状态时加在最后
    Keyword arguments:
    cid -- 角色id
    status_id -- 状态id
    value -- 新值
    """
    counts.record(str(cid), KEY, "set", {str(status_id): value})


def setdefault(cid: int, status_id: int, value: Num) -> None:
    """
    角色没有这个状态时加上它，值为 value，写进当前缓冲区。已有时不变
    Keyword arguments:
    cid -- 角色id
    status_id -- 状态id
    value -- 加上时的值
    """
    if status_id not in of(cid):
        set(cid, status_id, value)


def replace(cid: int, table: Mapping[int, Num]) -> None:
    """
    把角色的状态值整个换成 table，写进当前缓冲区
    Keyword arguments:
    cid -- 角色id
    table -- 状态id到状态值
    """
    stored = cast(core.JSON, counts.stored(table))
    counts.record(str(cid), KEY, "replace", stored)


def adopt_old_save(loaded_dict: dict[str, Any]) -> None:
    """
    读档时调用。存档里的角色对象带着 PICKLED 属性时（版本 19 之前的存档），从对象上删掉它。
    不空的表写进当前缓冲区，其中 float 的状态值换成 num.exact 的精确值
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    """
    for cid, table in counts.taken(loaded_dict, PICKLED):
        if table:
            replace(cid, {k: num.exact(v) for k, v in table.items()})
