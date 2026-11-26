"""
教育管理系统页签容器与全局课表面板。
负责绘制课表界面与分发输入，规则与文本由 class_schedule_service 提供。
"""

from types import FunctionType
from typing import Protocol

from Script.Core import constant, flow_handle, get_text
from Script.Config import normal_config
from Script.Design import game_time, basement
from Script.Modules.gameplay_resolution import class_schedule_service as svc
from Script.Modules.gameplay_resolution.class_schedule_service import (
    get_teacher_absent_mark as get_teacher_absent_mark,
)
from Script.System.Education_System import growth_panel
from Script.System.Education_System import education_constant, schedule_handle
from Script.UI.Panel import course_select_panel, schedule_template_panel
from Script.UI.Panel.sex_class_plan_panel import (
    Sex_Class_Plan_Panel,
    add_button,
    line_feed,
    text_line,
)
from Script.UI.Moudle import draw, view

_: FunctionType = get_text._
window_width: int = normal_config.config_normal.text_width
""" 全局配置的界面文本宽度。 """


class SubPanelProtocol(Protocol):
    """教育管理系统四个页签子面板共同遵守的绘制与输入协议。"""

    def draw_page(self, return_list: list[str]) -> None:
        """绘制当前页签内容并将按钮返回值追加到共享列表。"""
        ...

    def handle_yrn(self, yrn: str) -> None:
        """处理当前页签对应的玩家输入返回值。"""
        ...


class Education_Manage_Panel:
    """教育管理系统四页签主容器面板。"""

    def __init__(self, width: int) -> None:
        """初始化四个页签名称及对应的子面板实例映射。"""
        self.width: int = width
        self.now_panel: str = _("全局课表")
        self.panel_list: list[str] = [
            _("全局课表"),
            _("个人课表"),
            _("日程模板"),
            _("养成总览"),
        ]
        """ 顶部页签栏的四个页签显示名称列表。 """
        self.panel_map: dict[str, SubPanelProtocol] = {
            _("全局课表"): Class_Schedule_Panel(width),
            _("个人课表"): course_select_panel.Course_Select_Panel(width),
            _("日程模板"): schedule_template_panel.Schedule_Template_Panel(
                width
            ),
            _("养成总览"): growth_panel.Growth_Panel(width),
        }
        """ 页签名称到各子面板实例的映射表，各实例在容器生命周期内复用。 """

    def draw(self) -> None:
        """循环绘制教育管理系统容器、当前子页签与返回按钮并派发输入。"""
        title_draw = draw.TitleLineDraw(_("教育管理系统"), self.width)

        while 1:
            basement.get_base_updata()
            return_list: list[str] = []
            tab_return_map: dict[str, str] = {}
            title_draw.draw()
            self._draw_semester_head()
            for now_panel in self.panel_list:
                panel_width = int(self.width / len(self.panel_list))
                if now_panel == self.now_panel:
                    now_draw = draw.CenterDraw()
                    now_draw.text = f"[{now_panel}]"
                    now_draw.style = "onbutton"
                    now_draw.width = panel_width
                    now_draw.draw()
                else:
                    button = add_button(
                        return_list,
                        draw.CenterButton(
                            f"[{now_panel}]", f"\n{now_panel}", panel_width
                        ),
                    )
                    tab_return_map[button.return_text] = now_panel
            line_feed.draw()
            draw.LineDraw("+", self.width).draw()

            now_sub_panel = self.panel_map[self.now_panel]
            now_sub_panel.draw_page(return_list)

            line_feed.draw()
            back_draw = add_button(
                return_list,
                draw.CenterButton(_("[返回]"), _("返回"), window_width),
            )
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                view.now_panel_id = constant.Panel.IN_SCENE
                break
            if yrn in tab_return_map:
                self.change_panel(tab_return_map[yrn])
                continue
            now_sub_panel.handle_yrn(yrn)

    def _draw_semester_head(self) -> None:
        """绘制当前学期头部信息，学期过半时补充剩余生效天数提示。"""
        from Script.System.Education_System import semester_handle

        text_line(f"  {semester_handle.get_semester_head_text()}", self.width)
        if semester_handle.judge_semester_half_passed():
            text_line(
                _("　本学期已过半，现在改课表只影响剩下的 {0} 天").format(
                    semester_handle.get_semester_left_day()
                ),
                self.width,
                "gold_enrod",
            )
        line_feed.draw()

    def change_panel(self, now_panel: str) -> None:
        """切换容器当前激活的页签名称。"""
        self.now_panel = now_panel


