"""
基地经济与贸易的七个全局键
==========================
base.income_today 是今日各部门的龙门币总收入。base.traded_today 是 {资源id: 今日买入与卖出的总量}。
这两个键归本模块登记的规则所有，代码只能用 add 或 set 给它们记操作。一步里的几次操作合成一个 Change 交给规则。
其余五个键写入时整值替换。
base.shops_open 是已开放的贸易区商店名，按开放的先后排列。
base.food_shelves 是 {商店: {食谱id: {食物uid: 品质}}}。餐馆的商店名是餐馆id的字符串，地摊小贩的是 STALL。
base.supply_demand 是 {资源id: 供需系数}。表里没有的资源，调用方按系数 1 算。
base.main_traders 是 {资源类型: 主交易员的角色id}。表里没有的类型读 0，即空缺。
base.auto_trade 是 {资源id: 自动交易设置}。表里没有的资源读 DEFAULT_AUTO_TRADE。
各表的键在状态里存成字符串，读函数交出的资源id是 int。
交易员名单不存，由岗位名册 work.roster(TRADER_WORK) 算出。
"""

from collections.abc import Mapping
from typing import cast
from uuid import UUID

from Script.Core import cache_control, game_type
from Script.Kernel import core
from Script.Modules.domains import roster, work
from Script.Modules.gameplay_resolution import working

INCOME = "base.income_today"
""" 今日总收入在全局数据里的键 """
SHOPS = "base.shops_open"
""" 已开放商店名在全局数据里的键 """
SHELVES = "base.food_shelves"
""" 餐馆与地摊小贩的货架在全局数据里的键 """
SUPPLY = "base.supply_demand"
""" 供需系数在全局数据里的键 """
TRADED = "base.traded_today"
""" 今日各资源买卖总量在全局数据里的键 """
TRADERS = "base.main_traders"
""" 各资源类型的主交易员在全局数据里的键 """
AUTO_TRADE = "base.auto_trade"
""" 自动交易设置在全局数据里的键 """
STALL = "Stall_Vendor"
""" 地摊小贩在 base.food_shelves 里的商店名 """
TRADER_WORK = 111
""" 交易员的职位id """
AUTO_TRADE_KEYS = (
    "buy_on",
    "buy_stock",
    "buy_price_percent",
    "sell_on",
    "sell_stock",
    "sell_price_percent",
)
""" 一项自动交易设置的六个键 """
DEFAULT_AUTO_TRADE: Mapping[str, bool | int] = {
    "buy_on": False,
    "buy_stock": 0,
    "buy_price_percent": 100,
    "sell_on": False,
    "sell_stock": 0,
    "sell_price_percent": 100,
}
""" 没有设置过的资源读到的自动交易设置 """

type Shelf = Mapping[str, Mapping[str, int]]
""" 一家商店的食物：食谱id的字符串 -> 食物uid的字符串 -> 品质 """


def fold_income(old: core.JSON, op: str, operand: core.JSON) -> core.JSON:
    """
    今日总收入的一次操作。add 加上 operand，set 换成 operand
    Keyword arguments:
    old -- 当前收入
    op -- "add" 或 "set"，别的操作名报 ValueError
    operand -- 金额
    Return arguments:
    JSON -- 新收入
    """
    if op == "add":
        return cast(int, old) + cast(int, operand)
    if op == "set":
        return operand
    raise ValueError(f"{INCOME} has no op {op}")


def fold_traded(old: core.JSON, op: str, operand: core.JSON) -> core.JSON:
    """
    今日买卖总量的一次操作。add 给一种资源的总量加上一个数，表里没有这种资源时从 0 加起。
    set 换掉给出的各资源的总量，别的资源不变
    Keyword arguments:
    old -- 当前的 {资源id的字符串: 总量}
    op -- "add" 或 "set"，别的操作名报 ValueError
    operand -- add 时为 {"resource": 资源id的字符串, "by": 数量}，set 时为 {资源id的字符串: 新值}
    Return arguments:
    JSON -- 新的总量表
    """
    counts = dict(cast(Mapping[str, int], old))
    args = cast(Mapping[str, int | str], operand)
    if op == "add":
        resource = str(args["resource"])
        counts[resource] = counts.get(resource, 0) + cast(int, args["by"])
    elif op == "set":
        counts.update(cast(Mapping[str, int], args))
    else:
        raise ValueError(f"{TRADED} has no op {op}")
    return cast(core.JSON, counts)


