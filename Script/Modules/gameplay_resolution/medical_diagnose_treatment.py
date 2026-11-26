"""
玩家诊疗治疗文本服务（medical_diagnose_treatment）
==================================================
提供治疗方案摘要、未确诊折算提示、再检异常线索与药品缺口反馈文本。
本模块不导入 Script.UI 与 Script.Settle。
"""

from types import FunctionType
from typing import Any

from Script.Config import game_config
from Script.Core import get_text
from Script.Modules.domains import medical_patient, warehouse
from Script.Modules.gameplay_resolution import medical_diagnose_service as rules
from Script.Modules.gameplay_resolution.medical_diagnose_view import (
    severity_text,
)
from Script.System.Medical_System import medical_constant
from Script.System.Medical_System import medical_player_diagnose_function

_: FunctionType = get_text._
""" 翻译函数 """


def inventory() -> dict[int, float]:
    """
    读取仓库中各资源的当前库存并转为浮点数映射。
    Return arguments:
    dict[int, float] -- 按资源编号索引的当前库存量字典
    """
    return {
        rid: float(value or 0.0) for rid, value in warehouse.stock().items()
    }


def shortage(rid: int, amount: float, stock: dict[int, float]) -> float:
    """
    计算指定资源需求量相对当前库存的缺口，需求或差值不超过容差时返回 0.0。
    Keyword arguments:
    rid -- int，资源配置编号
    amount -- float，所需资源数量
    stock -- dict[int, float]，当前仓库库存映射
    Return arguments:
    float -- 超过浮点容差的资源缺口值，否则为 0.0
    """
    if amount <= medical_constant.FLOAT_EPSILON:
        return 0.0
    gap = amount - float(stock.get(rid, 0.0) or 0.0)
    return 0.0 if gap <= medical_constant.FLOAT_EPSILON else gap


def quantity(value: float) -> str:
    """
    将资源数量格式化为两位小数字符串，空值或非正数返回 0.00。
    Keyword arguments:
    value -- float，待格式化的资源数量
    Return arguments:
    str -- 两位小数格式的数量文本
    """
    if value is None or value <= 0.0:
        return "0.00"
    return f"{value:.2f}"


def suggestions(
    patient: medical_patient.MedicalPatient, catalog: rules.Catalog
) -> list[str]:
    """
    倒序扫描病人检查记录中的再检条目，按系统与部位去重生成异常线索行列表。
    Keyword arguments:
    patient -- medical_patient.MedicalPatient，当前诊疗的病人对象
    catalog -- rules.Catalog，按系统编号索引的检查目录
    Return arguments:
    list[str] -- 去重后的异常线索说明行列表
    """
    lines: list[str] = []
    seen: set[tuple[int, int]] = set()
    for record in reversed(patient.player_check_records):
        if not isinstance(record, dict) or record.get("result") != "recheck":
            continue
        key = (
            int(record.get("system_id", 0) or 0),
            int(record.get("part_id", 0) or 0),
        )
        if key in seen:
            continue
        seen.add(key)
        system, part = rules.catalog_part(catalog, *key)
        hint = record.get("hint_severity")
        hint = int(hint) if hint is not None else -1
        lines.append(
            _(
                "· {system}/{part} 可能存在{severity}异常，建议改用其他检查。"
            ).format(
                system=str(system.get("system_name", key[0])),
                part=str(part.get("part_name", key[1])),
                severity=severity_text(hint) if hint >= 0 else _("未知等级"),
            )
        )
    return lines


def _resource_lines(resources: list[Any], ratio: float) -> list[str]:
    """
    按折算系数格式化药品需求、缺口与库存明细行列表。
    Keyword arguments:
    resources -- list[Any]，预估摘要中的药品资源条目列表
    ratio -- float，结合未确诊并发症折算后的用量系数
    Return arguments:
    list[str] -- 以药品需求标题开头的多行明细列表
    """
    stock = inventory()
    lines = [_("药品需求：")]
    for item in resources:
        amount = float(item.get("amount", 0.0) or 0.0) * ratio
        try:
            rid = int(item.get("resource_id", 0) or 0)
        except (TypeError, ValueError):
            rid = 0
        lines.append(
            _(
                "  · {name} × {amount}（缺口 {shortage} 单位，库存 {stock} 单位）"
            ).format(
                name=item.get("name", "-"),
                amount=quantity(amount),
                shortage=quantity(shortage(rid, amount, stock)),
                stock=quantity(float(stock.get(rid, 0.0) or 0.0)),
            )
        )
    return lines


