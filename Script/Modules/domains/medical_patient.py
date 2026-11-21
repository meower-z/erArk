"""
医疗部数据存进 GameState 的形式，与病人 MedicalPatient
=========================================================
plain 把医疗部的值换成 JSON：枚举取值，datetime 取内核时钟的分钟数，整数键换成字符串。thaw 把冻结的 JSON 换回可改的。
病人存成以字段名为键的映射。MedicalPatient 第一次读一个字段时从它存的映射里取，取到的值留在实例上。
列表与字典取的是副本，记作病人自己的值。赋值也记作病人自己的值。
to_json 在病人自己的值没有一项与存的不同时交回存的映射本身，没改过的病人因此不用重新冻结。
本模块不登记键、行动、事件或规则，键由 domains.medical 拥有。
"""

import datetime
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from typing import Any, cast

from Script.Design import game_time
from Script.Kernel import core
from Script.System.Medical_System import medical_constant as mc

_MISSING = object()


def thaw(value: core.JSON) -> Any:
    """
    把冻结的 JSON 换成可改的：映射换成 dict，元组换成 list
    Keyword arguments:
    value -- JSON
    Return arguments:
    Any -- 可改的副本
    """
    if isinstance(value, Mapping):
        return {k: thaw(v) for k, v in value.items()}
    if isinstance(value, tuple | list):
        return [thaw(v) for v in value]
    return value


