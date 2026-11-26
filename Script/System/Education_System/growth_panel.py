"""
养成总览面板
负责绘制单个养成中孩子的各分区信息，并响应选人与成绩单翻页输入。
各分区的展示文本与判定规则由 growth_overview_service 提供。
"""

from types import FunctionType

from Script.Core import get_text
from Script.Modules.gameplay_resolution import growth_overview_service
from Script.Modules.tk_ui import student_select
from Script.System.Education_System import education_constant, growth_handle
from Script.UI.Moudle import draw

_: FunctionType = get_text._
""" 翻译函数 """
line_feed = draw.NormalDraw()
line_feed.text = "\n"
line_feed.width = 1


class Growth_Panel:
    """养成总览页面类，负责绘制所选孩子的成长状态并处理页面交互。"""

    def __init__(self, width: int) -> None:
        """初始化页面宽度、当前学生状态与成绩单翻页索引。"""
        self.width: int = width
        self.now_student: int = -1
        """ 当前展示的孩子角色编号，未选择时为 -1。 """
        self.student_list: list[int] = []
        """ 当前在养成中的候选孩子角色编号列表。 """
        self.report_card_index: int = -1
        """ 当前查看的成绩单历史索引，-1 表示回落至最新一份。 """

    def draw_page(self, return_list: list[str]) -> None:
        """刷新候选名单并按顺序绘制选人栏与养成总览各分区。"""
        self.student_list = growth_handle.get_student_candidate_list()
        if not self.student_list:
            self._draw_text(_("\n  目前还没有在养成中的孩子\n"))
            return
        if self.now_student not in self.student_list:
            self.now_student = -1
            self.report_card_index = -1
        if not student_select.draw_select_student_line(
            self.width, self.now_student, return_list
        ):
            return

        self._draw_stage(self.now_student)
        self._draw_subject(self.now_student)
        self._draw_attendance(self.now_student)
        self._draw_report_card(self.now_student, return_list)
        self._draw_personality(self.now_student)
        self._draw_event_history(self.now_student)
        self._draw_flag(self.now_student)

        line_feed.draw()
        draw.LineDraw("-", self.width).draw()

    def handle_yrn(self, yrn: str) -> None:
        """处理成绩单上下翻页与「选择学生」按钮返回值。"""
        if yrn == education_constant.REPORT_CARD_PREV:
            self.report_card_index -= 1
            return
        if yrn == education_constant.REPORT_CARD_NEXT:
            self.report_card_index += 1
            return
        if not self.student_list:
            return
        if yrn == education_constant.SELECT_STUDENT_RETURN:
            student_id = student_select.select_student(
                self.student_list,
                _("选择孩子"),
                _("请选择要查看养成总览的孩子：\n"),
                self.now_student,
            )
            if student_id != self.now_student:
                self.report_card_index = -1
            self.now_student = student_id

    def _draw_text(self, text: str, style: str = "") -> None:
        """按页面宽度创建并绘制单段普通文本，传入样式时一并应用。"""
        info_draw = draw.NormalDraw()
        info_draw.width = self.width
        info_draw.text = text
        if style:
            info_draw.style = style
        info_draw.draw()

    def _draw_cells(self, cells: list[growth_overview_service.Cell]) -> None:
        """按四列网格绘制左对齐文本单元并在每满四格及末尾换行。"""
        for index, (text, style) in enumerate(cells):
            now_draw = draw.LeftDraw()
            now_draw.width = int(self.width / 4)
            now_draw.text = text
            if style:
                now_draw.style = style
            now_draw.draw()
            if index % 4 == 3:
                line_feed.draw()
        line_feed.draw()

    def _draw_stage(self, character_id: int) -> None:
        """绘制孩子的母亲、阶段进度行及非空的胎教底子说明行。"""
        self._draw_text(growth_overview_service.stage_text(character_id))
        prenatal_text = growth_overview_service.prenatal_text(character_id)
        if prenatal_text:
            self._draw_text(prenatal_text, growth_overview_service.GRAY)

    def _draw_subject(self, character_id: int) -> None:
        """绘制「科目水平」标题行与各科目等级网格。"""
        draw.LittleTitleLineDraw(_("科目水平"), self.width).draw()
        self._draw_cells(growth_overview_service.subject_cells(character_id))

    def _draw_attendance(self, character_id: int) -> None:
        """存在养成数据时绘制「出勤」标题行与累计、本学期出勤文本。"""
        texts = growth_overview_service.attendance_texts(character_id)
        if texts is None:
            return
        draw.LittleTitleLineDraw(_("出勤"), self.width).draw()
        for text in texts:
            self._draw_text(text)

    def _draw_report_card(
        self, character_id: int, return_list: list[str]
    ) -> None:
        """绘制「学期成绩单」分区内容，多于一份时附加翻页按钮与页码。"""
        page = growth_overview_service.report_card_page(
            character_id, self.report_card_index
        )
        if page is None:
            return
        self.report_card_index = page.index
        draw.LittleTitleLineDraw(_("学期成绩单"), self.width).draw()
        self._draw_text(page.summary)
        if page.reason:
            self._draw_text(page.reason, growth_overview_service.GRAY)
        self._draw_text(page.progress, page.progress_style)
        if page.count <= 1:
            return
        button_width = int(self.width / 3)
        self._draw_page_button(
            page.index > 0,
            _("[← 上一学期]"),
            _("　← 上一学期"),
            education_constant.REPORT_CARD_PREV,
            button_width,
            return_list,
        )
        index_draw = draw.CenterDraw()
        index_draw.width = button_width
        index_draw.text = growth_overview_service.report_card_index_text(page)
        index_draw.draw()
        self._draw_page_button(
            page.index < page.count - 1,
            _("[下一学期 →]"),
            _("　下一学期 →"),
            education_constant.REPORT_CARD_NEXT,
            button_width,
            return_list,
        )
        line_feed.draw()

    def _draw_page_button(
        self,
        enabled: bool,
        button_text: str,
        blank_text: str,
        return_text: str,
        width: int,
        return_list: list[str],
    ) -> None:
        """可用时绘制翻页按钮并登记返回值，不可用时绘制灰色占位文本。"""
        if enabled:
            button_draw = draw.CenterButton(button_text, return_text, width)
            button_draw.draw()
            return_list.append(button_draw.return_text)
            return
        blank_draw = draw.CenterDraw()
        blank_draw.width = width
        blank_draw.style = growth_overview_service.GRAY
        blank_draw.text = blank_text
        blank_draw.draw()

    def _draw_personality(self, character_id: int) -> None:
        """存在养成数据时绘制「性格倾向」标题行与各倾向单元。"""
        cells = growth_overview_service.personality_cells(character_id)
        if cells is None:
            return
        draw.LittleTitleLineDraw(_("性格倾向"), self.width).draw()
        for text, style in cells:
            now_draw = draw.LeftDraw()
            now_draw.width = int(self.width / 4)
            now_draw.text = text
            if style:
                now_draw.style = style
            now_draw.draw()
        line_feed.draw()

    def _draw_event_history(self, character_id: int) -> None:
        """存在履历记录时绘制「养成履历」标题行、省略提示与近期条目。"""
        history = growth_overview_service.event_history(character_id)
        if history is None:
            return
        omit_text, rows = history
        draw.LittleTitleLineDraw(_("养成履历"), self.width).draw()
        if omit_text:
            self._draw_text(omit_text, growth_overview_service.GRAY)
        for text in rows:
            self._draw_text(text)
        line_feed.draw()

    def _draw_flag(self, character_id: int) -> None:
        """存在待处理条目时绘制「待处理」标题行与各项提示文本。"""
        text_list = growth_overview_service.pending_texts(character_id)
        if not text_list:
            return
        draw.LittleTitleLineDraw(_("待处理"), self.width).draw()
        for text in text_list:
            self._draw_text(text)
