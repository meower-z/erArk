"""
基地动力的发电、耗电与每日结算
==============================
理论发电量与耗电量、蓄电池自放电、人力发电的电量和一天的动力结算。
设施、储能与供电策略经 power 模块读写。燃料库存（资源15）在罗德岛缓存上直接扣除。
"""

import random
from types import FunctionType
from typing import TypedDict

from Script.Config import game_config
from Script.Core import cache_control, get_text
from Script.Design import handle_ability
from Script.Modules.domains import facility, power

_: FunctionType = get_text._


class FireDetail(TypedDict):
    """火力发电的理论值与中间量，fire_detail 的结果"""

    fuel_daily_plan: float
    """ 一天计划燃烧的燃料量 """
    eff_per_fuel: float
    """ 单位燃料的发电量 """
    operator_bonus: float
    """ 调控员系数，为火力的调控员加成加 1 """
    theory_total: float
    """ 一天的理论火力发电量 """


class Day(TypedDict):
    """一天的动力结算，settle_day 的结果"""

    fuel_plan: float
    """ 计划燃烧的燃料量 """
    fuel_use: float
    """ 实际燃烧的燃料量 """
    fire_power: float
    """ 火力发电量，按实际燃料占计划的比例折算 """
    clean: tuple[int, ...]
    """ 三类清洁能源设施的数量 """
    clean_power: float
    """ 清洁能源发电量 """
    generated: float
    """ 总发电量 """
    consumed: float
    """ 总耗电量 """
    short: bool
    """ 发电量少于耗电量 """
    gap: float
    """ 缺口电量，不 short 时为 0 """
    drawn: float
    """ 从蓄电池补进缺口的电量，不 short 时为 0 """
    remain_gap: float
    """ 补后仍缺的电量，不 short 时为 0 """
    shortage_ratio: float
    """ 仍缺的电量占耗电量的比例，没有仍缺的电量时为 0 """
    discharged: float
    """ 自放电损失的电量，short 时为 0 """
    discharge_rate: float
    """ 自放电量占放电前储能的比例，short 时为 0 """
    after_discharge: float | int
    """ 自放电后的储能，short 时为 0 """
    surplus: float
    """ 过剩电量，short 时为 0 """
    charged: float
    """ 充进蓄电池的电量，short 时为 0 """
    overflow: float
    """ 充不下而浪费的电量，short 时为 0 """
    storage: float | int
    """ 结算后的储能 """
    storage_max: int
    """ 最大储能 """


def operator_bonus(kind: int = -1) -> float:
    """
    供能调控员的效率加成。每人的值为能力48的修正减 1 再减半，不是主调控员的再除以 5
    指定 kind 时，别类的主调控员记 0
    Keyword arguments:
    kind -- -1 全部，0 火力，1 水力，2 风力，3 光伏
    Return arguments:
    float -- 各人之和，小于 0 时为 0，保留 1 位小数
    """
    mains = power.plant()["main_operators"]
    total: float = 0
    for chara_id in power.operator_ids():
        try:
            ability = cache_control.cache.character_data[chara_id].ability[48]
            value = handle_ability.get_ability_adjust(ability) - 1
        except Exception:
            value = handle_ability.get_ability_adjust(0) - 1
        value /= 2
        if chara_id not in mains:
            value = value / 5
        elif kind != -1 and chara_id != mains[kind]:
            value = 0
        total += value
    return round(max(total, 0), 1)


def _generation(category: str, level: int, default: float) -> float:
    try:
        cid = game_config.config_power_generation_level_index.get(
            category, {}
        ).get(level)
        if cid:
            return float(game_config.config_power_generation[cid].value)
    except Exception:
        pass
    return default


def fire_detail() -> FireDetail:
    """
    一天的理论火力发电量与中间量，不看燃料库存
    燃料量为副反应炉数量乘单台燃料。发电量为燃料量乘主反应炉等级的单位燃料发电量，再乘调控员系数
    Return arguments:
    FireDetail -- 燃料量与发电量保留 2 位小数，单位燃料发电量与系数保留 4 位小数
    """
    level = power.main_reactor_level()
    op_bonus = operator_bonus(0) + 1
    eff_per_fuel = _generation(_("主反应炉"), level, 5 + 2 * max(level - 1, 0))
    fuel = power.plant()["aux_reactors"] * _generation(_("副反应炉"), 1, 10)
    total = fuel * eff_per_fuel * op_bonus
    return {
        "fuel_daily_plan": round(fuel, 2),
        "eff_per_fuel": round(eff_per_fuel, 4),
        "operator_bonus": round(op_bonus, 4),
        "theory_total": round(total, 2),
    }


