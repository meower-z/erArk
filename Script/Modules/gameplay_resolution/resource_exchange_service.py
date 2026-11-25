"""
资源交易规则服务（resource_exchange_service）
=============================================
本模块提供资源交易报价、数量钳制、交易结算、列表过滤与配置写入。
公开常量 MONEY、TALK、PERCENT_CAP，数据类 Quote、Listing、
Roster、Deal，函数 quote、step、max_buy、max_sell、trade、
listings、roster、candidates、toggle_main_trader、
clear_main_trader、toggle_auto_trade、adjust_auto_trade_value。
本模块不执行界面绘制，也不导入 Script.UI、Script.Settle 或 Tk 模块。
"""

from dataclasses import dataclass
from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text
from Script.Modules.domains import abilities, economy, identity, location
from Script.Modules.domains import warehouse
from Script.Modules.gameplay_resolution import trade_service

_: FunctionType = get_text._
""" 翻译api """

MONEY = 1
""" 龙门币对应的资源编号常量。 """
TALK = 40
""" 话术技能对应的能力编号常量。 """
PERCENT_CAP = 300
""" 自动交易触发价格百分比的上限值。 """


@dataclass(frozen=True, slots=True)
class Quote:
    """
    主界面单次报价快照，含资源、数量、库存、仓容、资金、
    买卖价与波动、禁买与确认标志、主副交易员及加成。
    """

    name: str
    kind: str
    quantity: int
    stock: int
    capacity: int
    money: int
    buy_price: int
    buy_percent: float
    sell_price: int
    sell_percent: float
    cant_buy: bool
    confirm: bool
    main_id: int
    main_name: str | None
    main_bonus: float
    sub_bonus: float
    sub_names: tuple[str, ...]

    @property
    def total(self) -> int:
        """计算当前交易数量对应的预计总价，数量为 0 时返回 0。"""
        if self.quantity > 0:
            return self.buy_price * self.quantity
        return self.sell_price * -self.quantity

    @property
    def money_left(self) -> int:
        """计算当前交易后的预计剩余龙门币，买入扣除总价，卖出加上总价。"""
        if self.quantity > 0:
            return self.money - self.total
        return self.money + self.total


@dataclass(frozen=True, slots=True)
class Listing:
    """
    资源选择列表的单条展示数据，含编号、名称、简介、库存、
    仓容、可买时的买价元组与卖价元组。
    """

    resource_id: int
    name: str
    info: str
    stock: int
    capacity: int
    buy: tuple[int, float] | None
    sell: tuple[int, float]


@dataclass(frozen=True, slots=True)
class Roster:
    """交易员管理页快照，含交易员总数、各类型主交易员行与其余话术表。"""

    count: int
    rows: tuple[tuple[str, str], ...]
    others: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class Deal:
    """单次交易执行结果，含本地化提示文本 text 与成交标志 done。"""

    text: str
    done: bool


def _sellable(resource_id: int) -> bool:
    """判断资源在当前所在地是否允许卖出，非特产或身处产地时返回真。"""
    data = game_config.config_resouce[resource_id]
    return data.type != _("特产") or data.specialty == location.country()


