"""
玩家诊疗界面文本服务（medical_diagnose_view）
=============================================
提供患者概览、检查状态、检查菜单行、检查报告行、说明文本与操作按钮数据。
本模块不导入 Script.UI 与 Script.Settle。
"""

from dataclasses import dataclass
from types import FunctionType
from typing import Any

from Script.Config import game_config
from Script.Core import get_text
from Script.Design import attr_calculation
from Script.Modules.domains import medical_patient
from Script.Modules.gameplay_resolution import medical_diagnose_service as rules
from Script.System.Medical_System import medical_constant

_: FunctionType = get_text._
""" 翻译函数 """
OUTCOME_STYLES = {
    "positive": "warning",
    "negative": "green",
    "recheck": "pale_cerulean",
}
""" 检查结果键值到界面高亮样式名的映射表。 """


@dataclass(frozen=True)
class MenuRow:
    """检查菜单单行渲染数据的不可变数据类。"""

    kind: str
    """ 行类别，取值为 system、part、option 或 done。 """
    label: str
    """ 按钮或文本行显示的完整文案。 """
    name: str
    """ 按钮点击后传回输入循环的标识文本。 """
    width: int
    """ 按钮绘制宽度，0 表示使用面板总宽。 """
    style: str
    """ 绘制该行使用的界面样式名称。 """
    args: tuple[int, ...]
    """ 触发行回调时传入的整数编号参数元组。 """


def severity_text(level: int) -> str:
    """
    将并发症严重度数值转换为中文等级文本，未匹配时返回短横线。
    Keyword arguments:
    level -- int，并发症严重度等级数值（0 轻症、1 中症、2 重症）
    Return arguments:
    str -- 中文严重度名称或短横线
    """
    mapping = {0: _("轻症"), 1: _("中症"), 2: _("重症")}
    return mapping.get(int(level), "-")


def outcome_text(result: str) -> str:
    """
    将检查结果内部键值转换为中文展示文本，未匹配时原样返回。
    Keyword arguments:
    result -- str，检查结果键值（positive、negative 或 recheck）
    Return arguments:
    str -- 中文检查结果文本或原始键值
    """
    mapping = {
        "positive": _("阳性"),
        "negative": _("阴性"),
        "recheck": _("需再检"),
    }
    return mapping.get(result, result)


def overview_text(patient: medical_patient.MedicalPatient) -> str:
    """
    生成患者基础档案与症状观察、病人自述列表的概览文本。
    Keyword arguments:
    patient -- medical_patient.MedicalPatient，当前诊疗的病人对象
    Return arguments:
    str -- 含患者基本信息与症状记录的多行概览文本
    """
    severity = patient.severity_name
    if not severity:
        config = game_config.config_medical_severity.get(patient.severity_level)
        severity = config.name if config else _("未知病情")
    race = game_config.config_race.get(patient.race_id)
    text = _(
        "患者编号：{pid} | 病情：{severity} | 年龄：{age} 岁 | 种族：{race}\n"
    ).format(
        pid=patient.patient_id,
        severity=severity,
        age=patient.age,
        race=race.name if race is not None else _("未知种族"),
    )
    lines: list[str] = []
    for index, entry in enumerate(patient.complication_trace, start=1):
        config = game_config.config_medical_complication.get(
            entry.get("cid", entry.get("complication_id", 0))
        )
        if config is None:
            continue
        statement = config.patient_statement_clear
        if (
            patient.personality_type
            == medical_constant.MedicalPatientPersonality.IRRATIONAL
        ):
            statement = config.patient_statement_vague
        lines.append(
            _(
                "· 症状记录 {index}\n  外观观察：{appearance}\n  病人自述：{statement}"
            ).format(
                index=index,
                appearance=config.appearance_indicator or _("无可见异常"),
                statement=statement,
            )
        )
    if lines:
        text += "\n" + "\n".join(lines) + "\n"
    return text


def hint_status(value: int, options: list[str]) -> str:
    """
    生成当前治病提示档位的状态展示文本，索引越界时显示未配置。
    Keyword arguments:
    value -- int，当前诊疗提示档位索引
    options -- list[str]，配置的全部诊疗提示名称列表
    Return arguments:
    str -- 带前缀的治病提示状态文本
    """
    status = options[value] if 0 <= value < len(options) else _("未配置")
    return _("○治病提示：{status}").format(status=status)


