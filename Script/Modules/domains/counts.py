"""
角色的数值表：{id的字符串: 数值} 形状的角色键共用的只读视图与操作
============================================================
body.status（status）、inventory.items（inventory）与 body.manage（body_manage）的值都是这个形状。
前两个键归各自模块的规则所有。规则经 working.fold_all 用 fold 套用操作。body.manage 的写入整值替换这个键。
读出的 Table 是只读的 Mapping，键为 int。
"""

from collections.abc import Iterator, Mapping
from typing import Any, cast

from Script.Core.num import Num
from Script.Kernel import core
from Script.Modules.gameplay_resolution import working


class Table[V: Num](Mapping[int, V]):
    """存下的 {id的字符串: 数值} 的只读视图，键为 int"""

    __slots__ = ("_raw",)

    def __init__(self, raw: Mapping[str, V]) -> None:
        """
        Keyword arguments:
        raw -- 存下的表，{id的字符串: 数值}
        """
        self._raw = raw

    def __getitem__(self, key: int) -> V:
        """id 为 key 的值，没有时报 KeyError"""
        return self._raw[str(key)]

    def __iter__(self) -> Iterator[int]:
        """按存下的顺序给出 int 的 id"""
        return (int(key) for key in self._raw)

    def __len__(self) -> int:
        """项数"""
        return len(self._raw)

    def __contains__(self, key: object) -> bool:
        """表里有 id 为 key 的项时为 True"""
        return str(key) in self._raw


def fold(old: core.JSON, op: str, operand: core.JSON) -> core.JSON:
    """
    数值表的一次操作，交回新表，old 不变。
    add 给一项加 by，再先按给出的 max、后按给出的 min 夹住，表里没有这一项时报 KeyError。
    set 把给出的各项换成新值，表里没有的项加在最后。drop 删掉给出的各项，表里没有的项跳过。replace 交回整张新表。
    Keyword arguments:
    old -- 当前的表
    op -- "add"、"set"、"drop" 或 "replace"，别的名字报 ValueError
    operand -- add 时为 {"id", "by", 可选的 "max" 与 "min"}，set 与 replace 时为 {id的字符串: 新值}，
    drop 时为 id的字符串的序列
    Return arguments:
    JSON -- 新的表
    """
    if op == "replace":
        return operand
    values = dict(cast(Mapping[str, Num], old))
    if op == "set":
        values.update(cast(Mapping[str, Num], operand))
    elif op == "add":
        args = cast(Mapping[str, Num], operand)
        key = str(args["id"])
        value = values[key] + args["by"]
        if "max" in args:
            value = min(args["max"], value)
        if "min" in args:
            value = max(args["min"], value)
        values[key] = value
    elif op == "drop":
        for key in cast(tuple[str, ...], operand):
            values.pop(key, None)
    else:
        raise ValueError(f"no table op {op}")
    return cast(core.JSON, values)


def add_operand(
    key: int, by: Num, max: Num | None, min: Num | None
) -> dict[str, core.JSON]:
    """
    add 操作的操作数
    Keyword arguments:
    key -- 要加的那一项的 id
    by -- 加的量
    max -- 上限，None 时不夹
    min -- 下限，None 时不夹
    Return arguments:
    dict -- 操作数，为 None 的上下限不放进去
    """
    operand: dict[str, core.JSON] = {"id": str(key), "by": by}
    if max is not None:
        operand["max"] = max
    if min is not None:
        operand["min"] = min
    return operand


def stored(table: Mapping[int, Num]) -> dict[str, Num]:
    """
    把键为 int 的表换成存下的形状
    Keyword arguments:
    table -- id 到数值
    Return arguments:
    dict -- id的字符串到数值，顺序不变
    """
    return {str(key): value for key, value in table.items()}


def record(who: str, key: str, op: str, operand: core.JSON) -> None:
    """
    给数值表记一次操作，写进当前缓冲区。套用后表的键、顺序、值与值的类型都不变时不记（working.same）
    Keyword arguments:
    who -- 角色键
    key -- 表的键名
    op -- 操作名，见 fold
    operand -- 操作数，见 fold
    """
    old = cast(Mapping[str, Num], working.get(who, key))
    new = cast(Mapping[str, Num], fold(cast(core.JSON, old), op, operand))
    if not working.same(old, new):
        working.change(who, key, op, operand)


def taken(loaded_dict: dict[str, Any], name: str) -> Iterator[tuple[int, Any]]:
    """
    读档时用。从存档里每个带着属性 name 的角色对象上删掉这个属性，按角色逐个交回删掉的值
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    name -- 属性名
    Return arguments:
    Iterator -- (角色id, 属性值)，角色id取 character_data 的键
    """
    for cid, character in loaded_dict["character_data"].items():
        attrs = vars(character)
        if name in attrs:
            yield cid, attrs.pop(name)
