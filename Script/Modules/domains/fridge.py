"""
冰箱的全局键 base.fridge
========================
值是 {种类: {角色id的字符串: 存量（ml）}}，种类见 KINDS。没有这个键或某个种类时，那个种类读空表。
一个种类的表里，角色按第一次存进的先后排列。
这个键归本模块的规则 apply 所有。代码用 add 或 set 记一次操作，规则按顺序把操作套到当前值上。
给表里已有的角色加 0，或换成内容与顺序都相同的表时，不记操作。
"""

from collections.abc import Collection, Mapping
from typing import Any, cast

from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

KEY = "base.fridge"
""" 冰箱在全局数据里的键 """
MILK = "milk"
""" 母乳的种类名 """
URINE = "urine"
""" 尿液的种类名 """
KINDS = (MILK, URINE)
""" 全部种类 """
PICKLED = {"milk_in_fridge": MILK, "urine_in_fridge": URINE}
""" 版本 13 之前的存档里，罗德岛对象上的属性名到种类名 """

type Table = Mapping[str, int]
""" 一个种类存下的表：角色id的字符串到存量（ml） """


def fold(old: core.JSON, op: str, operand: core.JSON) -> core.JSON:
    """
    base.fridge 的一次操作。add 给一个种类里一名角色的存量加 by，表里没有这名角色时从 0 加起，加在表的最后。
    set 把给出的各种类的表整个换掉，别的种类不变
    Keyword arguments:
    old -- 当前的 {种类: 表}
    op -- "add" 或 "set"，别的名字报 ValueError
    operand -- add 时为 {"kind": 种类, "id": 角色id的字符串, "by": 加的量}，set 时为 {种类: 新表}
    Return arguments:
    JSON -- 新的冰箱
    """
    kinds = dict(cast(Mapping[str, Table], old))
    if op == "add":
        args = cast(Mapping[str, Any], operand)
        table = dict(kinds.get(args["kind"], {}))
        table[args["id"]] = table.get(args["id"], 0) + args["by"]
        kinds[args["kind"]] = table
    elif op == "set":
        kinds.update(cast(Mapping[str, Table], operand))
    else:
        raise ValueError(f"{KEY} has no op {op}")
    return cast(core.JSON, kinds)


working.register(KEY, {}, fold)


@core.rule(KEY)
def apply(game: core.GameState, change: core.Change) -> core.GameState:
    """
    base.fridge 的规则：用 working.fold_all 把 Change 带的一串操作依次套到当前的冰箱上
    Keyword arguments:
    game -- 状态
    change -- working.flush 给的 Change，operand 为 (操作名, 操作数) 的序列
    Return arguments:
    GameState -- 新状态
    """
    old = core.value(game, None, KEY)
    ops = cast(tuple[core.JSON, ...], change.operand)
    return core.with_value(game, None, KEY, working.fold_all(KEY, old, ops))


def _table(kind: str, game: core.GameState | None) -> Table:
    kinds = cast(Mapping[str, Table], working.get(None, KEY, game))
    return kinds.get(kind, {})


def table(kind: str, game: core.GameState | None = None) -> dict[int, int]:
    """
    一个种类的表
    Keyword arguments:
    kind -- 种类
    game -- 给出时只读这个状态，没有时读当前缓冲区，含还没套用的写入
    Return arguments:
    dict -- 角色id到存量，按第一次存进的先后排列。改它不改冰箱
    """
    return {int(cid): amount for cid, amount in _table(kind, game).items()}


def add(kind: str, character_id: int, by: int) -> None:
    """
    给一个种类里一名角色的存量加 by，作为一次操作记进当前缓冲区。表里已有这名角色且 by 为 0 时不记
    Keyword arguments:
    kind -- 种类
    character_id -- 角色id
    by -- 加的量
    """
    if by != 0 or str(character_id) not in _table(kind, None):
        operand = {"kind": kind, "id": str(character_id), "by": by}
        working.change(None, KEY, "add", cast(core.JSON, operand))


def _set(kind: str, new: Mapping[int, int]) -> None:
    stored = {str(cid): amount for cid, amount in new.items()}
    old = _table(kind, None)
    if stored != old or list(stored) != list(old):
        working.change(None, KEY, "set", cast(core.JSON, {kind: stored}))


def take(kind: str, character_id: int) -> int:
    """
    从一个种类的表里拿走一名角色的全部存量，这名角色离开表，作为一次操作记进当前缓冲区。
    表里没有这名角色时报 KeyError
    Keyword arguments:
    kind -- 种类
    character_id -- 角色id
    Return arguments:
    int -- 拿走的存量
    """
    rest = table(kind)
    amount = rest.pop(character_id)
    _set(kind, rest)
    return amount


def clear(kind: str) -> None:
    """
    清空一个种类的表。表已经是空的时不记操作
    Keyword arguments:
    kind -- 种类
    """
    _set(kind, {})


def remap(old_to_new: Mapping[int, int]) -> None:
    """
    角色换id时，把各种类的表里的旧id换成新id，顺序不变。
    换完后同一个id有几项时只留一项：位置取第一项的，存量取最后一项的
    Keyword arguments:
    old_to_new -- 旧id到新id，这里没有的id不变
    """
    for kind in KINDS:
        new: dict[int, int] = {}
        for cid, amount in table(kind).items():
            new[old_to_new.get(cid, cid)] = amount
        _set(kind, new)


def drop(ids: Collection[int]) -> int:
    """
    从各种类的表里删掉给出的角色
    Keyword arguments:
    ids -- 角色id
    Return arguments:
    int -- 删掉的条数，各种类分开计
    """
    count = 0
    for kind in KINDS:
        kept = {c: a for c, a in table(kind).items() if c not in ids}
        count += len(table(kind)) - len(kept)
        _set(kind, kept)
    return count


def adopt_old_save(loaded_dict: dict[str, Any], version: int) -> int:
    """
    读档时调用。从罗德岛对象上删掉 PICKLED 里的属性，把不空的表按存档里的先后写进当前缓冲区
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    version -- 存档的版本，旧存档为 0
    Return arguments:
    int -- 计入跨版本更新的条数：版本 13 之前的存档里缺一个属性记 1，属性不是 dict 时记 1，那个种类读空表
    """
    attrs = vars(loaded_dict["rhodes_island"])
    count = 0
    for old, kind in PICKLED.items():
        if old not in attrs:
            count += 1 if version < 13 else 0
            continue
        stored = attrs.pop(old)
        if type(stored) is not dict:
            count += 1
        elif stored:
            _set(kind, stored)
    return count
