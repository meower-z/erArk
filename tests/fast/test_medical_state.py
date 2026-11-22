# -*- coding: UTF-8 -*-
"""
基地医疗部的状态（base.medical、base.medical_clinic 与 base.medical_ward）
==========================================================================
- 写进 GameState 再读出，病人、经营日志、当日统计与药物累计器的值与类型不变（枚举、整数键、游戏时间），
  病人表的顺序不变。
- 改一个病人时，没改的病人沿用存的映射本身。只读的块（扫过所有病人、读过容器字段）什么也不写。
- editing() 块里出错（Exception）时什么也不写；玩家定下行动等别的 BaseException 照常写。
  块外给 state() 的属性赋值报 RuntimeError。
- 内核：写进 GameState 的值里已冻结的映射原样沿用。
- 读档。罗德岛对象带着医疗部属性（旧存档）时，值写进 GameState，这些属性与旧病人计数从对象上删掉。
  对象上没有医疗部属性（当前存档）时 GameState 不变。旧存档里的病人对象解开成属性包。
- 角色换 id 时，医生名单与分科配置里的旧 id 换成新 id。
"""

import datetime
import io
import pickle
from collections.abc import Mapping
from types import MappingProxyType
from typing import cast
from unittest import mock

from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import medical, medical_patient
from Script.Modules.gameplay_resolution import working
from Script.System.Medical_System import medical_constant as mc
from tests.fast.base import FastTestCase
from Script.Modules.save_load import legacy_pickle
from Script.Modules.save_load.legacy_pickle import LegacyObject


def full_patient(pid: int) -> medical_patient.MedicalPatient:
    """
    每个字段都不是默认值的病人
    Keyword arguments:
    pid -- 病人编号
    Return arguments:
    MedicalPatient -- 病人
    """
    return medical_patient.MedicalPatient(
        patient_id=pid,
        severity_level=2,
        complications=[3, 1],
        diagnose_progress=1.5,
        need_resources={7: 2.5, 3: 0.0},
        state=mc.MedicalPatientState.HOSPITALIZED,
        clinic_waiting_days=1,
        stay_days=4,
        need_surgery=True,
        surgery_blocked=True,
        personality_type=mc.MedicalPatientPersonality.RATIONAL,
        race_id=5,
        age=31,
        assigned_doctor_id=11,
        assigned_hospital_doctor_id=12,
        severity_name="中度",
        price_ratio=1.25,
        complication_trace=[{"system": "呼吸", "part": "肺", "id": 3}],
        system_keys=["呼吸"],
        player_session_active=True,
        player_previous_state="WAITING",
        player_used_checks=2,
        player_confirmed_complications=[3],
        player_check_records=[{"check": 1, "found": [3]}],
        player_pending_checks=[{"check": 2}],
        last_surgery_result="ok",
        surgery_blocked_resource=7,
        state_label="住院",
        medicine_recorded={7: 0.5},
        medicine_progress={7: 0.25},
        medicine_consumed_units={7: 3},
        last_consumed_units={7: 1},
    )


def typed(value: object) -> object:
    """
    值连同各层的类型，用来比较值与类型都相同
    Keyword arguments:
    value -- 值
    Return arguments:
    object -- 可比较的形式
    """
    if isinstance(value, medical_patient.MedicalPatient):
        return typed(value.as_dict())
    if isinstance(value, dict):
        return ("dict", [(typed(k), typed(v)) for k, v in value.items()])
    if isinstance(value, list):
        return ("list", [typed(v) for v in value])
    return (type(value).__name__, value)


def stored(key: str) -> Mapping[str, core.JSON]:
    """
    当前缓冲区里一张表的值
    Keyword arguments:
    key -- 键
    Return arguments:
    Mapping -- 存的映射
    """
    return cast(Mapping[str, core.JSON], working.get(None, key))


class Interrupt(BaseException):
    """像玩家定下行动时那样离开块的 BaseException"""


