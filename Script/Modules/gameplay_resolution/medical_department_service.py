"""
医疗部报表服务（medical_department_service）
============================================
提供医疗部概览、病人状态、药品缓存、待诊、手术、财务与日志的展示文本。
本模块不导入 Script.UI 与 Script.Settle。
"""

from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text
from Script.Modules.domains import identity, medical, medical_patient
from Script.System.Medical_System import medical_constant, medical_service

_: FunctionType = get_text._
""" 翻译函数 """
PENDING_PREVIEW = 6
""" 在诊病人示例最多展示的病例条数（6）。 """
SURGERY_PREVIEW = 8
""" 待手术病人列表最多展示的病例条数（8）。 """
SURGERY_RECORDS = 10
""" 近期手术记录最多展示的条数（10）。 """
RECENT_REPORTS = 3
""" 最近医疗经营日志最多读取的条数（3）。 """


def resource_name(resource_id: int) -> str:
    """
    查询资源编号对应的配置名称，缺省时返回编号字符串。
    Keyword arguments:
    resource_id -- int，资源配置编号
    Return arguments:
    str -- 资源名称或编号字符串
    """
    return getattr(
        game_config.config_resouce.get(resource_id), "name", str(resource_id)
    )


def _patients() -> list[medical_patient.MedicalPatient]:
    """
    汇总当前全部门诊病人与住院病人对象列表。
    Return arguments:
    list[medical_patient.MedicalPatient] -- 先门诊后住院的病人对象列表
    """
    outpatients = medical_service.get_patient_table(hospitalized=False)
    inpatients = medical_service.get_patient_table(hospitalized=True)
    return [*outpatients.values(), *inpatients.values()]


def _state_lines(header: str) -> str:
    """
    按状态枚举顺序统计门诊与住院病人人数并拼接标题行。
    Keyword arguments:
    header -- str，统计区首行标题文本
    Return arguments:
    str -- 含标题与各状态人数的多行文本
    """
    counts = {state: 0 for state in medical_constant.MedicalPatientState}
    for patient in _patients():
        counts[patient.state] += 1
    text = header
    for state, count in counts.items():
        text += (
            f"  {medical_constant.get_state_display_name(state)}：{count} 人\n"
        )
    return text


def waiting_outpatients() -> list[medical_patient.MedicalPatient]:
    """
    筛选门诊表中处于待诊队列状态集合内的病人列表。
    Return arguments:
    list[medical_patient.MedicalPatient] -- 处于待诊队列状态的门诊病人列表
    """
    return [
        patient
        for patient in medical_service.get_patient_table(
            hospitalized=False
        ).values()
        if patient.state in medical_constant.WAITING_QUEUE_STATE_SET
    ]


@medical_service.edits
def overview_text() -> str:
    """
    生成经营概览页的收费策略、医生配置、队列床位与今日收入三行摘要。
    Return arguments:
    str -- 经营概览三行摘要文本
    """
    state = medical.state()
    outpatients = medical_service.get_patient_table(hospitalized=False)
    waiting = len(waiting_outpatients())
    medication = sum(
        1
        for patient in outpatients.values()
        if patient.state
        == medical_constant.MedicalPatientState.WAITING_MEDICATION
    )
    beds = len(medical_service.get_patient_table(hospitalized=True))
    price_ratio = medical_service.get_medical_price_ratio()
    priority = medical_service.get_patient_priority_mode()
    text = _("收费系数：{0:.2f} 倍 | 接诊优先策略：{1}\n").format(
        price_ratio, medical_constant.translate_priority(priority)
    )
    text += _(
        "门诊医生：{0} 人（医疗能力总和 {1}） | 住院医生：{2} 人（医疗能力总和 {3}）\n"
    ).format(
        len(state.clinic_doctor_ids),
        int(state.clinic_doctor_power or 0),
        len(state.hospital_doctor_ids),
        int(state.hospital_doctor_power or 0),
    )
    text += _(
        "门诊排队 {0} 人 | 等待用药 {1} 人 | 住院 {2}/{3} 张床位 | 今日收入 {4} 龙门币\n"
    ).format(
        waiting,
        medication,
        beds,
        int(state.bed_limit),
        int(state.income_today),
    )
    return text


def overview_state_text() -> str:
    """
    生成经营概览页的病人状态统计文本。
    Return arguments:
    str -- 以「病人状态统计：」开头的状态人数文本
    """
    return _state_lines(_("病人状态统计：\n"))


def detail_state_text() -> str:
    """
    生成医疗明细页的病人状态概览文本。
    Return arguments:
    str -- 以「病人状态概览：」开头的状态人数文本
    """
    return _state_lines(_("病人状态概览：\n"))


def overview_cache_text() -> str:
    """
    生成经营概览页的药品扣除缓存文本，缓存为空时附带无记录提示。
    Return arguments:
    str -- 按资源编号升序排列的药品扣除缓存文本
    """
    text = _("药品扣除缓存：\n")
    accumulator = medical.state().accumulator
    if not accumulator:
        return text + _("  暂无扣除记录\n")
    for resource_id, progress in sorted(accumulator.items()):
        text += _("  {0}({1})：{2:.2f}\n").format(
            resource_name(resource_id), resource_id, float(progress)
        )
    return text


def detail_cache_text() -> str:
    """
    生成医疗明细页的药品扣除缓存文本，缓存为空时仅输出标题行。
    Return arguments:
    str -- 按资源编号升序排列的药品扣除缓存文本
    """
    text = _("药品扣除缓存：\n")
    for resource_id, progress in sorted(medical.state().accumulator.items()):
        text += (
            f"  {resource_name(resource_id)}({resource_id})：{progress:.2f}\n"
        )
    return text