def treatment_text(
    patient: medical_patient.MedicalPatient, catalog: rules.Catalog
) -> tuple[str, str]:
    """
    生成治疗方案或异常线索、收益预估与药品需求正文，以及独立的未确诊折算提示。
    Keyword arguments:
    patient -- medical_patient.MedicalPatient，当前诊疗的病人对象
    catalog -- rules.Catalog，按系统编号索引的检查目录
    Return arguments:
    tuple[str, str] -- 治疗摘要正文与独立绘制的未确诊 50% 折算提示
    """
    found = rules.confirmed(patient)
    found_set = {int(cid) for cid in found}
    actual = {int(cid) for cid in patient.complications if cid}
    missing = actual - found_set
    ratio = 1.0
    if actual and missing:
        ratio = (len(found_set) + 0.5 * len(missing)) / len(actual)
    lines: list[str] = []
    if found:
        lines.append(_("已确诊的并发症与治疗方案："))
        for cid in found:
            config = game_config.config_medical_complication.get(cid)
            if config is None:
                continue
            level = severity_text(
                int(getattr(config, "severity_level", 0) or 0)
            )
            plan = getattr(config, "treatment_plan", "") or _(
                "暂无详细治疗方案。"
            )
            lines.append(
                _("·({severity}){name}").format(
                    severity=level, name=config.name
                )
            )
            lines.append(_("  治疗方案：{plan}").format(plan=plan))
    else:
        lines.append(_("检查次数已达上限，以下为可能的异常线索："))
        clues = suggestions(patient, catalog)
        lines.extend(f"  {item}" for item in clues)
        if not clues:
            lines.append(
                _("  暂无明确线索，请考虑切换提示或交由其他医生继续诊疗。")
            )
    lines.append("\n")
    preview: dict[str, Any] = (
        medical_player_diagnose_function.estimate_patient_treatment_summary(
            patient
        )
    )
    resources: list[Any] = []
    if preview.get("success"):
        diagnose = float(preview.get("diagnose_income", 0))
        medicine = float(preview.get("predicted_medicine_income", 0))
        lines.append(
            _(
                "预计诊疗收益：{diagnose} 龙门币 | 预估药费收益：{medicine} 龙门币"
            ).format(
                diagnose=int(round(diagnose)),
                medicine=int(round(medicine * ratio)),
            )
        )
        raw = preview.get("resources")
        if isinstance(raw, list):
            resources = [entry for entry in raw if isinstance(entry, dict)]
        if resources:
            lines += _resource_lines(resources, ratio)
    notice = ""
    if missing:
        notice = _("未确诊 {count} 项并发症，相关药品需求按 50% 计入。\n")
        if resources:
            notice = _(
                "  * 未确诊 {count} 项并发症，相关药品需求按 50% 计入。\n"
            )
        notice = notice.format(count=len(missing))
    return "\n".join(lines) + "\n", notice


def shortage_lines(patient: medical_patient.MedicalPatient) -> list[str]:
    """
    汇总病人所需药品中超出当前库存且大于浮点容差的缺口明细行。
    Keyword arguments:
    patient -- medical_patient.MedicalPatient，当前诊疗的病人对象
    Return arguments:
    list[str] -- 每种短缺药品的缺口与库存说明行列表
    """
    stock = inventory()
    lines: list[str] = []
    for key, amount in patient.need_resources.items():
        try:
            rid = int(key)
        except (TypeError, ValueError):
            continue
        gap = shortage(rid, float(amount or 0.0), stock)
        if gap <= medical_constant.FLOAT_EPSILON:
            continue
        config = game_config.config_resouce.get(rid)
        lines.append(
            _("· {name} 缺口 {amount} 单位，当前库存 {stock} 单位。").format(
                name=getattr(config, "name", str(rid)) if config else str(rid),
                amount=quantity(gap),
                stock=quantity(float(stock.get(rid, 0.0) or 0.0)),
            )
        )
    return lines


def treatment_message(
    outcome: dict[str, object], patient: medical_patient.MedicalPatient
) -> str:
    """
    根据诊疗提交结果生成收益反馈，开药失败时附加具体缺口清单或库存不足提示。
    Keyword arguments:
    outcome -- dict[str, object]，诊疗提交接口返回的结果字典
    patient -- medical_patient.MedicalPatient，当前诊疗的病人对象
    Return arguments:
    str -- 诊疗收益与药品补充提示文本
    """
    text = _(
        "已完成诊疗，诊断收益 {diag} 龙门币，药费收益 {med} 龙门币。"
    ).format(
        diag=outcome.get("diagnose_income", 0),
        med=outcome.get("medicine_income", 0),
    )
    if outcome.get("medicine_success"):
        return text
    lines = shortage_lines(patient)
    if not lines:
        return text + "\n" + _("药品库存不足，请补充后再试。")
    return text + "\n" + _("当前仍缺少以下药品：") + "\n" + "\n".join(lines)
