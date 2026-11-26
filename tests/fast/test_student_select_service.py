"""
选择学生服务测试
================
在拦截受限模块的无界面子进程中验证选择学生服务的校验、文本、候选行与选人状态规则。
通过打桩通用选人面板与输入接口，验证选人界面循环与选人行返回值行为。
确认服务运行期间未加载也未尝试导入受限模块。
"""

from typing import Any
from unittest import mock

from Script.Core import flow_handle
from Script.Modules.tk_ui import student_select
from Script.System.Education_System import education_constant as ec
from Script.UI.Panel import common_select_NPC
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import ChildRun, run_ui_free

STUDENTS = ((201, "甲"), (202, "乙"), (205, "甲"))
""" 测试用候选角色编号与姓名表，含两位同名角色甲与一位角色乙。 """
LISTED = [201, 999, 202, 205]
""" 测试用候选编号列表，包含一个不存在的角色编号 999。 """
UI_FREE_RUN = """
from Script.Kernel import core
from Script.Modules.domains import identity
from Script.Modules.gameplay_resolution import student_select_service as svc
from Script.Modules.gameplay_resolution import working
out = payload


def on_select(character_id):
    del character_id


with working.based_on(core.state()):
    for cid, name in ((201, "甲"), (202, "乙"), (205, "甲")):
        identity.put(identity.Identity(cid, name=name, sex=1))
    out["has"] = [svc.has_student(cid) for cid in (-1, 201, 999)]
    out["current"] = svc.current_student_text(202)
    out["button"] = svc.select_button_text()
    out["hint"] = svc.select_hint_text()
    rows, names = svc.candidate_rows([201, 999, 202, 205], on_select, 202)
    out["rows"] = [[row[0], row[1] is on_select, row[2]] for row in rows]
    out["names"] = names
    out["typed"] = svc.StudentPick(202).result("甲", names)
    out["unknown"] = svc.StudentPick(202).result("返回", names)
    pick = svc.StudentPick(202)
    pick.pick(205)
    out["clicked"] = [pick.result("甲", names), pick.picked, pick.student_id]
"""
""" 在无界面子进程中构造测试角色并调用选择学生服务各公开入口的脚本。 """


class StudentSelectServiceTest(FastTestCase):
    """选择学生服务的规则与无界面导入隔离测试。"""

    child: ChildRun
    """ 无界面子进程执行脚本后的运行结果对象。 """
    out: dict[str, Any]
    """ 无界面子进程写入的测试输出字典。 """

    @classmethod
    def setUpClass(cls) -> None:
        """启动无界面子进程执行测试脚本并保存运行结果与输出字典。"""
        cls.child = run_ui_free(UI_FREE_RUN, boot=True)
        cls.out = cls.child.payload

    def test_ui_free(self) -> None:
        """验证无界面子进程运行期间未加载也未尝试导入受限模块。"""
        self.assertEqual(self.child.attempted, [])
        self.assertEqual(self.child.loaded, [])

    def test_has_student_needs_existing_id(self) -> None:
        """验证 has_student 对 -1 与不存在编号返回 False，对已存在编号返回 True。"""
        self.assertEqual(self.out["has"], [False, True, False])

    def test_line_texts(self) -> None:
        """验证当前学生文本格式以及未选人提示中包含「选择学生」按钮文本。"""
        self.assertEqual(self.out["current"], "  当前学生：乙")
        self.assertIn(self.out["button"], self.out["hint"])

    def test_rows_skip_missing_and_mark_current(self) -> None:
        """验证候选行跳过不存在角色 999，各行绑定传入回调并标记当前学生 202。"""
        expected = [[cid, True, [202]] for cid in (201, 202, 205)]
        self.assertEqual(self.out["rows"], expected)

    def test_first_listed_name_wins(self) -> None:
        """验证同名角色映射到名单中首个编号，未点击时输入甲返回 201。"""
        self.assertEqual(self.out["names"], {"甲": 201, "乙": 202})
        self.assertEqual(self.out["typed"], 201)

    def test_unknown_answer_keeps_current(self) -> None:
        """验证未点击且收到「返回」时维持当前学生编号 202。"""
        self.assertEqual(self.out["unknown"], 202)

    def test_click_beats_name_lookup(self) -> None:
        """验证回调选中同名角色 205 后，返回结果优先于按姓名甲的反查。"""
        self.assertEqual(self.out["clicked"], [205, True, 205])


