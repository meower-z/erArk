"""
角色的生理需求：角色的键 body.needs
===================================
值是 {"tired": 疲劳, "hunger": 饥饿, "urine": 尿意, "milk": 乳汁}，每项是 int 或 Fraction。
角色没有这一项时读默认值 DEFAULT（饥饿 240，其余 0）。
这个键归本模块的规则 apply 所有。代码不整值替换它，而是用 add 或 set 记一次操作，规则按顺序把操作套到当前值上。
"""

from collections.abc import Mapping
from typing import TypedDict, cast

from Script.Core.num import Num
from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

KEY = "body.needs"
""" 生理需求在角色数据里的键 """


class Needs(TypedDict):
    """一个角色的生理需求，每项是 int 或 Fraction"""

    tired: Num
    """ 疲劳 """
    hunger: Num
    """ 饥饿 """
    urine: Num
    """ 尿意 """
    milk: Num
    """ 乳汁 """


DEFAULT: Needs = {"tired": 0, "hunger": 240, "urine": 0, "milk": 0}
""" 角色没有 body.needs 时读到的值 """


def fold(old: core.JSON, op: str, operand: core.JSON) -> core.JSON:
    """
    一次操作。add 给 stat 加 by，再按给出的 max、min 夹住，值与类型同 min(x + by, max)、max(x + by, min)。
    set 把给出的各项换成新值，别的项不变。
    Keyword arguments:
    old -- 当前的需求
    op -- "add" 或 "set"，别的名字报 ValueError
    operand -- add 时为 {"stat", "by", 可选的 "max" 与 "min"}，set 时为 {需求项: 新值}
    Return arguments:
    JSON -- 新的需求
    """
    values = dict(cast(Mapping[str, Num], old))
    args = cast(Mapping[str, Num], operand)
    if op == "set":
        values.update(args)
    elif op == "add":
        stat = str(args["stat"])
        value = values[stat] + args["by"]
        if "max" in args:
            value = min(value, args["max"])
        if "min" in args:
            value = max(value, args["min"])
        values[stat] = value
    else:
        raise ValueError(f"{KEY} has no op {op}")
    return cast(core.JSON, values)


working.register(KEY, cast(core.JSON, DEFAULT), fold)


@core.rule(KEY)
def apply(game: core.GameState, change: core.Change) -> core.GameState:
    """
    body.needs 的规则：用 working.fold_all 把 Change 带的一串操作依次套到角色当前的需求上
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


def of(cid: int, game: core.GameState | None = None) -> Needs:
    """
    角色的生理需求
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读这个状态，没有时读当前缓冲区，含还没套用的写入
    Return arguments:
    Needs -- 生理需求，没有这一项时为 DEFAULT
    """
    return cast(Needs, working.get(str(cid), KEY, game))


def add(
    cid: int,
    stat: str,
    by: Num,
    *,
    max: Num | None = None,
    min: Num | None = None,
) -> None:
    """
    给一项需求加 by，再按给出的 max、min 夹住，作为一次操作记进当前缓冲区
    Keyword arguments:
    cid -- 角色id
    stat -- 需求项
    by -- 加的量，可以为负
    max -- 上限，None 时不夹
    min -- 下限，None 时不夹
    """
    operand: dict[str, core.JSON] = {"stat": stat, "by": by}
    if max is not None:
        operand["max"] = max
    if min is not None:
        operand["min"] = min
    working.change(str(cid), KEY, "add", operand)


def set(cid: int, **values: Num) -> None:
    """
    把给出的需求项换成新值，作为一次操作记进当前缓冲区，别的项不变
    Keyword arguments:
    cid -- 角色id
    values -- 需求项到新值
    """
    working.change(str(cid), KEY, "set", cast(core.JSON, values))
