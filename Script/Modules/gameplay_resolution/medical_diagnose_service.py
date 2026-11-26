"""
玩家诊疗规则服务（medical_diagnose_service）
============================================
提供玩家诊疗的能力计算、待检切换、提示等级解锁与高亮筛选规则。
本模块不导入 Script.UI 与 Script.Settle。
"""

from types import FunctionType
from typing import Any

from Script.Config import game_config, normal_config
from Script.Core import get_text
from Script.Modules.domains import abilities, activity, identity
from Script.Modules.domains import medical_patient
from Script.System.Medical_System import medical_constant

_: FunctionType = get_text._
""" 翻译函数 """

TALK_ABILITY_ID = 40
""" 话术能力配置编号（40）。 """
HINT_SETTING_ID = 12
""" 诊疗提示系统设置项编号（12）。 """
HINT_UNLOCKS = ((1, 1), (2, 2), (3, 3), (5, 4), (7, 5))
""" 医疗等级门槛与可解锁提示档位索引的对照表。 """

type Catalog = dict[int, dict[str, Any]]
""" 按系统编号索引的检查目录字典类型别名。 """
type Check = dict[str, int]
""" 单条待执行检查记录字典类型别名。 """
type Highlights = tuple[set[int], set[tuple[int, int]], set[int]]
""" 高亮系统集合、部位键集合与并发症编号集合的三元组类型别名。 """


def med_level(player: identity.Identity | None) -> int:
    """
    计算玩家诊疗提示所用的综合医疗等级，存在交互对象时叠加其一半能力并封顶为 8。
    Keyword arguments:
    player -- identity.Identity | None，当前执行诊疗的玩家角色对象
    Return arguments:
    int -- 不小于 0 的综合医疗等级
    """
    if player is None:
        return 0
    level = int(
        abilities.ability(0).get(medical_constant.MEDICAL_ABILITY_ID, 0) or 0
    )
    target_id = activity.target(player.cid)
    if target_id != 0 and identity.exists(target_id):
        level += int(
            abilities.ability(target_id).get(
                medical_constant.MEDICAL_ABILITY_ID, 0
            )
            / 2
            or 0
        )
        level = min(8, level)
    return max(0, level)


def check_limit(player: identity.Identity | None) -> int:
    """
    按玩家话术能力的两倍计算单次诊疗允许的检查上限，至少为 1。
    Keyword arguments:
    player -- identity.Identity | None，当前执行诊疗的玩家角色对象
    Return arguments:
    int -- 本次诊疗允许执行的检查次数上限
    """
    if player is None:
        return 1
    talk = max(0, int(abilities.ability(0).get(TALK_ABILITY_ID, 0) or 0))
    return max(1, talk * 2)


def pending_checks(patient: medical_patient.MedicalPatient) -> list[Check]:
    """
    整理病人的待执行检查列表，过滤非字典条目并将各编号字段转为整数。
    Keyword arguments:
    patient -- medical_patient.MedicalPatient，当前诊疗的病人对象
    Return arguments:
    list[Check] -- 含标准整数字段的待检记录列表
    """
    return [
        {
            "cid": int(item.get("cid", 0) or 0),
            "system_id": int(item.get("system_id", 0) or 0),
            "part_id": int(item.get("part_id", 0) or 0),
            "severity_level": int(item.get("severity_level", 0) or 0),
        }
        for item in patient.player_pending_checks
        if isinstance(item, dict)
    ]


def confirmed(patient: medical_patient.MedicalPatient) -> list[int]:
    """
    返回病人已由玩家确诊的并发症编号整数列表。
    Keyword arguments:
    patient -- medical_patient.MedicalPatient，当前诊疗的病人对象
    Return arguments:
    list[int] -- 已确诊并发症编号列表
    """
    return [int(cid) for cid in patient.player_confirmed_complications]


def used_checks(patient: medical_patient.MedicalPatient) -> int:
    """
    读取当前病人已消耗的玩家检查次数。
    Keyword arguments:
    patient -- medical_patient.MedicalPatient，当前诊疗的病人对象
    Return arguments:
    int -- 已使用的检查次数
    """
    return int(patient.player_used_checks or 0)


def target_count(patient: medical_patient.MedicalPatient, target: int) -> int:
    """
    确定目标并发症数量，传入目标值不大于 0 且病人有并发症时回退为实际数量。
    Keyword arguments:
    patient -- medical_patient.MedicalPatient，当前诊疗的病人对象
    target -- int，会话记录的目标并发症数量
    Return arguments:
    int -- 用于进度判定的目标并发症数量
    """
    if target <= 0 and patient.complications:
        return len(patient.complications)
    return target


