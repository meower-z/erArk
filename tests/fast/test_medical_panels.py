"""
医疗经营与玩家诊疗面板交互测试
==============================
本测试从 Script.UI.Panel 导入 medical_department_panel 与 medical_player_diagnose_panel。
测试用 bind 经 flow_handle.bind_cmd 注册按钮回调，并用 Clicks.answer 按预设应答执行已绑定命令。
DepartmentPanelTest 复用 MedicalCase，覆盖医疗部面板的收费设置、财务报表日志与医生管理页按钮流程。
DiagnosePanelTest 复用 DiagnoseCase，覆盖玩家诊疗流程的无病人返回、未检中止退出及检查后确认提前治疗。
"""

import sys
import types
import unittest
from unittest import mock

from Script.Config import game_config, normal_config
from Script.Core import constant, flow_handle
from Script.Modules.domains import medical
from Script.Modules.gameplay_resolution import medical_diagnose_service as rules
from Script.Modules.tk_ui import player_pick
from Script.System.Instruct_System import handle_instruct
from Script.System.Medical_System import medical_constant as mc
from Script.System.Medical_System import medical_service
from Script.UI.Moudle import draw, view
from Script.UI.Panel import medical_department_panel
from Script.UI.Panel import medical_player_diagnose_panel
from tests.fast.test_medical_department_service import CLINIC, MedicalCase
from tests.fast.test_medical_diagnose_service import A, C, DiagnoseCase
from tests.fast.test_medical_diagnose_service import name, patient

WIDTH = 100
""" 传给 Medical_Department_Panel 的面板宽度。 """
BASEMENT = "Script.UI.Panel.manage_basement_panel"
"""
医生管理子面板绘制时导入的基建面板模块名。该模块导入链触及 tests/fast 禁止加载的 Script.Core.image_catalog。
测试在 sys.modules 中为该模块名注入桩模块。
"""
PAD = "\u3000"
""" 用于对齐检查菜单按钮文本的全角空格。Clicks.answer 匹配选项时先从返回文本尾部去除该空格。 """


def bind(button: draw.CenterButton) -> None:
    """
    调用 flow_handle.bind_cmd，按 button.return_text 将 button.cmd_func 与 button.args 注册到 cmd_map。
    Keyword arguments:
    button -- draw.CenterButton，调用 draw 方法的按钮对象（含子类 draw.LeftButton）
    Return arguments:
    None -- 无返回值
    """
    flow_handle.bind_cmd(button.return_text, button.cmd_func, button.args)


class Clicks:
    """按预设应答驱动面板选项交互并记录选项列表的辅助对象。"""

    def __init__(self, case: unittest.TestCase) -> None:
        """
        绑定当前测试用例，并初始化预设应答队列与已见选项列表。
        Keyword arguments:
        case -- unittest.TestCase，用于执行断言的测试用例实例
        Return arguments:
        None -- 无返回值
        """
        self.case = case
        """ 用于执行断言的当前测试用例实例。 """
        self.answers: list[str] = []
        """ 按消费顺序排列的预设按钮返回值文本列表。 """
        self.seen: list[list[str]] = []
        """ 记录 answer 每次收到的按钮返回值列表副本。 """

    def answer(self, return_list: list[str], *args: object) -> str:
        """
        断言存在预设应答并取出队首项，再断言 return_list 去尾部 PAD 后恰有一项匹配并记录其副本。
        从 flow_handle.cmd_map 取出匹配项命令（未绑定时取 null_func），清空 cmd_map 后执行并返回该原始选项。
        Keyword arguments:
        return_list -- list[str]，面板本次给出的按钮返回值列表
        args -- tuple[object, ...]，其余位置参数，本方法不使用
        Return arguments:
        str -- return_list 中匹配预设应答的原始选项文本
        """
        self.case.assertTrue(self.answers, f"缺少针对 {return_list} 的预设应答")
        wanted = self.answers.pop(0)
        matches = [o for o in return_list if o.rstrip(PAD) == wanted]
        self.case.assertEqual(len(matches), 1, wanted)
        self.seen.append(list(return_list))
        command = flow_handle.cmd_map.get(matches[0], flow_handle.null_func)
        flow_handle.cmd_map.clear()
        command()
        return matches[0]


def install(case: unittest.TestCase) -> Clicks:
    """
    创建 Clicks 并为用例替换两类按钮的 draw 方法与 flow_handle.askfor_all。
    同时将 view.now_panel_id 临时设为 constant.Panel.CURE_PATIENT，便于断言面板返回时切回场景。
    Keyword arguments:
    case -- unittest.TestCase，注册补丁上下文的测试用例实例
    Return arguments:
    Clicks -- 已接入按钮绘制与选项应答补丁的辅助对象
    """
    clicks = Clicks(case)
    for button in (draw.CenterButton, draw.LeftButton):
        case.enterContext(mock.patch.object(button, "draw", bind))
    case.enterContext(
        mock.patch.object(flow_handle, "askfor_all", clicks.answer)
    )
    case.enterContext(
        mock.patch.object(view, "now_panel_id", constant.Panel.CURE_PATIENT)
    )
    return clicks