def fire_generation() -> float:
    """
    一天的理论火力发电量
    Return arguments:
    float -- 保留 2 位小数
    """
    return fire_detail()["theory_total"]


def clean_generation(kind: int = -1) -> float:
    """
    一天的理论清洁能源发电量。每类为设施数乘该类 3 级的单组发电量，再乘该类的调控员系数
    罗德岛行驶中时水力与风力为 0
    Keyword arguments:
    kind -- -1 三类之和，0 水力，1 风力，2 光伏
    Return arguments:
    float -- 保留 2 位小数
    """
    base = []
    for category, fallback in (
        (_("水力"), 60),
        (_("风力"), 40),
        (_("光伏"), 30),
    ):
        cid = game_config.config_power_generation_level_index.get(
            category, {}
        ).get(3)
        try:
            if cid is not None and cid in game_config.config_power_generation:
                base.append(
                    float(game_config.config_power_generation[cid].value)
                )
            else:
                base.append(fallback)
        except Exception:
            base.append(fallback)
    values = [
        count * base[i] * (operator_bonus(i + 1) + 1)
        for i, count in enumerate(power.plant()["clean"])
    ]
    if cache_control.cache.rhodes_island.move_target_and_time[0] != 0:
        values[0] = values[1] = 0
    if kind in (0, 1, 2):
        return round(values[kind], 2)
    return round(values[0] + values[1] + values[2], 2)


def power_generation() -> float:
    """
    火力与清洁能源的一天理论发电量之和
    Return arguments:
    float -- 保留 1 位小数
    """
    return round(float(fire_generation()) + clean_generation(), 1)


def zone_adjust(zone_cid: int) -> float:
    """
    区块当前供电策略的耗电系数
    Keyword arguments:
    zone_cid -- 区块id
    Return arguments:
    float -- 系数，策略配置里没有或换不成数时为 1.0
    """
    strategy = game_config.config_supply_strategy.get(
        power.strategy_of(zone_cid)
    )
    if strategy:
        try:
            return float(strategy.adjust)
        except Exception:
            return 1.0
    return 1.0


def zone_consumption(zone_cid: int) -> float:
    """
    区块一天的理论耗电量，为区块本身与所属设施在当前等级下的耗电乘区块策略的耗电系数
    Keyword arguments:
    zone_cid -- 区块id
    Return arguments:
    float -- 保留 2 位小数
    """
    levels = facility.levels()
    adjust = zone_adjust(zone_cid)
    total = 0.0
    zone = game_config.config_facility.get(zone_cid)
    zone_name = getattr(zone, "name", "") if zone else ""
    for facility_cid, facility_data in game_config.config_facility.items():
        try:
            if facility_data.type == -1 and facility_cid != zone_cid:
                continue
        except Exception:
            continue
        if not (
            facility_cid == zone_cid
            or (zone_name and zone_name in facility_data.name)
            or facility_data.type == zone_cid
        ):
            continue
        level = levels.get(facility_cid, 1)
        try:
            effect_cid = game_config.config_facility_effect_data[
                facility_data.name
            ][level]
            use = game_config.config_facility_effect[effect_cid].power_use
        except Exception:
            continue
        total += use * adjust
    return round(total, 2)


def power_consumption() -> float:
    """
    全部区块一天的理论耗电量之和，各区块已乘它的策略系数
    Return arguments:
    float -- 保留 2 位小数
    """
    total = 0.0
    for facility_cid, facility_data in game_config.config_facility.items():
        try:
            if facility_data.type == -1:
                total += zone_consumption(facility_cid)
        except Exception:
            continue
    return round(total, 2)


def self_discharge() -> tuple[float, float]:
    """
    蓄电池一天的自放电，放掉的电量从储能里扣除，储能不低于 0
    从 1 级到 3 级逐台计算。每台按单体容量乘自放电率，剩余储能不足一台容量时按剩余储能算
    Return arguments:
    tuple -- (放电量，保留 2 位小数, 放电量占放电前储能的比例，保留 4 位小数)
             没有储能或没有蓄电池时为 (0.0, 0.0)
    """
    before = power.storage()
    batteries = power.plant()["batteries"]
    if before <= 0 or sum(batteries) == 0:
        return 0.0, 0.0
    caps = power.storage_levels("电池容量", float, 0.0)
    rates = power.storage_levels("自放电率", float, 0.0)
    remaining = float(before)
    total = 0.0
    for level, count in enumerate(batteries):
        for _unit in range(int(count)):
            if remaining <= 0:
                break
            if remaining >= caps[level]:
                total += caps[level] * rates[level]
                remaining -= caps[level]
            else:
                total += remaining * rates[level]
                remaining = 0
        if remaining <= 0:
            break
    rate = total / float(before)
    power.set_storage(max(0.0, before - total))
    return round(total, 2), round(rate, 4)


