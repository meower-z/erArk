"""
角色的射精与精液数值（h.meters）与全局射精位置（h.shoot_position）
================================================================
h.meters 存每个角色的射精槽上限、当前射精槽、精液槽上限、当前精液槽与临时额外精液量。
角色没有这一项时读默认值 DEFAULT（各项为 0）。
这个键归本模块的规则 apply 所有：通过 add 或 set 记一次操作，规则按顺序把操作套到当前值上，
保留 int 与 Fraction 精确数值类型。
全局键 h.shoot_position 记当前射精位置（int），默认 0，整值替换，值未变时不写。
"""

from collections.abc import Mapping
from typing import Any, TypedDict, cast

from Script.Core import num
from Script.Core.num import Num
from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

KEY = "h.meters"
""" 射精与精液数值在角色数据里的键 """
SHOOT_POSITION = "h.shoot_position"
""" 当前射精位置在全局数据里的键 """

OLD_CHARA_FIELDS: Mapping[str, str] = {
    "eja_point_max": "eja_max",
    "eja_point": "eja",
    "semen_point_max": "semen_max",
    "semen_point": "semen",
    "tem_extra_semen_point": "extra_semen",
}
""" 旧角色对象上的五个属性名到 h.meters 项名 """
EXACT_FIELDS = frozenset({"eja_point", "semen_point"})
""" 旧档导入时需经 num.exact 转为精确数值的属性 """


class HMeters(TypedDict):
    """一个角色的射精与精液数值"""

    eja_max: int
    """ 射精槽上限 """
    eja: Num
    """ 当前射精槽 """
    semen_max: int
    """ 精液槽上限 """
    semen: Num
    """ 当前精液槽 """
    extra_semen: int
    """ 临时额外精液量 """


DEFAULT: HMeters = {
    "eja_max": 0,
    "eja": 0,
    "semen_max": 0,
    "semen": 0,
    "extra_semen": 0,
}
""" 角色没有 h.meters 时读到的值 """


def fold(old: core.JSON, op: str, operand: core.JSON) -> core.JSON:
    """
    套用一次操作。add 给 stat 加 by，再按给出的 max、min 夹住；
    set 把给出的各项换成新值，其余不变。
    Keyword arguments:
    old -- 当前数值表
    op -- "add" 或 "set"，别的名字报 ValueError
    operand -- add 时为 {"stat", "by", 可选 "max"/"min"}，set 时为 {项名: 新值}
    Return arguments:
    JSON -- 新的数值表
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
working.register(SHOOT_POSITION, 0)


@core.rule(KEY)
def apply(game: core.GameState, change: core.Change) -> core.GameState:
    """
    h.meters 的规则：把 Change 带的一串操作依次套到角色当前数值上
    Keyword arguments:
    game -- 状态
    change -- working.flush 给的 Change
    Return arguments:
    GameState -- 新状态
    """
    old = core.value(game, change.who, KEY)
    ops = cast(tuple[core.JSON, ...], change.operand)
    return core.with_value(
        game, change.who, KEY, working.fold_all(KEY, old, ops)
    )


def of(cid: int, game: core.GameState | None = None) -> HMeters:
    """
    读取角色的射精与精液数值
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    HMeters -- 数值表，没有这一项时为 DEFAULT
    """
    return cast(HMeters, working.get(str(cid), KEY, game))


def add(
    cid: int,
    stat: str,
    by: Num,
    *,
    max: Num | None = None,
    min: Num | None = None,
) -> None:
    """
    给一项数值加 by，再按给出的 max、min 夹住，记进当前缓冲区
    Keyword arguments:
    cid -- 角色id
    stat -- 项名
    by -- 增量，可以为负
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
    把给出的项换成新值，记进当前缓冲区
    Keyword arguments:
    cid -- 角色id
    values -- 项名到新值
    """
    working.change(str(cid), KEY, "set", cast(core.JSON, values))


def shoot_position(game: core.GameState | None = None) -> int:
    """
    读取全局射精位置
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    int -- 射精位置
    """
    return cast(int, working.get(None, SHOOT_POSITION, game))


def set_shoot_position(value: int) -> None:
    """
    写入全局射精位置，值未变时不写
    Keyword arguments:
    value -- 射精位置
    """
    if shoot_position() != value:
        working.put(None, SHOOT_POSITION, value)


def copy_replaced(old: object, new: object, old_id: int, new_id: int) -> None:
    """
    角色替换迁移时复制五个数值：旧档抄属性到新对象，v16+ 写入内核缓冲区
    Keyword arguments:
    old -- 旧角色对象
    new -- 新角色对象
    old_id -- 旧角色id
    new_id -- 新角色id
    """
    if hasattr(old, "eja_point"):
        for attr in OLD_CHARA_FIELDS:
            if hasattr(old, attr):
                setattr(new, attr, getattr(old, attr))
        return
    current = of(old_id)
    if current != DEFAULT:
        set(new_id, **current)


def adopt_world(loaded_dict: dict[str, Any], version: int) -> int:
    """
    读档时搬走旧缓存上的 shoot_position，写入全局键 h.shoot_position
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    version -- 存档版本，旧档为 0
    Return arguments:
    int -- 20 之前缺失时计 1，其余为 0
    """
    if "shoot_position" not in loaded_dict:
        return 1 if version < 20 else 0
    value = loaded_dict.pop("shoot_position")
    set_shoot_position(value)
    return 0


def adopt_old_save(loaded_dict: dict[str, Any]) -> int:
    """
    读档重建角色后，把旧角色对象上的五个数值属性迁入 h.meters 并删除原属性
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    Return arguments:
    int -- 更新条数（恒为 0）
    """
    for cid, character in loaded_dict["character_data"].items():
        attrs = vars(character)
        found = {
            attr: attrs.pop(attr) for attr in OLD_CHARA_FIELDS if attr in attrs
        }
        if not found:
            continue
        values: dict[str, Num] = {}
        for attr, stat in OLD_CHARA_FIELDS.items():
            raw = found.get(attr, 0)
            values[stat] = num.exact(raw) if attr in EXACT_FIELDS else raw
        if any(
            values[k] != v or type(values[k]) is not int
            for k, v in DEFAULT.items()
        ):
            set(cid, **values)
    return 0