class DepartmentPanelTest(MedicalCase):
    """医疗部面板收费设置、财务报表与医生管理子页的按钮交互测试。"""

    def setUp(self) -> None:
        """
        调用父类 setUp 并通过 install 挂载按钮与应答补丁。
        断言 sys.modules 未加载 BASEMENT 后注入含 change_npc_work_out 桩函数的模块，并登记清理。
        """
        super().setUp()
        self.clicks = install(self)
        """ 驱动医疗部面板按钮交互的 Clicks 辅助对象。 """
        self.adjust = mock.Mock()
        """ 替换基建面板 change_npc_work_out 回调的模拟函数。 """
        stub = types.ModuleType(BASEMENT)
        vars(stub).update(change_npc_work_out=self.adjust)
        self.assertNotIn(BASEMENT, sys.modules)
        sys.modules[BASEMENT] = stub
        self.addCleanup(sys.modules.pop, BASEMENT)

    def run_panel(self, *answers: str) -> list[list[str]]:
        """
        写入预设应答并绘制 Medical_Department_Panel，断言应答耗尽且面板编号回到 IN_SCENE。
        Keyword arguments:
        answers -- tuple[str, ...]，按顺序执行的预设按钮返回值文本
        Return arguments:
        list[list[str]] -- self.clicks.seen，当前用例累计记录的选项列表
        """
        self.clicks.answers = list(answers)
        medical_department_panel.Medical_Department_Panel(WIDTH).draw()
        self.assertEqual(self.clicks.answers, [])
        self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)
        return self.clicks.seen

    def test_price_tab_buttons_set_tomorrow_ratio(self) -> None:
        """
        进入「收费设置」页依次点击「+5%」「-10%」与「返回」，再重进该页点击「重置收费」与「返回」。
        断言首页与收费页按钮列表、当前页签「收费设置」不作为按钮，且次日收费系数先后为 0.95 与 1.0。
        """
        seen = self.run_panel("收费设置", "+5%", "-10%", "返回")
        self.assertEqual(
            seen[0],
            [
                "医生管理",
                "收费设置",
                "医疗明细",
                "手术管理",
                "财务报表",
                "返回",
            ],
        )
        steps = ["-10%", "-5%", "-1%", "+1%", "+5%", "+10%", "重置收费", "返回"]
        self.assertEqual(seen[1][-8:], steps)
        self.assertNotIn("收费设置", seen[1])
        self.assertAlmostEqual(
            medical_service.get_new_medical_price_ratio(), 0.95
        )
        self.run_panel("收费设置", "重置收费", "返回")
        self.assertEqual(medical_service.get_new_medical_price_ratio(), 1.0)

    def test_finance_log_button_shows_reports(self) -> None:
        """进入「财务报表」页点击「查看最近经营日志」并返回，断言该页末尾按钮与记录的默认空日志提示。"""
        seen = self.run_panel("财务报表", "查看最近经营日志", "返回")
        self.assertEqual(seen[1][-2:], ["查看最近经营日志", "返回"])
        self.assertEqual(self.world.wait_texts, ["\n暂无医疗经营日志记录。\n"])

    def test_doctor_tab_buttons(self) -> None:
        """
        配置两名门诊医生后进入「医生管理」页，依次触发「医生增减」「优先重症」并将甲医生分配至第二个门诊分科。
        断言增减回调参数、排序与选人按钮列表变化，且接诊优先级为 FOCUS_CRITICAL、该分科医生列表为 [1]。
        """
        self.edit(clinic_doctor_ids=[1, 2])
        category = medical_service.get_specialization_categories()[1]
        row = CLINIC + "分配到" + category["name"]
        seen = self.run_panel(
            "医生管理", "医生增减", "优先重症", row, "甲医生", "返回"
        )
        self.adjust.assert_called_once_with(
            WIDTH,
            [
                mc.MedicalDoctorProfession.CLINICIAN,
                mc.MedicalDoctorProfession.HOSPITALIST,
            ],
        )
        self.assertEqual(seen[1][5:8], ["医生增减", "优先重症", "优先轻症"])
        self.assertIn("正常排序", seen[3])
        self.assertNotIn("优先重症", seen[3])
        self.assertEqual(seen[4][-3:], ["甲医生", "乙医生", "返回"])
        with medical.editing() as state:
            mode = medical_service.get_patient_priority_mode()
            buckets = state.doctor_specializations[CLINIC]
        self.assertEqual(mode, mc.MedicalPatientPriority.FOCUS_CRITICAL)
        self.assertEqual(buckets[category["key"]], [1])