def pending_text() -> str:
    """
    按病情等级降序与病例编号升序生成前 6 名待诊门诊病人示例文本。
    Return arguments:
    str -- 在诊病人示例文本，无待诊病人时包含空列表提示
    """
    text = _("在诊病人示例：\n")
    pending = sorted(
        waiting_outpatients(), key=lambda p: (-p.severity_level, p.patient_id)
    )
    for patient in pending[:PENDING_PREVIEW]:
        text += _("  病例#{0} 等级：{1} | 状态：{2} | 并发症数：{3}\n").format(
            patient.patient_id,
            patient.severity_name or str(patient.severity_level),
            medical_constant.get_state_display_name(patient.state),
            len(patient.complications),
        )
    if not pending:
        text += _("  当前无待诊病人\n")
    return text


def surgery_text() -> str:
    """
    统计需手术住院病人总数并按病情等级降序与病例编号升序展示前 8 名。
    Return arguments:
    str -- 待手术病人清单文本，无待手术病人时包含空列表提示
    """
    waiting = sorted(
        (
            patient
            for patient in medical_service.get_patient_table(
                hospitalized=True
            ).values()
            if patient.need_surgery
        ),
        key=lambda p: (-p.severity_level, p.patient_id),
    )
    text = _("待手术病人：{0} 人\n").format(len(waiting))
    for patient in waiting[:SURGERY_PREVIEW]:
        text += _("  病例#{0} 等级：{1} | 阻塞：{2} | 需手术：{3}\n").format(
            patient.patient_id,
            patient.severity_name or str(patient.severity_level),
            patient.last_surgery_result or "-",
            "是" if patient.need_surgery else "否",
        )
    if not waiting:
        text += _("  当前无待手术病人\n")
    return text


def surgery_record_text() -> str:
    """
    生成最近至多 10 条手术记录的展示文本，缺失字段以短横线占位。
    Return arguments:
    str -- 近期手术记录文本，无记录时包含空记录提示
    """
    records = medical.state().surgery_records
    text = _("近期手术记录：\n")
    for record in records[-SURGERY_RECORDS:]:
        doctor = identity.get(record.get("doctor_id", 0))
        text += _("  时间：{0} | 病例#{1} | 医生：{2} | 结果：{3}\n").format(
            str(record.get("time", "-")),
            record.get("patient_id", "-"),
            getattr(doctor, "name", "-") or "-",
            record.get("status", "-"),
        )
    if not records:
        text += _("  暂无手术记录\n")
    return text


def _consumption_text(name: str, value: object) -> str:
    """
    格式化当日药品消耗总计及大于浮点容差的各药剂明细行。
    Keyword arguments:
    name -- str，药品消耗统计项的显示名称
    value -- object，原始药品消耗映射数据
    Return arguments:
    str -- 含总计与分项明细或无记录提示的多行文本
    """
    consumed = (
        medical_constant.MedicalDailyCounters._coerce_consumption_mapping(value)
    )
    total = sum(float(amount or 0.0) for amount in consumed.values())
    text = _("  {0}：总计 {1:.2f} 单位\n").format(name, total)
    details = ""
    for resource_id in sorted(consumed.keys()):
        units = float(consumed.get(resource_id, 0.0) or 0.0)
        if abs(units) <= medical_constant.FLOAT_EPSILON:
            continue
        details += _("    {0}({1})：{2:.2f} 单位\n").format(
            resource_name(resource_id), resource_id, units
        )
    return text + (details or _("    暂无药品消耗记录\n"))


def finance_text() -> str:
    """
    生成财务报表页的今日收入、累计收入与当日各项统计明细文本。
    Return arguments:
    str -- 医疗收入与今日统计多行文本
    """
    state = medical.state()
    text = _("今日医疗收入：{0} 龙门币\n").format(int(state.income_today))
    text += _("累计医疗收入：{0} 龙门币\n").format(int(state.income_total))
    counters = medical_constant.MedicalDailyCounters.from_mapping(
        state.daily_counters
    ).as_dict()
    text += _("今日统计：\n")
    for key, value in counters.items():
        name = medical_constant.DISPLAY_NAME_MAPPING.get(key, key)
        if key == "medicine_consumed":
            text += _consumption_text(name, value)
        else:
            text += _("  {0}：{1}\n").format(name, value)
    return text


def medicine_need_text() -> str:
    """
    汇总除刚刷新（REFRESHED）外全部门诊与住院病人的尚需药品并按编号升序输出。
    Return arguments:
    str -- 待诊与住院病人尚需药品清单文本
    """
    needs: dict[int, float] = {}
    for patient in _patients():
        if patient.state == medical_constant.MedicalPatientState.REFRESHED:
            continue
        for resource_id, amount in patient.need_resources.items():
            needs[resource_id] = needs.get(resource_id, 0.0) + float(amount)
    text = _("待诊/住院病人尚需药品：\n")
    for resource_id, amount in sorted(needs.items()):
        text += _("  {0}({1})：{2:.2f}\n").format(
            resource_name(resource_id), resource_id, amount
        )
    return text


def recent_reports_text() -> str:
    """
    读取并渲染最近至多 3 条医疗经营日志文本，不直接绘制到界面。
    Return arguments:
    str -- 渲染后的近期医疗经营日志或空记录提示文本
    """
    return medical_service.render_medical_reports(
        medical_service.get_recent_medical_reports(limit=RECENT_REPORTS),
        draw_flag=False,
        empty_message=_("\n暂无医疗经营日志记录。\n"),
    )