def check_status(
    patient: medical_patient.MedicalPatient,
    catalog: rules.Catalog,
    limits: tuple[int, int],
) -> str:
    """
    生成患者检查次数进度与当前待执行检查项明细文本。
    Keyword arguments:
    patient -- medical_patient.MedicalPatient，当前诊疗的病人对象
    catalog -- rules.Catalog，按系统编号索引的检查目录
    limits -- tuple[int, int]，检查总次数上限与单次并行上限
    Return arguments:
    str -- 含检查次数统计与待执行检查列表的文本
    """
    max_checks, max_parallel = limits
    pending = rules.pending_checks(patient)
    used = rules.used_checks(patient)
    text = _("患者愿意进行的检查次数：{used}/{limit}").format(
        used=used, limit=max_checks
    )
    if used < max_checks:
        text += _("（本次已选 {selected}/{max_parallel} 项）").format(
            selected=len(pending), max_parallel=max_parallel
        )
    text += "\n"
    if not pending:
        return text
    lines = []
    for option in pending:
        system, part = rules.catalog_part(
            catalog, option["system_id"], option["part_id"]
        )
        config = game_config.config_medical_complication.get(option["cid"])
        lines.append(
            _(
                "◆ 怀疑 {name}（{system} - {part} - {severity}），进行检查：{exam_method}"
            ).format(
                name=config.name if config else str(option["cid"]),
                system=system.get("system_name", "-"),
                part=part.get("part_name", "-"),
                severity=severity_text(option["severity_level"]),
                exam_method=(
                    getattr(config, "exam_method", "-") if config else "-"
                ),
            )
        )
    return text + _("待执行检查：\n") + "\n".join(lines) + "\n"


def _has_confirmed(options: list[dict[str, Any]], found: list[int]) -> bool:
    """
    判断检查选项列表中是否存在已确诊的并发症编号。
    Keyword arguments:
    options -- list[dict[str, Any]]，部位下的检查选项字典列表
    found -- list[int]，已确诊的并发症编号列表
    Return arguments:
    bool -- 存在任一已确诊并发症时为 True
    """
    return any(int(opt.get("cid", 0) or 0) in found for opt in options)


def menu_rows(
    patient: medical_patient.MedicalPatient,
    catalog: rules.Catalog,
    expanded: tuple[int | None, int | None],
    marks: tuple[list[int], rules.Highlights],
) -> list[MenuRow]:
    """
    按展开状态、高亮集合与已检记录生成三级检查菜单的渲染行列表。
    Keyword arguments:
    patient -- medical_patient.MedicalPatient，当前诊疗的病人对象
    catalog -- rules.Catalog，按系统编号索引的检查目录
    expanded -- tuple[int | None, int | None]，当前展开的系统编号与部位编号
    marks -- tuple[list[int], rules.Highlights]，已检查并发症列表与高亮三元组
    Return arguments:
    list[MenuRow] -- 按展示顺序排列的菜单行对象列表
    """
    open_system, open_part = expanded
    executed, (systems, parts, highlighted) = marks
    found = rules.confirmed(patient)
    picked = {item["cid"] for item in rules.pending_checks(patient)}
    rows: list[MenuRow] = []
    for system_id in sorted(catalog):
        info = catalog[system_id]
        name = str(info.get("system_name", system_id))
        system_open = system_id == open_system
        label = f"{'   [-]' if system_open else '   [+]'} {name}"
        part_map = info.get("parts", {})
        if system_id not in systems and any(
            _has_confirmed(part.get("options", []), found)
            for part in part_map.values()
        ):
            break
        style = "gold_enrod" if system_id in systems else "standard"
        width = max(len(label) * 2 + 4, 26)
        rows.append(MenuRow("system", label, name, width, style, (system_id,)))
        if not system_open:
            continue
        for part_id in sorted(part_map):
            part = part_map[part_id]
            if int(part.get("gender_limit", 2)) == 0:
                continue
            part_name = str(part.get("part_name", part_id))
            part_open = part_id == open_part
            label = f"{'     [-]' if part_open else '     [+]'} {part_name}"
            style = "standard"
            if (system_id, part_id) in parts:
                style = "gold_enrod"
            elif _has_confirmed(part.get("options", []), found):
                style = "deep_gray"
            width = max(len(label) * 2 + 4, 30)
            args = (system_id, part_id)
            rows.append(MenuRow("part", label, part_name, width, style, args))
            if not part_open:
                continue
            for option in part.get("options", []):
                cid = int(option.get("cid", 0) or 0)
                level = severity_text(int(option.get("severity_level", 0) or 0))
                title = attr_calculation.pad_display_width(
                    str(option.get("name", cid)), 38
                )
                box = "[✔]" if cid in picked else "[  ]"
                exam = option.get("exam_method", "-")
                label = f"        {box} {level} | {title} | {exam}"
                if cid in executed:
                    label = _("（已检查）") + label
                    rows.append(
                        MenuRow("done", label, title, 0, "deep_gray", ())
                    )
                    continue
                style = "gold_enrod" if cid in highlighted else "standard"
                args = (system_id, part_id, cid)
                rows.append(MenuRow("option", label, title, 0, style, args))
    return rows