def human_power(climax_degree: int, character_id: int) -> float | None:
    """
    一次人力发电的电量，按绝顶程度查发电配置里人力一类
    程度 5 及以上为程度 4 的电量乘 4 的（程度 - 4）次方。玩家（角色id 0）的电量再乘 10
    Keyword arguments:
    climax_degree -- 绝顶程度，1 小，2 普，3 强，4 超，5 及以上为多重绝顶
    character_id -- 角色id
    Return arguments:
    float | None -- 电量。程度不大于 0，或配置里没有这一程度（1 到 4）时为 None
    """
    table = game_config.config_power_generation_level_index.get(_("人力"), {})
    if climax_degree <= 0:
        return None
    if climax_degree >= 5:
        amount = game_config.config_power_generation[table.get(4, 0)].value * (
            4 ** (climax_degree - 4)
        )
    else:
        cid = table.get(climax_degree, 0)
        if not cid or cid not in game_config.config_power_generation:
            return None
        amount = game_config.config_power_generation[cid].value
    return amount * 10 if character_id == 0 else amount


def settle_day() -> Day:
    """
    结算一天的动力。按燃料库存烧燃料发火电，清洁能源每类乘 0.8 到 1.2 的随机数，再与耗电比较
    比较前储能先降到不超过最大储能。燃料从资源15的库存扣除，储能经 power 写入
    发电不足时从蓄电池补，补不上的部分计入缺口比例。发电有余时先自放电，再把过剩电量充进蓄电池，充不下的溢出
    Return arguments:
    Day -- 这一天的各项数值
    """
    island = cache_control.cache.rhodes_island
    detail = fire_detail()
    fuel_plan = detail["fuel_daily_plan"]
    fuel_have = island.materials_resouce.get(15, 0)
    fuel_use = min(fuel_plan, float(fuel_have))
    island.materials_resouce[15] = int(max(0, fuel_have - int(fuel_use)))
    fire_power = round(
        (
            detail["theory_total"] * (fuel_use / fuel_plan)
            if fuel_plan > 0
            else 0.0
        ),
        2,
    )
    clean_power = round(
        sum(
            clean_generation(kind) * random.uniform(0.8, 1.2)
            for kind in (0, 1, 2)
        ),
        2,
    )
    generated = round(fire_power + clean_power, 2)
    consumed = round(power_consumption(), 2)
    power.clamp_storage()
    top = power.storage_max()
    day: Day = {
        "fuel_plan": fuel_plan,
        "fuel_use": fuel_use,
        "fire_power": fire_power,
        "clean": power.plant()["clean"],
        "clean_power": clean_power,
        "generated": generated,
        "consumed": consumed,
        "short": generated + 1e-6 < consumed,
        "gap": 0.0,
        "drawn": 0.0,
        "remain_gap": 0.0,
        "shortage_ratio": 0.0,
        "discharged": 0.0,
        "discharge_rate": 0.0,
        "after_discharge": 0.0,
        "surplus": 0.0,
        "charged": 0.0,
        "overflow": 0.0,
        "storage": 0.0,
        "storage_max": top,
    }
    if day["short"]:
        gap = consumed - generated
        drawn = min(gap, power.storage())
        power.set_storage(power.storage() - drawn)
        remain = gap - drawn
        day["gap"], day["drawn"], day["remain_gap"] = gap, drawn, remain
        if remain > 1e-6:
            day["shortage_ratio"] = remain / consumed if consumed > 0 else 0
    else:
        discharged, rate = self_discharge()
        after = power.storage()
        surplus = generated - consumed
        charged = min(surplus, max(0.0, top - after))
        power.set_storage(after + charged)
        day["discharged"], day["discharge_rate"] = discharged, rate
        day["after_discharge"], day["surplus"] = after, surplus
        day["charged"], day["overflow"] = charged, surplus - charged
    day["storage"] = power.storage()
    return day
