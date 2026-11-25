"""
医疗部管理服务（medical_management_service）
============================================
提供医疗部医生管理、科室分配、接诊策略文本及收费系数调整计算。
本模块不导入 Script.UI 与 Script.Settle。
"""

from dataclasses import dataclass
from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text
from Script.Design import attr_calculation, handle_ability
from Script.Modules.domains import abilities, facility, identity, medical
from Script.Modules.gameplay_resolution import medical_department_service
from Script.System.Medical_System import medical_constant, medical_service

_: FunctionType = get_text._
""" 翻译函数 """
HOSPITAL_SPECIALTY_LEVEL = 3
""" 解锁住院医生分科展示所需的最低医疗设施等级（3）。 """
MIN_DOCTOR_SPEED = 0.25
""" 单名门诊医生诊疗速度及总速度的下限值（0.25）。 """
MIN_PRICE_RATIO = 0.10
""" 收费系数调整允许的最低下限值（0.10）。 """


@dataclass(frozen=True)
class SpecialtyRow:
    """单个医疗分科在医生管理页中的展示行数据。"""

    category_key: str
    """ 分科配置键值，用作分配操作的科室标识。 """
    summary: str
    """ 科室名称补齐 16 列宽后拼接人数与平均倍率的摘要文本。 """
    return_text: str
    """ 该科室分配按钮的返回值文本。 """
    doctors: str
    """ 以冒号开头的分科医生列表文本，无人时为「：空缺」。 """


@dataclass(frozen=True)
class AssignTarget:
    """医生分科分配流程所需的岗位、科室名称与已分配医生集合。"""

    role_key: str
    """ 目标岗位键值（门诊或住院）。 """
    category_key: str
    """ 目标分科键值。 """
    role_name: str
    """ 目标岗位的中文显示名称。 """
    category_name: str
    """ 目标分科的显示名称，未命中配置时回退为键值。 """
    assigned_ids: frozenset[int]
    """ 当前已分配至该分科的医生角色编号不可变集合。 """


def estimate_remaining_hours() -> float:
    """
    按待诊门诊病人剩余工时总和与门诊医生速度总和估算完成耗时。
    Return arguments:
    float -- 预计完成全部待诊门诊所需小时数
    """
    remaining = 0.0
    for patient in medical_department_service.waiting_outpatients():
        severity = game_config.config_medical_severity.get(
            patient.severity_level
        )
        if severity is None:
            continue
        base_hours = float(severity.base_hours)
        remaining += max(base_hours - float(patient.diagnose_progress), 0.0)
    speed = 0.0
    for doctor_id in medical.state().clinic_doctor_ids:
        character = identity.get(doctor_id)
        if character is None:
            continue
        level = abilities.ability(character.cid).get(
            medical_constant.MEDICAL_ABILITY_ID, 0
        )
        speed += max(
            float(handle_ability.get_ability_adjust(level)), MIN_DOCTOR_SPEED
        )
    if speed <= 0:
        speed = MIN_DOCTOR_SPEED
    return remaining / speed


def doctor_text() -> str:
    """
    生成医生管理页的门诊与住院人数、能力总和、床位占用及预计耗时文本。
    Return arguments:
    str -- 医生管理页顶部四行状态文本
    """
    state = medical.state()
    clinic = medical_service.list_role_doctors(
        medical_constant.SPECIALIZATION_ROLE_CLINIC
    )
    hospital = medical_service.list_role_doctors(
        medical_constant.SPECIALIZATION_ROLE_HOSPITAL
    )
    beds = len(medical_service.get_patient_table(hospitalized=True))
    text = _("门诊医生：{0} 人 | 医疗能力总和 {1}\n").format(
        len(clinic), int(state.clinic_doctor_power or 0)
    )
    text += _("住院医生：{0} 人 | 医疗能力总和 {1}\n").format(
        len(hospital), int(state.hospital_doctor_power or 0)
    )
    text += _("床位上限 {0} 张，当前占用 {1} 张\n").format(
        int(state.bed_limit), beds
    )
    text += _("按当前排班预计完成全部门诊耗时约 {0:.2f} 小时\n").format(
        estimate_remaining_hours()
    )
    return text


def priority_text(mode: medical_constant.MedicalPatientPriority) -> str:
    """
    生成当前接诊优先策略的单行展示文本。
    Keyword arguments:
    mode -- medical_constant.MedicalPatientPriority，接诊优先策略枚举值
    Return arguments:
    str -- 形如「当前接诊优先策略：…」的展示文本
    """
    return _("当前接诊优先策略：{0}\n").format(
        medical_constant.translate_priority(mode)
    )


def shows_hospital_specialties() -> bool:
    """
    判断当前医疗设施等级是否达到 3 级以显示住院医生分科区块。
    Return arguments:
    bool -- 设施等级不低于 3 时返回 True，否则返回 False
    """
    level = facility.level(medical_constant.MEDICAL_FACILITY_ID, 0)
    return level >= HOSPITAL_SPECIALTY_LEVEL


def role_name(role_key: str) -> str:
    """
    查询岗位键值对应的中文显示名称，未命中映射时返回原键值。
    Keyword arguments:
    role_key -- str，医生岗位键值
    Return arguments:
    str -- 岗位中文名称或原键值
    """
    return medical_constant.ROLE_DISPLAY_NAME.get(role_key, role_key)


