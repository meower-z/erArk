"""
动力系统面板服务（power_panel_service）
=======================================
提供动力系统管理面板的纯查询、文案组装与写入封装，不绘制界面，
也不导入 Script.UI、Script.Settle 或 Tk 模块。
常量：POWER_ZONE、STRATEGY_COUNT、FUEL、AUX_MODULE、
BATTERY_MODULE、CLEAN_MODULE、CRAFT、LOW_FUEL_DAYS。
数据类：Zone、Operator、CleanRow、BatteryRow。
函数：zones、step_strategy、chara_name、main_operators、
assistants、candidates、fuel_text、plant_modules_text、
battery_modules_text、change_clean、change_battery、
main_efficiency、aux_fuel、aux_adjustable、clean_rows、battery_rows。
"""

from dataclasses import dataclass
from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text
from Script.Modules.domains import abilities, facility, identity, location
from Script.Modules.domains import power, power_supply, warehouse

_: FunctionType = get_text._
""" 翻译api """

POWER_ZONE = 1
""" 动力区对应的设施编号。 """
STRATEGY_COUNT = 5
""" 供电策略循环切换的策略总数。 """
FUEL = 15
""" 燃料对应的罗德岛资源编号。 """
AUX_MODULE = 51
""" 副源石反应炉扩展模块对应的罗德岛资源编号。 """
BATTERY_MODULE = 52
""" 蓄电池通用扩展模块对应的罗德岛资源编号。 """
CLEAN_MODULE = 53
""" 清洁能源通用扩展模块对应的罗德岛资源编号。 """
CRAFT = 48
""" 调控员界面显示的制造能力编号。 """
LOW_FUEL_DAYS = 3
""" 燃料库存不足预警的天数阈值，低于该天数时追加警告。 """


@dataclass(frozen=True, slots=True)
class Zone:
    """供电策略列表中的单个区块条目，包含区块编号 cid、名称 name、策略标签 strategy 与耗电量 consumption。"""

    cid: int
    name: str
    strategy: str
    consumption: float


@dataclass(frozen=True, slots=True)
class Operator:
    """调控员展示条目，包含角色编号 chara_id、显示名称 name 与可选制造等级 craft。"""

    chara_id: int
    name: str
    craft: int | None


@dataclass(frozen=True, slots=True)
class CleanRow:
    """清洁能源设施展示行，包含设施数量 count、单组日理论产出 output 与是否可用标志 usable。"""

    count: int
    output: float
    usable: bool


@dataclass(frozen=True, slots=True)
class BatteryRow:
    """蓄电池等级展示行，包含数量 count、单台容量 capacity、日自放电率 rate 与是否可用标志 usable。"""

    count: int
    capacity: int
    rate: float
    usable: bool


def zones() -> list[Zone]:
    """
    按设施配置顺序收集非动力区区块的供电策略与耗电，
    跳过读取 type 异常或 type 不为 -1 的条目。
    Return arguments:
    list[Zone] -- 各区块的名称、策略百分比标签与耗电量列表
    """
    supply = game_config.config_supply_strategy
    rows = []
    for cid, data in game_config.config_facility.items():
        try:
            if data.type != -1:
                continue
        except Exception:
            continue
        if cid == POWER_ZONE:
            continue
        now = supply[power.strategy_of(cid)]
        label = f"{now.name}({int(now.adjust * 100)}%)"
        rows.append(
            Zone(cid, data.name, label, power_supply.zone_consumption(cid))
        )
    return rows


def step_strategy(cid: int, step: int) -> None:
    """
    按指定步长循环调整单个区块的供电策略，对 STRATEGY_COUNT 取模后写入 power.set_strategy。
    Keyword arguments:
    cid -- int，目标区块的设施编号
    step -- int，策略步进偏移量（如 1 或 -1）
    Return arguments:
    None -- 无返回值
    """
    power.set_strategy(cid, (power.strategy_of(cid) + step) % STRATEGY_COUNT)


def chara_name(chara_id: int) -> str:
    """
    查询角色用于动力面板的显示名称。
    角色编号为 0 时返回空串，不存在或查询异常时回退为干员加编号。
    Keyword arguments:
    chara_id -- int，角色编号
    Return arguments:
    str -- 角色显示名称或回退文案
    """
    if chara_id == 0:
        return ""
    try:
        chara = identity.get(chara_id)
        if chara and hasattr(chara, "name"):
            return str(chara.name)
    except Exception:
        pass
    return _("干员") + str(chara_id)


