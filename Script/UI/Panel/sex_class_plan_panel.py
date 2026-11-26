"""
临时性技实操课编辑与指定必修学生面板。
提供共享绘制辅助函数，排课规则与文本由 sex_class_plan_service 提供。
"""

from types import FunctionType

from Script.Core import flow_handle, get_text
from Script.Modules.gameplay_resolution import sex_class_plan_service as plan
from Script.System.Education_System import sex_class_handle
from Script.UI.Moudle import draw

_: FunctionType = get_text._
line_feed = draw.NormalDraw()
line_feed.text = "\n"
line_feed.width = 1


def text_line(text: str, width: int, style: str = "") -> None:
    """按指定宽度与可选样式绘制一行普通文本。"""
    now_draw = draw.NormalDraw()
    now_draw.width = width
    now_draw.text = text
    if style:
        now_draw.style = style
    now_draw.draw()


def add_button(
    return_list: list[str], button: draw.CenterButton
) -> draw.CenterButton:
    """绘制按钮对象并将其返回值追加到共享返回列表。"""
    button.draw()
    return_list.append(button.return_text)
    return button


class Sex_Class_Plan_Panel:
    """临时性技实操课编辑与必修学生选择界面面板。"""

    def __init__(self, width: int) -> None:
        """记录面板绘制宽度。"""
        self.width: int = width

    def edit(self, classroom: str, week_day: int, period: int) -> None:
        """循环绘制临时实操课编辑页，处理主修切换、必修点名、保存与删除。"""
        draft = plan.load_draft(classroom, week_day, period)
        ability_id = draft.ability_id
        must_attend = draft.must_attend
        third = int(self.width / 3)

        while 1:
            draw.TitleLineDraw(_("排一节性技实操课"), self.width).draw()
            text_line(
                plan.info_text(classroom, week_day, period, draft.date_ordinal),
                self.width,
            )
            if draft.other_classroom:
                text_line(
                    _("  该节已在{0}排了实操课，确定后改到本教室\n\n").format(
                        draft.other_classroom
                    ),
                    self.width,
                    "gold_enrod",
                )
            text_line(
                _(
                    "  主修科目（这一门的相关动作有额外经验加成，其他动作照样能做）：\n"
                ),
                self.width,
            )
            return_list: list[str] = []
            id_by_return: dict[str, int] = {}
            for text, now_ability_id, selected in plan.subject_buttons(
                ability_id
            ):
                button = add_button(
                    return_list,
                    draw.CenterButton(
                        text,
                        f"SUB_{now_ability_id}",
                        int(self.width / 8),
                        normal_style="gold_enrod" if selected else "standard",
                    ),
                )
                id_by_return[button.return_text] = now_ability_id
            line_feed.draw()
            line_feed.draw()

            for text, style in plan.attendance_lines(
                classroom, week_day, period, must_attend
            ):
                text_line(text, self.width, style)

            add_draw = add_button(
                return_list,
                draw.CenterButton(_("[指定必修学生]"), "ADD_MUST", third),
            )
            ok_draw = add_button(
                return_list, draw.CenterButton(_("[确定]"), "OK", third)
            )
            line_feed.draw()
            del_draw = None
            if draft.exists:
                del_draw = add_button(
                    return_list,
                    draw.CenterButton(_("[删除本节临时课]"), "DEL", third),
                )
            back_draw = add_button(
                return_list, draw.CenterButton(_("[返回]"), "BACK", third)
            )
            line_feed.draw()

            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                return
            if del_draw is not None and yrn == del_draw.return_text:
                sex_class_handle.del_temp_class(draft.date_ordinal, period)
                return
            if yrn == ok_draw.return_text:
                sex_class_handle.set_temp_class(
                    draft.date_ordinal,
                    period,
                    classroom,
                    ability_id,
                    must_attend=must_attend,
                )
                return
            if yrn == add_draw.return_text:
                must_attend = self.select_must_attend(
                    must_attend, week_day, period
                )
                continue
            if yrn in id_by_return:
                ability_id = id_by_return[yrn]

    def select_must_attend(
        self, must_attend: list[int], week_day: int, period: int
    ) -> list[int]:
        """循环绘制必修学生选择页，按点击切换选中并在完成后返回名单。"""
        must_attend = list(must_attend)
        while 1:
            draw.TitleLineDraw(_("指定必修学生"), self.width).draw()
            text_line(
                _(
                    "  被点名的学生无论原本排了什么课都会来，且不会翘课。名字前的√为已选中。\n"
                ),
                self.width,
            )
            return_list: list[str] = []
            id_by_return: dict[str, int] = {}
            rows = plan.must_rows(must_attend, week_day, period)
            for count, row in enumerate(rows, 1):
                button = add_button(
                    return_list,
                    draw.LeftButton(
                        row.label,
                        f"MUST_{row.character_id}",
                        int(self.width / 6),
                    ),
                )
                id_by_return[button.return_text] = row.character_id
                if count % 6 == 0:
                    line_feed.draw()
            if len(rows) % 6:
                line_feed.draw()
            if not rows:
                text_line(_("\n  目前没有可参加的学生\n"), self.width)
            summary = plan.replace_summary(rows)
            if summary:
                text_line(summary, self.width, "deep_gray")
            line_feed.draw()
            back_draw = add_button(
                return_list,
                draw.CenterButton(_("[完成]"), "DONE", int(self.width / 3)),
            )
            line_feed.draw()
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                return must_attend
            if yrn in id_by_return:
                must_attend = plan.toggled(must_attend, id_by_return[yrn])
