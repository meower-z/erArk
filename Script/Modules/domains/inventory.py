"""
角色的道具与食物背包：角色键 inventory.items 与 inventory.food_bag
=================================================================
inventory.items 存 {道具id字符串: 数量}，缺失时读空表。
新角色由 character.init_attr 补上 Item.csv 缺的道具，数量为 0。
该键归本模块规则 apply 所有。代码用 add_item、set_item、drop_item、replace_items 记操作，操作见 counts.fold。
套用后值不变的操作不记。
inventory.food_bag 存 {食物uid字符串: 食物记录}，按放入顺序排列，记录见 kitchen.record。
缺失时读空背包。写入整值替换该键。replace_foods 在记录、顺序与值类型都没变时不写。
foods 返回带缓存的只读 FoodView 映射。clone_mutable_snapshot_foods 返回新建的可修改 Food 字典。
"""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, cast
from uuid import UUID

from Script.Core import game_type
from Script.Kernel import core
from Script.Modules.domains import counts, kitchen
from Script.Modules.gameplay_resolution import readonly, working

ITEMS = "inventory.items"
""" 道具在角色数据里的键 """
FOODS = "inventory.food_bag"
""" 食物背包在角色数据里的键 """
PICKLED_ITEMS = "item"
""" 版本 19 之前的存档里，角色对象上道具的属性名 """
PICKLED_FOODS = "food_bag"
""" 版本 19 之前的存档里，角色对象上食物背包的属性名 """

type Bag = Mapping[str, Mapping[str, core.JSON]]
""" 存下的食物背包：食物uid的字符串到食物记录 """

working.register(ITEMS, {}, counts.fold)
working.register(FOODS, {})


@core.rule(ITEMS)
def apply(game: core.GameState, change: core.Change) -> core.GameState:
    """
    inventory.items 的规则：用 working.fold_all 把 Change 带的一串操作依次套到角色当前的道具上
    Keyword arguments:
    game -- 状态
    change -- working.flush 给的 Change，operand 为 (操作名, 操作数) 的序列
    Return arguments:
    GameState -- 新状态
    """
    old = core.value(game, change.who, ITEMS)
    ops = cast(tuple[core.JSON, ...], change.operand)
    return core.with_value(
        game, change.who, ITEMS, working.fold_all(ITEMS, old, ops)
    )


def items(cid: int, game: core.GameState | None = None) -> counts.Table[int]:
    """
    角色的道具
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读这个状态，没有时读当前缓冲区，含还没套用的写入
    Return arguments:
    counts.Table -- 道具id到数量的只读表
    """
    raw = working.get(str(cid), ITEMS, game)
    return counts.Table(cast(Mapping[str, int], raw))


def add_item(
    cid: int, item_id: int, by: int, *, max: int | None = None
) -> None:
    """
    给一种道具的数量加 by，再按给出的 max 夹住，写进当前缓冲区。角色没有这种道具时报 KeyError
    Keyword arguments:
    cid -- 角色id
    item_id -- 道具id
    by -- 加的量，可以为负
    max -- 上限，None 时不夹
    """
    operand = counts.add_operand(item_id, by, max, None)
    counts.record(str(cid), ITEMS, "add", operand)


def set_item(cid: int, item_id: int, value: int) -> None:
    """
    把一种道具的数量换成 value，写进当前缓冲区。角色没有这种道具时加在最后
    Keyword arguments:
    cid -- 角色id
    item_id -- 道具id
    value -- 数量
    """
    counts.record(str(cid), ITEMS, "set", {str(item_id): value})


def drop_item(cid: int, item_id: int) -> None:
    """
    从角色的道具里删掉一种道具，写进当前缓冲区。没有这种道具时不变
    Keyword arguments:
    cid -- 角色id
    item_id -- 道具id
    """
    counts.record(str(cid), ITEMS, "drop", (str(item_id),))


def replace_items(cid: int, table: Mapping[int, int]) -> None:
    """
    把角色的道具整个换成 table，写进当前缓冲区
    Keyword arguments:
    cid -- 角色id
    table -- 道具id到数量
    """
    stored = cast(core.JSON, counts.stored(table))
    counts.record(str(cid), ITEMS, "replace", stored)


