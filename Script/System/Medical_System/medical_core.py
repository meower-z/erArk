# -*- coding: UTF-8 -*-
"""医疗系统核心通用工具模块

集中存放医疗系统中多个子模块共用的基础辅助函数，
例如缓存对象查找、病人定位、床位与等级计算等。
"""

from __future__ import annotations

import functools
import math
from collections.abc import Callable

from Script.Config import config_def, game_config
from Script.Modules.domains import (
    economy,
    facility,
    location,
    medical,
    medical_patient,
    warehouse,
)
from Script.System.Medical_System import medical_constant
from Script.Modules.domains import abilities, country
from Script.Modules.domains import identity
from Script.Modules.save_load.legacy_pickle import LegacyObject


def edits[**P, R](fn: Callable[P, R]) -> Callable[P, R]:
    """装饰器：函数在 domains.medical.editing() 块里运行，改医疗部数据的入口函数用它。

    参数:
        fn (Callable): 改医疗部数据的函数。
    返回:
        Callable: 包好的函数。
    """

    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        with medical.editing():
            return fn(*args, **kwargs)

    return wrapper


def _bump_daily_counter(
    key: str,
    value: object,
) -> None:
    """更新医疗日度统计表中的计数。

    参数:
        key (str): 统计字段名称，例如 "hospitalized_today"。
        value (object): 本次需要累加的数值或药品消耗映射。
    返回:
        None: 直接在医疗日度统计对象上写入变更。
    """

    # 获取显性统计结构，若缺失则自动初始化。
    counters = _obtain_daily_counters()

    # 在目标字段累加增量，保持运行期数据一致。
    counters.bump(key, value)


@edits
def _apply_income_to_rhodes(
    income_value: int,
) -> None:
    """为罗德岛医疗系统入账指定收入。

    参数:
        income_value (int): 本次入账的龙门币数值，仅当大于 0 时生效。
    返回:
        None: 无返回值。医疗部的今日与累计收入、龙门币库存加上收入，今日总收入 base.income_today 也加上收入。
    """

    # 收入不合法时直接退出。
    if income_value <= 0:
        return
    # 更新医疗收入字段并累计到全局收益。
    medical.state().income_today += income_value
    medical.state().income_total += income_value
    economy.add_income(income_value)
    # 同步物资仓库中的龙门币库存。
    warehouse.set(1, int(warehouse.stock().get(1, 0) or 0) + income_value)


def _obtain_daily_counters() -> medical_constant.MedicalDailyCounters:
    """返回医疗域的当日统计结构。

    返回:
        medical_constant.MedicalDailyCounters:
            规范化后的统计对象。
    """

    # 读取现有统计字段并在必要时转化为结构体实例。
    raw_value = medical.state().daily_counters
    counters = medical_constant.MedicalDailyCounters.from_mapping(raw_value)

    # 将规范化结果回写至医疗域状态，确保后续访问保持一致。
    medical.state().daily_counters = counters
    return counters


def _locate_patient(
    patient_id: int,
) -> tuple[medical_patient.MedicalPatient | None, bool]:
    """在门诊和住院列表中查找病人，返回病人对象与是否住院标记。

    参数:
        patient_id (int): 目标病人的唯一编号。
    返回:
        Tuple[Optional[medical_patient.MedicalPatient], bool]:
            找到的病人对象以及是否处于住院列表的布尔标记。
    """

    # 先在门诊病人表中查找。
    patient = medical.state().today.get(patient_id)
    if patient is not None:
        return patient, False

    # 再尝试在住院病人表中查找。
    patient = medical.state().hospitalized.get(patient_id)
    if patient is not None:
        return patient, True

    return None, False


def _get_medical_facility_level() -> int:
    """读取医疗部设施等级，缺省返回 0。

    返回:
        int: 医疗部设施等级，缺省为 0。
    """

    return int(facility.level(medical_constant.MEDICAL_FACILITY_ID, 0) or 0)


def _pick_hospital_level_config(
    level: int,
) -> config_def.Medical_Hospital_Level | None:
    """根据设施等级选取对应的医院等级配置。

    参数:
        level (int): 医疗设施等级。
    返回:
        Optional[config_def.Medical_Hospital_Level]: 匹配到的配置实例，若无则为 None。
    """

    # 若配置表为空则直接返回。
    if not game_config.config_medical_hospital_level:
        return None
    # 优先命中完全匹配的等级。
    if level in game_config.config_medical_hospital_level:
        return game_config.config_medical_hospital_level[level]
    # 退而求其次选择不超过目标等级的最大配置。
    eligible = [
        candidate
        for candidate in game_config.config_medical_hospital_level.keys()
        if candidate <= level
    ]
    if eligible:
        return game_config.config_medical_hospital_level[max(eligible)]
    # 若仍未命中则使用最小等级作为兜底。
    minimal = min(game_config.config_medical_hospital_level.keys())
    return game_config.config_medical_hospital_level.get(minimal)