def plain(value: object) -> core.JSON:
    """
    把医疗部的值换成 JSON：枚举取值，datetime 取内核时钟的分钟数，整数键换成字符串，list 换成元组
    Keyword arguments:
    value -- 值，别的类型报 TypeError
    Return arguments:
    JSON -- 值
    """
    if isinstance(value, Enum):
        return cast(core.JSON, value.value)
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, datetime.datetime):
        return game_time.minutes(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: plain(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        out: dict[str, core.JSON] = {}
        for k, v in value.items():
            if not isinstance(k, str | int) or isinstance(k, bool):
                raise TypeError(f"{k!r} is not a str or int key")
            out[str(k)] = plain(v)
        return out
    if isinstance(value, list | tuple):
        return tuple(plain(v) for v in value)
    raise TypeError(f"{value!r} is not medical data")


def same(a: object, b: object) -> bool:
    """
    两个 JSON 值相同：映射的键与顺序相同，各项相同；数值的类型也相同
    Keyword arguments:
    a -- 值
    b -- 值
    Return arguments:
    bool -- 相同时为 True
    """
    if a is b:
        return True
    if isinstance(a, Mapping) and isinstance(b, Mapping):
        return len(a) == len(b) and all(
            ka == kb and same(va, vb)
            for (ka, va), (kb, vb) in zip(a.items(), b.items(), strict=True)
        )
    if isinstance(a, tuple | list) and isinstance(b, tuple | list):
        return len(a) == len(b) and all(map(same, a, b))
    return type(a) is type(b) and a == b


def _int_keys(value: core.JSON) -> dict[int, Any]:
    return {int(k): thaw(v) for k, v in cast(Mapping[str, Any], value).items()}


@dataclass(frozen=True)
class _Field:
    default: Callable[[], Any]
    decode: Callable[[core.JSON], Any]
    container: bool = False


def _scalar(default: object) -> _Field:
    return _Field(lambda: default, lambda raw: raw)


def _enum(kind: type[Enum], default: Enum) -> _Field:
    members = kind._value2member_map_
    return _Field(lambda: default, lambda raw: members.get(raw, raw))


def _list() -> _Field:
    return _Field(list, thaw, True)


def _int_dict() -> _Field:
    return _Field(dict, _int_keys, True)


_PATIENT: dict[str, _Field] = {
    "patient_id": _scalar(0),
    "severity_level": _scalar(0),
    "complications": _list(),
    "diagnose_progress": _scalar(0.0),
    "need_resources": _int_dict(),
    "state": _enum(mc.MedicalPatientState, mc.MedicalPatientState.REFRESHED),
    "clinic_waiting_days": _scalar(0),
    "stay_days": _scalar(0),
    "need_surgery": _scalar(False),
    "surgery_blocked": _scalar(False),
    "personality_type": _enum(
        mc.MedicalPatientPersonality, mc.MedicalPatientPersonality.RATIONAL
    ),
    "race_id": _scalar(0),
    "age": _scalar(18),
    "assigned_doctor_id": _scalar(0),
    "assigned_hospital_doctor_id": _scalar(0),
    "severity_name": _scalar(""),
    "price_ratio": _scalar(1.0),
    "complication_trace": _list(),
    "system_keys": _list(),
    "player_session_active": _scalar(False),
    "player_previous_state": _scalar(""),
    "player_used_checks": _scalar(0),
    "player_confirmed_complications": _list(),
    "player_check_records": _list(),
    "player_pending_checks": _list(),
    "last_surgery_result": _scalar(""),
    "surgery_blocked_resource": _scalar(None),
    "state_label": _scalar(""),
    "medicine_recorded": _int_dict(),
    "medicine_progress": _int_dict(),
    "medicine_consumed_units": _int_dict(),
    "last_consumed_units": _int_dict(),
}
""" 病人的字段：默认值、从存的 JSON 读出的方法、是否是读出后可能被原地修改的容器 """


class MedicalPatient:
    """
    医疗流程里的病人。字段名、类型与默认值见下。第一次读字段时从它存进 GameState 的映射里取，
    读到的列表与字典是副本，记作病人自己的值（可能被原地修改）；赋值也记作病人自己的值
    """

    patient_id: int
    """病人唯一编号（运行时自增生成）"""
    severity_level: int
    """病情等级，来自 MedicalSeverity.csv"""
    complications: list[int]
    """已抽取并发症 ID 列表"""
    diagnose_progress: float
    """诊疗进度（工时单位）"""
    need_resources: dict[int, float]
    """药物需求累计值，key=资源 ID，value=需求数量"""
    state: mc.MedicalPatientState
    """病人当前状态"""
    clinic_waiting_days: int
    """已门诊等待天数"""
    stay_days: int
    """已住院天数"""
    need_surgery: bool
    """是否需要手术治疗"""
    surgery_blocked: bool
    """手术是否因条件不足被阻塞"""
    personality_type: mc.MedicalPatientPersonality
    """病人性格"""
    race_id: int
    """病人种族 ID（排除博士）"""
    age: int
    """病人年龄"""
    assigned_doctor_id: int
    """当前绑定的门诊医生编号（0 表示未绑定）"""
    assigned_hospital_doctor_id: int
    """当前绑定的住院医生编号（0 表示未绑定）"""
    severity_name: str
    """病情等级对应的名称标签，用于 UI 展示"""
    price_ratio: float
    """刷新/接诊时记录的收费系数快照"""
    complication_trace: list[dict[str, Any]]
    """并发症追踪记录，包含系统/部位等辅助信息"""
    system_keys: list[str]
    """病人关联的生理系统标签集合（字符串形式）"""
    player_session_active: bool
    """标记玩家诊疗会话是否处于激活状态"""
    player_previous_state: str
    """玩家介入前病人的原始状态字符串"""
    player_used_checks: int
    """本次玩家诊疗流程已使用的检查次数"""
    player_confirmed_complications: list[int]
    """玩家诊疗流程中已确诊的并发症 ID 列表"""
    player_check_records: list[dict[str, Any]]
    """玩家诊疗流程中产生的检查记录摘要列表"""
    player_pending_checks: list[dict[str, Any]]
    """玩家诊疗流程中等待执行的检查计划列表"""
    last_surgery_result: str
    """最近一次手术流程的结果标识"""
    surgery_blocked_resource: int | None
    """导致手术阻塞的药物资源 ID，None 表示不存在阻塞"""
    state_label: str
    """调试用途的最新状态字符串"""
    medicine_recorded: dict[int, float]
    """累计登记但尚未扣除的药品需求量"""
    medicine_progress: dict[int, float]
    """住院每日用药进度缓存"""
    medicine_consumed_units: dict[int, int]
    """历史累计消耗的药物单位数"""
    last_consumed_units: dict[int, int]
    """最近一次用药操作实际消耗的资源记录"""

    def __init__(self, **values: object) -> None:
        """
        新病人
        Keyword arguments:
        values -- 字段名到值，没给的字段取默认值，不是字段的名字报 TypeError
        """
        unknown = values.keys() - _PATIENT.keys()
        if unknown:
            raise TypeError(f"MedicalPatient has no field {sorted(unknown)}")
        own = {
            name: values[name] if name in values else spec.default()
            for name, spec in _PATIENT.items()
        }
        vars(self).update(own, _stored={}, _own=own)

    @classmethod
    def stored(cls, value: Mapping[str, core.JSON]) -> "MedicalPatient":
        """
        存在 GameState 里的病人
        Keyword arguments:
        value -- 病人的映射
        Return arguments:
        MedicalPatient -- 病人，读字段时从 value 取
        """
        patient = cls.__new__(cls)
        vars(patient).update(_stored=value, _own={})
        return patient

    def __getattr__(self, name: str) -> Any:
        """
        第一次读一个字段时从存的映射里取，取到的值留在实例上，之后直接读到。列表与字典取出副本，记作自己的值
        Keyword arguments:
        name -- 字段名，不是字段时报 AttributeError
        Return arguments:
        Any -- 值
        """
        spec = _PATIENT.get(name)
        own = vars(self).get("_own")
        if spec is None or own is None:
            raise AttributeError(name)
        if name in own:
            return own[name]
        raw = vars(self)["_stored"].get(name, _MISSING)
        value = spec.default() if raw is _MISSING else spec.decode(raw)
        if spec.container:
            own[name] = value
        vars(self)[name] = value
        return value

    def __setattr__(self, name: str, value: object) -> None:
        """
        给一个字段赋值，记在自己身上
        Keyword arguments:
        name -- 字段名，不是字段时报 AttributeError
        value -- 值
        """
        if name not in _PATIENT:
            raise AttributeError(f"MedicalPatient has no field {name}")
        vars(self)["_own"][name] = value
        vars(self)[name] = value

    def to_json(self) -> Mapping[str, core.JSON]:
        """
        病人存进 GameState 的映射。没有一项与存的不同时，交回存的那个映射本身
        Return arguments:
        Mapping -- 字段名到 JSON
        """
        stored = vars(self)["_stored"]
        changed = {}
        for name, value in vars(self)["_own"].items():
            new = plain(value)
            if not same(stored.get(name, _MISSING), new):
                changed[name] = new
        return {**stored, **changed} if changed else stored

    def as_dict(self) -> dict[str, Any]:
        """
        Return arguments:
        dict -- 字段名到值，按字段的顺序
        """
        return {name: getattr(self, name) for name in _PATIENT}

    def ensure_resource_keys(self) -> None:
        """补齐药物需求键，避免读取和累计过程中出现缺省键"""

        for resource_id in mc.ALL_MEDICINE_RESOURCE_IDS:
            self.need_resources.setdefault(resource_id, 0.0)


def from_attrs(attrs: Mapping[str, object]) -> MedicalPatient:
    """
    由旧存档里病人对象的属性建病人，不是字段的属性不要
    Keyword arguments:
    attrs -- 属性名到值
    Return arguments:
    MedicalPatient -- 新病人
    """
    return MedicalPatient(**{k: v for k, v in attrs.items() if k in _PATIENT})


def patients(value: core.JSON) -> dict[int, MedicalPatient]:
    """
    存的病人表换成病人id到病人的字典，顺序不变
    Keyword arguments:
    value -- {病人id的字符串: 病人的映射}
    Return arguments:
    dict -- 病人id到病人（读字段时从存的映射取）
    """
    table = cast(Mapping[str, Mapping[str, core.JSON]], value)
    return {int(k): MedicalPatient.stored(v) for k, v in table.items()}


def patients_json(table: Mapping[int, MedicalPatient]) -> dict[str, core.JSON]:
    """
    病人表存进 GameState 的形式，顺序不变。没改过的病人沿用存的映射
    Keyword arguments:
    table -- 病人id到病人
    Return arguments:
    dict -- {病人id的字符串: 病人的映射}
    """
    return {str(k): v.to_json() for k, v in table.items()}


def _timed(entry: Mapping[str, core.JSON]) -> dict[str, Any]:
    out = thaw(entry)
    if isinstance(out.get("time"), int):
        out["time"] = game_time.at(out["time"])
    return cast(dict[str, Any], out)


def _report(entry: Mapping[str, core.JSON]) -> dict[str, Any]:
    out = _timed(entry)
    if isinstance(out.get("inventory_detail"), dict):
        out["inventory_detail"] = _int_keys(out["inventory_detail"])
    stats = out.get("stats")
    if isinstance(stats, dict) and isinstance(
        stats.get("medicine_consumed"), dict
    ):
        stats["medicine_consumed"] = _int_keys(stats["medicine_consumed"])
    return out


def _counters(value: core.JSON) -> mc.MedicalDailyCounters | None:
    if value is None:
        return None
    data = thaw(value)
    data["medicine_consumed"] = _int_keys(data["medicine_consumed"])
    return mc.MedicalDailyCounters(**data)


SMALL_DECODE: dict[str, Callable[[Any], Any]] = {
    "accumulator": _int_keys,
    "surgery_records": lambda v: [_timed(e) for e in v],
    "daily_counters": _counters,
    "recent_reports": lambda v: [_report(e) for e in v],
}
""" base.medical 里要换回原来类型的项，别的项用 thaw """
