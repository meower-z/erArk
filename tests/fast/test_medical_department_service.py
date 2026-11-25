"""
医疗部服务测试
==============
验证医疗部报表服务的概览、状态统计、药品缓存、待诊、手术、财务与日志文本。
验证医疗部管理服务的耗时估算、分科展示与分配、设施等级门槛及收费系数调整。
在拦截 Script.UI 与 Script.Settle 的独立子进程中验证两项服务可无界面运行。
"""

from typing import cast
from unittest import mock

from Script.Config import game_config
from Script.Design import handle_ability
from Script.Kernel import core
from Script.Modules.domains import abilities, facility, medical, medical_patient
from Script.Modules.gameplay_resolution import (
    medical_department_service as dept,
)
from Script.Modules.gameplay_resolution import (
    medical_management_service as mgmt,
)
from Script.Modules.gameplay_resolution import working
from Script.System.Medical_System import medical_constant as mc
from Script.System.Medical_System import medical_service
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import ChildRun, run_ui_free

S = mc.MedicalPatientState
""" MedicalPatientState 枚举的简写别名。 """
CLINIC = mc.SPECIALIZATION_ROLE_CLINIC
""" 门诊医生岗位键值的简写常量。 """
HOSPITAL = mc.SPECIALIZATION_ROLE_HOSPITAL
""" 住院医生岗位键值的简写常量。 """
GENERAL = mc.SPECIALIZATION_GENERAL_KEY
""" 全科分科键值的简写常量。 """
UI_FREE_RUN = """
from Script.Kernel import core
from Script.Modules.domains import facility, identity, medical, medical_patient
from Script.Modules.gameplay_resolution import medical_department_service as dept
from Script.Modules.gameplay_resolution import medical_management_service as mgmt
from Script.Modules.gameplay_resolution import working
from Script.System.Medical_System import medical_constant as mc
from Script.System.Medical_System import medical_service
from Script.Modules.save_load import kernel_state
S = mc.MedicalPatientState
core.reset_state(core.GameState(kernel_state.first_clock(), {}, {}))
with working.based_on(core.state()):
    for cid, name in ((0, "doctor"), (1, "a"), (2, "b")):
        identity.put(identity.Identity(cid, name=name))
    medical_service.init_medical_department_data()
    with medical.editing() as m:
        m.today, m.hospitalized, m.accumulator, m.surgery_records = {}, {}, {}, []
    texts = [dept.recent_reports_text(), dept.overview_cache_text(), dept.pending_text(),
        dept.surgery_text(), dept.surgery_record_text(), mgmt.doctor_text()]
    with medical.editing() as m:
        m.today = {1: medical_patient.MedicalPatient(patient_id=1, severity_level=1, state=S.REFRESHED,
            need_resources={7: 1.0})}
        m.hospitalized = {2: medical_patient.MedicalPatient(patient_id=2, severity_level=2, state=S.HOSPITALIZED,
            need_surgery=True, need_resources={7: 2.0})}
        m.clinic_doctor_ids = [1, 9]
        m.hospital_doctor_ids = [2]
        m.accumulator = {7: 0.5}
        m.surgery_records = [{"doctor_id": 2, "patient_id": 2, "status": "ok"}]
        m.daily_counters = mc.MedicalDailyCounters.from_mapping({"medicine_consumed": {7: 1.0, 3: 0.0}})
        m.new_price_ratio = 1.2
    medical_service.append_medical_report({"title": "t", "income": 1})
    facility.set_level(mc.MEDICAL_FACILITY_ID, 3)
    texts += [dept.overview_text(), dept.overview_state_text(), dept.detail_state_text(),
        dept.overview_cache_text(), dept.detail_cache_text(), dept.pending_text(), dept.surgery_text(),
        dept.surgery_record_text(), dept.finance_text(), dept.medicine_need_text(), dept.recent_reports_text(),
        mgmt.doctor_text(), mgmt.priority_text(mc.MedicalPatientPriority.NORMAL), mgmt.price_text(),
        mgmt.specialty_heading(mc.SPECIALIZATION_ROLE_HOSPITAL)]
    payload["hospital"] = mgmt.shows_hospital_specialties()
    payload["rows"] = len(mgmt.specialty_rows(mc.SPECIALIZATION_ROLE_CLINIC))
    key = medical_service.get_specialization_categories()[1]["key"]
    target = mgmt.assign_target(mc.SPECIALIZATION_ROLE_CLINIC, key)
    texts += [mgmt.assign_prompt(target), mgmt.assign_doctor(target, 1), mgmt.assign_doctor(target, 5),
        mgmt.adjust_price_ratio(-200), mgmt.reset_price_ratio()]
    with medical.editing() as m:
        m.new_price_ratio = 0.0
        m.daily_counters = mc.MedicalDailyCounters()
    texts += [mgmt.adjust_price_ratio(5), mgmt.price_text(), dept.finance_text()]
    payload["hours"] = mgmt.estimate_remaining_hours()
    payload["texts"] = len([t for t in texts if t])
"""
""" 在拦截界面与结算导入的子进程中依次调用两项服务全部公开函数的脚本。 """