def _calculate_patient_refresh_count(
    level_config: config_def.Medical_Hospital_Level,
) -> int:
    """
    依据医院等级、收费系数与罗德岛所在国家的感染率计算今日应刷新的病人数。

    参数:
        level_config (config_def.Medical_Hospital_Level): 医院等级配置内容。
    返回:
        int: 预计应刷新病人的数量。
    """

    # 读取医院等级配置中的基础病人数，不足时直接返回零。
    base_count = max(int(level_config.daily_patient_base), 0)
    if base_count <= 0:
        return 0

    # 计算收费系数对刷新数量的倍率，确保空值时回落到 1.0。
    price_ratio = float(medical.state().price_ratio or 1.0)
    refresh_multiplier = resolve_price_refresh_multiplier(price_ratio)

    # 叠加国家感染率系数：表里没有当前国家或系数无效时使用 1.0 兜底。
    infection_ratio_table = country.table(country.RATIO)
    # 获取当前国家 ID
    current_country_id = location.country()
    # 获取当前国家的感染人数的影响系数，缺失时默认为 1.0。
    infection_ratio = (
        float(infection_ratio_table.get(current_country_id, 1.0) or 1.0)
        if current_country_id is not None
        else 1.0
    )

    # 汇总三项倍率，取整后返回非负的刷新数量。
    refresh_value = base_count * refresh_multiplier * infection_ratio
    return max(int(math.floor(refresh_value)), 0)


def _calculate_medical_bed_limit() -> int:
    """计算当前医疗部床位上限（基础值 + 兜底当前在院人数）。

    返回:
        int: 计算后的床位上限，至少等于当前在院人数。
    """

    # 根据设施等级查找当前医院等级配置。
    level_config = _pick_hospital_level_config(_get_medical_facility_level())
    base_limit = int(level_config.bed_limit) if level_config else 0
    # 每使用一个模块则提供2个额外床位。
    module_count = int(medical.state().bed_modules or 0) * 3
    # 医生数量提供额外床位加成。
    hospital_bonus = (
        len(medical.state().hospital_doctor_ids or [])
        * medical_constant.HOSPITAL_DOCTOR_BED_BONUS
    )
    total_limit = base_limit + module_count + hospital_bonus
    # 确保床位不低于现有住院人数。
    current_occupancy = len(medical.state().hospitalized)
    return max(total_limit, current_occupancy)


def _calculate_doctor_power(doctor_ids: list[int] | None) -> float:
    """计算医生列表的医疗能力总和，用于缓存字段刷新。

    参数:
        doctor_ids (Optional[list[int]]): 医生编号列表，允许为 None 或空列表。
    返回:
        float: 医疗能力等级的加总结果。
    """

    # 没有医生编号时直接返回零。
    if not doctor_ids:
        return 0.0
    total_power = 0.0
    for doctor_id in doctor_ids:
        if not identity.exists(doctor_id):
            continue
        total_power += float(medical_level(doctor_id) or 0)
    return total_power


def medical_level(cid: int) -> int:
    """
    角色的医疗能力等级（能力编号 medical_constant.MEDICAL_ABILITY_ID）
    Keyword arguments:
    cid -- 角色id
    Return arguments:
    int -- 等级，能力表里没有这一项时为 0
    """
    return abilities.ability(cid).get(medical_constant.MEDICAL_ABILITY_ID, 0)


