"""
基地计数的全局键 base.tallies
=============================
值是 {计数名: 数}，计数名见 NAMES。没有这个键或其中一项时，那一项读 0。
favorability 是上次日结之后记下的好感度上升总量。character_handle.add_favorability 在当前角色是玩家，
或当前角色的交互对象是玩家时记下它。日结时它按百分之一折成粉红凭证，随后清零。
semen 是上次日结之后记下的精液量（ml）。日结时它加进仓库的资源 12，随后清零。
aromatherapy 是剩下的调香次数。日结与刷新基地时，它按疗养庭院的等级重置。
fallen_certificates 是陷落角色提供、还没入库的粉红凭证。每周一次的日结先加上它，同一次日结把它入库后清零。
这个键归本模块的规则 apply 所有。代码用 add 或 set 记一次操作，规则按顺序把操作套到当前值上。
加 0 与换成相同的值时不记操作。
"""

from collections.abc import Mapping
from typing import Any, cast

from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

KEY = "base.tallies"
""" 基地计数在全局数据里的键 """
FAVORABILITY = "favorability"
""" 上次日结之后好感度上升总量的计数名 """
SEMEN = "semen"
""" 上次日结之后记下的精液量（ml）的计数名 """
AROMATHERAPY = "aromatherapy"
""" 剩下的调香次数的计数名 """
FALLEN = "fallen_certificates"
""" 陷落角色提供、还没入库的粉红凭证的计数名 """
NAMES = (FAVORABILITY, SEMEN, AROMATHERAPY, FALLEN)
""" 全部计数名 """
PICKLED = {
    "total_favorability_increased": FAVORABILITY,
    "total_semen_count": SEMEN,
    "remaining_aromatherapy_sessions_today": AROMATHERAPY,
    "week_fall_chara_pink_certificate_add": FALLEN,
}
""" 版本 13 之前的存档里，罗德岛对象上的属性名到计数名 """


def fold(old: core.JSON, op: str, operand: core.JSON) -> core.JSON:
    """
    base.tallies 的一次操作。add 给一项计数加 by，set 把给出的各项换成新值
    Keyword arguments:
    old -- 当前的 {计数名: 数}
    op -- "add" 或 "set"，别的名字报 ValueError
    operand -- add 时为 {"name": 计数名, "by": 加的量}，set 时为 {计数名: 新值}
    Return arguments:
    JSON -- 新的计数表
    """
    values = dict(cast(Mapping[str, int], old))
    if op == "add":
        args = cast(Mapping[str, Any], operand)
        values[args["name"]] = values.get(args["name"], 0) + args["by"]
    elif op == "set":
        values.update(cast(Mapping[str, int], operand))
    else:
        raise ValueError(f"{KEY} has no op {op}")
    return cast(core.JSON, values)


working.register(KEY, {}, fold)


@core.rule(KEY)
def apply(game: core.GameState, change: core.Change) -> core.GameState:
    """
    base.tallies 的规则：用 working.fold_all 把 Change 带的一串操作依次套到当前的计数表上
    Keyword arguments:
    game -- 状态
    change -- working.flush 给的 Change，operand 为 (操作名, 操作数) 的序列
    Return arguments:
    GameState -- 新状态
    """
    old = core.value(game, None, KEY)
    ops = cast(tuple[core.JSON, ...], change.operand)
    return core.with_value(game, None, KEY, working.fold_all(KEY, old, ops))


def get(name: str, game: core.GameState | None = None) -> int:
    """
    一项计数
    Keyword arguments:
    name -- 计数名
    game -- 给出时只读这个状态，没有时读当前缓冲区，含还没套用的写入
    Return arguments:
    int -- 计数，没有记过时为 0
    """
    return cast(Mapping[str, int], working.get(None, KEY, game)).get(name, 0)


def add(name: str, by: int) -> None:
    """
    给一项计数加 by，作为一次操作记进当前缓冲区。by 为 0 时不记
    Keyword arguments:
    name -- 计数名
    by -- 加的量，可以为负
    """
    if by != 0:
        working.change(None, KEY, "add", {"name": name, "by": by})


def set(name: str, value: int) -> None:
    """
    把一项计数换成 value，作为一次操作记进当前缓冲区。值不变时不记
    Keyword arguments:
    name -- 计数名
    value -- 新值
    """
    if get(name) != value:
        working.change(None, KEY, "set", {name: value})


def adopt_old_save(loaded_dict: dict[str, Any], version: int) -> int:
    """
    读档时调用。从罗德岛对象上删掉 PICKLED 里的属性，把与当前值不同的值写进当前缓冲区
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    version -- 存档的版本，旧存档为 0
    Return arguments:
    int -- 计入跨版本更新的条数：版本 13 之前的存档里缺一个属性记 1
    """
    attrs = vars(loaded_dict["rhodes_island"])
    count = 0
    for old, name in PICKLED.items():
        if old in attrs:
            set(name, attrs.pop(old))
        elif version < 13:
            count += 1
    return count
