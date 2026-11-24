"""
载具服务（vehicle_service）
===========================
提供基地载具表补齐、机库状态与文本组装、载具列表筛选排序分页、交易判定与买卖执行，以及外勤委托载具损坏回收结算。
本模块依赖标准库、配置、翻译工具、领域数据与存档修补注册，不导入界面、窗口、Tk、结算或指令处理模块。
"""

import random
from dataclasses import dataclass
from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text
from Script.Modules.domains import commission, facility, warehouse
from Script.Modules.save_load import reset

_: FunctionType = get_text._
""" 翻译api """

HANGAR = 14
""" 机库设施在设施配置中的编号（14）。 """
MONEY = 1
""" 龙门币在仓库库存中的资源编号（1）。 """
SELL_RATE = 0.8
""" 出售载具时的价格回收系数（0.8）。 """


@dataclass(frozen=True, slots=True)
class HangarStatus:
    """机库状态快照，记录当前机库等级、载具容量上限、全部载具总持有量与当前龙门币数量。"""

    level: int
    limit: int
    owned: int
    money: int


@dataclass(frozen=True, slots=True)
class VehicleRow:
    """载具列表单行数据，记录载具编号、总持有量与外勤中数量。"""

    cid: int
    owned: int
    out: int


@dataclass(frozen=True, slots=True)
class VehiclePage:
    """载具列表分页结果，记录当前页载具行元组、修正后的当前页码、总页数，以及上一页和下一页的目标页码。"""

    rows: tuple[VehicleRow, ...]
    page: int
    total: int
    prev: int
    next: int


@dataclass(frozen=True, slots=True)
class VehicleTrade:
    """载具交易页面状态，记录该载具持有量、当前龙门币、购买后剩余龙门币、剩余机库空间，以及购买和出售是否可用。"""

    owned: int
    money: int
    money_left: int
    space_left: int
    can_buy: bool
    can_sell: bool


@reset.repair
def update_basement_vehicle_data() -> None:
    """
    补齐基地载具表中缺失的载具配置条目。
    已通过 reset.repair 注册为读档修补步骤，也在新游戏初始化时调用。
    底层调用 commission.fill_vehicles，按配置顺序在表尾为缺失载具追加 (0, 0)，无缺失时不写入。
    Return arguments:
    None -- 直接更新基地载具表
    """
    commission.fill_vehicles()


def hangar_status() -> HangarStatus:
    """
    读取当前机库等级、载具容量上限、载具总持有量与当前龙门币数量。
    总持有量统计载具表中所有条目的持有数之和，包含特殊载具。
    Return arguments:
    HangarStatus -- 当前机库与资金状态快照
    """
    level = facility.level(HANGAR)
    name = game_config.config_facility[HANGAR].name
    effect_cid = game_config.config_facility_effect_data[name][level]
    limit = game_config.config_facility_effect[effect_cid].effect
    owned = sum(count[0] for count in commission.vehicles().values())
    return HangarStatus(level, limit, owned, warehouse.amount(MONEY))


def hangar_text(status: HangarStatus) -> str:
    """
    按机库状态快照拼接三行机库信息说明文本，每行以换行符结尾。
    Keyword arguments:
    status -- HangarStatus，当前机库状态快照
    Return arguments:
    str -- 包含载具用途说明、机库等级与数量、当前龙门币的三行文本
    """
    text = _(
        "○载具用于给执行外勤委托的干员提供交通和其他方面的辅助，提高委托效率\n"
    )
    text += _("○当前机库等级：{0}，载具数量：{1}/{2}\n").format(
        status.level, status.owned, status.limit
    )
    return text + _("○当前龙门币数量：{0}\n").format(status.money)


def listed_vehicles(
    tab: str, sort_by: str, ascending: bool
) -> list[VehicleRow]:
    """
    按标签页筛选并按指定条件稳定排序载具列表。
    常规载具标签保留获得方式为基础的载具，特殊载具标签保留已持有的非基础载具，其他标签保留全部配置载具。
    Keyword arguments:
    tab -- str，标签页名称
    sort_by -- str，排序条件名称，支持持有量、价钱、速度、运载量，其他值按载具编号排序
    ascending -- bool，为 True 时升序，为 False 时降序
    Return arguments:
    list[VehicleRow] -- 筛选并排序后的载具行列表
    """
    vehicles = commission.vehicles()
    rows = []
    for cid, vehicle in game_config.config_vehicle.items():
        owned, out = vehicles[cid]
        basic = vehicle.acquiring == _("基础")
        if tab == _("常规载具") and not basic:
            continue
        if tab == _("特殊载具") and (basic or owned == 0):
            continue
        rows.append(VehicleRow(cid, owned, out))
    keys = {
        _("持有量"): lambda row: row.owned,
        _("价钱"): lambda row: game_config.config_vehicle[row.cid].price,
        _("速度"): lambda row: game_config.config_vehicle[row.cid].speed,
        _("运载量"): lambda row: game_config.config_vehicle[row.cid].capacity,
    }
    rows.sort(key=keys.get(sort_by, lambda row: row.cid), reverse=not ascending)
    return rows