def _ensure_runtime_dict() -> None:
    """确保医疗运行期字段存在且类型正确。

    返回:
        None: 若字段缺失或类型不符，则按默认值修正。
    """

    # 保证病人、住院与手术记录容器存在且为正确类型。
    medical.state().today = dict(medical.state().today or {})
    medical.state().hospitalized = dict(medical.state().hospitalized or {})
    medical.state().surgery_records = list(
        medical.state().surgery_records or []
    )

    # 校正药品累加器，确保所有资源键都已注册。
    accumulator = dict(medical.state().accumulator or {})
    for resource_id in medical_constant.ALL_MEDICINE_RESOURCE_IDS:
        accumulator.setdefault(resource_id, 0.0)
    medical.state().accumulator = accumulator

    # 转换收入、计数器与日志等字段的类型。
    medical.state().income_today = int(medical.state().income_today or 0)
    medical.state().income_total = int(medical.state().income_total or 0)
    medical.state().daily_counters = (
        medical_constant.MedicalDailyCounters.from_mapping(
            medical.state().daily_counters
        )
    )
    medical.state().recent_reports = list(medical.state().recent_reports or [])
    medical.state().clinic_doctor_ids = list(
        medical.state().clinic_doctor_ids or []
    )
    medical.state().hospital_doctor_ids = list(
        medical.state().hospital_doctor_ids or []
    )
    medical.state().clinic_doctor_power = float(
        medical.state().clinic_doctor_power or 0.0
    )
    medical.state().hospital_doctor_power = float(
        medical.state().hospital_doctor_power or 0.0
    )
    # 处理接诊优先策略，保证值转换为合法枚举。
    priority_value = medical.state().priority_mode
    try:
        resolved_priority = medical_constant.MedicalPatientPriority(
            str(priority_value)
        )
    except ValueError:
        resolved_priority = medical_constant.MedicalPatientPriority.NORMAL
    medical.state().priority_mode = resolved_priority.value


def _resolve_default_price_ratio() -> float:
    """返回收费系数的默认值，默认 1.0。

    返回:
        float: 收费系数默认值。
    """
    return 1.0


def clamp(
    value: float, min_value: float | None, max_value: float | None
) -> float:
    """带上下限的数值夹取，None 表示不限制。

    参数:
        value (float): 原始数值。
        min_value (Optional[float]): 允许的最小值，None 表示无下限。
        max_value (Optional[float]): 允许的最大值，None 表示无上限。
    返回:
        float: 夹取后的结果。
    """

    # 按照下限约束数值。
    result = value
    if min_value is not None:
        result = max(result, float(min_value))
    # 再按上限约束数值。
    if max_value is not None:
        result = min(result, float(max_value))
    return result


def _pick_price_config(price_ratio: float) -> list[float]:
    """根据收费系数计算刷新倍率与收入倍率。

    参数:
        price_ratio (float): 当前收费系数。
    返回:
        List[float]: 包含刷新倍率与收入倍率的列表。
    """

    # 计算收费系数偏离 1.0 的幅度，并转换为步数。
    delta = price_ratio - 1.0
    steps = int(abs(delta) / 0.05)

    # 正偏时刷新倍率递减，负偏时递增。
    refresh_multiplier = 1.0
    if delta > 0:
        for _ in range(steps):
            refresh_multiplier *= 0.92
    elif delta < 0:
        for _ in range(steps):
            refresh_multiplier *= 1.08

    # 收入倍率与刷新倍率相反，正偏增长、负偏衰减。
    income_multiplier = 1.0
    if delta > 0:
        for _ in range(steps):
            income_multiplier *= 1.05
    elif delta < 0:
        for _ in range(steps):
            income_multiplier *= 0.95

    return [refresh_multiplier, income_multiplier]


def resolve_price_refresh_multiplier(price_ratio: float) -> float:
    """根据收费系数找到刷新倍率，若配置缺失返回 1.0。

    参数:
        price_ratio (float): 当前收费系数。
    返回:
        float: 刷新倍率，缺省为 1.0。
    """

    # 获取倍率配置并返回刷新倍率分量。
    config = _pick_price_config(price_ratio)
    if not config:
        return 1.0
    return config[0]


def resolve_price_income_multiplier(price_ratio: float) -> float:
    """根据收费系数找到收入倍率，若配置缺失返回 1.0。

    参数:
        price_ratio (float): 当前收费系数。
    返回:
        float: 收入倍率，缺省为 1.0。
    """

    # 获取倍率配置并返回收入倍率分量。
    config = _pick_price_config(price_ratio)
    if not config:
        return 1.0
    return config[1]


def _migrate_legacy_income(rhodes_island: LegacyObject) -> None:
    """
    导入旧存档中的医疗收入字段。

    参数:
        rhodes_island (LegacyObject): 读档载入的旧存档罗德岛对象。
    返回:
        None: 将旧存档的医疗收入写入医疗域状态，无返回值。
    """

    # 读取旧字段数值并写入新字段。
    legacy_total = medical.state().income_total
    legacy_today = medical.state().income_today
    medical.state().income_total = int(legacy_total or 0)
    medical.state().income_today = int(legacy_today or 0)

    # 兼容更旧的 medical_income 字段。
    if hasattr(rhodes_island, "medical_income"):
        legacy_income = int(getattr(rhodes_island, "medical_income", 0) or 0)
        medical.state().income_total = max(
            medical.state().income_total, legacy_income
        )