@medical_service.edits
def specialty_rows(role_key: str) -> list[SpecialtyRow]:
    """
    汇总指定岗位各分科的医生人数、平均倍率与成员列表并构造展示行。
    Keyword arguments:
    role_key -- str，医生岗位键值
    Return arguments:
    list[SpecialtyRow] -- 该岗位各分科的展示行对象列表
    """
    rows = []
    for category in medical_service.get_doctor_specialization_overview(
        role_key
    ):
        doctors = [
            _("{0}(Lv{1},x{2:.2f})").format(
                detail.get("name", str(detail.get("id"))),
                detail.get("ability_level", 0),
                detail.get("bonus_multiplier", 1.0),
            )
            for detail in category.get("doctor_details", [])
        ]
        name = category.get("category_name", category.get("category_key", "-"))
        summary = _("  {0}（{1} 人，平均倍率 x{2:.2f}）").format(
            attr_calculation.pad_display_width(name, 16),
            category.get("doctor_count", 0),
            category.get("average_bonus_multiplier", 1.0),
        )
        rows.append(
            SpecialtyRow(
                category.get(
                    "category_key", medical_constant.SPECIALIZATION_GENERAL_KEY
                ),
                summary,
                role_key + _("分配到{0}").format(name),
                _("：{0}").format("、".join(doctors) if doctors else _("空缺")),
            )
        )
    return rows


def specialty_heading(role_key: str) -> str:
    """
    生成指定岗位分科区块的标题行文本。
    Keyword arguments:
    role_key -- str，医生岗位键值
    Return arguments:
    str -- 形如「<岗位名称>科室情况：」的标题文本
    """
    return _("{0}科室情况：\n").format(role_name(role_key))


@medical_service.edits
def assign_target(role_key: str, category_key: str) -> AssignTarget:
    """
    查询指定岗位与分科的显示名称及已分配医生编号并构造分配目标。
    Keyword arguments:
    role_key -- str，医生岗位键值
    category_key -- str，目标分科键值
    Return arguments:
    AssignTarget -- 包含岗位、科室名称与已分配编号集合的目标对象
    """
    category_name = next(
        (
            item["name"]
            for item in medical_service.get_specialization_categories()
            if item.get("key") == category_key
        ),
        category_key,
    )
    assigned: frozenset[int] = frozenset()
    for category in medical_service.get_doctor_specialization_overview(
        role_key
    ):
        if category.get("category_key") == category_key:
            assigned = frozenset(category.get("doctor_ids", []))
            break
    return AssignTarget(
        role_key, category_key, role_name(role_key), category_name, assigned
    )


def assign_prompt(target: AssignTarget) -> str:
    """
    根据分配目标生成干员选择面板顶部的引导提示文本。
    Keyword arguments:
    target -- AssignTarget，医生分科分配目标对象
    Return arguments:
    str -- 引导选择医生分配至目标科室的提示文本
    """
    return _("请选择一名{0}分配至「{1}」：\n").format(
        target.role_name, target.category_name
    )


@medical_service.edits
def assign_doctor(target: AssignTarget, doctor_id: int) -> str:
    """
    将指定医生分配至目标分科并返回操作结果的中文反馈文本。
    Keyword arguments:
    target -- AssignTarget，医生分科分配目标对象
    doctor_id -- int，待分配医生的角色编号
    Return arguments:
    str -- 分配成功或包含失败原因的反馈文本
    """
    result = medical_service.assign_doctor_specialization(
        target.role_key, doctor_id, target.category_key
    )
    if not result.get("success"):
        return _("分配失败：{0}").format(result.get("reason", "unknown"))
    name = getattr(identity.get(doctor_id), "name", str(doctor_id))
    return _("已将 {0} 调整至「{1}」({2})").format(
        name, target.category_name, target.role_name
    )


@medical_service.edits
def price_text() -> str:
    """
    生成收费设置页的当前系数、待生效系数、日刷新预测与倍率说明文本。
    Return arguments:
    str -- 收费设置页多行状态与预测文本
    """
    ratio = medical_service.get_medical_price_ratio()
    pending = medical_service.get_new_medical_price_ratio()
    preview = medical_service.predict_medical_patient_refresh(
        price_ratio=ratio,
        level=facility.level(medical_constant.MEDICAL_FACILITY_ID, 0),
    )
    text = _("当前收费系数：{0:.2f} 倍 ({1:.0f}%)\n").format(ratio, ratio * 100)
    if pending > 0:
        text += _("  └ 待调整系数：{0:.2f} 倍（明日生效）\n").format(pending)
    text += _("预计刷新病人数：{0:.0f} 人/日\n").format(
        preview.get("predicted_count", 0.0)
    )
    text += _("刷新倍率修正：{0:.2f} | 收入倍率：{1:.2f}\n").format(
        preview.get("refresh_multiplier", 1.0),
        preview.get("income_multiplier", 1.0),
    )
    return text + _("收费系数越高，病人刷新量越低，但单次收入越高。\n")


@medical_service.edits
def adjust_price_ratio(delta_percent: int) -> str:
    """
    以待生效系数或当前系数为基准按百分比增减并下限钳制后写入新值。
    Keyword arguments:
    delta_percent -- int，收费系数调整的百分点增量
    Return arguments:
    str -- 告知新收费系数将于明天生效的反馈文本
    """
    pending = medical_service.get_new_medical_price_ratio()
    if pending > 0:
        base = pending
    else:
        base = medical_service.get_medical_price_ratio()
    ratio = max(base + delta_percent / 100.0, MIN_PRICE_RATIO)
    medical_service.set_medical_price_ratio(ratio)
    return _("已调整收费系数至 {0:.2f} 倍，明天生效").format(ratio)


@medical_service.edits
def reset_price_ratio() -> str:
    """
    将明日生效的待调整收费系数重置为 1.0 倍并返回提示文本。
    Return arguments:
    str -- 告知收费系数已重置为 1.00 倍并于明天生效的反馈文本
    """
    medical_service.set_medical_price_ratio(1.0)
    return _("收费系数已重置为 1.00 倍，明天生效")
