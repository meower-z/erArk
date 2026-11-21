"""
基地医疗部的全局键 base.medical、base.medical_clinic 与 base.medical_ward
===========================================================================
base.medical_clinic 是今日门诊病人表，base.medical_ward 是住院病人表，都是 {病人id的字符串: 病人}，按表里的顺序存。
病人的存法见 domains.medical_patient。
base.medical 存其余的医疗部数据（收费系数、收入、计数、日志、医生名单与分科、玩家诊疗记录等），键名见 SMALL。
日志与手术记录里的时间（time）存成内核时钟的分钟数。没有这些键时读 SMALL 的默认值与空表。
三个键都整值替换（working.put）。
写医疗部数据的代码在 editing() 里运行：块里 state() 都给同一个 Medical，离开最外层的块时把变了的键写进当前缓冲区。
块外 state() 给按当前缓冲区读出的视图（三个键没变时是同一个），对它的修改不写回。
"""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any, cast

from Script.Kernel import core
from Script.Modules.domains import medical_patient
from Script.Modules.gameplay_resolution import working
from Script.System.Medical_System import medical_constant as mc

KEY = "base.medical"
""" 医疗部除病人表以外的数据在全局数据里的键 """
CLINIC = "base.medical_clinic"
""" 今日门诊病人表在全局数据里的键 """
WARD = "base.medical_ward"
""" 住院病人表在全局数据里的键 """
SMALL: Mapping[str, core.JSON] = {
    "price_ratio": 0.0,
    "new_price_ratio": 0.0,
    "bed_modules": 0,
    "bed_limit": 0,
    "accumulator": {},
    "surgery_records": (),
    "income_today": 0,
    "income_total": 0,
    "weekly_weighted_treatment": 0,
    "daily_counters": None,
    "recent_reports": (),
    "clinic_doctor_ids": (),
    "clinic_doctor_power": 0.0,
    "hospital_doctor_ids": (),
    "hospital_doctor_power": 0.0,
    "priority_mode": "",
    "player_patient_id": 0,
    "examined_patient_ids": (),
    "doctor_specializations": {},
}
""" base.medical 的项与没有这个键时读到的值 """
OLD_NAMES = {
    "medical_patients_today": "today",
    "medical_hospitalized": "hospitalized",
    "medical_price_ratio": "price_ratio",
    "new_medical_price_ratio": "new_price_ratio",
    "used_hospital_bed_modules": "bed_modules",
    "medical_bed_limit": "bed_limit",
    "medical_inventory_accumulator": "accumulator",
    "medical_surgery_records": "surgery_records",
    "medical_income_today": "income_today",
    "medical_income_total": "income_total",
    "medical_weekly_weighted_treatment": "weekly_weighted_treatment",
    "medical_daily_counters": "daily_counters",
    "medical_recent_reports": "recent_reports",
    "medical_clinic_doctor_ids": "clinic_doctor_ids",
    "medical_clinic_doctor_power": "clinic_doctor_power",
    "medical_hospital_doctor_ids": "hospital_doctor_ids",
    "medical_hospital_doctor_power": "hospital_doctor_power",
    "medical_patient_priority_mode": "priority_mode",
    "medical_player_current_patient_id": "player_patient_id",
    "player_examined_patient_ids": "examined_patient_ids",
    "medical_doctor_specializations": "doctor_specializations",
}
""" 罗德岛对象上旧的属性名到 Medical 的属性名 """
OLD_TABLES = ("medical_patients_today", "medical_hospitalized")
""" OLD_NAMES 里的两张病人表 """
DEAD_FIELDS = (
    "patient_now",
    "patient_cured",
    "patient_max",
    "patient_cured_all",
)
""" 版本 9 之前的存档里，罗德岛对象上没有代码读的旧病人计数，读档时删掉 """
working.register(KEY, cast(core.JSON, SMALL))
working.register(CLINIC, {})
working.register(WARD, {})


