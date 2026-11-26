"""
玩家诊疗服务测试
================
验证诊疗规则服务的能力计算、提示切换、待检限制、高亮筛选与耗时计算。
验证诊疗界面与治疗文本服务的菜单展开、操作按钮、未确诊折算与缺口提示。
在拦截 Script.UI 与 Script.Settle 的独立子进程中验证三项服务无界面运行。
"""

from typing import cast
from unittest import mock

from Script.Config import game_config, normal_config
from Script.Kernel import core
from Script.Modules.domains import abilities, activity, identity, medical
from Script.Modules.domains import medical_patient, warehouse
from Script.Modules.gameplay_resolution import medical_diagnose_service as rules
from Script.Modules.gameplay_resolution import (
    medical_diagnose_treatment as cure,
)
from Script.Modules.gameplay_resolution import medical_diagnose_view as view
from Script.Modules.gameplay_resolution import working
from Script.System.Medical_System import medical_constant as mc
from Script.System.Medical_System import medical_player_diagnose_function
from Script.System.Medical_System import medical_service
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import ChildRun, run_ui_free

A, B, C = 1001001, 1001011, 20120015
""" 测试用例使用的三个并发症编号：轻症 A、中症 B 与重症 C。 """
MED = mc.MedicalMedicineResource.NORMAL.value
""" 测试使用的常规药剂资源编号常量。 """
HINT2 = {"hint_severity": 2}
""" 标识再检线索为重症提示等级的字典片段。 """
UI_FREE_RUN = """
from Script.Config import game_config, normal_config
from Script.Kernel import core
from Script.Modules.domains import abilities, activity, identity, medical, medical_patient, warehouse
from Script.Modules.gameplay_resolution import medical_diagnose_service as rules
from Script.Modules.gameplay_resolution import medical_diagnose_treatment as cure
from Script.Modules.gameplay_resolution import medical_diagnose_view as view
from Script.Modules.gameplay_resolution import working
from Script.System.Medical_System import medical_player_diagnose_function as session
from Script.System.Medical_System import medical_constant, medical_service
from Script.Modules.save_load import kernel_state
core.reset_state(core.GameState(kernel_state.first_clock(), {}, {}))
normal_config.system_setting.base_setting = {12: 5}
out = []
with working.based_on(core.state()), medical.editing():
    identity.put(identity.Identity(0, name="doctor"))
    identity.put(identity.Identity(1, name="helper"))
    medical_service.init_medical_department_data()
    abilities.ability(0)[46] = 5
    abilities.ability(0)[40] = 1
    abilities.ability(1)[46] = 4
    activity.set_target(0, 1)
    trace = [{"cid": 1001001, "system_id": 10, "part_id": 1001},
        {"complication_id": 20120015, "system_id": 20, "part_id": 2001, "severity_level": 2}, {"cid": 9}]
    p = medical_patient.MedicalPatient(patient_id=1, severity_level=1, complications=[1001001, 20120015, 9],
        complication_trace=trace, need_resources={21: 2.0, 22: 0.0}, race_id=-1,
        personality_type=medical_constant.MedicalPatientPersonality.IRRATIONAL)
    empty = medical_patient.MedicalPatient(patient_id=2, severity_level=99, complications=[])
    player = identity.get(0)
    catalog = session.build_player_check_catalog(p)
    other = next(o["cid"] for pid, part in sorted(catalog[10]["parts"].items()) if pid != 1001 for o in part["options"])
    out += [rules.highlights(p, hint) for hint in range(6)]
    for limits in ((2, 2), (0, 2), (2, 0)):
        for check in ((10, 1001, 1001001), (20, 2001, 20120015), (10, 1001, 1001001), (99, 9, 1001011), (99, 9, 5)):
            rules.toggle_pending(p, catalog, check, limits)
    out += [view.menu_rows(p, catalog, (10, 1001), ([1001011], rules.highlights(p, 5))),
        view.check_status(p, catalog, (2, 2)), view.check_status(p, catalog, (0, 1)),
        view.operation_buttons(p, 2, False), view.operation_buttons(p, 2, True)]
    p.player_confirmed_complications = [other]
    out += [view.menu_rows(p, catalog, (10, None), ([], rules.highlights(p, 2))),
        view.menu_rows(p, catalog, (60, None), ([], rules.highlights(p, 2)))]
    p.player_confirmed_complications = [1001001, 9]
    rules.toggle_pending(p, catalog, (10, 1001, 1001001), (2, 2))
    out += [view.menu_rows(p, catalog, (None, None), ([], rules.highlights(p, 1))),
        rules.med_level(None), rules.med_level(player), rules.check_limit(None), rules.check_limit(player),
        rules.target_count(p, 0), rules.target_count(empty, 0), rules.undiagnosed(p, 3, [1]),
        rules.missing_count(p, 0, [1001001]), rules.missing_count(empty, 3, [1]), rules.hint_indices(4, 0),
        rules.hint_indices(7, 6), rules.hint_context(player), rules.next_hint(player), rules.next_hint(None),
        rules.session_minutes(0), rules.session_minutes(2), rules.option_info(catalog, 10, 1001, 1001001),
        rules.option_info(catalog, 1, 1, 1001011), rules.option_info(catalog, 1, 1, 5)]
    payload["hint"] = dict(normal_config.system_setting.base_setting)
    normal_config.system_setting.base_setting = {12: 5}
    out.append(rules.hint_context(None))
    options = game_config.config_system_setting_option[12]
    game_config.config_system_setting_option[12] = []
    out.append(rules.next_hint(player))
    game_config.config_system_setting_option[12] = options
    normal_config.system_setting.base_setting = None
    out += [rules.hint_context(player), rules.check_results({"results": [{"cid": 1}, 2]}),
        rules.check_results({"results": 3})]
    executed = []
    rules.mark_executed(executed, [{"cid": 0}, {"cid": 4}, {"cid": 4}])
    p.player_check_records = [{"result": "recheck", "system_id": 10, "part_id": 1001, "hint_severity": 1},
        {"result": "recheck", "system_id": 10, "part_id": 1001}, {"result": "recheck", "system_id": 7},
        {"result": "negative"}, 3]
    out += [executed, view.overview_text(p), view.overview_text(empty), view.help_text(),
        view.hint_status(2, ["a", "b", "c"]), view.hint_status(9, []), view.check_status(empty, {}, (1, 1)),
        view.report_rows([{"result": "positive", "cid": 1}, {"result": "odd", "name": "n", "message": "m"}]),
        view.operation_buttons(p, 2, False), view.operation_buttons(empty, 0, False),
        view.severity_text(5), view.outcome_text("recheck")]
    warehouse.set(21, 1)
    out += [cure.treatment_text(p, catalog), cure.shortage_lines(p), cure.quantity(0.0)]
    p.player_confirmed_complications = []
    out += [cure.treatment_text(p, catalog), cure.treatment_text(empty, {})]
    p.player_check_records = []
    p.complications = [1001001]
    p.need_resources = {"x": 1.0, 21: 0.0}
    out += [cure.treatment_text(p, catalog), cure.treatment_message({"medicine_success": True}, p),
        cure.treatment_message({}, p), cure.shortage(21, 0.0, {})]
    p.need_resources = {21: 5.0}
    out.append(cure.treatment_message({"diagnose_income": 3}, p))
    payload["levels"] = [rules.med_level(player), rules.check_limit(player)]
payload["values"] = len(out)
"""
""" 在无界面隔离子进程中遍历三项服务公开入口的测试脚本。 """


