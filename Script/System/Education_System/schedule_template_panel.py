"""
日程模板面板（schedule_template_panel）
=======================================
负责日程模板表、编辑页与各选择页的绘制和输入处理。展示文本由 schedule_template_service 提供。
"""

from types import FunctionType

from Script.Core import get_text, flow_handle
from Script.Modules.gameplay_resolution import schedule_template_service
from Script.System.Education_System import (
    education_constant,
    schedule_template_handle,
    growth_handle,
)
from Script.UI.Moudle import draw, panel

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
line_feed.text = "\n"
line_feed.width = 1


def _draw_button_rows(
    rows: list[list[schedule_template_service.Button]],
    prefix: str,
    width: int,
    return_list: list[str],
    id_by_return: dict[str, int],
) -> None:
    """逐行绘制左对齐按钮，登记返回码与对应编号并在每行末尾换行。"""
    for row in rows:
        for value, text in row:
            now_draw = draw.LeftButton(text, f"{prefix}{value}", width)
            now_draw.draw()
            return_list.append(now_draw.return_text)
            id_by_return[now_draw.return_text] = value
        line_feed.draw()


class Schedule_Template_Panel:
    """教育管理界面的日程模板子面板，负责展示模板表与处理编辑、新建和批量套用。"""

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        self.template_id_by_return: dict[str, int] = {}
        """ 本轮模板行按钮的返回值 → 模板编号，由 draw_page 写、handle_yrn 读 """

    def draw_page(self, return_list: list[str]) -> None:
        """
        绘制日程模板主页并将本页按钮返回码写入 return_list。
        输入等待由外层教育管理容器统一处理。
        """
        draw.TitleLineDraw(_("日程模板"), self.width).draw()
        self._draw_head()
        self.template_id_by_return = self._draw_template_table()
        return_list.extend(self.template_id_by_return.keys())

        line_feed.draw()
        draw.LineDraw("-", self.width).draw()
        create_draw = draw.CenterButton(
            _("[新建模板]"), _("新建模板"), int(self.width / 2)
        )
        create_draw.draw()
        return_list.append(create_draw.return_text)
        apply_draw = draw.CenterButton(
            _("[批量套用到多个孩子]"), _("批量套用"), int(self.width / 2)
        )
        apply_draw.draw()
        return_list.append(apply_draw.return_text)
        line_feed.draw()

    def handle_yrn(self, yrn: str) -> None:
        """按容器传入的按钮返回码分发到批量套用、新建模板或模板编辑流程。"""
        if yrn == _("批量套用"):
            self._batch_apply()
            return
        if yrn == _("新建模板"):
            self._create_template()
            return
        if yrn in self.template_id_by_return:
            self._edit_template(self.template_id_by_return[yrn])

    def _draw_head(self) -> None:
        """以金色样式绘制模板表表头。"""
        head_draw = draw.NormalDraw()
        head_draw.width = self.width
        head_draw.text = schedule_template_service.head_text()
        head_draw.style = "gold_enrod"
        head_draw.draw()

    def _draw_template_table(self) -> dict[str, int]:
        """绘制全部模板行按钮，并返回按钮返回码到模板编号的映射。"""
        template_id_by_return: dict[str, int] = {}
        _draw_button_rows(
            [[row] for row in schedule_template_service.template_rows()],
            "TEMPLATE_",
            self.width,
            [],
            template_id_by_return,
        )
        return template_id_by_return

    def _edit_template(self, template_id: int) -> None:
        """
        打开指定模板的编辑页，处理时段修改、重命名与删除操作。
        预设模板用同宽灰字占位替代删除按钮，使返回按钮位置保持不变。
        """
        while 1:
            name = schedule_template_service.template_name(template_id)
            if name is None:
                return
            return_list: list[str] = []
            slot_by_return: dict[str, int] = {}
            draw.TitleLineDraw(
                _("编辑模板：{0}").format(name), self.width
            ).draw()
            _draw_button_rows(
                [
                    [button]
                    for button in schedule_template_service.slot_buttons(
                        template_id
                    )
                ],
                "SLOT_",
                int(self.width / 2),
                return_list,
                slot_by_return,
            )
            draw.LineDraw("-", self.width).draw()
            rename_draw = draw.CenterButton(
                _("[重命名]"), _("重命名"), int(self.width / 3)
            )
            rename_draw.draw()
            return_list.append(rename_draw.return_text)
            if schedule_template_handle.judge_template_is_preset(template_id):
                null_draw = draw.CenterDraw()
                null_draw.width = int(self.width / 3)
                null_draw.style = "deep_gray"
                null_draw.text = _("（预设模板不可删除）")
                null_draw.draw()
                delete_draw = None
            else:
                delete_draw = draw.CenterButton(
                    _("[删除本模板]"), _("删除本模板"), int(self.width / 3)
                )
                delete_draw.draw()
                return_list.append(delete_draw.return_text)
            back_draw = draw.CenterButton(
                _("[返回]"), _("返回编辑"), int(self.width / 3)
            )
            back_draw.draw()
            return_list.append(back_draw.return_text)
            line_feed.draw()

            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                break
            if yrn == rename_draw.return_text:
                new_name = self._ask_template_name(_("给这套模板起个新名字"))
                schedule_template_handle.rename_template(template_id, new_name)
                continue
            if delete_draw is not None and yrn == delete_draw.return_text:
                if schedule_template_handle.delete_template(template_id):
                    break
                continue
            if yrn in slot_by_return:
                entertainment_id = self._select_activity()
                if entertainment_id is not None:
                    schedule_template_handle.set_template_slot(
                        template_id, slot_by_return[yrn], entertainment_id
                    )

    def _ask_template_name(self, ask_text: str) -> str:
        """弹出单行输入框采集模板名称并去除首尾空白。"""
        ask_panel = panel.AskForOneMessage()
        ask_panel.set(ask_text, education_constant.TEMPLATE_NAME_MAX)
        line_feed.draw()
        return ask_panel.draw().strip()

    def _create_template(self) -> None:
        """
        询问名称并新建一套空模板，创建成功后立即进入编辑页。
        新建模板的三个时段均为空，进入编辑页便于直接配置活动。
        """
        new_name = self._ask_template_name(
            _("给新模板起个名字（直接回车用默认名）")
        )
        new_id = schedule_template_handle.create_template(new_name)
        if new_id:
            self._edit_template(new_id)

    def _select_activity(self) -> int | None:
        """
        打开选择活动页，返回所选娱乐编号或在取消时返回 None。
        返回 0 表示该时段选择自由选择娱乐活动。
        """
        while 1:
            return_list: list[str] = []
            id_by_return: dict[str, int] = {}
            draw.TitleLineDraw(_("选择活动"), self.width).draw()
            _draw_button_rows(
                schedule_template_service.activity_rows(),
                "ACT_",
                int(self.width / 6),
                return_list,
                id_by_return,
            )
            line_feed.draw()
            back_draw = draw.CenterButton(
                _("[取消]"), _("取消选择活动"), self.width
            )
            back_draw.draw()
            return_list.append(back_draw.return_text)
            line_feed.draw()

            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                return None
            if yrn in id_by_return:
                return id_by_return[yrn]

    def _batch_apply(self) -> None:
        """
        先选择模板再多选候选孩子，确认后批量套用并显示结果提示。
        候选名单取自 growth_handle.get_student_candidate_list。
        """
        template_id = self._select_template()
        if template_id is None:
            return
        child_list = growth_handle.get_student_candidate_list()
        if not child_list:
            info_draw = draw.NormalDraw()
            info_draw.width = self.width
            info_draw.text = _("\n当前没有可安排日程的孩子\n")
            info_draw.style = "deep_gray"
            info_draw.draw()
            return
        selected_set: set[int] = set()
        while 1:
            return_list: list[str] = []
            id_by_return: dict[str, int] = {}
            name = schedule_template_service.template_name(template_id)
            if name is None:
                return
            draw.TitleLineDraw(
                _("批量套用：{0}").format(name), self.width
            ).draw()
            _draw_button_rows(
                schedule_template_service.child_rows(child_list, selected_set),
                "CHILD_",
                int(self.width / 6),
                return_list,
                id_by_return,
            )
            confirm_draw = draw.CenterButton(
                _("[确认套用]"), _("确认套用"), int(self.width / 2)
            )
            confirm_draw.draw()
            return_list.append(confirm_draw.return_text)
            back_draw = draw.CenterButton(
                _("[取消]"), _("取消批量套用"), int(self.width / 2)
            )
            back_draw.draw()
            return_list.append(back_draw.return_text)
            line_feed.draw()

            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                return
            if yrn == confirm_draw.return_text:
                info_draw = draw.NormalDraw()
                info_draw.width = self.width
                info_draw.text = schedule_template_service.batch_apply(
                    template_id, selected_set
                )
                info_draw.style = "gold_enrod"
                info_draw.draw()
                return
            if yrn in id_by_return:
                selected_set ^= {id_by_return[yrn]}

    def _select_template(self) -> int | None:
        """
        打开选择模板页，返回模板编号、0（不套用）或在取消时返回 None。
        调用方必须用 is None 判断取消，因为 0 是不套用日程的有效选项。
        """
        return_list: list[str] = []
        id_by_return: dict[str, int] = {}
        draw.TitleLineDraw(_("选择模板"), self.width).draw()
        _draw_button_rows(
            schedule_template_service.template_choice_rows(),
            "PICK_",
            int(self.width / 6),
            return_list,
            id_by_return,
        )
        none_draw = draw.CenterButton(
            _("[不套用日程（恢复随机）]"), _("不套用日程"), int(self.width / 2)
        )
        none_draw.draw()
        return_list.append(none_draw.return_text)
        id_by_return[none_draw.return_text] = 0
        back_draw = draw.CenterButton(
            _("[取消]"), _("取消选择模板"), int(self.width / 2)
        )
        back_draw.draw()
        return_list.append(back_draw.return_text)
        line_feed.draw()

        yrn = flow_handle.askfor_all(return_list)
        if yrn in id_by_return:
            return id_by_return[yrn]
        return None