class Medical:
    """医疗部的数据。病人表在第一次读时才建，属性名见 SMALL 与 today、hospitalized"""

    today: dict[int, medical_patient.MedicalPatient]
    """今日门诊病人，病人id:病人"""
    hospitalized: dict[int, medical_patient.MedicalPatient]
    """住院病人，病人id:病人"""
    price_ratio: float
    """当前收费系数，0 表示尚未初始化"""
    new_price_ratio: float
    """下次日结算时生效的收费系数，0 表示未调整"""
    bed_modules: int
    """已使用的住院病房基建模块数量"""
    bed_limit: int
    """ 住院床位上限。医疗部初始化、日结、新收费系数生效与产出病房模块时按 _calculate_medical_bed_limit 重算 """
    accumulator: dict[int, float]
    """药物扣除累计器，资源id:累计小数"""
    surgery_records: list[dict[str, Any]]
    """今日手术记录列表"""
    income_today: int
    """今日医疗板块龙门币收入"""
    income_total: int
    """累计医疗板块龙门币收入"""
    weekly_weighted_treatment: int
    """本周医疗区治疗加权量"""
    daily_counters: mc.MedicalDailyCounters | None
    """医疗系统当日统计数据"""
    recent_reports: list[dict[str, Any]]
    """医疗系统近期经营日志"""
    clinic_doctor_ids: list[int]
    """当前分配为门诊医生的干员id列表"""
    clinic_doctor_power: float
    """门诊医生医疗能力总和"""
    hospital_doctor_ids: list[int]
    """当前分配为住院医生的干员id列表"""
    hospital_doctor_power: float
    """住院医生医疗能力总和"""
    priority_mode: str
    """病人接诊优先策略"""
    player_patient_id: int
    """玩家诊疗面板当前占用的病人ID，0 表示无会话"""
    examined_patient_ids: list[int]
    """玩家本次诊疗过的病人id列表"""
    doctor_specializations: dict[str, dict[str, list[int]]]
    """医生分科配置，岗位:系统:医生id列表"""

    def __init__(
        self, game: core.GameState | None = None, editable: bool = False
    ) -> None:
        """
        读出医疗部数据
        Keyword arguments:
        game -- 给出时只读这个状态，没有时读当前缓冲区，含还没套用的写入
        editable -- editing() 块的 Medical 为 True。为 False 时给属性赋值报 RuntimeError
        """
        raw = {key: working.get(None, key, game) for key in (KEY, CLINIC, WARD)}
        vars(self).update(_raw=raw, _tables={}, _editable=editable)

    def __getattr__(self, name: str) -> Any:
        """
        第一次读一项时才从存的值解出它：SMALL 的项解出后记在自己身上，today 与 hospitalized 由存的表建出病人表
        Keyword arguments:
        name -- 属性名，别的名字报 AttributeError
        Return arguments:
        Any -- 值
        """
        key = {"today": CLINIC, "hospitalized": WARD}.get(name)
        tables = vars(self).get("_tables")
        if tables is None or (key is None and name not in SMALL):
            raise AttributeError(name)
        if key is None:
            small = cast(Mapping[str, core.JSON], vars(self)["_raw"][KEY])
            decode = medical_patient.SMALL_DECODE.get(
                name, medical_patient.thaw
            )
            value = decode(small.get(name, SMALL[name]))
            vars(self)[name] = value
            return value
        if name not in tables:
            tables[name] = medical_patient.patients(vars(self)["_raw"][key])
        return tables[name]

    def __setattr__(self, name: str, value: object) -> None:
        """
        换掉一项数据，名字只能是 SMALL 的项或两张病人表。只读的视图（块外的 state()、of()）报 RuntimeError
        Keyword arguments:
        name -- 属性名，别的名字报 AttributeError
        value -- 新值
        """
        if not vars(self)["_editable"]:
            raise RuntimeError(f"medical.{name} 只在 editing() 块里能改")
        if name in ("today", "hospitalized"):
            vars(self)["_tables"][name] = value
        elif name in SMALL:
            vars(self)[name] = value
        else:
            raise AttributeError(f"Medical has no field {name}")

    def sources(self) -> tuple[core.JSON, ...]:
        """
        Return arguments:
        tuple -- 读出它时三个键的值（KEY、CLINIC、WARD）
        """
        raw = vars(self)["_raw"]
        return (raw[KEY], raw[CLINIC], raw[WARD])

    def encoded(self) -> dict[str, core.JSON]:
        """
        Return arguments:
        dict -- 每个键现在的 JSON。没建过的病人表不在里面，SMALL 的项一项也没读过、改过时 KEY 不在里面
        """
        out: dict[str, core.JSON] = {}
        held = vars(self)
        if any(name in held for name in SMALL):
            small = cast(Mapping[str, core.JSON], held["_raw"][KEY])
            out[KEY] = {
                name: (
                    medical_patient.plain(held[name])
                    if name in held
                    else small.get(name, default)
                )
                for name, default in SMALL.items()
            }
        tables = held["_tables"]
        for name, key in (("today", CLINIC), ("hospitalized", WARD)):
            if name in tables:
                out[key] = medical_patient.patients_json(tables[name])
        return out

    def as_fields(self) -> dict[str, Any]:
        """
        Return arguments:
        dict -- 罗德岛对象上旧的属性名到值
        """
        return {old: getattr(self, new) for old, new in OLD_NAMES.items()}