def undiagnosed(
    patient: medical_patient.MedicalPatient, target: int, found: list[int]
) -> bool:
    """
    判断病人是否仍有尚未确诊的目标并发症。
    Keyword arguments:
    patient -- medical_patient.MedicalPatient，当前诊疗的病人对象
    target -- int，会话记录的目标并发症数量
    found -- list[int]，已确诊的并发症编号列表
    Return arguments:
    bool -- 目标数大于 0 且已确诊数不足时为 True
    """
    count = target_count(patient, target)
    return count > 0 and len(found) < count


def missing_count(
    patient: medical_patient.MedicalPatient, target: int, found: list[int]
) -> int:
    """
    统计病人尚未确诊的并发症数量，无实际并发症集合时按目标数与已确诊数差值估算。
    Keyword arguments:
    patient -- medical_patient.MedicalPatient，当前诊疗的病人对象
    target -- int，会话记录的目标并发症数量
    found -- list[int]，已确诊的并发症编号列表
    Return arguments:
    int -- 未确诊的并发症项数
    """
    actual = {int(cid) for cid in patient.complications if cid}
    found_set = {int(cid) for cid in found}
    if not actual and target:
        return max(target - len(found_set), 0)
    return len(actual - found_set)


def catalog_part(
    catalog: Catalog, system_id: int, part_id: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    从检查目录中查询指定系统与部位对应的信息字典，缺失时返回空字典。
    Keyword arguments:
    catalog -- Catalog，按系统编号索引的检查目录
    system_id -- int，身体系统编号
    part_id -- int，身体部位编号
    Return arguments:
    tuple[dict[str, Any], dict[str, Any]] -- 系统信息字典与部位信息字典
    """
    system_info = catalog.get(system_id, {})
    return system_info, system_info.get("parts", {}).get(part_id, {})


def option_info(
    catalog: Catalog, system_id: int, part_id: int, cid: int
) -> dict[str, Any]:
    """
    查询检查目录中指定并发症选项信息，目录缺失时依次回退到并发症配置与默认字典。
    Keyword arguments:
    catalog -- Catalog，按系统编号索引的检查目录
    system_id -- int，身体系统编号
    part_id -- int，身体部位编号
    cid -- int，并发症配置编号
    Return arguments:
    dict[str, Any] -- 含 cid、name 与 severity_level 的选项字典
    """
    __, part_info = catalog_part(catalog, system_id, part_id)
    for option in part_info.get("options", []):
        if int(option.get("cid", 0) or 0) == cid:
            return option
    config = game_config.config_medical_complication.get(cid)
    if config is not None:
        return {
            "cid": cid,
            "name": config.name,
            "severity_level": int(getattr(config, "severity_level", 0) or 0),
        }
    return {"cid": cid, "name": str(cid), "severity_level": 0}


def toggle_pending(
    patient: medical_patient.MedicalPatient,
    catalog: Catalog,
    check: tuple[int, int, int],
    limits: tuple[int, int],
) -> None:
    """
    切换指定并发症在病人待检列表中的选中状态，新增时校验次数上限、并行上限与已确诊状态。
    Keyword arguments:
    patient -- medical_patient.MedicalPatient，当前诊疗的病人对象
    catalog -- Catalog，按系统编号索引的检查目录
    check -- tuple[int, int, int]，由系统编号、部位编号与并发症编号组成的三元组
    limits -- tuple[int, int]，由检查总次数上限与单次并行上限组成的二元组
    Return arguments:
    None -- 原地更新 patient.player_pending_checks
    """
    system_id, part_id, cid = check
    max_checks, max_parallel = limits
    pending = pending_checks(patient)
    info = option_info(catalog, system_id, part_id, cid)
    for index, item in enumerate(pending):
        if item["cid"] == cid:
            pending.pop(index)
            patient.player_pending_checks = pending
            return
    if used_checks(patient) >= max_checks or len(pending) >= max_parallel:
        return
    if cid in confirmed(patient):
        return
    pending.append(
        {
            "cid": cid,
            "system_id": system_id,
            "part_id": part_id,
            "severity_level": int(info.get("severity_level", 0)),
        }
    )
    patient.player_pending_checks = pending


def check_results(result: dict[str, object]) -> list[dict[str, object]]:
    """
    从检查执行返回值中读取字典格式的检查结果条目列表。
    Keyword arguments:
    result -- dict[str, object]，检查执行函数返回的结果字典
    Return arguments:
    list[dict[str, object]] -- 过滤后的字典条目列表
    """
    raw = result.get("results", [])
    if not isinstance(raw, list):
        return []
    return [entry for entry in raw if isinstance(entry, dict)]


def mark_executed(executed: list[int], pending: list[Check]) -> None:
    """
    将本次执行的有效并发症编号按顺序去重追加至已检查编号列表。
    Keyword arguments:
    executed -- list[int]，记录已执行并发症编号的列表
    pending -- list[Check]，本次提交执行的待检记录列表
    Return arguments:
    None -- 原地更新 executed 列表
    """
    for option in pending:
        cid = int(option.get("cid", 0) or 0)
        if cid and cid not in executed:
            executed.append(cid)


def hint_indices(level: int, total: int) -> list[int]:
    """
    根据综合医疗等级与提示选项总数计算允许使用的提示档位索引列表。
    Keyword arguments:
    level -- int，综合医疗等级
    total -- int，配置中的诊疗提示选项总数
    Return arguments:
    list[int] -- 升序排列的可用提示档位索引列表
    """
    if total <= 0:
        return [0]
    allowed = {0}
    for required, index in HINT_UNLOCKS:
        if index < total and level >= required:
            allowed.add(index)
    return sorted(allowed)


def hint_context(
    player: identity.Identity | None,
) -> tuple[int, list[int], list[str]]:
    """
    读取当前诊疗提示档位与可用选项，档位越界时钳制至最高可用档并写回全局基础设置。
    Keyword arguments:
    player -- identity.Identity | None，当前执行诊疗的玩家角色对象
    Return arguments:
    tuple[int, list[int], list[str]] -- 当前档位、允许档位列表与全部提示名称
    """
    options = game_config.config_system_setting_option.get(HINT_SETTING_ID, [])
    allowed = hint_indices(med_level(player), len(options))
    setting = getattr(normal_config.system_setting, "base_setting", {})
    if not isinstance(setting, dict):
        setting = {}
        normal_config.system_setting.base_setting = setting
    value = int(setting.get(HINT_SETTING_ID, 0) or 0)
    if value not in allowed:
        value = allowed[-1]
        setting[HINT_SETTING_ID] = value
    return value, allowed, options


def next_hint(player: identity.Identity | None) -> str | None:
    """
    将全局诊疗提示设置循环切换至下一可用档位，不可切换时返回反馈文本。
    Keyword arguments:
    player -- identity.Identity | None，当前执行诊疗的玩家角色对象
    Return arguments:
    str | None -- 切换成功时返回 None，无法切换时返回提示文案
    """
    value, allowed, options = hint_context(player)
    if not options:
        return _("当前版本未配置诊疗提示选项，无法切换。")
    if len(allowed) <= 1:
        return _("博士当前的医疗能力等级不足以启用额外的诊疗提示。")
    position = allowed.index(value)
    setting = normal_config.system_setting.base_setting
    setting[HINT_SETTING_ID] = allowed[(position + 1) % len(allowed)]
    return None


def highlights(
    patient: medical_patient.MedicalPatient, hint: int
) -> Highlights:
    """
    按提示档位筛选未确诊并发症对应的高亮系统、部位与具体选项集合。
    Keyword arguments:
    patient -- medical_patient.MedicalPatient，当前诊疗的病人对象
    hint -- int，当前生效的诊疗提示档位
    Return arguments:
    Highlights -- 高亮系统编号、部位键与并发症编号三元组
    """
    trace = patient.complication_trace
    if hint <= 0 or not trace:
        return set(), set(), set()
    found = set(confirmed(patient))
    systems: set[int] = set()
    parts: set[tuple[int, int]] = set()
    by_severity: dict[int, set[int]] = {}
    for entry in trace:
        cid = int(entry.get("cid", entry.get("complication_id", 0)) or 0)
        if cid and cid in found:
            continue
        system_id = int(entry.get("system_id", 0) or 0)
        part_id = int(entry.get("part_id", 0) or 0)
        severity = entry.get("severity_level")
        if severity is None and cid:
            config = game_config.config_medical_complication.get(cid)
            severity = getattr(config, "severity_level", 0) if config else 0
        if system_id:
            systems.add(system_id)
        if system_id and part_id:
            parts.add((system_id, part_id))
        if cid:
            by_severity.setdefault(int(severity or 0), set()).add(cid)
    options: set[int] = set()
    if hint >= 3:
        options |= by_severity.get(0, set())
    if hint >= 4:
        options |= by_severity.get(1, set())
    if hint >= 5:
        for level, ids in by_severity.items():
            if level >= 2:
                options |= ids
    return systems, parts if hint >= 2 else set(), options


def session_minutes(checks_executed: int) -> int:
    """
    按已执行的检查轮数计算诊疗耗时，至少 1 轮时每轮计 10 分钟，否则计 5 分钟。
    Keyword arguments:
    checks_executed -- int，本次会话实际执行的检查轮数
    Return arguments:
    int -- 用于行为结算的持续分钟数
    """
    return checks_executed * 10 if checks_executed > 0 else 5