working.register(INCOME, 0, fold_income)
working.register(SHOPS, ())
working.register(SHELVES, {})
working.register(SUPPLY, {})
working.register(TRADED, {}, fold_traded)
working.register(TRADERS, {})
working.register(AUTO_TRADE, {})


def _apply(game: core.GameState, change: core.Change) -> core.GameState:
    old = core.value(game, change.who, change.key)
    ops = cast(tuple[core.JSON, ...], change.operand)
    new = working.fold_all(change.key, old, ops)
    return core.with_value(game, change.who, change.key, new)


@core.rule(INCOME)
def apply_income(game: core.GameState, change: core.Change) -> core.GameState:
    """
    base.income_today 的规则：把 Change 带的操作依次套到当前收入上
    Keyword arguments:
    game -- 状态
    change -- 缓冲区换成的 Change，operand 为 (操作名, 操作数) 的序列
    Return arguments:
    GameState -- 新状态
    """
    return _apply(game, change)


@core.rule(TRADED)
def apply_traded(game: core.GameState, change: core.Change) -> core.GameState:
    """
    base.traded_today 的规则：把 Change 带的操作依次套到当前的买卖总量表上
    Keyword arguments:
    game -- 状态
    change -- 缓冲区换成的 Change，operand 为 (操作名, 操作数) 的序列
    Return arguments:
    GameState -- 新状态
    """
    return _apply(game, change)


def income(game: core.GameState | None = None) -> int:
    """
    今日各部门的龙门币总收入
    Keyword arguments:
    game -- 给出时只读这个状态，不给时读当前缓冲区
    Return arguments:
    int -- 收入
    """
    return cast(int, working.get(None, INCOME, game))


def add_income(amount: int) -> None:
    """
    今日总收入加上 amount，作为一次 add 操作记进当前缓冲区
    Keyword arguments:
    amount -- 金额
    """
    working.change(None, INCOME, "add", amount)


def set_income(amount: int) -> None:
    """
    今日总收入换成 amount，作为一次 set 操作记进当前缓冲区
    Keyword arguments:
    amount -- 金额
    """
    working.change(None, INCOME, "set", amount)


def shops_open(game: core.GameState | None = None) -> tuple[str, ...]:
    """
    已开放的贸易区商店名，按开放的先后排列
    Keyword arguments:
    game -- 给出时只读这个状态，不给时读当前缓冲区
    Return arguments:
    tuple -- 商店名
    """
    return cast(tuple[str, ...], working.get(None, SHOPS, game))


def open_shop(name: str) -> None:
    """
    在已开放的商店名末尾加上 name，写进当前缓冲区
    Keyword arguments:
    name -- 商店名
    """
    working.put(None, SHOPS, (*shops_open(), name))


def shelf_table(game: core.GameState | None = None) -> Mapping[str, Shelf]:
    """
    全部商店的货架
    Keyword arguments:
    game -- 给出时只读这个状态，不给时读当前缓冲区
    Return arguments:
    Mapping -- 商店名（餐馆id的字符串或 STALL）到这家商店的货架
    """
    return cast(Mapping[str, Shelf], working.get(None, SHELVES, game))


def shelf(shop: int | str, game: core.GameState | None = None) -> Shelf:
    """
    一家商店的货架
    Keyword arguments:
    shop -- 餐馆id或 STALL
    game -- 给出时只读这个状态，不给时读当前缓冲区
    Return arguments:
    Shelf -- 食谱id的字符串 -> 食物uid的字符串 -> 品质，商店不在表里时为空表
    """
    return shelf_table(game).get(str(shop), {})


def has_shelf(shop: int | str) -> bool:
    """
    商店在 base.food_shelves 里有没有一项
    Keyword arguments:
    shop -- 餐馆id或 STALL
    Return arguments:
    bool -- 有时为 True
    """
    return str(shop) in shelf_table()