def _craft(chara_id: int) -> int:
    """
    读取指定角色的制造能力（编号 48）等级，缺少该能力时返回 0。
    Keyword arguments:
    chara_id -- int，角色编号
    Return arguments:
    int -- 制造能力等级
    """
    return abilities.ability(chara_id).get(CRAFT, 0)


def main_operators() -> list[Operator]:
    """
    按火、水、风、光顺序返回四个主调控员槽位的展示条目，
    空缺槽位（编号 0）名称为空且制造等级为 None。
    Return arguments:
    list[Operator] -- 四个主调控员槽位对应的条目列表
    """
    return [
        Operator(cid, chara_name(cid), _craft(cid) if cid != 0 else None)
        for cid in power.plant()["main_operators"]
    ]


def assistants() -> list[Operator]:
    """
    按供能调控员名册顺序收集未担任主调控员的辅助调控员条目。
    名称为空时回退为 (未知)，角色不存在时制造等级为 None。
    Return arguments:
    list[Operator] -- 辅助调控员展示条目列表
    """
    mains = power.plant()["main_operators"]
    rows = []
    for cid in power.operator_ids():
        if cid in mains:
            continue
        chara = identity.get(cid)
        craft = _craft(chara.cid) if chara else None
        rows.append(Operator(cid, chara_name(cid) or _("(未知)"), craft))
    return rows


def candidates() -> list[int]:
    """
    返回可被任命为主调控员的角色编号列表，即供能调控员名册中排除玩家（编号 0）后的结果。
    Return arguments:
    list[int] -- 候选干员角色编号列表
    """
    return [cid for cid in power.operator_ids() if cid != 0]


def _sailing() -> bool:
    """
    判断罗德岛当前是否处于行驶中。
    Return arguments:
    bool -- location.move() 非空时为 True，否则为 False
    """
    return location.move() is not None


def _level() -> int:
    """
    读取动力区（设施 1）的当前等级，无记录时默认返回 1。
    Return arguments:
    int -- 动力区等级
    """
    return facility.level(POWER_ZONE, 1)