class Class_Schedule_Panel:
    """按单间教室分页展示并编辑全局课表的子面板。"""

    def __init__(self, width: int) -> None:
        """初始化全局课表子面板宽度与教室、格子派发状态。"""
        self.width: int = width
        self.now_room: str = ""
        """ 当前选中的教室名称。 """
        self.room_list: list[str] = []
        """ 当前已开放的教室名称列表。 """
        self.cell_return: dict[str, tuple] = {}
        """ 周表按钮返回值到 (星期, 节次) 的派发映射。 """

    def draw_page(self, return_list: list[str]) -> None:
        """刷新已开放教室列表并绘制教室页签、周表及底部操作按钮。"""
        self.room_list = schedule_handle.get_classroom_list()
        self.cell_return = {}
        if not self.room_list:
            text_line(_("\n  尚未开放任何教室\n"), self.width)
            return
        if self.now_room not in self.room_list:
            self.now_room = self.room_list[0]

        for room in self.room_list:
            room_width = max(1, int(self.width / max(1, len(self.room_list))))
            if room == self.now_room:
                now_draw = draw.CenterDraw()
                now_draw.text = f"[{room}]"
                now_draw.style = "onbutton"
                now_draw.width = room_width
                now_draw.draw()
            else:
                add_button(
                    return_list,
                    draw.CenterButton(
                        f"[{room}]", f"\nROOM_{room}", room_width
                    ),
                )
        line_feed.draw()
        draw.LineDraw("-", self.width).draw()
        text_line(svc.classroom_info_text(self.now_room), self.width)

        self.cell_return = self._draw_week_table(self.now_room)
        return_list.extend(self.cell_return.keys())
        line_feed.draw()
        draw.LineDraw("-", self.width).draw()

        half = int(self.width / 2)
        add_button(
            return_list,
            draw.CenterButton(_("[一键排满全部教室]"), _("一键排课"), half),
        )
        add_button(
            return_list,
            draw.CenterButton(_("[清空本教室]"), _("清空本教室"), half),
        )
        line_feed.draw()

    def handle_yrn(self, yrn: str) -> None:
        """处理自动排课、清空本教室、点选课表格子与切换教室输入。"""
        if not self.room_list:
            return
        if yrn == _("一键排课"):
            self._auto_fill_schedule()
            return
        if yrn == _("清空本教室"):
            self._clear_room(self.now_room)
            return
        if yrn in self.cell_return:
            week_day, period = self.cell_return[yrn]
            self._edit_cell(self.now_room, week_day, period)
            return
        for room in self.room_list:
            if yrn == f"\nROOM_{room}":
                self.now_room = room
                return

    def _draw_week_table(self, classroom: str) -> dict[str, tuple]:
        """绘制指定教室的 7 天乘 9 节周表并返回按钮派发映射。"""
        cell_return: dict[str, tuple] = {}
        cell_width = svc.cell_width(self.width)
        text_line(_("  节次        "), svc.HEAD_WIDTH)
        for name in education_constant.WEEK_NAME:
            now_draw = draw.CenterDraw()
            now_draw.width = cell_width
            now_draw.text = name
            now_draw.draw()
        line_feed.draw()

        for period in range(len(game_time.CLASS_PERIOD_START)):
            text_line(svc.period_head_text(period), svc.HEAD_WIDTH)
            for week_day in range(len(education_constant.WEEK_NAME)):
                cell = svc.week_cell(classroom, week_day, period, cell_width)
                button = draw.CenterButton(
                    cell.text,
                    f"\nCELL_{week_day}_{period}",
                    cell_width,
                    normal_style="deep_gray" if cell.absent else "standard",
                    tooltip=cell.tooltip,
                )
                button.draw()
                cell_return[button.return_text] = (week_day, period)
            line_feed.draw()
        return cell_return

    def _auto_fill_schedule(self) -> None:
        """调用课表服务执行自动排课并绘制结果提示。"""
        text_line(svc.auto_fill(), self.width, "gold_enrod")

    def _clear_room(self, classroom: str) -> None:
        """调用课表服务清空指定教室的每周课表。"""
        svc.clear_room(classroom)

    def _edit_cell(self, classroom: str, week_day: int, period: int) -> None:
        """依次选择科目与教师并写入或清空格子，或进入临时实操课编辑。"""
        ability_id = self._select_subject(classroom, week_day, period)
        if ability_id == -1:
            return
        if ability_id == -2:
            self._edit_sex_class(classroom, week_day, period)
            return
        if ability_id == 0:
            schedule_handle.clear_class_cell(classroom, week_day, period)
            return
        teacher_id = self._select_teacher(
            classroom, week_day, period, ability_id
        )
        if teacher_id == -2:
            return
        schedule_handle.set_class_cell(
            classroom, week_day, period, ability_id, teacher_id
        )

    def _edit_sex_class(
        self, classroom: str, week_day: int, period: int
    ) -> None:
        """打开指定教室与时段的临时性技实操课编辑界面。"""
        Sex_Class_Plan_Panel(self.width).edit(classroom, week_day, period)

    def _select_must_attend(
        self, must_attend: list[int], classroom: str, week_day: int, period: int
    ) -> list[int]:
        """打开指定必修学生选择界面并返回更新后的名单。"""
        return Sex_Class_Plan_Panel(self.width).select_must_attend(
            must_attend, week_day, period
        )

    def _select_subject(
        self, classroom: str, week_day: int, period: int
    ) -> int:
        """绘制科目选择页并返回能力编号、清空 0、取消 -1 或实操课 -2。"""
        draw.TitleLineDraw(_("选择科目"), self.width).draw()
        text_line(
            svc.subject_header_text(classroom, week_day, period), self.width
        )
        overlay = svc.overlay_text(classroom, week_day, period)
        if overlay:
            text_line(overlay, self.width, "gold_enrod")
        line_feed.draw()

        return_list: list[str] = []
        id_by_return: dict[str, int] = {}
        for index, (label, ability_id) in enumerate(svc.subject_labels()):
            button = add_button(
                return_list,
                draw.LeftButton(label, str(index), int(self.width / 4)),
            )
            id_by_return[button.return_text] = ability_id
            if index % 4 == 3:
                line_feed.draw()
        line_feed.draw()
        half = int(self.width / 2)
        sex_class_draw = None
        if svc.has_sex_class_entry(classroom):
            sex_class_draw = add_button(
                return_list,
                draw.CenterButton(
                    _("[排一节性技实操课]"), _("排一节性技实操课"), half
                ),
            )
            line_feed.draw()
        line_feed.draw()
        back_draw = add_button(
            return_list, draw.CenterButton(_("[取消]"), _("取消"), half)
        )
        clear_text = _("[清空每周课表这一格]") if overlay else _("[清空本格]")
        clear_draw = add_button(
            return_list, draw.CenterButton(clear_text, _("清空本格"), half)
        )
        line_feed.draw()

        yrn = flow_handle.askfor_all(return_list)
        if yrn == back_draw.return_text:
            return -1
        if sex_class_draw is not None and yrn == sex_class_draw.return_text:
            return -2
        if yrn == clear_draw.return_text:
            return 0
        return id_by_return.get(yrn, -1)

    def _select_teacher(
        self, classroom: str, week_day: int, period: int, ability_id: int
    ) -> int:
        """绘制候选教师页并支持切换排序，返回教师编号、不排 -1 或取消 -2。"""
        sort_desc = True
        ability_name = svc.ability_label(ability_id)
        while 1:
            draw.TitleLineDraw(_("选择授课教师"), self.width).draw()
            text_line(
                _(
                    "  名字后是该教师的{0}等级与本周已排的节数；灰色的是本节已在别处上课的。\n"
                ).format(ability_name),
                self.width,
            )
            return_list: list[str] = []
            id_by_return: dict[str, int] = {}
            sort_text = (
                _("[按{0}等级↓]").format(ability_name)
                if sort_desc
                else _("[按{0}等级↑]").format(ability_name)
            )
            sort_draw = add_button(
                return_list,
                draw.CenterButton(
                    sort_text, "SORT_TEACHER", int(self.width / 3)
                ),
            )
            line_feed.draw()
            draw.LineDraw("-", self.width).draw()

            teacher_width = int(self.width / 6)
            rows = svc.teacher_rows(
                ability_id, week_day, period, classroom, sort_desc
            )
            for count, row in enumerate(rows, 1):
                if row.conflict:
                    now_draw = draw.LeftDraw()
                    now_draw.width = teacher_width
                    now_draw.style = "deep_gray"
                    now_draw.text = row.label
                    now_draw.draw()
                else:
                    button = add_button(
                        return_list,
                        draw.LeftButton(
                            row.label, str(row.teacher_id), teacher_width
                        ),
                    )
                    id_by_return[button.return_text] = row.teacher_id
                if count % 6 == 0:
                    line_feed.draw()
            if len(rows) % 6:
                line_feed.draw()
            summary = svc.conflict_summary(rows)
            if summary:
                text_line(summary, self.width, "deep_gray")
            line_feed.draw()

            none_draw = add_button(
                return_list,
                draw.CenterButton(
                    _("[本节不排教师（学生自习）]"),
                    _("不排教师"),
                    int(self.width / 2),
                ),
            )
            back_draw = add_button(
                return_list,
                draw.CenterButton(_("[取消]"), _("取消"), int(self.width / 2)),
            )
            line_feed.draw()

            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                return -2
            if yrn == none_draw.return_text:
                return -1
            if yrn == sort_draw.return_text:
                sort_desc = not sort_desc
                continue
            return id_by_return.get(yrn, -2)