def quote(resource_id: int, quantity: int) -> Quote:
    """
    读取资源与交易员状态并生成主界面报价快照。
    Keyword arguments:
    resource_id -- int，资源编号
    quantity -- int，带符号交易数量，正数买入、负数卖出
    Return arguments:
    Quote -- 含价格、确认标志与主副交易员信息的报价快照
    """
    data = game_config.config_resouce[resource_id]
    stock = warehouse.amount(resource_id)
    money = warehouse.amount(MONEY)
    buy_price, buy_percent = trade_service.get_resouce_price(resource_id, True)
    sell_price, sell_percent = trade_service.get_resouce_price(
        resource_id, False
    )
    _multiplier, main_bonus, sub_bonus = (
        trade_service.calculate_trade_multiplier(resource_id, True)
    )
    cant_buy = data.cant_buy == 1
    if quantity > 0:
        confirm = money >= buy_price * quantity and not cant_buy
    elif quantity < 0:
        confirm = stock >= -quantity and _sellable(resource_id)
    else:
        confirm = False
    main_id = economy.main_trader(data.type)
    sub_names = tuple(
        identity.of(cid).name
        for cid in economy.trade_operator_ids()
        if cid != main_id and identity.exists(cid)
    )
    return Quote(
        name=data.name,
        kind=data.type,
        quantity=quantity,
        stock=stock,
        capacity=warehouse.capacity(),
        money=money,
        buy_price=buy_price,
        buy_percent=buy_percent,
        sell_price=sell_price,
        sell_percent=sell_percent,
        cant_buy=cant_buy,
        confirm=confirm,
        main_id=main_id,
        main_name=identity.of(main_id).name if main_id > 0 else None,
        main_bonus=main_bonus,
        sub_bonus=sub_bonus,
        sub_names=sub_names,
    )


def step(resource_id: int, quantity: int, delta: int) -> int:
    """
    增减交易数量并先后按剩余仓容上限与负库存下限夹紧。
    Keyword arguments:
    resource_id -- int，资源编号
    quantity -- int，当前带符号交易数量
    delta -- int，本次增减步长
    Return arguments:
    int -- 夹紧后的带符号交易数量
    """
    stock = warehouse.amount(resource_id)
    quantity = min(quantity + delta, warehouse.capacity() - stock)
    return max(quantity, -stock)