def fuel_text() -> str:
    """
    组装发电设施页面的燃料库存与预警文案。
    按库存除以日计划消耗向下取整算天数（日耗不大于 1e-6 时取 9999），
    低于 LOW_FUEL_DAYS 或行驶中时追加对应警告。
    Return arguments:
    str -- 包含燃料状态与可选警告的多行本地化文本
    """
    stock = warehouse.stock().get(FUEL, 0)
    daily = power_supply.fire_detail()["fuel_daily_plan"]
    days = int(stock // daily) if daily > 1e-6 else 9999
    text = _(
        "  当前燃料库存: {0} 单位，每日计划消耗 {1:.1f} 单位，约可支持 {2} 天\n"
    ).format(stock, daily, days)
    if days < LOW_FUEL_DAYS:
        text += _("！燃料库存不足3天，建议尽快前往贸易区采购补充！\n")
    if _sailing():
        text += _("！当前罗德岛处于行驶中，水力与风力发电设施无法工作！\n")
    return text


def plant_modules_text() -> str:
    """
    组装副源石反应炉与清洁能源通用扩展模块的已用和总上限文案，区块基础额为动力区等级乘 2 加 3。
    Return arguments:
    str -- 两行扩展模块统计的本地化文本
    """
    base = _level() * 2 + 3
    plant = power.plant()
    aux = _(
        "  副源石反应炉扩展模块 ：已用 {0} / 总 {1} （含区块等级提供的{2}）\n"
    ).format(plant["aux_reactors"], warehouse.amount(AUX_MODULE) + base, base)
    clean = _(
        "  清洁能源通用扩展模块 ：已用 {0} / 总 {1} （含区块等级提供的{2}）\n"
    ).format(sum(plant["clean"]), warehouse.amount(CLEAN_MODULE) + base, base)
    return aux + clean


def battery_modules_text() -> str:
    """
    组装蓄电池通用扩展模块的已用和总上限文案，区块基础额为动力区等级乘 2 加 8。
    Return arguments:
    str -- 单行蓄电池模块统计的本地化文本
    """
    base = _level() * 2 + 8
    total = warehouse.amount(BATTERY_MODULE) + base
    return _(
        "  蓄电池通用扩展模块 ：已用 {0} / 总 {1} （含区块等级提供的{2}）\n"
    ).format(sum(power.plant()["batteries"]), total, base)


def change_clean(kind: int, delta: int) -> str | None:
    """
    调用 power.change_clean 增减指定类型清洁能源设施，增加触达上限时返回本地化提示文本。
    Keyword arguments:
    kind -- int，清洁能源类型下标（0 水力、1 风力、2 光伏）
    delta -- int，增减步长（1 或 -1）
    Return arguments:
    str | None -- 触达上限时返回提示文本，否则返回 None
    """
    limit = power.change_clean(kind, delta)
    if limit is None:
        return None
    return _(
        "三种清洁能源设施总数已达上限({0})，可通过生产清洁能源模块扩展上限"
    ).format(limit)


def change_battery(level: int, delta: int) -> str | None:
    """
    调用 power.change_battery 增减指定等级蓄电池，增加触达上限时返回本地化提示文本。
    Keyword arguments:
    level -- int，蓄电池等级下标（0 为 L1、1 为 L2、2 为 L3）
    delta -- int，增减步长（大于 0 为增加，否则为减少）
    Return arguments:
    str | None -- 触达上限时返回提示文本，否则返回 None
    """
    limit = power.change_battery(level, delta)
    if limit is None:
        return None
    return _("蓄电池总数已达上限({0})，可通过生产蓄电池扩展上限").format(limit)


def _generation(category: str, level: int) -> float:
    """
    按发电类别与等级从发电配置表查询对应数值并转为浮点数。
    Keyword arguments:
    category -- str，发电配置表中的类别名称
    level -- int，目标配置等级
    Return arguments:
    float -- 配置表中的浮点数值
    """
    index = game_config.config_power_generation_level_index
    return float(
        game_config.config_power_generation[index[category][level]].value
    )


def main_efficiency() -> int:
    """
    查询主源石反应炉在当前等级下的单位燃料发电效率。
    Return arguments:
    int -- 主反应炉单位燃料发电量
    """
    return int(_generation(_("主反应炉"), power.main_reactor_level()))


def aux_fuel() -> int:
    """
    查询单台副源石反应炉（等级 1 配置）的每日燃料消耗量。
    Return arguments:
    int -- 单台副反应炉日耗燃料量
    """
    return int(_generation(_("副反应炉"), 1))


def aux_adjustable() -> bool:
    """
    判断当前动力区等级是否允许调整副源石反应炉数量（需达到 2 级）。
    Return arguments:
    bool -- 动力区等级大于等于 2 时返回 True，否则返回 False
    """
    return _level() >= 2


def clean_rows() -> list[CleanRow]:
    """
    按水力、风力、光伏、人力顺序组装清洁能源设施展示行。
    读取 3 级配置理论产出并按动力区等级与行驶状态判定可用性，
    不可用行理论产出置为 0.0，人力行数量为 0。
    Return arguments:
    list[CleanRow] -- 四类清洁能源设施的展示行列表
    """
    level = _level()
    sailing = _sailing()
    clean = power.plant()["clean"]
    rows = []
    categories = (_("水力"), _("风力"), _("光伏"), _("人力"))
    for kind, category in enumerate(categories):
        output = _generation(category, 3)
        usable = not (
            (sailing and kind in (0, 1))
            or (kind == 1 and level < 4)
            or (kind == 2 and level < 5)
        )
        count = clean[kind] if kind < len(clean) else 0
        rows.append(CleanRow(count, output if usable else 0.0, usable))
    return rows


def battery_rows() -> list[BatteryRow]:
    """
    按 L1、L2、L3 顺序组装蓄电池展示行，读取数量、单体容量与自放电率，
    按动力区等级判定可用性（L2 需 3 级，L3 需 4 级）。
    Return arguments:
    list[BatteryRow] -- 三级蓄电池的展示行列表
    """
    level = _level()
    caps = power.storage_levels(_("电池容量"), int, 0)
    rates = power.storage_levels(_("自放电率"), float, 0.0)
    batteries = power.plant()["batteries"]
    usable = (True, level >= 3, level >= 4)
    return [
        BatteryRow(batteries[i], caps[i], rates[i], usable[i]) for i in range(3)
    ]
