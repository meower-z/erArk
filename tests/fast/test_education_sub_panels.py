"""
教育系统子面板交互与状态写入测试
================================
本测试验证 Script.UI.Panel 下日程模板、个人课表与临时性技实操课三个子面板登记的按钮返回值与写入状态。
测试以 _answer 替换 flow_handle.askfor_all，断言各页面给出预设按钮并按预设序列响应交互。
用例覆盖模板时段写入、个人日程套用与单人覆盖隔离，以及实践教室临时性技实操课保存与删除。
"""

from unittest import mock

from Script.Core import flow_handle
from Script.Modules.domains import chara_life
from Script.System.Education_System import education_constant as E
from Script.System.Education_System import schedule_handle
from Script.System.Education_System import schedule_template_handle as handle
from Script.System.Education_System import sex_class_handle
from Script.UI.Panel import course_select_panel, schedule_template_panel
from Script.UI.Panel import sex_class_plan_panel
from tests import kernel_data
from tests.fast.base import FastTestCase

WIDTH = 120
""" 传给三个教育子面板的面板宽度。 """
STUDENT = 1
""" 测试用学生角色编号。 """
CLASSMATE = 2
""" 共用同一日程模板的对照学生角色编号。 """


class EducationSubPanelTest(FastTestCase):
    """日程模板、个人课表与临时性技实操课子面板的交互测试。"""

    def setUp(self) -> None:
        """
        创建博士与学生岗角色学生甲，初始化测试活动编号与空步骤列表。
        随后将 flow_handle.askfor_all 替换为 self._answer。
        """
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(STUDENT, "学生甲")
        kernel_data.put(chara_life.work_type.set, STUDENT, E.STUDENT_WORK_TYPE)
        self.activity = handle.get_schedule_activity_rows()[2][0]
        """ 选择活动页提供的可排娱乐活动编号。 """
        self.steps: list[str] = []
        """ 按顺序消耗的预设按钮返回值列表。 """
        self.enterContext(
            mock.patch.object(flow_handle, "askfor_all", self._answer)
        )

    def _answer(self, return_list: list[str], *args: object) -> str:
        """
        断言预设步骤非空后取出队首返回值，并断言该值位于 return_list 中再返回。
        Keyword arguments:
        return_list -- list[str]，面板本次给出的按钮返回值列表
        args -- tuple[object, ...]，其余位置参数，本方法不使用
        Return arguments:
        str -- 从 self.steps 队首取出的按钮返回值
        """
        self.assertTrue(
            self.steps, f"预设步骤已耗尽，界面再次询问：{return_list}"
        )
        step = self.steps.pop(0)
        self.assertIn(step, return_list)
        return step

    def test_template_slot_takes_chosen_activity(self) -> None:
        """登记日程模板页按钮并在编辑页为晚上时段选定活动，断言步骤耗尽、模板按钮存在且模板数据正确。"""
        template_id = kernel_data.written(handle.create_template, "周末")
        page = schedule_template_panel.Schedule_Template_Panel(WIDTH)
        return_list: list[str] = []
        page.draw_page(return_list)
        self.steps = ["SLOT_2", f"ACT_{self.activity}", "返回编辑"]
        with kernel_data.writing():
            page.handle_yrn(f"TEMPLATE_{template_id}")
        self.assertEqual(self.steps, [])
        self.assertIn(f"TEMPLATE_{template_id}", return_list)
        self.assertEqual(
            handle.get_template_data(template_id),
            {
                E.TEMPLATE_KEY_NAME: "周末",
                E.TEMPLATE_KEY_SLOT: {2: self.activity},
            },
        )

    def test_student_schedule_takes_template_and_override(self) -> None:
        """
        为学生乙套用新建模板后，进入学生甲日程编辑页套用同一模板并覆盖上午时段。
        断言步骤耗尽、返回列表含 EDIT_SCHEDULE、学生甲日程正确，且学生乙与共用模板均未受影响。
        """
        template_id = kernel_data.written(handle.create_template, "上课日")
        self.world.chara(CLASSMATE, "学生乙")
        kernel_data.written(handle.apply_template, CLASSMATE, template_id)
        page = course_select_panel.Course_Select_Panel(WIDTH)
        page.now_student = STUDENT
        return_list: list[str] = []
        page.draw_page(return_list)
        self.steps = [
            "CHANGE_TEMPLATE",
            f"PICK_{template_id}",
            "CHILD_SLOT_0",
            f"ACT_{self.activity}",
            "返回日程",
        ]
        with kernel_data.writing():
            page.handle_yrn("EDIT_SCHEDULE")
        self.assertEqual(self.steps, [])
        self.assertIn("EDIT_SCHEDULE", return_list)
        self.assertEqual(
            [handle.get_child_slot_activity(STUDENT, slot) for slot in (0, 1)],
            [self.activity, 0],
        )
        self.assertIn("上课日", handle.get_child_schedule_text(STUDENT))
        self.assertEqual(handle.get_child_slot_activity(CLASSMATE, 0), 0)
        self.assertEqual(
            handle.get_template_data(template_id),
            {E.TEMPLATE_KEY_NAME: "上课日", E.TEMPLATE_KEY_SLOT: {}},
        )

    def test_temp_class_saves_subject_then_deletes(self) -> None:
        """在实践教室打开临时性技实操课编辑页保存主修科目，再重新打开删除，断言保存字段、步骤耗尽与记录清空。"""
        rooms = schedule_handle.get_classroom_list(E.COURSE_TYPE_PRACTICE)
        classroom = rooms[0]
        subject = E.SEX_CLASS_ABILITY_LIST[1]
        page = sex_class_plan_panel.Sex_Class_Plan_Panel(WIDTH)
        self.steps = [f"SUB_{subject}", "OK"]
        with kernel_data.writing():
            page.edit(classroom, 2, 1)
        date_ordinal = sex_class_handle.get_date_ordinal_by_week_day(2, 1)
        saved = sex_class_handle.get_temp_class(date_ordinal, 1)
        self.assertIsNotNone(saved)
        self.assertEqual(
            (saved["classroom"], saved["ability_id"], saved["must_attend"]),
            (classroom, subject, []),
        )
        self.steps = ["DEL"]
        with kernel_data.writing():
            page.edit(classroom, 2, 1)
        self.assertEqual(self.steps, [])
        self.assertIsNone(sex_class_handle.get_temp_class(date_ordinal, 1))