def max_buy(resource_id: int, quantity: int) -> int:
    """
    计算资金与剩余仓容允许的最大买入量，禁买或买价非正时保持原值。
    Keyword arguments:
    resource_id -- int，资源编号
    quantity -- int，无法计算时原样返回的当前数量
    Return arguments:
    int -- 非负最大买入量，无法计算时返回原数量
    """
    if game_config.config_resouce[resource_id].cant_buy == 1:
        return quantity
    buy_price = trade_service.get_resouce_price(resource_id, True)[0]
    if buy_price <= 0:
        return quantity
    room = warehouse.capacity() - warehouse.amount(resource_id)
    return max(min(warehouse.amount(MONEY) // buy_price, room), 0)


def max_sell(resource_id: int) -> int:
    """
    返回指定资源的全部库存负值作为最大卖出数量。
    Keyword arguments:
    resource_id -- int，资源编号
    Return arguments:
    int -- 当前库存的相反数
    """
    return -warehouse.amount(resource_id)


def trade(resource_id: int, quantity: int) -> Deal | None:
    """
    执行买入或卖出并生成本地化成交结果，数量为 0 时返回 None。
    Keyword arguments:
    resource_id -- int，资源编号
    quantity -- int，带符号交易数量，正数买入、负数卖出
    Return arguments:
    Deal | None -- 含提示文本与成交标志的结果，数量为 0 返回 None
    """
    if quantity == 0:
        return None
    buy = quantity > 0
    wanted = abs(quantity)
    result = trade_service.perform_trade(resource_id, wanted, buy)
    if not result:
        return Deal(_("\n交易未能执行，请检查资金、仓库或库存限制。\n"), False)
    got = result["quantity"]
    total = result["total_price"]
    text = _(
        "\n交易成功！\n当前龙门币数量：{0}({1})\n资源{2}数量：{3}/{4}({5})\n"
    ).format(
        warehouse.amount(MONEY),
        ("-" if buy else "+") + str(total),
        game_config.config_resouce[resource_id].name,
        warehouse.amount(resource_id),
        warehouse.capacity(),
        ("+" if buy else "-") + str(got),
    )
    if got != wanted:
        text += _("(本次实际成交{0}单位)\n").format(got)
    return Deal(text, True)


def listings(res_type: str) -> tuple[Listing, ...]:
    """
    按配置顺序列出指定类型的可选资源，隐藏零库存的非本地特产。
    Keyword arguments:
    res_type -- str，本地化后的资源类型名称
    Return arguments:
    tuple[Listing, ...] -- 过滤后的资源展示项元组
    """
    found = []
    for rid, data in game_config.config_resouce.items():
        if data.type != res_type:
            continue
        if warehouse.amount(rid) == 0 and not _sellable(rid):
            continue
        buy = None
        if data.cant_buy == 0:
            buy = trade_service.get_resouce_price(rid, True)
        found.append(
            Listing(
                resource_id=rid,
                name=data.name,
                info=data.info,
                stock=warehouse.amount(rid),
                capacity=warehouse.capacity(),
                buy=buy,
                sell=trade_service.get_resouce_price(rid, False),
            )
        )
    return tuple(found)


def roster() -> Roster:
    """
    汇总交易员总数、各可交易类型的主交易员行与其余交易员话术等级。
    Return arguments:
    Roster -- 跳过无与货币类型后的交易员管理快照
    """
    rows = []
    mains = set()
    for res_type in trade_service.get_trade_resource_types():
        if res_type in {_("无"), _("货币")}:
            continue
        main_id = economy.main_trader(res_type)
        if main_id:
            mains.add(main_id)
        name = identity.of(main_id).name if main_id > 0 else _("空缺")
        rows.append((res_type, name))
    others = tuple(
        (identity.of(cid).name, abilities.ability(cid).get(TALK, 0))
        for cid in economy.trade_operator_ids()
        if cid not in mains and identity.exists(cid)
    )
    return Roster(len(economy.trade_operator_ids()), tuple(rows), others)


def candidates() -> list[int]:
    """
    返回可任命为主交易员的干员编号列表，排除角色 0。
    Return arguments:
    list[int] -- 非主角交易员角色编号列表
    """
    return [cid for cid in economy.trade_operator_ids() if cid != 0]


def toggle_main_trader(res_type: str, chara_id: int) -> None:
    """
    为指定资源类型任命或撤销主交易员，非交易员干员直接忽略。
    Keyword arguments:
    res_type -- str，资源类型名称
    chara_id -- int，待切换的干员编号
    Return arguments:
    None -- 无返回值
    """
    if chara_id not in economy.trade_operator_ids():
        return
    current = economy.main_trader(res_type)
    economy.set_main_trader(res_type, 0 if current == chara_id else chara_id)


def clear_main_trader(res_type: str) -> None:
    """
    将指定资源类型的主交易员清空为 0。
    Keyword arguments:
    res_type -- str，资源类型名称
    Return arguments:
    None -- 无返回值
    """
    economy.set_main_trader(res_type, 0)


def toggle_auto_trade(res_id: int, key: str) -> None:
    """
    翻转指定资源的一项自动交易布尔开关并写回状态。
    Keyword arguments:
    res_id -- int，资源编号
    key -- str，开关字段键名
    Return arguments:
    None -- 无返回值
    """
    settings = economy.auto_trade(res_id)
    settings[key] = not settings.get(key, False)
    economy.set_auto_trade(res_id, settings)


def adjust_auto_trade_value(
    res_id: int,
    key: str,
    delta: int,
    is_percent: bool = False,
    reset: bool = False,
) -> None:
    """
    按步长调整资源的自动交易数值并夹紧至上下限，或直接重置为 0。
    Keyword arguments:
    res_id、delta -- int，资源编号与增减步长
    key -- str，自动交易设置字段键名
    is_percent、reset -- bool，百分比上限开关与置零重置开关
    Return arguments:
    None -- 无返回值
    """
    settings = economy.auto_trade(res_id)
    if reset:
        settings[key] = 0
        economy.set_auto_trade(res_id, settings)
        return
    value = max(settings.get(key, 0) + delta, 0)
    if is_percent:
        value = min(PERCENT_CAP, value)
    elif warehouse.capacity() > 0:
        value = min(warehouse.capacity(), value)
    settings[key] = value
    economy.set_auto_trade(res_id, settings)