def patient(
    pid: int, state: mc.MedicalPatientState, severity: int = 1, **fields: object
) -> medical_patient.MedicalPatient:
    """构造带有编号、状态、病情等级与附加字段的测试病人对象。"""
    return medical_patient.MedicalPatient(
        patient_id=pid, severity_level=severity, state=state, **fields
    )


def lines(text: str) -> list[str]:
    """将多行文本按行拆分为字符串列表。"""
    return text.splitlines()


class MedicalCase(FastTestCase):
    """医疗部服务测试基类，负责初始化角色与空医疗部状态。"""

    def setUp(self) -> None:
        """创建测试角色与工作区状态并重置医疗部基础数据。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "甲医生")
        self.world.chara(2, "乙医生")
        self.world.chara(3, "丙医生")
        self.enterContext(working.based_on(core.state()))
        medical_service.init_medical_department_data()
        self.edit(
            today={},
            hospitalized={},
            accumulator={},
            surgery_records=[],
            recent_reports=[],
            clinic_doctor_ids=[],
            hospital_doctor_ids=[],
            new_price_ratio=0.0,
            price_ratio=1.0,
        )

    @staticmethod
    def edit(**fields: object) -> None:
        """在医疗部编辑块内批量更新指定状态字段。"""
        with medical.editing() as state:
            for name, value in fields.items():
                setattr(state, name, value)


class ReportTextTest(MedicalCase):
    """医疗部报表服务文本生成规则测试集。"""

    def test_overview_counts_queue_beds_and_staff(self) -> None:
        """验证经营概览文本正确统计收费策略、医生能力、排队、床位与今日收入。"""
        self.edit(
            today={
                1: patient(1, S.REFRESHED),
                2: patient(2, S.IN_TREATMENT_PLAYER),
                3: patient(3, S.WAITING_MEDICATION),
                4: patient(4, S.MEDICINE_GRANTED),
                6: patient(6, S.WAITING_MEDICATION),
            },
            hospitalized={5: patient(5, S.HOSPITALIZED)},
            bed_limit=4,
            income_today=120,
            price_ratio=1.5,
            priority_mode=mc.MedicalPatientPriority.FOCUS_CRITICAL.value,
            clinic_doctor_ids=[1, 2],
            clinic_doctor_power=7.6,
            hospital_doctor_ids=[3],
            hospital_doctor_power=2.0,
        )
        critical = mc.translate_priority(
            mc.MedicalPatientPriority.FOCUS_CRITICAL
        )
        self.assertEqual(
            lines(dept.overview_text()),
            [
                f"收费系数：1.50 倍 | 接诊优先策略：{critical}",
                "门诊医生：2 人（医疗能力总和 7） | 住院医生：1 人（医疗能力总和 2）",
                "门诊排队 2 人 | 等待用药 2 人 | 住院 1/4 张床位 | 今日收入 120 龙门币",
            ],
        )

    def test_state_counts_cover_both_tables(self) -> None:
        """验证概览与明细的状态统计同时计入门诊表与住院表。"""
        self.edit(
            today={1: patient(1, S.REFRESHED), 2: patient(2, S.REFRESHED)},
            hospitalized={3: patient(3, S.HOSPITALIZED)},
        )
        counts = {S.REFRESHED: 2, S.HOSPITALIZED: 1}
        body = [
            f"  {mc.get_state_display_name(state)}：{counts.get(state, 0)} 人"
            for state in S
        ]
        self.assertEqual(
            lines(dept.overview_state_text()), ["病人状态统计："] + body
        )
        self.assertEqual(
            lines(dept.detail_state_text()), ["病人状态概览："] + body
        )

    def test_medicine_cache_lists_sorted_resources(self) -> None:
        """验证两处药品扣除缓存的空态差异、编号升序与未知资源回退。"""
        self.assertEqual(
            lines(dept.overview_cache_text()),
            ["药品扣除缓存：", "  暂无扣除记录"],
        )
        self.assertEqual(lines(dept.detail_cache_text()), ["药品扣除缓存："])
        self.edit(accumulator={7: 0.5, 3: 1.25})
        name = {rid: dept.resource_name(rid) for rid in (3, 7)}
        body = [f"  {name[3]}(3)：1.25", f"  {name[7]}(7)：0.50"]
        self.assertEqual(lines(dept.overview_cache_text())[1:], body)
        self.assertEqual(lines(dept.detail_cache_text())[1:], body)
        self.assertEqual(dept.resource_name(-5), "-5")

    def test_pending_preview_orders_by_severity_then_id(self) -> None:
        """验证待诊示例按病情降序与编号升序截断前 6 条及空态提示。"""
        self.assertEqual(
            lines(dept.pending_text()), ["在诊病人示例：", "  当前无待诊病人"]
        )
        today = {
            pid: patient(pid, S.REFRESHED, severity=pid % 3)
            for pid in range(1, 9)
        }
        today[9] = patient(9, S.WAITING_MEDICATION, severity=5)
        today[2] = patient(2, S.IN_TREATMENT, severity=2, complications=[1, 2])
        self.edit(today=today)
        shown = lines(dept.pending_text())[1:]
        self.assertEqual(
            [line.split("#")[1].split(" ")[0] for line in shown],
            ["2", "5", "8", "1", "4", "7"],
        )
        self.assertIn("并发症数：2", shown[0])

    def test_surgery_lists_waiting_and_recent_records(self) -> None:
        """验证待手术列表排序截断前 8 条及近期手术记录保留末 10 条。"""
        self.assertEqual(
            lines(dept.surgery_text()),
            ["待手术病人：0 人", "  当前无待手术病人"],
        )
        self.assertEqual(
            lines(dept.surgery_record_text()),
            ["近期手术记录：", "  暂无手术记录"],
        )
        ward = {
            pid: patient(
                pid, S.HOSPITALIZED, severity=pid % 2, need_surgery=True
            )
            for pid in range(1, 11)
        }
        ward[11] = patient(11, S.HOSPITALIZED, severity=3)
        ward[1] = patient(
            1, S.HOSPITALIZED, need_surgery=True, last_surgery_result="blocked"
        )
        records = [
            {"patient_id": n, "doctor_id": 1, "status": "ok"} for n in range(12)
        ]
        records[-1] = {"patient_id": 99, "doctor_id": 42}
        self.edit(hospitalized=ward, surgery_records=records)
        shown = lines(dept.surgery_text())
        self.assertEqual(shown[0], "待手术病人：10 人")
        self.assertEqual(
            [line.split("#")[1].split(" ")[0] for line in shown[1:]],
            ["1", "3", "5", "7", "9", "2", "4", "6"],
        )
        self.assertIn("阻塞：blocked | 需手术：是", shown[1])
        self.assertIn("阻塞：- | 需手术：是", shown[2])
        history = lines(dept.surgery_record_text())[1:]
        self.assertEqual(len(history), 10)
        self.assertEqual(
            history[0], "  时间：- | 病例#2 | 医生：甲医生 | 结果：ok"
        )
        self.assertEqual(history[-1], "  时间：- | 病例#99 | 医生：- | 结果：-")

    def test_finance_totals_and_consumption_detail(self) -> None:
        """验证财务文本输出收入、当日统计及药品消耗明细与空消耗提示。"""
        counters = mc.MedicalDailyCounters.from_mapping(
            {"hospitalized_today": 2, "medicine_consumed": {7: 2.0, 3: 0.0}}
        )
        self.edit(income_today=30, income_total=900, daily_counters=counters)
        text = lines(dept.finance_text())
        self.assertEqual(
            text[:3],
            [
                "今日医疗收入：30 龙门币",
                "累计医疗收入：900 龙门币",
                "今日统计：",
            ],
        )
        self.assertIn(
            f"  {mc.DISPLAY_NAME_MAPPING['hospitalized_today']}：2", text
        )
        consumed = mc.DISPLAY_NAME_MAPPING["medicine_consumed"]
        index = text.index(f"  {consumed}：总计 2.00 单位")
        self.assertEqual(
            text[index + 1], f"    {dept.resource_name(7)}(7)：2.00 单位"
        )
        self.assertNotIn(f"{dept.resource_name(3)}(3)", "".join(text))
        self.edit(daily_counters=mc.MedicalDailyCounters())
        text = lines(dept.finance_text())
        index = text.index(f"  {consumed}：总计 0.00 单位")
        self.assertEqual(text[index + 1], "    暂无药品消耗记录")

    def test_medicine_need_skips_refreshed_patients(self) -> None:
        """验证尚需药品统计跳过 REFRESHED 状态病人并按资源编号累加汇总。"""
        self.edit(
            today={
                1: patient(1, S.REFRESHED, need_resources={7: 5.0}),
                2: patient(2, S.IN_TREATMENT, need_resources={7: 1.5, 3: 1}),
            },
            hospitalized={3: patient(3, S.HOSPITALIZED, need_resources={7: 2})},
        )
        self.assertEqual(
            lines(dept.medicine_need_text()),
            [
                "待诊/住院病人尚需药品：",
                f"  {dept.resource_name(3)}(3)：1.00",
                f"  {dept.resource_name(7)}(7)：3.50",
            ],
        )

    def test_recent_reports_show_latest_three(self) -> None:
        """验证近期日志空态提示及仅渲染最新 3 条医疗经营日志。"""
        self.assertEqual(
            dept.recent_reports_text(), "\n暂无医疗经营日志记录。\n"
        )
        with medical.editing():
            for n in range(4):
                medical_service.append_medical_report({"title": f"○第{n}"})
        text = dept.recent_reports_text()
        self.assertTrue(text.startswith("\n○第3\n"))
        self.assertEqual([n for n in range(4) if f"○第{n}" in text], [1, 2, 3])


class ManagementTest(MedicalCase):
    """医疗部管理服务规则与写入逻辑测试集。"""

    def test_estimate_divides_waiting_hours_by_doctor_speed(self) -> None:
        """验证剩余耗时按待诊工时除以门诊医生速度总和及下限 0.25 计算。"""
        severity = sorted(game_config.config_medical_severity)
        hours = [
            game_config.config_medical_severity[s].base_hours for s in severity
        ]
        self.edit(
            today={
                1: patient(1, S.REFRESHED, severity[0], diagnose_progress=0.5),
                2: patient(2, S.IN_TREATMENT, severity[1]),
                3: patient(3, S.WAITING_MEDICATION, severity[1]),
                4: patient(4, S.REFRESHED, -1),
                5: patient(5, S.REFRESHED, severity[0], diagnose_progress=99.0),
            },
        )
        remaining = max(hours[0] - 0.5, 0.0) + hours[1]
        self.assertAlmostEqual(
            mgmt.estimate_remaining_hours(), remaining / 0.25
        )
        abilities.ability(1)[mc.MEDICAL_ABILITY_ID] = 4
        abilities.ability(2)[mc.MEDICAL_ABILITY_ID] = 0
        self.edit(clinic_doctor_ids=[1, 2, 77])
        speed = handle_ability.get_ability_adjust(4)
        speed += handle_ability.get_ability_adjust(0)
        self.assertAlmostEqual(
            mgmt.estimate_remaining_hours(), remaining / speed
        )
        with mock.patch.object(
            handle_ability, "get_ability_adjust", return_value=0.1
        ):
            self.assertAlmostEqual(
                mgmt.estimate_remaining_hours(), remaining / 0.5
            )

    def test_doctor_text_counts_roles_and_beds(self) -> None:
        """验证医生管理文本的医生人数、能力、床位、耗时及优先策略行。"""
        self.edit(
            clinic_doctor_ids=[1, 2],
            clinic_doctor_power=3.9,
            hospital_doctor_ids=[3],
            hospital_doctor_power=1.0,
            bed_limit=6,
            hospitalized={4: patient(4, S.HOSPITALIZED)},
        )
        self.assertEqual(
            lines(mgmt.doctor_text()),
            [
                "门诊医生：2 人 | 医疗能力总和 3",
                "住院医生：1 人 | 医疗能力总和 1",
                "床位上限 6 张，当前占用 1 张",
                "按当前排班预计完成全部门诊耗时约 0.00 小时",
            ],
        )
        normal = mc.MedicalPatientPriority.NORMAL
        self.assertEqual(
            mgmt.priority_text(normal),
            f"当前接诊优先策略：{mc.translate_priority(normal)}\n",
        )

    def test_hospital_specialties_need_level_three(self) -> None:
        """验证住院分科展示门槛在医疗设施 2 级关闭、3 级开启。"""
        facility.set_level(mc.MEDICAL_FACILITY_ID, 2)
        self.assertFalse(mgmt.shows_hospital_specialties())
        facility.set_level(mc.MEDICAL_FACILITY_ID, 3)
        self.assertTrue(mgmt.shows_hospital_specialties())

    def test_specialty_rows_and_assignment(self) -> None:
        """验证分科展示行、分配目标、成功与失败反馈及未知科室回退。"""
        abilities.ability(1)[mc.MEDICAL_ABILITY_ID] = 2
        self.edit(clinic_doctor_ids=[1, 2], hospital_doctor_ids=[3])
        categories = medical_service.get_specialization_categories()
        other = categories[1]
        self.assertEqual(
            mgmt.specialty_heading(HOSPITAL),
            f"{mc.ROLE_DISPLAY_NAME[HOSPITAL]}科室情况：\n",
        )
        rows = mgmt.specialty_rows(CLINIC)
        self.assertEqual(
            [row.category_key for row in rows], [c["key"] for c in categories]
        )
        self.assertEqual(
            rows[0].return_text, CLINIC + f"分配到{categories[0]['name']}"
        )
        self.assertIn("（2 人，平均倍率 x", rows[0].summary)
        self.assertEqual(rows[1].doctors, "：空缺")
        target = mgmt.assign_target(CLINIC, other["key"])
        self.assertEqual(
            (target.role_name, target.category_name, target.assigned_ids),
            (mc.ROLE_DISPLAY_NAME[CLINIC], other["name"], frozenset()),
        )
        self.assertEqual(
            mgmt.assign_prompt(target),
            f"请选择一名{target.role_name}分配至「{other['name']}」：\n",
        )
        self.assertEqual(
            mgmt.assign_doctor(target, 1),
            f"已将 甲医生 调整至「{other['name']}」({target.role_name})",
        )
        self.assertEqual(
            mgmt.assign_target(CLINIC, other["key"]).assigned_ids,
            frozenset({1}),
        )
        bonus = 1.0 + 2 * mc.SPECIALIZATION_BONUS_PER_LEVEL
        self.assertEqual(
            mgmt.specialty_rows(CLINIC)[1].doctors,
            f"：甲医生(Lv2,x{bonus:.2f})",
        )
        self.assertEqual(
            mgmt.assign_doctor(target, 3), "分配失败：doctor_not_in_role"
        )
        self.assertEqual(
            mgmt.assign_target(CLINIC, "missing").category_name, "missing"
        )

    def test_price_text_and_adjustments(self) -> None:
        """验证收费文本显示、待生效系数增减、0.10 下限钳制与重置为 1.0。"""
        self.edit(price_ratio=1.5)
        text = lines(mgmt.price_text())
        self.assertEqual(text[0], "当前收费系数：1.50 倍 (150%)")
        self.assertFalse(any("待调整" in line for line in text))
        self.assertEqual(
            text[-1], "收费系数越高，病人刷新量越低，但单次收入越高。"
        )
        self.assertEqual(
            mgmt.adjust_price_ratio(10), "已调整收费系数至 1.60 倍，明天生效"
        )
        self.assertIn(
            "  └ 待调整系数：1.60 倍（明日生效）", lines(mgmt.price_text())
        )
        self.assertEqual(
            mgmt.adjust_price_ratio(-5), "已调整收费系数至 1.55 倍，明天生效"
        )
        self.assertEqual(
            mgmt.adjust_price_ratio(-500), "已调整收费系数至 0.10 倍，明天生效"
        )
        self.assertAlmostEqual(medical.state().new_price_ratio, 0.1)
        self.assertEqual(
            mgmt.reset_price_ratio(), "收费系数已重置为 1.00 倍，明天生效"
        )
        self.assertEqual(medical.state().new_price_ratio, 1.0)
        self.assertEqual(medical.state().price_ratio, 1.5)


class UiFreeRunTest(FastTestCase):
    """医疗部服务无界面子进程导入隔离测试集。"""

    child: ChildRun
    """ 子进程运行结果对象，记录载荷及受限模块检查信息。 """
    error: str
    """ 子进程启动或执行异常时的错误信息，正常为空字符串。 """

    @classmethod
    def setUpClass(cls) -> None:
        """在测试类初始化阶段启动拦截界面与结算导入的子进程并缓存结果。"""
        super().setUpClass()
        cls.error = ""
        try:
            cls.child = run_ui_free(UI_FREE_RUN, boot=True)
        except RuntimeError as error:
            cls.error = str(error)
            cls.child = ChildRun({}, [], [])

    def test_no_ui_or_settle_loaded(self) -> None:
        """验证子进程执行无报错且未加载或尝试导入 Script.UI 与 Script.Settle。"""
        self.assertEqual(self.error, "")
        self.assertEqual((self.child.loaded, self.child.attempted), ([], []))

    def test_child_results(self) -> None:
        """验证子进程中各服务入口返回非空文本及预期状态值。"""
        out = self.child.payload
        self.assertEqual((out["hospital"], out["texts"]), (True, 29))
        self.assertGreater(cast(int, out["rows"]), 1)
        self.assertGreater(cast(float, out["hours"]), 0)