def _bag(cid: int, game: core.GameState | None = None) -> Bag:
    return cast(Bag, working.get(str(cid), FOODS, game))


def _view(stored: core.JSON) -> Mapping[UUID, kitchen.FoodView]:
    bag = cast(Bag, stored)
    return MappingProxyType(
        {UUID(uid): kitchen.food_view(uid, kept) for uid, kept in bag.items()}
    )


def foods(
    cid: int, game: core.GameState | None = None
) -> Mapping[UUID, kitchen.FoodView]:
    """
    读取角色背包食物的只读视图映射，原始值未变时复用缓存
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读该 GameState，为 None 时读当前缓冲区（含未套用的写入）
    Return arguments:
    Mapping[UUID, kitchen.FoodView] -- 食物uid到只读 FoodView 的只读映射，按放入顺序排列
    """
    return readonly.view(str(cid), FOODS, _view, game)


def clone_mutable_snapshot_foods(
    cid: int, game: core.GameState | None = None
) -> dict[UUID, game_type.Food]:
    """
    按当前背包记录新建可修改的 Food 字典副本，修改副本不影响背包
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读该 GameState，为 None 时读当前缓冲区（含未套用的写入）
    Return arguments:
    dict[UUID, game_type.Food] -- 食物uid到新建 Food 对象的字典，按放入顺序排列
    """
    return {
        UUID(uid): kitchen.food(uid, kept)
        for uid, kept in _bag(cid, game).items()
    }


def replace_foods(
    cid: int, new: Mapping[UUID, game_type.Food | kitchen.FoodView]
) -> None:
    """
    把角色的背包整个换成 new，写进当前缓冲区。记录、顺序与值的类型都没变时不写（working.same）
    Keyword arguments:
    cid -- 角色id
    new -- 食物uid到食物，按放进的顺序
    """
    stored = {str(uid): kitchen.record(food) for uid, food in new.items()}
    old = _bag(cid)
    if not working.same(old, stored):
        working.put(str(cid), FOODS, cast(core.JSON, stored))


def put_food(cid: int, food: game_type.Food) -> None:
    """
    把食物放进角色的背包，键为食物的 uid，写进当前缓冲区。背包里已有这个 uid 时换掉它的记录，位置不变。没有时放在最后
    Keyword arguments:
    cid -- 角色id
    food -- 食物
    """
    bag = clone_mutable_snapshot_foods(cid)
    bag[food.uid] = food
    replace_foods(cid, bag)


def drop_food(cid: int, uid: UUID) -> None:
    """
    从角色的背包里拿掉一份食物，写进当前缓冲区。背包里没有这个 uid 时报 KeyError
    Keyword arguments:
    cid -- 角色id
    uid -- 食物uid
    """
    take_food(cid, uid)


def take_food(cid: int, uid: UUID) -> game_type.Food:
    """
    从角色的背包里拿走一份食物，写进当前缓冲区。背包里没有这个 uid 时报 KeyError
    Keyword arguments:
    cid -- 角色id
    uid -- 食物uid
    Return arguments:
    game_type.Food -- 拿走的食物，按记录新建
    """
    bag = clone_mutable_snapshot_foods(cid)
    food = bag.pop(uid)
    replace_foods(cid, bag)
    return food


def adopt_old_save(loaded_dict: dict[str, Any]) -> None:
    """
    读档时调用。存档里的角色对象带着 PICKLED_ITEMS 或 PICKLED_FOODS 属性时（版本 19 之前的存档），从对象上删掉这些属性。
    不空的道具表与背包写进当前缓冲区。背包里食物的 uid 取背包的键
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    """
    for cid, table in counts.taken(loaded_dict, PICKLED_ITEMS):
        if table:
            replace_items(cid, table)
    for cid, bag in counts.taken(loaded_dict, PICKLED_FOODS):
        if bag:
            stored = {str(u): kitchen.record(f) for u, f in bag.items()}
            working.put(str(cid), FOODS, cast(core.JSON, stored))