class DiagnosePanelTest(DiagnoseCase):
    """玩家亲自诊疗面板流程的按钮交互测试。"""

    def setUp(self) -> None:
        """
        调用父类 setUp 并挂载按钮与应答补丁，同时打桩指令通用结算函数。
        将博士医疗与话术等级均设为 2，并将诊疗提示设置项初始化为 0。
        """
        super().setUp()
        self.clicks = install(self)
        """ 驱动玩家诊疗面板按钮交互的 Clicks 辅助对象。 """
        self.settle = mock.Mock()
        """ 替换 handle_instruct.chara_handle_instruct_common_settle 的模拟函数。 """
        self.enterContext(
            mock.patch.object(
                handle_instruct,
                "chara_handle_instruct_common_settle",
                self.settle,
            )
        )
        self.levels(2, talk=2)
        normal_config.system_setting.base_setting[rules.HINT_SETTING_ID] = 0

    def admit(self, *complications: int) -> None:
        """
        按给定并发症编号构造一名处于 REFRESHED 状态的待诊病人，并将其设为今日唯一病人。
        Keyword arguments:
        complications -- tuple[int, ...]，待诊病人携带的并发症配置编号序列
        Return arguments:
        None -- 无返回值
        """
        sick = patient(
            list(complications), state=mc.MedicalPatientState.REFRESHED
        )
        medical.state().today = {sick.patient_id: sick}

    def test_no_patient_returns_to_scene(self) -> None:
        """无待诊病人时，诊疗流程不弹出选项即返回 True，将面板切回 IN_SCENE 且不触发结算。"""
        medical.state().today = {}
        self.assertTrue(
            medical_player_diagnose_panel.start_player_diagnose_flow()
        )
        self.assertEqual(self.clicks.seen, [])
        self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)
        self.settle.assert_not_called()

    def test_abort_before_checks_backs_out(self) -> None:
        """
        在未执行检查前选择「提前结束诊疗并返回」，断言流程抛出 player_pick.Back 且仅给出一次三按钮列表。
        断言病人退回 REFRESHED 并清除会话与接诊编号，面板切回 IN_SCENE 且不触发结算。
        """
        self.admit(A)
        self.clicks.answers = ["提前结束诊疗并返回"]
        with self.assertRaises(player_pick.Back):
            medical_player_diagnose_panel.start_player_diagnose_flow()
        self.assertEqual(
            self.clicks.seen,
            [["切换提示", "切换检查菜单", "提前结束诊疗并返回"]],
        )
        sick = medical.state().today[1]
        self.assertEqual(sick.state, mc.MedicalPatientState.REFRESHED)
        self.assertFalse(sick.player_session_active)
        self.assertEqual(medical.state().player_patient_id, 0)
        self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)
        self.settle.assert_not_called()

    def test_check_then_confirm_early_treatment(self) -> None:
        """
        对含并发症 A 与 C 的病人依次切换提示、按 A 的系统与部位勾选并执行检查，经一次返回后再确认提前治疗。
        断言提示档位、各步按钮列表变化、确诊与已检记录、面板回到 IN_SCENE 及以 CURE_PATIENT 结算一次。
        """
        self.admit(A, C)
        info = game_config.config_medical_complication[A]
        body = game_config.config_medical_body_system_by_system[info.system_id]
        part = body[info.part_id]
        self.clicks.answers = [
            "切换提示",
            "切换检查菜单",
            part.system_name,
            part.part_name,
            name(A),
            "执行所选检查",
            "开药并结束诊疗",
            "[返回继续检查]",
            "开药并结束诊疗",
            "[确认就这样治疗]",
        ]
        self.assertTrue(
            medical_player_diagnose_panel.start_player_diagnose_flow()
        )
        self.assertEqual(self.clicks.answers, [])
        seen = self.clicks.seen
        self.assertEqual(rules.hint_context(self.player)[0], 1)
        self.assertIn("执行所选检查", seen[5])
        self.assertNotIn("提前结束诊疗并返回", seen[6])
        self.assertEqual(seen[7][-2:], ["[确认就这样治疗]", "[返回继续检查]"])
        self.assertEqual(seen[8][-2:], ["开药并结束诊疗", "开药并接诊下一位"])
        sick = medical.state().today[1]
        self.assertEqual(sick.player_confirmed_complications, [A])
        self.assertEqual(sick.player_used_checks, 1)
        self.assertEqual(medical.state().examined_patient_ids, [1])
        self.assertEqual(medical.state().player_patient_id, 0)
        self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)
        self.settle.assert_called_once_with(
            constant.Behavior.CURE_PATIENT, duration=10, force_taget_wait=False
        )