def stock(shop: int | str, foods: Shelf) -> None:
    """
    把一家商店的货架整个换成 foods，写进当前缓冲区。商店已在表里时，它在表里的位置不变
    Keyword arguments:
    shop -- 餐馆id或 STALL
    foods -- 食谱id的字符串 -> 食物uid的字符串 -> 品质
    """
    shelves = shelf_table()
    working.put(None, SHELVES, cast(core.JSON, {**shelves, str(shop): foods}))


def food(recipe: str, uid: str, quality: int) -> game_type.Food:
    """
    货架上的一份食物对应的食物对象。uid 取自货架，不另取。其余属性与 cooking.cook 不带制作者做出的食物相同
    Keyword arguments:
    recipe -- 食谱id的字符串
    uid -- 食物uid的字符串
    quality -- 品质
    Return arguments:
    Food -- 食物
    """
    made = game_type.Food(UUID(uid))
    made.quality = quality
    made.recipe = int(recipe)
    made.name = cache_control.cache.recipe_data[made.recipe].name
    return made


def take(shop: int | str, recipe: str, uid: str) -> game_type.Food | None:
    """
    从商店的货架上拿走一份食物，写进当前缓冲区
    Keyword arguments:
    shop -- 餐馆id或 STALL
    recipe -- 食谱id的字符串
    uid -- 食物uid的字符串
    Return arguments:
    Food | None -- 拿走的食物。货架上没有这份食物时为 None，什么也不写
    """
    foods = shelf(shop)
    row = foods.get(recipe, {})
    if uid not in row:
        return None
    rest = {key: quality for key, quality in row.items() if key != uid}
    stock(shop, {**foods, recipe: rest})
    return food(recipe, uid, row[uid])


def supply_demand(game: core.GameState | None = None) -> dict[int, float]:
    """
    表里记下的供需系数
    Keyword arguments:
    game -- 给出时只读这个状态，不给时读当前缓冲区
    Return arguments:
    dict -- 资源id到供需系数，只含表里有的资源。调用方把表里没有的资源按 1 算
    """
    stored = cast(Mapping[str, float], working.get(None, SUPPLY, game))
    return {int(rid): value for rid, value in stored.items()}


def set_supply_demand(table: Mapping[int, float]) -> None:
    """
    把供需系数表整个换成 table，写进当前缓冲区
    Keyword arguments:
    table -- 资源id到供需系数
    """
    stored = {str(rid): value for rid, value in table.items()}
    working.put(None, SUPPLY, cast(core.JSON, stored))


def traded_today(game: core.GameState | None = None) -> dict[int, int]:
    """
    今日各资源的买入卖出总量
    Keyword arguments:
    game -- 给出时只读这个状态，不给时读当前缓冲区
    Return arguments:
    dict -- 资源id到总量，只含表里有的资源。表里没有的资源总量为 0
    """
    stored = cast(Mapping[str, int], working.get(None, TRADED, game))
    return {int(rid): count for rid, count in stored.items()}


def add_traded(rid: int, quantity: int) -> None:
    """
    资源 rid 的今日买卖总量加上 quantity，作为一次 add 操作记进当前缓冲区
    Keyword arguments:
    rid -- 资源id
    quantity -- 数量
    """
    operand = {"resource": str(rid), "by": quantity}
    working.change(None, TRADED, "add", cast(core.JSON, operand))


def set_traded(counts: Mapping[int, int]) -> None:
    """
    把 counts 里各资源的今日买卖总量换成新值，作为一次 set 操作记进当前缓冲区。别的资源不变
    Keyword arguments:
    counts -- 资源id到新值
    """
    operand = {str(rid): count for rid, count in counts.items()}
    working.change(None, TRADED, "set", cast(core.JSON, operand))


def main_traders(game: core.GameState | None = None) -> dict[str, int]:
    """
    表里记下的主交易员
    Keyword arguments:
    game -- 给出时只读这个状态，不给时读当前缓冲区
    Return arguments:
    dict -- 新的字典：资源类型到角色id，0 为空缺，只含表里有的类型
    """
    return dict(cast(Mapping[str, int], working.get(None, TRADERS, game)))