def report_rows(results: list[dict[str, object]]) -> list[tuple[str, str, str]]:
    """
    将检查结果列表整理为居中结果标签、样式名与说明后缀的三元组列表。
    Keyword arguments:
    results -- list[dict[str, object]]，累计的检查结果字典列表
    Return arguments:
    list[tuple[str, str, str]] -- 每条报告对应的结果标签、样式名与后缀文本
    """
    rows = []
    for result in results:
        key = str(result.get("result", "") or "")
        outcome = attr_calculation.pad_display_width(
            outcome_text(key), 6, align="center"
        )
        suffix = _(") 怀疑 {name}，检查结果：{message}\n").format(
            name=result.get("name", str(result.get("cid", ""))),
            message=result.get("message", ""),
        )
        rows.append((outcome, OUTCOME_STYLES.get(key, "standard"), suffix))
    return rows


def help_text() -> str:
    """
    生成玩家诊疗面板顶部的菜单操作、检查次数与提示规则说明文本。
    Return arguments:
    str -- 三行操作说明文本
    """
    text = _(
        "○展开检查菜单以从系统 → 部位 → 并发症逐级挑选检查项目，项目格式为：病症等级|怀疑病症名|检查方式。\n"
    )
    text += _(
        "○患者愿意进行的检查次数与博士的话术能力等级有关，等级越高可尝试次数就越高。\n"
    )
    text += _(
        "○开启治疗提示后，会根据博士的医疗能力等级（+交互干员的一半）来高亮显示正确的患病系统、部位、症状等，能力越高显示越具体。\n"
    )
    return text


def operation_buttons(
    patient: medical_patient.MedicalPatient, max_checks: int, awaiting: bool
) -> list[tuple[str, str, str, tuple[bool, ...]]]:
    """
    按确认等待状态、待检列表与检查进度生成底部操作按钮描述列表。
    Keyword arguments:
    patient -- medical_patient.MedicalPatient，当前诊疗的病人对象
    max_checks -- int，本次诊疗允许的检查总次数上限
    awaiting -- bool，是否处于提前结束治疗的二次确认状态
    Return arguments:
    list[tuple[str, str, str, tuple[bool, ...]]] -- 按钮文案、回传名、动作键与参数列表
    """
    if awaiting:
        confirm, cancel = _("[确认就这样治疗]"), _("[返回继续检查]")
        return [
            (confirm, confirm, "confirm", ()),
            (cancel, cancel, "cancel", ()),
        ]
    used = rules.used_checks(patient)
    pending = rules.pending_checks(patient)
    buttons: list[tuple[str, str, str, tuple[bool, ...]]] = []
    if pending and used < max_checks:
        buttons.append((_("[执行所选检查]"), _("执行所选检查"), "execute", ()))
    if pending:
        buttons.append(
            (_("[清空已选待检项]"), _("清空已选待检项"), "clear", ())
        )
    if rules.confirmed(patient) or used >= max_checks:
        buttons.append(
            (_("[开药并结束诊疗]"), _("开药并结束诊疗"), "treat", (False,))
        )
        buttons.append(
            (_("[开药并接诊下一位]"), _("开药并接诊下一位"), "treat", (True,))
        )
    if used == 0:
        buttons.append(
            (_("[提前结束诊疗并返回]"), _("提前结束诊疗并返回"), "abort", ())
        )
    return buttons
