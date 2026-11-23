"""
资源交易服务（trade_service）
=============================
提供资源交易的价格计算、交易员加成、供需调节、交易执行与每日自动交易逻辑。
不直接导入界面模块，供资源交易面板与基地每日结算调用。
"""

import random
from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text
from Script.Modules.domains import abilities, economy, identity, location
from Script.Modules.domains import warehouse

_: FunctionType = get_text._
""" 翻译api """


def _get_resource_type_key(resouce_id: int) -> str:
    """
    返回指定资源在配置中的类型名称。
    Keyword arguments:
    resouce_id -- int，资源配置编号
    Return arguments:
    str -- 该资源的类型名称
    """

    return game_config.config_resouce[resouce_id].type


def get_trade_resource_types() -> list[str]:
    """
    按配置顺序返回除编号 0 外去重后的资源类型名称列表。
    Keyword arguments:
    无
    Return arguments:
    list[str] -- 去重后的资源类型名称列表
    """

    res_types: list[str] = []
    seen_type: set = set()
    for res_id in game_config.config_resouce:
        if res_id == 0:
            continue
        res_type = game_config.config_resouce[res_id].type
        if res_type in seen_type:
            continue
        seen_type.add(res_type)
        res_types.append(res_type)
    return res_types


def calculate_trade_multiplier(
    resouce_id: int, buy_flag: bool
) -> tuple[float, float, float]:
    """
    计算指定资源在交易员话术加成下的价格乘数。
    在岗主交易员按 40 号话术能力每级提供 0.5% 加成。
    其余存在的交易员按 40 号话术能力每级提供 0.1% 加成。
    最终乘数在买入时不低于 0.5，在卖出时不高于 2.0。
    Keyword arguments:
    resouce_id -- int，资源配置编号
    buy_flag -- bool，True 表示买入，False 表示卖出
    Return arguments:
    tuple[float, float, float] -- (价格乘数, 主交易员加成, 副交易员加成)
    """

    TRADE_MAIN_RATE: float = 0.005
    """ 主交易员每级话术带来的价格百分比调整 """
    TRADE_SUB_RATE: float = 0.001
    """ 副交易员每级话术带来的价格百分比调整 """
    MIN_BUY_MULTIPLIER: float = 0.5
    """ 交易员调整的买入价格下限（为基础价格的百分比） """
    MAX_SELL_MULTIPLIER: float = 2.0
    """ 交易员调整的卖出价格上限（为基础价格的百分比） """

    res_type = _get_resource_type_key(resouce_id)
    trade_ids = economy.trade_operator_ids()
    main_id = economy.main_trader(res_type)
    main_bonus = 0.0
    sub_bonus = 0.0
    if main_id in trade_ids and main_id > 0:
        ability_lv = abilities.ability(main_id).get(40, 0)
        main_bonus = ability_lv * TRADE_MAIN_RATE
    for chara_id in trade_ids:
        if chara_id == main_id or not identity.exists(chara_id):
            continue
        ability_lv = abilities.ability(chara_id).get(40, 0)
        sub_bonus += ability_lv * TRADE_SUB_RATE
    total_bonus = main_bonus + sub_bonus
    if buy_flag:
        multiplier = max(MIN_BUY_MULTIPLIER, 1 - total_bonus)
    else:
        multiplier = min(MAX_SELL_MULTIPLIER, 1 + total_bonus)
    return multiplier, main_bonus, sub_bonus