def main_trader(res_type: str) -> int:
    """
    一种资源类型的主交易员
    Keyword arguments:
    res_type -- 资源类型
    Return arguments:
    int -- 角色id，空缺或表里没有这种类型时为 0
    """
    return main_traders().get(res_type, 0)


def _put_traders(table: Mapping[str, int]) -> None:
    if table != main_traders():
        working.put(None, TRADERS, cast(core.JSON, dict(table)))


def set_main_trader(res_type: str, chara_id: int) -> None:
    """
    任命或清空一种资源类型的主交易员，写进当前缓冲区
    Keyword arguments:
    res_type -- 资源类型
    chara_id -- 角色id，0 为清空
    """
    working.put(None, TRADERS, {**main_traders(), res_type: chara_id})


def drop_invalid_traders() -> None:
    """
    把无效的主交易员改为 0（空缺）。主交易员不是 int、不在 character_data 里或职位不是 TRADER_WORK 时无效。
    表有变化时才写进当前缓冲区
    """
    characters = cache_control.cache.character_data
    table = main_traders()
    for res_type, main_id in table.items():
        if (
            not isinstance(main_id, int)
            or main_id not in characters
            or characters[main_id].work.work_type != TRADER_WORK
        ):
            table[res_type] = 0
    _put_traders(table)


def remap_traders(old_to_new: Mapping[int, int]) -> None:
    """
    角色换id时，把主交易员表里的旧id换成新id。表有变化时才写进当前缓冲区
    Keyword arguments:
    old_to_new -- 旧id到新id，这里没有的id不变
    """
    table = main_traders()
    _put_traders({t: old_to_new.get(cid, cid) for t, cid in table.items()})


def trade_operator_ids() -> list[int]:
    """
    交易员名单：岗位名册 work.roster(TRADER_WORK) 里的角色。
    按已招募干员 roster.active() 此刻的遍历顺序排列
    Return arguments:
    list -- 角色id，已不在 roster.active() 里的交易员按名册的顺序排在最后
    """
    traders = work.roster(TRADER_WORK)
    active = roster.active()
    ordered = [cid for cid in active if cid in traders]
    return ordered + [cid for cid in traders if cid not in active]


def auto_trade(rid: int) -> dict[str, bool | int]:
    """
    一种资源的自动交易设置。没有设置过的资源读 DEFAULT_AUTO_TRADE。设置过的资源缺的键读 0
    Keyword arguments:
    rid -- 资源id
    Return arguments:
    dict -- 新的字典，含 AUTO_TRADE_KEYS 的六个键，存的设置里多出的键也在。改它不改状态，要用 set_auto_trade 写回
    """
    table = cast(
        Mapping[str, Mapping[str, bool | int]], working.get(None, AUTO_TRADE)
    )
    stored = table.get(str(rid))
    if stored is None:
        return dict(DEFAULT_AUTO_TRADE)
    return {**dict.fromkeys(AUTO_TRADE_KEYS, 0), **stored}


def auto_trade_table(
    game: core.GameState | None = None,
) -> dict[int, dict[str, bool | int]]:
    """
    表里记下的自动交易设置，原样读出，不补缺的键
    Keyword arguments:
    game -- 给出时只读这个状态，不给时读当前缓冲区
    Return arguments:
    dict -- 资源id到设置
    """
    table = cast(
        Mapping[str, Mapping[str, bool | int]],
        working.get(None, AUTO_TRADE, game),
    )
    return {int(rid): dict(setting) for rid, setting in table.items()}


def set_auto_trade(rid: int, setting: Mapping[str, bool | int]) -> None:
    """
    把一种资源的自动交易设置整个换成 setting，写进当前缓冲区
    Keyword arguments:
    rid -- 资源id
    setting -- 设置
    """
    table = cast(Mapping[str, core.JSON], working.get(None, AUTO_TRADE))
    working.put(
        None, AUTO_TRADE, {**table, str(rid): cast(core.JSON, dict(setting))}
    )