_open: list[Medical] = []
_view: list[Medical] = []


def state() -> Medical:
    """
    医疗部的数据。在 editing() 块里时为块的 Medical，可以改；块外为按当前缓冲区读出的只读视图，属性赋值报错。
    三个键的值没变时块外各次调用给同一个视图
    Return arguments:
    Medical -- 医疗部的数据
    """
    if _open:
        return _open[-1]
    sources = tuple(working.get(None, key) for key in (KEY, CLINIC, WARD))
    if _view and all(map(lambda a, b: a is b, _view[0].sources(), sources)):
        return _view[0]
    _view[:] = [Medical()]
    return _view[0]


def of(game: core.GameState) -> Medical:
    """
    只读 game 里的医疗部数据
    Keyword arguments:
    game -- 游戏状态
    Return arguments:
    Medical -- 医疗部的数据
    """
    return Medical(game)


@contextmanager
def editing() -> Iterator[Medical]:
    """
    改医疗部数据的块。嵌套的块共用最外层的 Medical。最外层的块结束时，把三个键里值变了的写进当前缓冲区（working.put）。
    块里抛出 Exception（出错）时什么也不写；抛出别的 BaseException（如玩家定下行动的 Chosen）时照常写
    Return arguments:
    Iterator -- 医疗部的数据
    """
    if _open:
        yield _open[-1]
        return
    medical = Medical(editable=True)
    _open.append(medical)
    try:
        yield medical
    except Exception:
        raise
    except BaseException:
        _write(medical)
        raise
    else:
        _write(medical)
    finally:
        _open.clear()


def _write(medical: Medical) -> None:
    for key, new in medical.encoded().items():
        if not medical_patient.same(working.get(None, key), new):
            working.put(None, key, new)


def remap_doctors(old_to_new: Mapping[int, int]) -> None:
    """
    角色换id时，把门诊、住院医生名单与分科配置里的旧id换成新id
    Keyword arguments:
    old_to_new -- 旧id到新id，表里没有的id不变
    """
    with editing() as m:
        m.clinic_doctor_ids = [
            old_to_new.get(i, i) for i in m.clinic_doctor_ids
        ]
        m.hospital_doctor_ids = [
            old_to_new.get(i, i) for i in m.hospital_doctor_ids
        ]
        for systems in m.doctor_specializations.values():
            for system, ids in systems.items():
                systems[system] = [old_to_new.get(i, i) for i in ids]


class PickledPatient:
    """版本 9 之前的存档里的病人（Medical_System.medical_constant.MedicalPatient）解开成的属性包"""


def adopt_island(loaded_dict: dict[str, Any]) -> None:
    """
    读档时，罗德岛对象带着 OLD_NAMES 里的医疗部属性（游戏写的存档里，只有版本 9 之前的带着它们）就把它们写进
    当前缓冲区的医疗部数据，再从对象上删掉这些属性与 DEAD_FIELDS。对象上没有这些属性时什么也不写
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    """
    island = loaded_dict.get("rhodes_island")
    attrs = vars(island) if island is not None else {}
    found = {name: attrs.pop(name) for name in OLD_NAMES if name in attrs}
    for name in DEAD_FIELDS:
        attrs.pop(name, None)
    if found:
        put_fields(found)


def put_fields(values: Mapping[str, Any]) -> None:
    """
    在 editing() 里把按旧属性名给出的值写进医疗部数据（读旧存档用）
    Keyword arguments:
    values -- 罗德岛对象上旧的属性名到值，病人表（OLD_TABLES）的病人是带 __dict__ 的对象。病人身上不是字段的属性不要
    """
    with editing() as m:
        for old, given in values.items():
            value = given
            if old in OLD_TABLES:
                value = {
                    pid: medical_patient.from_attrs(vars(p))
                    for pid, p in given.items()
                }
            elif OLD_NAMES[old] == "daily_counters" and given is not None:
                value = mc.MedicalDailyCounters.from_mapping(given)
            setattr(m, OLD_NAMES[old], value)
