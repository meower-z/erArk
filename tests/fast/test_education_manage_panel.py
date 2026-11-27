"""
教育管理与全局课表面板交互测试
==============================
本测试从 Script.UI.Panel 导入 class_schedule_panel 与 growth_panel，验证两份面板的按钮交互。
测试复用 GrowthCase，以 _answer 替换 flow_handle.askfor_all，按预设返回值序列响应询问并记录按钮列表。
用例覆盖容器在「全局课表」与「养成总览」间切换后返回场景，以及课表格子写入后清空本教室。
"""

from unittest import mock

from Script.Core import constant, flow_handle
from Script.Modules.domains import chara_life
from Script.System.Education_System import education_constant as ec
from Script.System.Education_System import schedule_handle
from Script.UI.Moudle import view
from Script.UI.Panel import class_schedule_panel, growth_panel
from tests.fast.test_growth_overview_service import GrowthCase

WIDTH = 120
""" 传给教育管理容器与全局课表面板的面板宽度。 """
TEACHER = 20
""" 测试用授课教师角色编号。 """


class EducationManagePanelTest(GrowthCase):
    """教育管理容器面板与全局课表子面板的按钮交互测试。"""

    def setUp(self) -> None:
        """
        调用父类 setUp，初始化预设步骤队列与已见按钮列表。
        将 flow_handle.askfor_all 替换为 self._answer，并将 view.now_panel_id 临时设为 constant.Panel.EDUCATION_MANAGE。
        """
        super().setUp()
        self.steps: list[str] = []
        """ 按消费顺序排列的预设按钮返回值列表。 """
        self.seen: list[list[str]] = []
        """ 记录 _answer 每次收到的按钮返回值列表副本。 """
        self.enterContext(
            mock.patch.object(flow_handle, "askfor_all", self._answer)
        )
        self.enterContext(
            mock.patch.object(
                view, "now_panel_id", constant.Panel.EDUCATION_MANAGE
            )
        )

    def _answer(self, return_list: list[str], *args: object) -> str:
        """
        断言 self.steps 非空并取出队首返回值，断言该值位于 return_list 中。
        将 return_list 的副本追加到 self.seen，并返回该预设值。
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
        self.seen.append(list(return_list))
        return step

    def test_tabs_open_growth_overview_then_return(self) -> None:
        """
        驱动 Education_Manage_Panel 依次切换至「养成总览」、切回「全局课表」并返回。
        断言「养成总览」挂载 Growth_Panel 且步骤耗尽。同时断言当前页签、各次按钮列表及面板编号 IN_SCENE 均正确。
        """
        page = class_schedule_panel.Education_Manage_Panel(WIDTH)
        self.assertIsInstance(
            page.panel_map["养成总览"], growth_panel.Growth_Panel
        )
        self.steps = ["\n养成总览", "\n全局课表", "返回"]
        page.draw()
        self.assertEqual(self.steps, [])
        self.assertEqual(page.now_panel, "全局课表")
        self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)
        first, growth_page, last = self.seen
        self.assertIn("\n养成总览", first)
        self.assertNotIn("\n全局课表", first)
        self.assertIn("\nCELL_0_0", first)
        self.assertIn(ec.SELECT_STUDENT_RETURN, growth_page)
        self.assertNotIn("\nCELL_0_0", growth_page)
        self.assertIn("\nCELL_0_0", last)

    def test_cell_takes_subject_and_teacher_then_room_clears(self) -> None:
        """
        配置教师岗角色后绘制 Class_Schedule_Panel，点选周二第 3 节并依次选定首门科目与该教师。
        断言预设步骤耗尽且该格写入所选科目与教师。随后执行「清空本教室」，断言该格变为 None。
        """
        self.world.chara(TEACHER, "教师")
        chara_life.work_type.set(TEACHER, ec.TEACHER_WORK_TYPE)
        page = class_schedule_panel.Class_Schedule_Panel(WIDTH)
        return_list: list[str] = []
        page.draw_page(return_list)
        room = page.now_room
        ability_id = ec.SUBJECT_ABILITY_LIST[0]
        self.steps = ["0", str(TEACHER)]
        page.handle_yrn("\nCELL_1_2")
        self.assertEqual(self.steps, [])
        self.assertEqual(
            schedule_handle.get_class_cell(room, 1, 2), [ability_id, TEACHER]
        )
        page.handle_yrn("清空本教室")
        self.assertIsNone(schedule_handle.get_class_cell(room, 1, 2))