class MedicalStateTest(FastTestCase):
    """医疗部数据的存取、块的写入、内核的冻结、读档与换 id"""

    def setUp(self) -> None:
        """GameState 的读写记在 working.based_on(core.state()) 开的缓冲区里"""
        super().setUp()
        self.enterContext(working.based_on(core.state()))

    def test_patient_table_round_trip(self) -> None:
        """病人表写进 GameState 再读出，各字段的值与类型不变；删掉再放回的病人排到最后"""
        table = {
            3: full_patient(3),
            1: medical_patient.MedicalPatient(patient_id=1),
            2: medical_patient.MedicalPatient(patient_id=2),
        }
        with medical.editing() as m:
            m.hospitalized = dict(table)
        self.assertEqual(typed(medical.state().hospitalized), typed(table))
        with medical.editing() as m:
            m.hospitalized[1] = m.hospitalized.pop(1)
        self.assertEqual(list(medical.state().hospitalized), [3, 2, 1])
        self.assertEqual(list(stored(medical.WARD)), ["3", "2", "1"])

    def test_small_values_round_trip(self) -> None:
        """经营日志、手术记录、当日统计与药物累计器写进再读出，值与类型不变（游戏时间、整数键）"""
        when = game_time.at(game_time.minutes(game_time.now()) + 90)
        report = {
            "time": when,
            "income": 30,
            "inventory_detail": {7: 4, 3: 0},
            "stats": {"medicine_consumed": {7: 1.5}, "patients": 2},
        }
        counters = mc.MedicalDailyCounters(
            hospitalized_today=2, medicine_consumed={7: 1.5}
        )
        price = medical.state().price_ratio
        with medical.editing() as m:
            m.recent_reports = [report]
            m.surgery_records = [
                {"time": when, "patient_id": 3, "result": "ok"}
            ]
            m.daily_counters = counters
            m.accumulator = {7: 0.25}
            m.doctor_specializations = {"clinic": {"呼吸": [11, 12]}}
            m.income_total = 120
        view = medical.state()
        self.assertEqual(typed(view.recent_reports), typed([report]))
        self.assertEqual(view.surgery_records[0]["time"], when)
        self.assertEqual(view.daily_counters, counters)
        self.assertEqual(typed(view.accumulator), typed({7: 0.25}))
        self.assertEqual(
            view.doctor_specializations, {"clinic": {"呼吸": [11, 12]}}
        )
        self.assertEqual((view.income_total, view.price_ratio), (120, price))

    def test_untouched_patients_keep_stored_mapping(self) -> None:
        """扫过所有病人、读过容器字段的块什么也不写；改一个病人时，另一个病人存的映射原样沿用"""
        with medical.editing() as m:
            m.today = {1: full_patient(1), 2: full_patient(2)}
        before = stored(medical.CLINIC)
        with medical.editing() as m:
            for p in m.today.values():
                _ = (
                    p.state,
                    p.severity_level,
                    p.need_resources,
                    p.complication_trace,
                )
        self.assertIs(stored(medical.CLINIC), before)
        with medical.editing() as m:
            patient = m.today[1]
            patient.need_resources[7] += 1.0
        after = stored(medical.CLINIC)
        self.assertIsNot(after, before)
        self.assertIs(after["2"], before["2"])
        self.assertEqual(medical.state().today[1].need_resources[7], 3.5)

    def test_block_exits(self) -> None:
        """出错离开的块不写；BaseException 离开的块照常写；块外给 state() 的属性赋值报错"""
        with self.assertRaises(ValueError), medical.editing() as m:
            m.income_today = 5
            raise ValueError
        self.assertEqual(medical.state().income_today, 0)
        with self.assertRaises(Interrupt), medical.editing() as m:
            m.income_today = 6
            raise Interrupt
        self.assertEqual(medical.state().income_today, 6)
        with self.assertRaises(RuntimeError):
            medical.state().income_today = 7
        with medical.editing() as m:
            self.assertEqual(m.income_today, 6)
        self.assertEqual(medical.of(core.state()).income_today, 0)

    def test_nested_proxy_kept(self) -> None:
        """写进 GameState 的值里已冻结的映射原样沿用，不再冻结一次"""
        inner = MappingProxyType({"a": 1})
        game = core.with_value(core.state(), None, medical.WARD, {"1": inner})
        stored = game.data[medical.WARD]
        assert isinstance(stored, MappingProxyType)
        self.assertIs(stored["1"], inner)

    def test_old_island_moves_into_state(self) -> None:
        """旧存档的罗德岛对象带着医疗部属性与旧病人计数。值写进 GameState，这些属性从对象上删掉"""
        bag = LegacyObject()
        vars(bag).update(
            patient_id=9,
            state=mc.MedicalPatientState.HOSPITALIZED,
            need_resources={7: 1.0},
            retired_field=1,
        )
        island = LegacyObject()
        vars(island).update(
            medical_hospitalized={9: bag},
            medical_patients_today={},
            medical_income_total=50,
            medical_daily_counters=mc.MedicalDailyCounters(discharged_today=1),
            medical_doctor_specializations={"clinic": {"呼吸": [11]}},
            patient_now=3,
            patient_cured=1,
            patient_max=10,
            patient_cured_all=4,
        )
        medical.adopt_island({"rhodes_island": island})
        view = medical.state()
        patient = view.hospitalized[9]
        self.assertEqual(
            (
                patient.patient_id,
                patient.state,
                patient.need_resources,
                patient.age,
            ),
            (9, mc.MedicalPatientState.HOSPITALIZED, {7: 1.0}, 18),
        )
        self.assertEqual(view.income_total, 50)
        self.assertEqual(
            view.daily_counters, mc.MedicalDailyCounters(discharged_today=1)
        )
        self.assertEqual(
            view.doctor_specializations, {"clinic": {"呼吸": [11]}}
        )
        gone = set(medical.OLD_NAMES) | set(medical.DEAD_FIELDS)
        self.assertEqual(gone & set(vars(island)), set())

    def test_current_island_keeps_state(self) -> None:
        """当前存档的罗德岛对象没有医疗部属性。GameState 里的医疗部数据不变"""
        with medical.editing() as m:
            m.income_total = 8
        before = working.get(None, medical.KEY)
        medical.adopt_island({"rhodes_island": LegacyObject()})
        self.assertIs(working.get(None, medical.KEY), before)

    def test_old_patient_class_unpickles_to_bag(self) -> None:
        """旧存档的 medical_constant.MedicalPatient 对象加载为 LegacyObject 并保留全部属性"""
        old = type(
            "MedicalPatient",
            (),
            {"__module__": mc.__name__, "__qualname__": "MedicalPatient"},
        )
        patient = old()
        vars(patient).update(patient_id=4, stay_days=2)
        with mock.patch.object(mc, "MedicalPatient", old, create=True):
            data = pickle.dumps(patient)
        loaded = legacy_pickle.LegacyUnpickler(
            io.BytesIO(data), datetime.datetime
        ).load()
        self.assertIs(type(loaded), LegacyObject)
        self.assertEqual(vars(loaded), {"patient_id": 4, "stay_days": 2})

    def test_remap_doctors(self) -> None:
        """角色换 id 时，门诊、住院医生名单与分科配置里的旧 id 换成新 id，没换的不变"""
        with medical.editing() as m:
            m.clinic_doctor_ids = [1, 2]
            m.hospital_doctor_ids = [3]
            m.doctor_specializations = {"hospital": {"呼吸": [3, 2]}}
        medical.remap_doctors({1: 5, 3: 6})
        view = medical.state()
        self.assertEqual(
            (
                view.clinic_doctor_ids,
                view.hospital_doctor_ids,
                view.doctor_specializations,
            ),
            ([5, 2], [6], {"hospital": {"呼吸": [6, 2]}}),
        )