def _adjust_supply_demand_after_trade(
    resouce_id: int, quantity: int, buy_flag: bool
) -> None:
    """
    按单次成交量分步更新指定资源的供需系数。
    成交量不超过 0 时直接返回，否则每满 50 单位迭代一步。
    供需系数在买入时上调且不超过 5.0，在卖出时下调且不低于 0.1，每步结果保留四位小数。
    计算完成后将更新后的供需表写回经济状态。
    Keyword arguments:
    resouce_id -- int，资源配置编号
    quantity -- int，本次实际成交数量
    buy_flag -- bool，True 表示买入，False 表示卖出
    Return arguments:
    None -- 直接写回经济状态中的供需系数
    """

    if quantity <= 0:
        return
    supply_demand_dict = economy.supply_demand()
    supply_demand_dict.setdefault(resouce_id, 1)
    today_total = economy.traded_today().get(resouce_id, 0)
    for _step in range(quantity // 50):
        cur_sd = supply_demand_dict[resouce_id]
        if buy_flag:
            delta_sd = 0.001 * 10 * (1 / cur_sd)
            delta_sd *= 1 + (today_total / 1000)
            supply_demand_dict[resouce_id] = round(
                min(5.0, cur_sd + delta_sd), 4
            )
        else:
            delta_sd = 0.001 * 10 * cur_sd
            delta_sd /= 1 + (today_total / 1000)
            supply_demand_dict[resouce_id] = round(
                max(0.1, cur_sd - delta_sd), 4
            )
    economy.set_supply_demand(supply_demand_dict)


def perform_trade(
    resouce_id: int, quantity: int, buy_flag: bool
) -> dict[str, int] | None:
    """
    执行单次资源买卖结算并更新库存、龙门币、供需系数与今日成交量。
    买入受剩余仓容与持有龙门币限制。
    卖出受当前资源库存限制。
    数量或单价不大于 0、或截断后无法成交时返回 None。
    Keyword arguments:
    resouce_id -- int，资源配置编号
    quantity -- int，请求的交易数量
    buy_flag -- bool，True 表示买入，False 表示卖出
    Return arguments:
    dict[str, int] | None -- 成交时返回含 quantity、price、total_price 的字典，未成交时返回 None
    """

    if quantity <= 0:
        return None
    price, _percent = get_resouce_price(resouce_id, buy_flag)
    if price <= 0:
        return None
    warehouse.ensure(resouce_id)
    warehouse.ensure(1)

    result_quantity = quantity
    if buy_flag:
        capacity_left = warehouse.capacity() - warehouse.amount(resouce_id)
        if capacity_left <= 0:
            return None
        result_quantity = min(result_quantity, capacity_left)
        if price > 0:
            affordable = warehouse.amount(1) // price
            result_quantity = min(result_quantity, affordable)
        if result_quantity <= 0:
            return None
        total_price = price * result_quantity
        warehouse.add(resouce_id, result_quantity)
        warehouse.add(1, -total_price)
        _adjust_supply_demand_after_trade(resouce_id, result_quantity, True)
    else:
        available = warehouse.amount(resouce_id)
        result_quantity = min(result_quantity, available)
        if result_quantity <= 0:
            return None
        total_price = price * result_quantity
        warehouse.add(resouce_id, -result_quantity)
        warehouse.add(1, total_price)
        _adjust_supply_demand_after_trade(resouce_id, result_quantity, False)

    economy.add_traded(resouce_id, result_quantity)

    return {
        "quantity": result_quantity,
        "price": price,
        "total_price": price * result_quantity,
    }


def auto_trade_resources() -> list[str]:
    """
    按各资源的自动交易设置依次执行自动卖出与自动买入，返回成交明细文本列表。
    本函数不执行任何界面绘制。
    没有在岗交易员时直接返回空列表。
    存在在岗交易员时，逐类处理已任命主交易员且类别不为「无」和「货币」的资源。
    Keyword arguments:
    无
    Return arguments:
    list[str] -- 本次触发成交的自动交易明细行列表，无成交时返回空列表
    """

    if not economy.trade_operator_ids():
        return []

    summary_lines: list[str] = []
    for res_type in get_trade_resource_types():
        if res_type in {"无", "货币"}:
            continue
        if not economy.main_trader(res_type):
            continue

        for resouce_id, resouce_data in game_config.config_resouce.items():
            if resouce_id == 0 or resouce_data.type != res_type:
                continue
            settings = economy.auto_trade(resouce_id)
            buy_on = settings.get("buy_on", False)
            buy_stock = settings.get("buy_stock", 0)
            buy_percent = settings.get("buy_price_percent", 0)
            sell_on = settings.get("sell_on", False)
            sell_stock = settings.get("sell_stock", 0)
            sell_percent = settings.get("sell_price_percent", 0)
            warehouse.ensure(resouce_id)

            if (
                sell_on
                and sell_stock >= 0
                and sell_percent > 0
                and warehouse.amount(resouce_id) > sell_stock
            ):
                _price_now, percent_sell = get_resouce_price(resouce_id, False)
                if percent_sell + 100 >= sell_percent:
                    need_qty = warehouse.amount(resouce_id) - sell_stock
                    trade_ret = perform_trade(resouce_id, need_qty, False)
                    if trade_ret:
                        summary_lines.append(
                            _("  · 自动卖出{0} x {1}，单价{2}，总计{3}").format(
                                _(resouce_data.name),
                                trade_ret["quantity"],
                                trade_ret["price"],
                                trade_ret["total_price"],
                            )
                        )

            if (
                buy_on
                and buy_stock > 0
                and buy_percent > 0
                and resouce_data.cant_buy == 0
                and warehouse.amount(resouce_id) < buy_stock
            ):
                _price_now, percent_buy = get_resouce_price(resouce_id, True)
                if percent_buy + 100 <= buy_percent:
                    need_qty = buy_stock - warehouse.amount(resouce_id)
                    trade_ret = perform_trade(resouce_id, need_qty, True)
                    if trade_ret:
                        summary_lines.append(
                            _("  · 自动买入{0} x {1}，单价{2}，总计{3}").format(
                                _(resouce_data.name),
                                trade_ret["quantity"],
                                trade_ret["price"],
                                trade_ret["total_price"],
                            )
                        )

    return summary_lines


def get_resouce_price(
    resouce_id: int, buy_or_sell_flag: bool, self_check: bool = True
) -> tuple[int, float]:
    """
    计算指定资源的买入或卖出单价以及相对基础交易价的波动百分比。
    单价结合基础价格系数、当前供需系数与交易员价格乘数得出。
    开启 self_check 时保证买入价不低于卖出价且卖出价不高于买入价。
    Keyword arguments:
    resouce_id -- int，资源配置编号
    buy_or_sell_flag -- bool，True 表示买入，False 表示卖出
    self_check -- bool，是否执行买卖倒挂校验，默认 True
    Return arguments:
    tuple[int, float] -- (取整后的交易单价, 相对基础交易价的波动百分比)
    """
    resouce_data = game_config.config_resouce[resouce_id]
    base_price: float = resouce_data.price
    if (
        resouce_data.type == _("特产")
        and resouce_data.specialty == location.country()
    ):
        base_price *= 1.5
    else:
        base_price = 1.1 * base_price if buy_or_sell_flag else 0.9 * base_price
    supply_demand = economy.supply_demand().get(resouce_id, 1)
    multiplier, _tem1, _tem2 = calculate_trade_multiplier(
        resouce_id, buy_or_sell_flag
    )
    final_adjustment = supply_demand * multiplier
    price = base_price * final_adjustment
    if buy_or_sell_flag and self_check:
        sell_price = get_resouce_price(resouce_id, False, self_check=False)[0]
        price = max(price, sell_price)
        final_adjustment = max(final_adjustment, sell_price / base_price)
    elif not buy_or_sell_flag and self_check:
        buy_price = get_resouce_price(resouce_id, True, self_check=False)[0]
        price = min(price, buy_price)
        final_adjustment = min(final_adjustment, buy_price / base_price)
    percent = (final_adjustment - 1) * 100
    return int(price), percent


def daily_supply_demand_fluctuation() -> list[str]:
    """
    执行每日供需系数的均值回归与随机波动，并触发当日自动交易。
    除编号 1 的资源外，将其余配置资源的今日成交量归零并按下限 0.1 更新供需系数。
    Keyword arguments:
    无
    Return arguments:
    list[str] -- auto_trade_resources 返回的自动交易成交明细行列表
    """
    supply_demand_dict = economy.supply_demand()
    traded_reset: dict[int, int] = {}
    for res_id in game_config.config_resouce:
        if res_id == 1:
            continue
        traded_reset[res_id] = 0
        cur = supply_demand_dict.get(res_id, 1)
        revert = (1 - cur) * 0.05
        rand_fluct = random.uniform(-0.005, 0.005) + random.uniform(
            -abs(cur - 1) * 0.02, abs(cur - 1) * 0.02
        )
        delta = revert + rand_fluct
        new_val = max(0.1, cur + delta)
        supply_demand_dict[res_id] = round(new_val, 4)
    economy.set_traded(traded_reset)
    economy.set_supply_demand(supply_demand_dict)

    return auto_trade_resources()