class StudentSelectPanelTest(FastTestCase):
    """选人界面入口在打桩通用选人面板与输入后的交互行为测试。"""

    def setUp(self) -> None:
        """创建测试角色与桩状态，并替换通用选人面板与输入读取函数。"""
        super().setUp()
        self.world.chara(0, "博士")
        for cid, name in STUDENTS:
            self.world.chara(cid, name)
        self.answers: list[str] = []
        """ 供输入桩按顺序弹出的待返回文本队列。 """
        self.click: int | None = None
        """ 面板桩模拟点击的角色编号，为 None 时不触发行回调。 """
        self.shown: list[list[list]] = []
        """ 每次调用面板桩时记录的候选行编号与高亮列表快照。 """
        self.enterContext(
            mock.patch.object(
                common_select_NPC,
                "common_select_npc_button_list_func",
                side_effect=self.panel,
            )
        )
        self.enterContext(
            mock.patch.object(
                flow_handle, "askfor_all", side_effect=self.askfor
            )
        )

    def panel(
        self, page: Any, title: str, info: str, state: dict
    ) -> tuple[list[str], list[str], dict]:
        """
        记录本次渲染的候选行，按 click 触发对应行回调并返回固定选项列表。
        Keyword arguments:
        page -- Any，携带当前 text_list 候选行数据的分页对象
        title -- str，选人面板标题文本
        info -- str，选人面板说明文本
        state -- dict，选人面板的筛选与分页状态字典
        Return arguments:
        tuple[list[str], list[str], dict] -- 固定返回选项列表、翻页列表与传入的状态字典
        """
        self.shown.append([[row[0], row[2]] for row in page.text_list])
        for row in page.text_list:
            if row[0] == self.click:
                row[1](row[0])
        return ["甲", "乙", "返回", "翻页"], ["翻页"], state

    def askfor(self, return_list: list[str]) -> str:
        """
        从预设答案队列头部弹出一条输入文本作为界面返回值。
        Keyword arguments:
        return_list -- list[str]，本次等待输入允许的返回值列表
        Return arguments:
        str -- 预设队列中的下一条输入文本
        """
        return self.answers.pop(0)

    def test_click_returns_clicked_student(self) -> None:
        """验证点击同名角色 205 并返回甲时，select_student 返回 205。"""
        self.click = 205
        self.answers = ["甲"]
        self.assertEqual(
            student_select.select_student(LISTED, "t", "", 202), 205
        )

    def test_answer_name_resolves_first_listed(self) -> None:
        """验证未触发点击回调而直接返回甲时，按姓名反查返回首个同名编号 201。"""
        self.answers = ["甲"]
        self.assertEqual(
            student_select.select_student(LISTED, "t", "", 202), 201
        )

    def test_page_turn_redraws_then_back_keeps_current(self) -> None:
        """验证先返回「翻页」会重绘相同候选行，再返回「返回」维持当前学生 202。"""
        self.answers = ["翻页", "返回"]
        self.assertEqual(
            student_select.select_student(LISTED, "t", "", 202), 202
        )
        rows = [[201, [202]], [202, [202]], [205, [202]]]
        self.assertEqual(self.shown, [rows, rows])

    def test_select_line_reports_selection(self) -> None:
        """验证选人行按当前学生是否有效返回布尔值，并追加「选择学生」按钮返回值。"""
        for now_student, expected in ((-1, False), (999, False), (201, True)):
            return_list: list[str] = []
            drawn = student_select.draw_select_student_line(
                120, now_student, return_list
            )
            self.assertEqual(drawn, expected)
            self.assertEqual(return_list, [ec.SELECT_STUDENT_RETURN])
