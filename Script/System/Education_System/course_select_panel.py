"""
个人课表面板。
负责绘制个人课表界面与分发输入，规则与文本由 course_select_service 提供。
"""

from types import FunctionType

from Script.Core import get_text, flow_handle
from Script.Design import game_time
from Script.Modules.domains import identity
from Script.Modules.gameplay_resolution import course_select_service as svc
from Script.Modules.gameplay_resolution.class_schedule_service import (
    HEAD_WIDTH,
    cell_width,
    period_head_text,
)
from Script.Modules.tk_ui import student_select
from Script.System.Education_System import education_constant
from Script.System.Education_System import growth_handle
from Script.System.Education_System import schedule_template_handle
from Script.UI.Moudle import draw

_: FunctionType = get_text._
""" 本地化翻译函数。 """
line_feed = draw.NormalDraw()
line_feed.text = "\n"
line_feed.width = 1


class Course_Select_Panel:
    """教育管理系统的个人课表子面板，负责绘制周表、日程微调与选课交互。"""

    def __init__(self, width: int) -> None:
        """初始化个人课表子面板宽度及当前学生、名单与格子派发状态。"""
        self.width: int = width
        self.now_student: int = -1
        """ 当前选中的学生角色编号，未选择时为 -1。 """
        self.student_list: list[int] = []
        """ 当前全部职业为学生的候选干员角色编号列表。 """
        self.cell_return: dict[str, tuple] = {}
        """ 周表按钮返回值到 (星期, 节次) 的派发映射。 """

    def draw_page(self, return_list: list[str]) -> None:
        """每轮重算学生名单并清空格子派发映射，再绘制选人行、周表、日程与操作按钮。"""
        self.student_list = growth_handle.get_course_candidate_list()
        self.cell_return = {}
        if not self.student_list:
            info_draw = draw.NormalDraw()
            info_draw.width = self.width
            info_draw.text = _("\n  目前还没有职业为学生的干员\n")
            info_draw.draw()
            return
        if self.now_student not in self.student_list:
            self.now_student = -1
        if not student_select.draw_select_student_line(
            self.width, self.now_student, return_list
        ):
            return

        self.cell_return = self._draw_week_table(self.now_student)
        return_list.extend(self.cell_return.keys())
        line_feed.draw()
        draw.LineDraw("-", self.width).draw()

        schedule_draw = draw.LeftButton(
            _(" 日程：{0} [改]").format(
                schedule_template_handle.get_child_schedule_text(
                    self.now_student
                )
            ),
            "EDIT_SCHEDULE",
            self.width,
        )
        schedule_draw.draw()
        return_list.append(schedule_draw.return_text)
        line_feed.draw()
        draw.LineDraw("-", self.width).draw()

        for text, return_text in (
            (_("[一键选课]"), _("一键选课")),
            (_("[复制到其他学生]"), _("复制")),
            (_("[清空]"), _("清空")),
        ):
            button = draw.CenterButton(text, return_text, int(self.width / 3))
            button.draw()
            return_list.append(button.return_text)
        line_feed.draw()

    def handle_yrn(self, yrn: str) -> None:
        """处理选学生、一键选课、清空、复制、日程微调与点击课表格子的输入。"""
        if not self.student_list:
            return
        if yrn == education_constant.SELECT_STUDENT_RETURN:
            self.now_student = student_select.select_student(
                self.student_list,
                _("选择学生"),
                _("请选择要查看或编辑个人课表的学生：\n"),
                self.now_student,
            )
            return
        if self.now_student == -1:
            return
        if yrn == _("一键选课"):
            self._auto_fill_course(self.now_student)
            return
        if yrn == _("清空"):
            svc.clear_student(self.now_student)
            return
        if yrn == _("复制"):
            self._copy_to_others(self.now_student, self.student_list)
            return
        if yrn == "EDIT_SCHEDULE":
            self._edit_schedule(self.now_student)
            return
        if yrn in self.cell_return:
            week_day, period = self.cell_return[yrn]
            self._edit_cell(self.now_student, week_day, period)

    def _draw_week_table(self, character_id: int) -> dict[str, tuple]:
        """绘制指定学生的 7 天乘 9 节个人课表并返回按钮派发映射。"""
        cell_return: dict[str, tuple] = {}
        now_width = cell_width(self.width)

        head_draw = draw.NormalDraw()
        head_draw.width = HEAD_WIDTH
        head_draw.text = _("  节次        ")
        head_draw.draw()
        for name in education_constant.WEEK_NAME:
            now_draw: draw.CenterDraw | draw.CenterButton = draw.CenterDraw()
            now_draw.width = now_width
            now_draw.text = name
            now_draw.draw()
        line_feed.draw()

        for period in range(len(game_time.CLASS_PERIOD_START)):
            head_draw = draw.NormalDraw()
            head_draw.width = HEAD_WIDTH
            head_draw.text = period_head_text(period)
            head_draw.draw()
            for week_day in range(len(education_constant.WEEK_NAME)):
                now_draw = draw.CenterButton(
                    svc.cell_text(character_id, week_day, period),
                    f"\nMYCELL_{week_day}_{period}",
                    now_width,
                )
                now_draw.draw()
                cell_return[now_draw.return_text] = (week_day, period)
            line_feed.draw()
        return cell_return

    def _auto_fill_course(self, character_id: int) -> None:
        """调用个人课表服务执行一键选课并绘制结果提示。"""
        info_draw = draw.NormalDraw()
        info_draw.width = self.width
        info_draw.style = "gold_enrod"
        info_draw.text = svc.auto_fill_text(character_id)
        info_draw.draw()

    def _edit_schedule(self, character_id: int) -> None:
        """绘制单个学生的日程模板与三时段覆盖编辑页，并按输入套用模板或单槽活动。"""
        from Script.System.Education_System import schedule_template_panel

        template_panel = schedule_template_panel.Schedule_Template_Panel(
            self.width
        )
        while 1:
            return_list: list[str] = []
            slot_by_return: dict[str, int] = {}
            draw.TitleLineDraw(
                _("{0}的日程").format(identity.of(character_id).name),
                self.width,
            ).draw()
            change_draw = draw.LeftButton(
                _(" 日程模板：{0} [改]").format(
                    schedule_template_handle.get_child_schedule_text(
                        character_id
                    )
                ),
                "CHANGE_TEMPLATE",
                self.width,
            )
            change_draw.draw()
            return_list.append(change_draw.return_text)
            line_feed.draw()
            draw.LineDraw("-", self.width).draw()
            tip_draw = draw.NormalDraw()
            tip_draw.width = self.width
            tip_draw.text = _(
                "  点某个时段可单独指定活动；选「自由选择娱乐活动」即取消单独指定、回到模板的安排；"
                "不符合条件的活动会退回自由选择\n"
            )
            tip_draw.style = "deep_gray"
            tip_draw.draw()
            for slot, label in enumerate(svc.slot_labels(character_id)):
                now_draw = draw.LeftButton(
                    label, f"CHILD_SLOT_{slot}", int(self.width / 2)
                )
                now_draw.draw()
                return_list.append(now_draw.return_text)
                slot_by_return[now_draw.return_text] = slot
                line_feed.draw()
            back_draw = draw.CenterButton(
                _("[返回]"), _("返回日程"), int(self.width / 2)
            )
            back_draw.draw()
            return_list.append(back_draw.return_text)
            line_feed.draw()

            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                return
            if yrn == change_draw.return_text:
                template_id = template_panel._select_template()
                if template_id is not None:
                    schedule_template_handle.apply_template(
                        character_id, template_id
                    )
                continue
            if yrn in slot_by_return:
                entertainment_id = template_panel._select_activity()
                if entertainment_id is not None:
                    schedule_template_handle.set_child_override(
                        character_id, slot_by_return[yrn], entertainment_id
                    )

    def _copy_to_others(
        self, character_id: int, student_list: list[int]
    ) -> None:
        """每行 6 人列出其余候选学生，并将当前学生的个人课表复制到所选目标。"""
        draw.TitleLineDraw(_("复制课表到"), self.width).draw()
        return_list: list[str] = []
        id_by_return: dict[str, int] = {}
        count = 0
        for label, other_id in svc.copy_targets(character_id, student_list):
            now_draw = draw.LeftButton(
                label, f"COPY_{other_id}", int(self.width / 6)
            )
            now_draw.draw()
            return_list.append(now_draw.return_text)
            id_by_return[now_draw.return_text] = other_id
            count += 1
            if count % 6 == 0:
                line_feed.draw()
        if count % 6:
            line_feed.draw()
        back_draw = draw.CenterButton(
            _("[取消]"), _("取消"), int(self.width / 2)
        )
        back_draw.draw()
        return_list.append(back_draw.return_text)
        line_feed.draw()

        yrn = flow_handle.askfor_all(return_list)
        if yrn in id_by_return:
            svc.copy_schedule(character_id, id_by_return[yrn])

    def _edit_cell(self, character_id: int, week_day: int, period: int) -> None:
        """打开指定节次的选课流程，在玩家未取消时写入或清空该课表格子。"""
        result = self._select_course(character_id, week_day, period)
        if result is not None:
            svc.apply_choice(character_id, week_day, period, result)

    def _select_course(
        self, character_id: int, week_day: int, period: int
    ) -> tuple[int, str | int] | str | None:
        """绘制本节各教室常规课与个人式课型入口，返回课表元组、清空标记或 None。"""
        draw.TitleLineDraw(_("选择课程"), self.width).draw()
        info_draw = draw.NormalDraw()
        info_draw.width = self.width
        info_draw.text = svc.course_head_text(character_id, week_day, period)
        info_draw.draw()

        return_list: list[str] = []
        result_by_return: dict[str, tuple] = {}

        head_draw = draw.NormalDraw()
        head_draw.width = self.width
        head_draw.style = "gold_enrod"
        head_draw.text = _("  本节各教室的课（选中即去上这节课）：\n")
        head_draw.draw()
        class_count = 0
        now_draw: draw.LeftDraw | draw.LeftButton | draw.CenterButton
        for row in svc.classroom_rows(week_day, period):
            if row.choice is None:
                now_draw = draw.LeftDraw()
                now_draw.width = int(self.width / 2)
                now_draw.style = "deep_gray"
                now_draw.text = row.text
                now_draw.draw()
                line_feed.draw()
                continue
            class_count += 1
            now_draw = draw.LeftButton(
                row.text,
                f"CLS_{row.classroom}",
                int(self.width / 2),
                normal_style="deep_gray" if row.absent else "standard",
            )
            now_draw.draw()
            return_list.append(now_draw.return_text)
            result_by_return[now_draw.return_text] = row.choice
            line_feed.draw()
        if not class_count:
            empty_draw = draw.NormalDraw()
            empty_draw.width = self.width
            empty_draw.style = "deep_gray"
            empty_draw.text = _(
                "  本节所有教室都没有排课，先去「全局课表」排好再来选\n"
            )
            empty_draw.draw()

        line_feed.draw()
        draw.LineDraw("-", self.width).draw()
        type_head_draw = draw.NormalDraw()
        type_head_draw.width = self.width
        type_head_draw.style = "gold_enrod"
        type_head_draw.text = _("  不去教室，改上：\n")
        type_head_draw.draw()
        type_by_return: dict[str, int] = {}
        for course_type in (
            education_constant.COURSE_TYPE_PE,
            education_constant.COURSE_TYPE_INTEREST,
            education_constant.COURSE_TYPE_INTERN,
        ):
            now_draw = draw.CenterButton(
                _("[{0}]").format(
                    education_constant.COURSE_TYPE_NAME[course_type]
                ),
                f"CT_{course_type}",
                int(self.width / 6),
            )
            now_draw.draw()
            return_list.append(now_draw.return_text)
            type_by_return[now_draw.return_text] = course_type
        line_feed.draw()

        line_feed.draw()
        clear_draw = draw.CenterButton(
            _("[清空本格]"), _("清空本格"), int(self.width / 2)
        )
        clear_draw.draw()
        return_list.append(clear_draw.return_text)
        back_draw = draw.CenterButton(
            _("[取消]"), _("取消"), int(self.width / 2)
        )
        back_draw.draw()
        return_list.append(back_draw.return_text)
        line_feed.draw()

        yrn = flow_handle.askfor_all(return_list)
        if yrn == back_draw.return_text:
            return None
        if yrn == clear_draw.return_text:
            return "CLEAR"
        if yrn in result_by_return:
            return result_by_return[yrn]
        if yrn in type_by_return:
            course_type = type_by_return[yrn]
            target = self._select_target(
                character_id, week_day, period, course_type
            )
            if target is None:
                return None
            return (course_type, target)
        return None

    def _select_target(
        self, character_id: int, week_day: int, period: int, course_type: int
    ) -> str | int | None:
        """绘制个人式课型候选项页并返回所选目标或 None，周日实习课直接提示不可排。"""
        draw.TitleLineDraw(
            _("选择{0}的内容").format(
                education_constant.COURSE_TYPE_NAME[course_type]
            ),
            self.width,
        ).draw()
        return_list: list[str] = []
        target_by_return: dict[str, str | int] = {}
        options: list[svc.TargetOption] = []
        now_draw: draw.LeftDraw | draw.LeftButton | draw.NormalDraw
        closed = (
            course_type == education_constant.COURSE_TYPE_INTERN
            and week_day == education_constant.WEEK_DAY_COUNT - 1
        )
        if closed:
            now_draw = draw.NormalDraw()
            now_draw.width = self.width
            now_draw.style = "deep_gray"
            now_draw.text = _(
                "\n  周日全岛无人上班，实习课找不到带教干员，本日不可排\n"
            )
            now_draw.draw()
        else:
            options = svc.target_options(character_id, course_type)
        for index, option in enumerate(options, 1):
            if option.enabled:
                now_draw = draw.LeftButton(
                    option.text, f"TG_{option.target}", int(self.width / 6)
                )
                now_draw.draw()
                return_list.append(now_draw.return_text)
                target_by_return[now_draw.return_text] = option.target
            else:
                now_draw = draw.LeftDraw()
                now_draw.width = int(self.width / 6)
                now_draw.style = "deep_gray"
                now_draw.text = option.text
                now_draw.draw()
            if index % 6 == 0:
                line_feed.draw()
        if len(options) % 6:
            line_feed.draw()

        if not closed and not any(option.enabled for option in options):
            info_draw = draw.NormalDraw()
            info_draw.width = self.width
            info_draw.text = _("\n  本节次没有可选的内容\n")
            info_draw.draw()
        line_feed.draw()
        back_draw = draw.CenterButton(
            _("[取消]"), _("取消"), int(self.width / 2)
        )
        back_draw.draw()
        return_list.append(back_draw.return_text)
        line_feed.draw()

        yrn = flow_handle.askfor_all(return_list)
        return target_by_return.get(yrn, None)
