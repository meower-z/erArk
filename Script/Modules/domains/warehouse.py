"""
基地仓库的全局键 base.stock 与 base.warehouse_modules
======================================================
base.stock 是 {资源id的字符串: 库存}，按记下的先后排列，没有这一项时读空表。
新游戏与新周目由 start 给每种配置资源记下库存。读档时 save_handle.install_save 给存档里缺的配置资源记下 0。
版本 7 之前的存档里的库存与扩展模块数由 adopt_old_save 写进这两个键。
这个键归本模块的规则 apply 所有。代码不整值替换它，而是用 add 或 set 记一次操作，规则按顺序把操作套到当前值上。
base.warehouse_modules 是已用的仓储空间扩展模块数，没有这一项时读 0，写入整值替换。
仓库容量（Rhodes_Island.warehouse_capacity）由仓储区的设施等级与扩展模块数算出，留在罗德岛对象上，不进 GameState。
"""

from collections.abc import Mapping
from typing import Any, cast

from Script.Config import game_config
from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

KEY = "base.stock"
""" 资源库存在全局数据里的键 """
MODULES = "base.warehouse_modules"
""" 已用的仓储空间扩展模块数在全局数据里的键 """
PICKLED_STOCK = "materials_resouce"
""" 版本 7 之前的存档里，资源库存在罗德岛对象上的属性名 """
PICKLED_MODULES = "used_extra_warehouse_capacity_module"
""" 版本 7 之前的存档里，已用的仓储空间扩展模块数在罗德岛对象上的属性名 """


def fold(old: core.JSON, op: str, operand: core.JSON) -> core.JSON:
    """
    base.stock 的一次操作。add 给一种资源的库存加 by，表里没有这种资源时报 KeyError。
    set 把给出的各资源换成新值，表里没有的资源按给出的先后加在最后，别的资源不变。
    Keyword arguments:
    old -- 当前的库存表
    op -- "add" 或 "set"，别的名字报 ValueError
    operand -- add 时为 {"id": 资源id的字符串, "by": 加的量}，set 时为 {资源id的字符串: 新库存}
    Return arguments:
    JSON -- 新的库存表
    """
    values = dict(cast(Mapping[str, int], old))
    if op == "set":
        values.update(cast(Mapping[str, int], operand))
    elif op == "add":
        args = cast(Mapping[str, int], operand)
        rid = str(args["id"])
        values[rid] = values[rid] + args["by"]
    else:
        raise ValueError(f"{KEY} has no op {op}")
    return cast(core.JSON, values)


working.register(KEY, {}, fold)
working.register(MODULES, 0)


@core.rule(KEY)
def apply(game: core.GameState, change: core.Change) -> core.GameState:
    """
    base.stock 的规则：用 working.fold_all 把 Change 带的一串操作依次套到当前的库存表上
    Keyword arguments:
    game -- 状态
    change -- working.flush 给的 Change，operand 为 (操作名, 操作数) 的序列
    Return arguments:
    GameState -- 新状态
    """
    old = core.value(game, None, KEY)
    ops = cast(tuple[core.JSON, ...], change.operand)
    return core.with_value(game, None, KEY, working.fold_all(KEY, old, ops))


def _stored(game: core.GameState | None) -> Mapping[str, int]:
    return cast(Mapping[str, int], working.get(None, KEY, game))


def stock(game: core.GameState | None = None) -> dict[int, int]:
    """
    库存表。返回的是新建的 dict，改它不改库存
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区，含还没套用的写入
    Return arguments:
    dict -- 资源id（int）到库存，按记下的先后排列，没有 base.stock 时为空表
    """
    return {int(rid): value for rid, value in _stored(game).items()}


def amount(rid: int, game: core.GameState | None = None) -> int:
    """
    一种资源的库存，表里没有这种资源时报 KeyError
    Keyword arguments:
    rid -- 资源id
    game -- 给出时只读这个状态，没有时读当前缓冲区，含还没套用的写入
    Return arguments:
    int -- 库存
    """
    return _stored(game)[str(rid)]


def add(rid: int, by: int) -> None:
    """
    给一种资源的库存加 by，作为一次操作记进当前缓冲区。表里没有这种资源时报 KeyError
    Keyword arguments:
    rid -- 资源id
    by -- 加的量，可以为负
    """
    working.change(None, KEY, "add", {"id": str(rid), "by": by})


def set_all(values: Mapping[int, int]) -> None:
    """
    把给出的各资源的库存换成新值，作为一次操作记进当前缓冲区。表里没有的资源按给出的先后加在最后
    Keyword arguments:
    values -- 资源id到新库存
    """
    operand = {str(rid): value for rid, value in values.items()}
    working.change(None, KEY, "set", cast(core.JSON, operand))


def set(rid: int, value: int) -> None:
    """
    把一种资源的库存换成 value，作为一次操作记进当前缓冲区。表里没有这种资源时加在最后
    Keyword arguments:
    rid -- 资源id
    value -- 新库存
    """
    set_all({rid: value})


def ensure(rid: int) -> None:
    """
    表里没有这种资源时，把它的库存记为 0，作为一次操作记进当前缓冲区。表里已有时不写
    Keyword arguments:
    rid -- 资源id
    """
    if str(rid) not in _stored(None):
        set(rid, 0)


def start(initial: Mapping[int, int]) -> None:
    """
    新基地的库存：每种配置资源记为 0，再换上 initial 里的值，作为一次操作记进当前缓冲区。
    表里没有的资源按配置的先后加在最后
    Keyword arguments:
    initial -- 资源id到开局库存
    """
    set_all({rid: 0 for rid in game_config.config_resouce} | dict(initial))


def extra_modules(game: core.GameState | None = None) -> int:
    """
    已用的仓储空间扩展模块数
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区，含还没套用的写入
    Return arguments:
    int -- 模块数，没有 base.warehouse_modules 时为 0
    """
    return cast(int, working.get(None, MODULES, game))


def set_extra_modules(value: int) -> None:
    """
    把已用的仓储空间扩展模块数整值换成 value，写进当前缓冲区。仓库容量不跟着变，由调用方更新
    Keyword arguments:
    value -- 模块数
    """
    working.put(None, MODULES, value)


def adopt_old_save(loaded_dict: dict[str, Any]) -> None:
    """
    读档时调用。罗德岛对象带着 PICKLED_STOCK 时（版本 0 到 6 的存档），按存档里的先后把库存写进当前缓冲区的 base.stock，
    把 PICKLED_MODULES 写进 base.warehouse_modules（对象上没有时写 0），再从对象上删掉这两个属性。
    对象上没有 PICKLED_STOCK 时什么也不写
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    """
    island = vars(loaded_dict["rhodes_island"])
    if PICKLED_STOCK not in island:
        return
    set_all(island.pop(PICKLED_STOCK))
    set_extra_modules(island.pop(PICKLED_MODULES, 0))