def patient(
    complications: list[int], **fields: object
) -> medical_patient.MedicalPatient:
    """按给定并发症编号列表与附加字段构造测试用病人对象。"""
    configs = [
        game_config.config_medical_complication[c] for c in complications
    ]
    trace = [
        {"cid": c.cid, "system_id": c.system_id, "part_id": c.part_id}
        | {"severity_level": c.severity_level}
        for c in configs
    ]
    fields.setdefault("complication_trace", trace)
    return medical_patient.MedicalPatient(
        patient_id=1, severity_level=1, complications=complications, **fields
    )


def tree(sick: medical_patient.MedicalPatient) -> rules.Catalog:
    """为指定测试病人构建检查目录树。"""
    return medical_player_diagnose_function.build_player_check_catalog(sick)


def name(cid: int) -> str:
    """按并发症配置编号查询对应的并发症名称。"""
    return game_config.config_medical_complication[cid].name


class DiagnoseCase(FastTestCase):
    """玩家诊疗服务测试基类，初始化角色、医疗状态并隔离基础设置。"""

    def setUp(self) -> None:
        """准备博士与助手角色、医疗编辑事务及可恢复的全局基础设置。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "助手")
        self.enterContext(working.based_on(core.state()))
        self.enterContext(medical.editing())
        medical_service.init_medical_department_data()
        setting = normal_config.system_setting
        saved = setting.base_setting
        setting.base_setting = dict(saved)
        self.addCleanup(setattr, setting, "base_setting", saved)
        self.player = identity.get(0)

    @staticmethod
    def levels(med: int, talk: int = 0, helper: int | None = None) -> None:
        """设置博士医疗与话术能力，并在传入助手等级时绑定交互对象。"""
        abilities.ability(0)[mc.MEDICAL_ABILITY_ID] = med
        abilities.ability(0)[rules.TALK_ABILITY_ID] = talk
        if helper is not None:
            abilities.ability(1)[mc.MEDICAL_ABILITY_ID] = helper
            activity.set_target(0, 1)


class RulesTest(DiagnoseCase):
    """验证 medical_diagnose_service 的各项核心规则。"""

    def test_check_limit_two_per_talk_level(self) -> None:
        """验证检查次数上限按话术等级两倍计算且最小为 1。"""
        self.levels(0, talk=0)
        self.assertEqual(rules.check_limit(self.player), 1)
        self.levels(0, talk=3)
        self.assertEqual(rules.check_limit(self.player), 6)
        self.assertEqual(rules.check_limit(None), 1)

    def test_med_level_adds_half_of_target_capped(self) -> None:
        """验证综合医疗等级叠加交互对象一半能力并封顶为 8。"""
        self.levels(3)
        self.assertEqual(rules.med_level(self.player), 3)
        self.levels(3, helper=7)
        self.assertEqual(rules.med_level(self.player), 6)
        self.levels(6, helper=8)
        self.assertEqual(rules.med_level(self.player), 8)
        self.assertEqual(rules.med_level(None), 0)

    def test_hint_clamps_and_cycles_within_level(self) -> None:
        """验证提示档位钳制、循环切换、等级不足与未配置反馈。"""
        base = normal_config.system_setting.base_setting
        self.levels(2)
        base[rules.HINT_SETTING_ID] = 5
        value, allowed, options = rules.hint_context(self.player)
        self.assertEqual((value, allowed, len(options)), (2, [0, 1, 2], 6))
        self.assertEqual(base[rules.HINT_SETTING_ID], 2)
        cycle = []
        for __ in range(3):
            self.assertIsNone(rules.next_hint(self.player))
            cycle.append(base[rules.HINT_SETTING_ID])
        self.assertEqual(cycle, [0, 1, 2])
        self.levels(0)
        locked = rules.next_hint(self.player)
        self.assertEqual(
            locked, "博士当前的医疗能力等级不足以启用额外的诊疗提示。"
        )
        self.assertEqual(base[rules.HINT_SETTING_ID], 0)
        self.levels(7)
        self.assertEqual(rules.hint_indices(7, 6), [0, 1, 2, 3, 4, 5])
        self.assertEqual(rules.hint_indices(4, 6), [0, 1, 2, 3])
        self.assertEqual(rules.hint_indices(7, 3), [0, 1, 2])
        with mock.patch.dict(
            game_config.config_system_setting_option, {12: []}
        ):
            self.assertEqual(
                rules.next_hint(self.player),
                "当前版本未配置诊疗提示选项，无法切换。",
            )

    def test_toggle_pending_respects_limits(self) -> None:
        """验证待检切换遵守并行上限、取消选中、次数耗尽与已确诊拦截。"""
        sick = patient([A, C])
        catalog = tree(sick)
        rules.toggle_pending(sick, catalog, (10, 1001, B), (2, 1))
        self.assertEqual(
            sick.player_pending_checks,
            [{"cid": B, "system_id": 10, "part_id": 1001, "severity_level": 1}],
        )
        rules.toggle_pending(sick, catalog, (20, 2001, C), (2, 1))
        self.assertEqual(len(sick.player_pending_checks), 1)
        rules.toggle_pending(sick, catalog, (10, 1001, B), (2, 1))
        self.assertEqual(sick.player_pending_checks, [])
        sick.player_used_checks = 2
        rules.toggle_pending(sick, catalog, (10, 1001, A), (2, 2))
        self.assertEqual(sick.player_pending_checks, [])
        sick.player_used_checks = 0
        sick.player_confirmed_complications = [A]
        rules.toggle_pending(sick, catalog, (10, 1001, A), (2, 2))
        self.assertEqual(sick.player_pending_checks, [])

    def test_missing_count_and_menu_visibility(self) -> None:
        """验证未确诊项计数与待检菜单显示条件的边界判定。"""
        sick = patient([A, C])
        self.assertEqual(rules.missing_count(sick, 2, [A]), 1)
        self.assertTrue(rules.undiagnosed(sick, 2, [A]))
        self.assertFalse(rules.undiagnosed(sick, 2, [A, C]))
        self.assertTrue(rules.undiagnosed(sick, 0, [A]))
        empty = patient([])
        self.assertEqual(rules.missing_count(empty, 3, [A]), 2)
        self.assertFalse(rules.undiagnosed(empty, 0, []))

    def test_highlights_grow_with_hint_level(self) -> None:
        """验证不同提示档位下系统、部位与各严重度选项的高亮递增规律。"""
        sick = patient([A, B, C])
        seen = [rules.highlights(sick, hint) for hint in range(6)]
        systems, parts = {10, 20}, {(10, 1001), (20, 2001)}
        self.assertEqual(seen[0], (set(), set(), set()))
        self.assertEqual(seen[1], (systems, set(), set()))
        self.assertEqual(seen[2], (systems, parts, set()))
        self.assertEqual([s[2] for s in seen[3:]], [{A}, {A, B}, {A, B, C}])
        sick.player_confirmed_complications = [C]
        self.assertEqual(
            rules.highlights(sick, 5), ({10}, {(10, 1001)}, {A, B})
        )
        bare = patient([C], complication_trace=[{"cid": C, "system_id": 20}])
        self.assertEqual(
            [rules.highlights(bare, h)[2] for h in (4, 5)], [set(), {C}]
        )

    def test_checks_record_and_session_minutes(self) -> None:
        """验证检查结果过滤、已检编号去重追加及会话耗时规则。"""
        result: dict[str, object] = {"results": [{"cid": A}, "bad"]}
        self.assertEqual(rules.check_results(result), [{"cid": A}])
        executed = [A]
        rules.mark_executed(executed, [{"cid": 0}, {"cid": A}, {"cid": B}])
        self.assertEqual(executed, [A, B])
        self.assertEqual([rules.session_minutes(n) for n in (0, 3)], [5, 30])


class ViewTest(DiagnoseCase):
    """验证 medical_diagnose_view 的菜单行、状态文本与按钮生成。"""

    def test_menu_rows_follow_expansion(self) -> None:
        """验证检查菜单行随展开状态、已检标记、高亮与性别限制变化。"""
        sick = patient([A, C])
        catalog = tree(sick)
        none = (set(), set(), set())
        rows = view.menu_rows(sick, catalog, (None, None), ([], none))
        self.assertEqual([r.args[0] for r in rows], sorted(catalog))
        self.assertTrue(all(r.label.startswith("   [+]") for r in rows))
        sick.player_pending_checks = [
            {"cid": A, "system_id": 10, "part_id": 1001}
        ]
        marks = ([B], rules.highlights(sick, 5))
        rows = view.menu_rows(sick, catalog, (10, 1001), marks)
        kinds = [r.kind for r in rows[:4]]
        self.assertEqual(kinds, ["system", "part", "option", "option"])
        self.assertEqual(rows[0].style, "gold_enrod")
        option, done = rows[2], next(r for r in rows if r.kind == "done")
        self.assertIn("[✔] 轻症 | " + name(A), option.label)
        self.assertEqual(option.args, (10, 1001, A))
        self.assertEqual(option.style, "gold_enrod")
        self.assertTrue(done.label.startswith("（已检查）        [  ] 中症 | "))
        both = patient([A, B])
        both.player_confirmed_complications = [A]
        hint = ([], rules.highlights(both, 1))
        rows = view.menu_rows(both, tree(both), (10, None), hint)
        self.assertEqual(
            [r.style for r in rows[:2]], ["gold_enrod", "deep_gray"]
        )
        system = min(
            s for s in catalog if 0 in self.limits(catalog, s).values()
        )
        rows = view.menu_rows(sick, catalog, (system, None), ([], none))
        shown = [r.args[1] for r in rows if r.kind == "part"]
        limits = self.limits(catalog, system)
        self.assertEqual(shown, [p for p in sorted(limits) if limits[p]])

    @staticmethod
    def limits(catalog: rules.Catalog, system: int) -> dict[int, int]:
        """读取目录中指定系统下各部位的性别限制映射。"""
        parts = catalog[system]["parts"]
        return {pid: part["gender_limit"] for pid, part in parts.items()}

    def test_check_status_lists_pending(self) -> None:
        """验证检查状态文本按已用次数与待检列表生成进度及明细。"""
        sick = patient([A, C])
        catalog = tree(sick)
        sick.player_pending_checks = [
            {"cid": A, "system_id": 10, "part_id": 1001, "severity_level": 0}
        ]
        text = view.check_status(sick, catalog, (2, 2))
        config = game_config.config_medical_complication[A]
        system = catalog[10]["system_name"]
        part = catalog[10]["parts"][1001]["part_name"]
        self.assertEqual(
            text.splitlines(),
            [
                "患者愿意进行的检查次数：0/2（本次已选 1/2 项）",
                "待执行检查：",
                f"◆ 怀疑 {config.name}（{system} - {part} - 轻症），"
                f"进行检查：{config.exam_method}",
            ],
        )
        sick.player_used_checks = 2
        self.assertEqual(
            view.check_status(sick, catalog, (2, 2)).splitlines()[0],
            "患者愿意进行的检查次数：2/2",
        )

    def test_operation_buttons_follow_state(self) -> None:
        """验证操作按钮动作键与参数随二次确认、确诊与待检状态变化。"""
        sick = patient([A, C])

        def keys(awaiting: bool = False) -> list[str]:
            """返回当前状态下操作按钮列表的动作键顺序。"""
            return [b[2] for b in view.operation_buttons(sick, 2, awaiting)]

        self.assertEqual(keys(True), ["confirm", "cancel"])
        self.assertEqual(keys(), ["abort"])
        sick.player_confirmed_complications = [A]
        self.assertEqual(keys(), ["treat", "treat", "abort"])
        treat = view.operation_buttons(sick, 2, False)[:2]
        self.assertEqual([b[3] for b in treat], [(False,), (True,)])
        sick.player_confirmed_complications = []
        sick.player_pending_checks = [{"cid": A}]
        self.assertEqual(keys(), ["execute", "clear", "abort"])
        sick.player_used_checks = 2
        self.assertEqual(keys(), ["clear", "treat", "treat"])

    def test_overview_and_reports(self) -> None:
        """验证非理性病人的自述概览文本与检查报告行的样式及回退。"""
        config = game_config.config_medical_complication[A]
        vague = mc.MedicalPatientPersonality.IRRATIONAL
        sick = patient([A], personality_type=vague, race_id=-1, age=30)
        text = view.overview_text(sick)
        self.assertIn("年龄：30 岁 | 种族：未知种族", text)
        self.assertIn("病人自述：" + config.patient_statement_vague, text)
        results = [{"result": "positive", "cid": A}, {"result": "odd"}]
        rows = view.report_rows(cast(list[dict[str, object]], results))
        self.assertEqual([row[1] for row in rows], ["warning", "standard"])
        self.assertEqual(rows[0][2], f") 怀疑 {A}，检查结果：\n")
        self.assertEqual(rows[1][0].strip(), "odd")


class TreatmentTest(DiagnoseCase):
    """验证 medical_diagnose_treatment 的治疗摘要与缺口反馈。"""

    def test_unconfirmed_need_counts_half(self) -> None:
        """验证存在未确诊并发症时药品需求按 50% 折算并生成提示。"""
        sick = patient([A, C], need_resources={MED: 2.0})
        sick.player_confirmed_complications = [A]
        warehouse.set(MED, 1)
        catalog = tree(sick)
        summary, notice = cure.treatment_text(sick, catalog)
        medicine = game_config.config_resouce[MED].name
        self.assertIn(f"·(轻症){name(A)}", summary)
        self.assertIn(
            f"  · {medicine} × 1.50（缺口 0.50 单位，库存 1.00 单位）", summary
        )
        self.assertEqual(
            notice, "  * 未确诊 1 项并发症，相关药品需求按 50% 计入。\n"
        )

    def test_spent_checks_list_recheck_clues(self) -> None:
        """验证无确诊结果时按再检记录去重输出异常线索或空线索提示。"""
        sick = patient([A])
        catalog = tree(sick)
        summary = cure.treatment_text(sick, catalog)[0].splitlines()
        self.assertEqual(
            summary[:2],
            [
                "检查次数已达上限，以下为可能的异常线索：",
                "  暂无明确线索，请考虑切换提示或交由其他医生继续诊疗。",
            ],
        )
        sick.player_check_records = [
            {"result": "recheck", "system_id": 10, "part_id": 1001},
            {"result": "recheck", "system_id": 10, "part_id": 1001},
            {"result": "recheck", "system_id": 9, "part_id": 3} | HINT2,
            {"result": "negative", "system_id": 8, "part_id": 4},
        ]
        part = catalog[10]["parts"][1001]["part_name"]
        self.assertEqual(
            cure.treatment_text(sick, catalog)[0].splitlines()[1:4],
            [
                "  · 9/3 可能存在重症异常，建议改用其他检查。",
                f"  · {catalog[10]['system_name']}/{part} "
                "可能存在未知等级异常，建议改用其他检查。",
                "",
            ],
        )

    def test_treatment_message_lists_shortages(self) -> None:
        """验证诊疗结束反馈在缺药、库存足够与成功分支下的输出文案。"""
        sick = patient([A], need_resources={MED: 3.0})
        warehouse.set(MED, 1)
        outcome: dict[str, object] = {"diagnose_income": 7}
        outcome["medicine_income"] = 2
        medicine = game_config.config_resouce[MED].name
        self.assertEqual(
            cure.treatment_message(outcome, sick).splitlines(),
            [
                "已完成诊疗，诊断收益 7 龙门币，药费收益 2 龙门币。",
                "当前仍缺少以下药品：",
                f"· {medicine} 缺口 2.00 单位，当前库存 1.00 单位。",
            ],
        )
        warehouse.set(MED, 3)
        self.assertTrue(
            cure.treatment_message(outcome, sick).endswith("请补充后再试。")
        )
        outcome["medicine_success"] = True
        self.assertNotIn("\n", cure.treatment_message(outcome, sick))


class UiFreeRunTest(FastTestCase):
    """验证三项诊疗服务可在屏蔽界面与结算模块的独立子进程中运行。"""

    child: ChildRun
    """ 保存无界面隔离子进程的执行结果对象。 """
    error: str
    """ 保存无界面隔离子进程运行失败时的错误信息。 """

    @classmethod
    def setUpClass(cls) -> None:
        """启动拦截界面与结算导入的独立子进程并执行诊疗服务脚本。"""
        super().setUpClass()
        cls.error = ""
        try:
            cls.child = run_ui_free(UI_FREE_RUN, boot=True)
        except RuntimeError as error:
            cls.error = str(error)
            cls.child = ChildRun({}, [], [])

    def test_no_ui_or_settle_loaded(self) -> None:
        """验证子进程执行无报错且未加载或尝试导入受限模块。"""
        self.assertEqual(self.error, "")
        self.assertEqual((self.child.loaded, self.child.attempted), ([], []))

    def test_child_results(self) -> None:
        """验证子进程返回的能力等级、提示设置与执行结果数量符合预期。"""
        out = self.child.payload
        self.assertEqual((out["levels"], out["hint"]), ([7, 2], {"12": 0}))
        self.assertGreater(cast(int, out["values"]), 50)