def page_of(rows: list[VehicleRow], page: int, per_page: int) -> VehiclePage:
    """
    对载具行列表计算分页切片与循环翻页目标。
    总页数至少为 1，超出总页数的页码会下调为最后一页，首页的上一页与末页的下一页互相循环。
    Keyword arguments:
    rows -- list[VehicleRow]，完整载具行列表
    page -- int，请求的页码（从 1 开始）
    per_page -- int，每页显示的载具条数
    Return arguments:
    VehiclePage -- 当前页数据与翻页信息
    """
    total = max(1, (len(rows) + per_page - 1) // per_page)
    page = min(page, total)
    start = (page - 1) * per_page
    prev = page - 1 if page > 1 else total
    after = page + 1 if page < total else 1
    return VehiclePage(
        tuple(rows[start : start + per_page]), page, total, prev, after
    )


def row_cells(row: VehicleRow) -> tuple[str, ...]:
    """
    生成载具列表单行的六个原始单元格文本。
    Keyword arguments:
    row -- VehicleRow，单条载具列表数据
    Return arguments:
    tuple[str, ...] -- 依次为名称、外勤中/总持有量、价格、速度、运载量与特殊效果的六元组
    """
    vehicle = game_config.config_vehicle[row.cid]
    return (
        vehicle.name,
        f"{row.out}/{row.owned}",
        str(vehicle.price),
        str(vehicle.speed),
        str(vehicle.capacity),
        vehicle.special,
    )


def trade_status(vehicle_id: int, owned_total: int) -> VehicleTrade:
    """
    计算指定载具在交易页面的资金余量、机库余量及买卖可用状态。
    只有获得方式为基础的载具允许交易，购买需机库未满且龙门币足够，出售需存在闲置载具。
    Keyword arguments:
    vehicle_id -- int，载具编号
    owned_total -- int，调用方传入的当前载具总持有量
    Return arguments:
    VehicleTrade -- 交易页面所需的数量与按钮可用状态
    """
    vehicle = game_config.config_vehicle[vehicle_id]
    owned, out = commission.vehicles()[vehicle_id]
    status = hangar_status()
    money_left = status.money - vehicle.price
    basic = vehicle.acquiring == _("基础")
    return VehicleTrade(
        owned,
        status.money,
        money_left,
        status.limit - owned_total,
        basic and owned_total < status.limit and money_left >= 0,
        basic and owned - out > 0,
    )


def detail_text(vehicle_id: int, trade: VehicleTrade) -> str:
    """
    组装指定载具在购买页面的属性、介绍、持有量与龙门币说明文本。
    介绍文本中的字面转义换行符会展开为换行加六个空格。
    Keyword arguments:
    vehicle_id -- int，载具编号
    trade -- VehicleTrade，该载具的交易页面状态
    Return arguments:
    str -- 载具详情与当前持有信息文本
    """
    vehicle = game_config.config_vehicle[vehicle_id]
    description = vehicle.description
    if "\\n" in description:
        description = description.replace("\\n", "\n      ")
    text = _("\n 载具名称：{0}").format(vehicle.name)
    text += _("\n 载具速度：{0}").format(vehicle.speed)
    text += _("\n 运载量：{0}").format(vehicle.capacity)
    text += _("\n 购入价格：{0}（出售价格为购入的0.8倍）").format(vehicle.price)
    text += _("\n 特殊效果：{0}").format(vehicle.special)
    text += _("\n 介绍：{0}").format(description)
    text += _("\n\n 该载具当前已拥有数量：{0}").format(trade.owned)
    return text + _("\n 当前龙门币数量：{0}").format(trade.money)


def buy_vehicle(vehicle_id: int) -> bool:
    """
    扣除龙门币并购入一辆指定载具，资金不足时不做写入。
    本函数只校验龙门币是否足够，不检查机库上限或获得方式，写入落入当前写缓冲。
    Keyword arguments:
    vehicle_id -- int，载具编号
    Return arguments:
    bool -- 购买成功返回 True，龙门币不足返回 False
    """
    price = game_config.config_vehicle[vehicle_id].price
    if warehouse.amount(MONEY) < price:
        return False
    warehouse.add(MONEY, -price)
    commission.add_vehicle(vehicle_id, owned=1)
    return True


def sell_vehicle(vehicle_id: int) -> int:
    """
    按购入价格的 0.8 倍向下取整回收龙门币，并将指定载具持有量减 1。
    本函数不做前置条件校验，由调用方负责按钮可用性控制，写入落入当前写缓冲。
    Keyword arguments:
    vehicle_id -- int，载具编号
    Return arguments:
    int -- 出售实际获得的龙门币数量
    """
    price = int(game_config.config_vehicle[vehicle_id].price * SELL_RATE)
    warehouse.add(MONEY, price)
    commission.add_vehicle(vehicle_id, owned=-1)
    return price


def settle_vehicle(commision_id: int) -> str:
    """
    结算指定外勤委托派出载具的损坏与归还。
    按委托等级乘以 0.05 作为初始损坏率，逐辆抽取随机数。
    随机数低于当前损坏率时，该载具持有数与外勤中数各减 1，拼接损坏提示并将后续损坏率减半。
    未命中损坏时仅将该载具外勤中数减 1。
    Keyword arguments:
    commision_id -- int，外勤委托编号
    Return arguments:
    str -- 拼接后的载具损坏提示文本，无载具损坏时返回空字符串
    """
    vehicle_text = ""
    send_vehicle_list = commission.ongoing()[commision_id].vehicles
    base_rate = 0.05 * game_config.config_commission[commision_id].level
    for vehicle_id in send_vehicle_list:
        if random.random() < base_rate:
            commission.add_vehicle(vehicle_id, owned=-1, out=-1)
            vehicle_text += _("({0}损坏)").format(
                game_config.config_vehicle[vehicle_id].name
            )
            base_rate *= 0.5
        else:
            commission.add_vehicle(vehicle_id, out=-1)

    return vehicle_text
