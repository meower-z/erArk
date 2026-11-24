"""
招募面板，负责招募线策略设置、招聘专员任命与待确认干员列表展示。
"""

from __future__ import annotations

from types import FunctionType
from Script.Core import constant, flow_handle, get_text
from Script.Design import attr_calculation, basement
from Script.UI.Moudle import draw, panel, view
from Script.Config import game_config, normal_config
from Script.Modules.domains import facility, identity, recruit, work
from Script.Modules.gameplay_resolution import recruit_service

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """
HR_COLUMN_WIDTHS = (15, 12, 8, 6, 10, 10, 8, 8, 6, 6, 6)
""" 招聘专员管理表格十一列从职位列起的显示宽度元组 """


def draw_text(text: str, style: str = "standard") -> None:
    """使用新建 NormalDraw 以样式 style 绘制文本 text，无返回值。"""
    now_draw = draw.NormalDraw()
    now_draw.text = text
    now_draw.style = style
    now_draw.draw()


def ask_with_back(return_list: list[str], width: int) -> bool:
    """按宽度 width 绘制居中 [返回] 按钮并加入 return_list 后等待输入，选中返回时返回 True。"""
    back_draw = draw.CenterButton(_("[返回]"), _("返回"), width)
    back_draw.draw()
    line_feed.draw()
    return_list.append(back_draw.return_text)
    return flow_handle.askfor_all(return_list) == back_draw.return_text


def hr_row_text(cells: tuple[str, ...]) -> str:
    """将单元格 cells 按 HR_COLUMN_WIDTHS 补齐显示宽度并用 ' | ' 拼接为两格缩进的表格行文本。"""
    return "  " + " | ".join(
        attr_calculation.pad_display_width(str(cell), width)
        for cell, width in zip(cells, HR_COLUMN_WIDTHS, strict=True)
    )


class Recruit_Panel:
    """
    用于招募的面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.now_panel = _("招募")
        """ 当前绘制的页面 """
        self.draw_list: list[draw.NormalDraw] = []
        """ 绘制的文本列表 """
        self.show_detail_line: int = -1
        """ 当前展开详情的招募线编号 """

    def toggle_detail(self, line_id: int) -> None:
        """展开或收起招募详情"""
        same = self.show_detail_line == line_id
        self.show_detail_line = -1 if same else line_id

    def draw(self) -> None:
        """绘制对象"""
        basement.get_base_updata()
        title_draw = draw.TitleLineDraw(_("招募"), self.width)
        now_level = facility.level(7)
        line_count = len(recruit.lines())
        recruitable = recruit_service.find_recruitable_npc()
        while 1:
            return_list = []
            title_draw.draw()
            now_text = _("  当前设施等级为：{0}，可同时有{1}条招募线\n").format(
                now_level, line_count
            )
            if not recruit.pending():
                now_text += _("  当前没有已招募待确认的干员\n")
            else:
                now_text += _("  当前已招募待确认的干员有：")
                for chara_id in recruit.pending():
                    if chara_id == 0 or not identity.exists(chara_id):
                        continue
                    character_data = identity.of(chara_id)
                    now_text += f" [{str(character_data.adv).rjust(4,'0')}]{character_data.name}"
                now_text += "\n"
            draw_text(now_text)

            for line_id, line in recruit.lines().items():
                return_list += self.draw_line(line_id, line, recruitable)
            line_feed.draw()

            button_text = _("[001]招聘专员管理")
            button_draw = draw.LeftButton(
                _(button_text),
                _(button_text),
                int(self.width / 3),
                cmd_func=self.select_npc_position,
            )
            if any(line["main"] == 0 for line in recruit.lines().values()):
                button_draw.normal_style = "gold_enrod"
            return_list.append(button_draw.return_text)
            button_draw.draw()
            line_feed.draw()
            line_feed.draw()
            if ask_with_back(return_list, window_width):
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def draw_line(
        self, line_id: int, line: recruit.Line, ids: list[int]
    ) -> list[str]:
        """
        绘制招募线 line_id（line）的进度、策略、[调整策略] 按钮、基于 ids 的可招募数（0 为 red）与 [详情] 名单。
        再绘制效率说明（空缺用 warning 样式标出），返回本线绘制按钮的返回文本列表。
        """
        return_list = []
        progress = round(line["progress"], 1)
        draw_text(_("\n {0}号招募进度：{1}%").format(line_id + 1, progress))
        strategy_id = line["strategy"]
        strategy = game_config.config_recruitment_strategy[strategy_id]
        draw_text(_("\n    招募策略：{0}      ").format(strategy.name))
        button_text = _(" [调整策略] ")
        button_draw = draw.CenterButton(
            _(button_text),
            _("{0}_{1}").format(button_text, line_id),
            len(button_text) * 2,
            cmd_func=self.select_recruitment_strategy,
            args=line_id,
        )
        return_list.append(button_draw.return_text)
        button_draw.draw()
        line_feed.draw()
        candidates = recruit_service.line_candidates(
            strategy_id, line["main"], ids
        )
        draw_text(_("    当前策略剩余可招募干员数："))
        draw_text(str(len(candidates)), "standard" if candidates else "red")
        if candidates:
            detail_btn_text = _(" [详情] ")
            detail_btn = draw.CenterButton(
                detail_btn_text,
                _("{0}_{1}").format(detail_btn_text, line_id),
                len(detail_btn_text) * 2,
                cmd_func=self.toggle_detail,
                args=(line_id,),
            )
            detail_btn.draw()
            return_list.append(detail_btn.return_text)
        line_feed.draw()
        if self.show_detail_line == line_id and candidates:
            names = "、".join([identity.of(cid).name for cid in candidates])
            draw_text("      " + names + "\n")
        efficiency = recruit_service.calculate_recruit_line_efficiency
        vacant_str = _("空缺")
        parts = ("    " + efficiency(line_id)[0]).split(vacant_str)
        for i, part in enumerate(parts):
            draw_text(part)
            if i < len(parts) - 1:
                draw_text(vacant_str, "warning")
        line_feed.draw()
        return return_list

    def select_recruitment_strategy(self, recruit_line_id: int) -> None:
        """选择招募策略"""
        draw.LineDraw("-", window_width).draw()
        info_draw = draw.NormalDraw()
        info_draw.width = window_width
        return_list = []
        strategy_id = recruit.lines()[recruit_line_id]["strategy"]
        strategy = game_config.config_recruitment_strategy[strategy_id]
        info_draw.text = _(" {0}号招募当前的策略为：{1}").format(
            recruit_line_id + 1, strategy.name
        )
        info_draw.text += _(
            "\n\n 当前可以选择的策略有（系数越高越简单、招募越快）：\n"
        )
        info_draw.draw()
        line_feed.draw()
        for option in recruit_service.strategy_options(recruit_line_id):
            button_draw = draw.LeftButton(
                option.text,
                f"\n{option.cid}",
                window_width,
                cmd_func=self.change_recruit_line_produce,
                args=(recruit_line_id, option.cid),
            )
            button_draw.draw()
            return_list.append(button_draw.return_text)
            line_feed.draw()

        line_feed.draw()
        ask_with_back(return_list, window_width)
        view.now_panel_id = constant.Panel.IN_SCENE

    def select_npc_position(self) -> None:
        """招聘专员管理(任命各线主招聘专员)"""
        from Script.UI.Panel import manage_basement_panel

        page = 0
        items_per_page = 10
        header = (_("职位"), _("名字"), _("加成"), _("话术"), _("势力"))
        header += (_("出生地"), _("职业"), _("种族"), _("外表"), _("胸部"))
        header += (_("臀部"),)

        while 1:
            basement.update_work_people()
            draw.TitleLineDraw(_("招聘专员管理"), self.width).draw()
            return_list = []
            hr_count = len(work.roster(work.HR_WORK))
            draw_text(_("  当前招聘专员数量：{0}      \n").format(hr_count))
            button_text = _("[招聘专员增减]")
            button_draw = draw.CenterButton(
                _(button_text),
                _(button_text),
                len(button_text) * 2 + 2,
                cmd_func=manage_basement_panel.change_npc_work_out,
                args=(self.width, [132]),
            )
            return_list.append(button_draw.return_text)
            button_draw.draw()
            line_feed.draw()
            line_feed.draw()
            draw_text(hr_row_text(header) + "\n")
            div = draw.LineDraw("-", self.width)
            div.draw()

            for line_id, line in recruit.lines().items():
                role = _("主召聘专员({0}号)").format(line_id + 1)
                cells = recruit_service.hr_cells(line["main"], True)
                btn = draw.LeftButton(
                    hr_row_text((role, *cells)),
                    f"任命_{line_id+1}",
                    self.width,
                    normal_style=(
                        "gold_enrod" if line["main"] == 0 else "standard"
                    ),
                    cmd_func=lambda idx=line_id: self._appoint_main_hr(idx),
                )
                btn.draw()
                return_list.append(btn.return_text)
                line_feed.draw()

            line_feed.draw()
            div.draw()
            line_feed.draw()
            other_ops = recruit_service.sub_hr_ids()
            max_page = max(0, (len(other_ops) - 1) // items_per_page)
            page = min(page, max_page)
            start_idx = page * items_per_page
            curr_ops = other_ops[start_idx : start_idx + items_per_page]
            if not curr_ops:
                draw_text(_("  副招聘专员：暂无\n"))
            for cid in curr_ops:
                cells = recruit_service.hr_cells(cid, False)
                draw_text(hr_row_text((_("副招聘专员"), *cells)) + "\n")
            line_feed.draw()
            line_feed.draw()

            if max_page > 0:

                def turn(step: int) -> None:
                    nonlocal page
                    page += step

                for text, return_text, shown, step in (
                    (_("[上一页]"), _("上一页"), page > 0, -1),
                    (_("[下一页]"), _("下一页"), page < max_page, 1),
                ):
                    if not shown:
                        null_btn = draw.CenterDraw()
                        null_btn.text = " "
                        null_btn.width = int(self.width / 2)
                        null_btn.draw()
                        continue
                    page_btn = draw.CenterButton(
                        text,
                        return_text,
                        int(self.width / 2),
                        cmd_func=lambda step=step: turn(step),
                    )
                    page_btn.draw()
                    return_list.append(page_btn.return_text)
                line_feed.draw()
                line_feed.draw()

            if ask_with_back(return_list, self.width):
                break

    def _appoint_main_hr(self, line_id: int) -> None:
        """任命某条招募线主招聘专员(重复选择同一人可撤销)"""
        from Script.UI.Panel import common_select_NPC

        button_type = common_select_NPC.CommonSelectNPCButtonList
        now_draw_panel = panel.PageHandlePanel(
            [], button_type, 50, 5, window_width, True, False, 0
        )
        select_state: dict[str, int | str] = {}

        def _make(chara_id: int) -> None:
            recruit_service.appoint_main_hr(line_id, chara_id)

        while 1:
            info_text = _(
                "请选择一名招聘专员担任第{0}号招募线主招聘专员:\n"
            ).format(line_id + 1)
            now_draw_panel.text_list = [
                [npc_id, _make, [recruit.lines()[line_id]["main"]]]
                for npc_id in work.roster(work.HR_WORK)
                if npc_id != 0
            ]
            return_list, _other_return_list, select_state = (
                common_select_NPC.common_select_npc_button_list_func(
                    now_draw_panel, _("任命主招聘专员"), info_text, select_state
                )
            )
            yrn = flow_handle.askfor_all(return_list)
            if yrn == _("返回"):
                break

    def change_recruit_line_produce(
        self, asrecruit_line_id: int, recruitment_strategy_cid: int
    ) -> None:
        """更改招募线的策略，改为停止招募（策略 11）时进度归 0"""
        recruit_service.set_line_strategy(
            asrecruit_line_id, recruitment_strategy_cid
        )

    def settle_npc_id(self, chara_id: int) -> None:
        """结算干员的id变更"""
        self.now_chara_id = chara_id

    def settle_assembly_line_id(self, asrecruit_line_id: int) -> None:
        """结算流水线的id变更"""
        self.target_position = asrecruit_line_id
