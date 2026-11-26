"""
怀孕总览面板（pregnancy_panel）
===============================
绘制怀孕状态总览界面（总览、生育谱系图与异常女儿排查页签）并处理交互输入。
文案与规则由 pregnancy_overview_service 提供，get_date_text 供其他模块调用。
"""

import datetime
from types import FunctionType
from Script.Core import get_text, flow_handle, constant, py_cmd, text_handle
from Script.UI.Moudle import draw, view
from Script.Config import normal_config
from Script.Modules.gameplay_resolution import pregnancy_overview_service
from Script.System.Pregnancy_System import family_tree_draw, pregnancy_constant

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """


def get_date_text(now_time: datetime.datetime) -> str:
    """
    将时间格式化为"X月X日"文本，月份用游戏的春夏秋冬月名（非四季月由 game_time.get_month_text 兜底归并）
    Keyword arguments:
    now_time -- 时间
    Return arguments:
    str -- 格式化文本
    """
    return pregnancy_constant.format_season_date(now_time)


class Pregnancy_Overview_Panel:
    """
    怀孕总览面板对象（总览页+生育谱系图页）
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.now_page: int = 0
        """ 当前页签（0总览，1生育谱系图） """
        self.tree_center_id: int = 0
        """ 谱系图当前的中心角色id（初始为玩家） """
        self.tree_page: int = 0
        """ 谱系图当前的家族分页页码（0起） """
        self.pending_remove_id: int = 0
        """ 异常女儿排查页里待二次确认移除的角色id（0为无） """

    def draw(self) -> None:
        """绘制对象"""
        title_draw = draw.TitleLineDraw(_("怀孕状态总览"), self.width)
        while 1:
            title_draw.draw()
            py_cmd.clr_cmd()
            return_list = []

            page_name_list = pregnancy_overview_service.page_names()
            if self.now_page >= len(page_name_list):
                self.now_page = 0
                self.pending_remove_id = 0
            for page_id in range(len(page_name_list)):
                if page_id == self.now_page:
                    now_draw: draw.CenterDraw | draw.CenterButton
                    now_draw = draw.CenterDraw()
                    now_draw.text = f"[{page_name_list[page_id]}]"
                    now_draw.style = "onbutton"
                    now_draw.width = int(self.width / len(page_name_list))
                    now_draw.draw()
                else:
                    now_draw = draw.CenterButton(
                        f"[{page_name_list[page_id]}]",
                        page_name_list[page_id],
                        int(self.width / len(page_name_list)),
                        cmd_func=self.change_page,
                        args=(page_id,),
                    )
                    now_draw.draw()
                    return_list.append(now_draw.return_text)
            line_feed.draw()
            line_draw = draw.LineDraw("+", self.width)
            line_draw.draw()

            if self.now_page == 0:
                return_list.extend(self.draw_overview_page())
            elif self.now_page == 1:
                return_list.extend(self.draw_family_tree_page())
            else:
                return_list.extend(self.draw_abnormal_daughter_page())

            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            line_feed.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def draw_overview_page(self) -> list:
        """
        绘制总览页（排序/筛选+干员阶段列表）
        Return arguments:
        list -- 监听的按钮返回文本列表
        """
        return_list = []

        info_draw = draw.NormalDraw()
        info_draw.text = _("排序方式：")
        info_draw.draw()
        sort_text = pregnancy_overview_service.sort_button_text(
            view.pregnancy_panel_sort_type
        )
        sort_draw = draw.LeftButton(
            sort_text,
            _("切换排序"),
            len(sort_text) * 2,
            cmd_func=self.change_sort_type,
        )
        sort_draw.draw()
        return_list.append(sort_draw.return_text)
        line_feed.draw()

        info_draw = draw.NormalDraw()
        info_draw.text = _("阶段筛选：")
        info_draw.draw()
        now_draw: draw.NormalDraw | draw.LeftButton
        for stage_id in range(len(pregnancy_constant.STAGE_NAME_LIST)):
            if stage_id == view.pregnancy_panel_filter_type:
                now_draw = draw.NormalDraw()
                now_draw.text = (
                    f"▶{pregnancy_constant.STAGE_NAME_LIST[stage_id]}  "
                )
                now_draw.style = "gold_enrod"
                now_draw.draw()
            else:
                draw_text = (
                    f"  {pregnancy_constant.STAGE_NAME_LIST[stage_id]}  "
                )
                now_draw = draw.LeftButton(
                    draw_text,
                    pregnancy_constant.STAGE_NAME_LIST[stage_id],
                    len(draw_text) * 2,
                    cmd_func=self.change_filter_type,
                    args=(stage_id,),
                )
                now_draw.draw()
                return_list.append(now_draw.return_text)
        line_feed.draw()
        line_feed.draw()

        chara_stage_list = pregnancy_overview_service.overview_rows(
            view.pregnancy_panel_filter_type, view.pregnancy_panel_sort_type
        )
        if not len(chara_stage_list):
            info_draw = draw.NormalDraw()
            info_draw.text = _("当前没有处于怀孕阶段的干员\n")
            info_draw.width = self.width
            info_draw.draw()
            return return_list

        for character_id, name, line_text in chara_stage_list:
            name_draw = draw.LeftButton(
                f"[{name}]",
                f"{character_id}_{name}",
                20,
                cmd_func=self.jump_to_tree,
                args=(character_id,),
            )
            name_draw.draw()
            return_list.append(name_draw.return_text)
            info_draw = draw.NormalDraw()
            info_draw.text = line_text
            info_draw.width = self.width - 20
            info_draw.draw()
            line_feed.draw()

        return return_list

    def draw_family_tree_page(self) -> list:
        """
        绘制生育谱系图页（带完整连线的传统家谱图：上1代+中心+下2代共4代，夫妇以╤相连并自其所在列
        经代间排版行连线到子女，玩家名按父本位置重复显示，超宽时按家族自动分页，点击角色换中心）
        Return arguments:
        list -- 监听的按钮返回文本列表
        """
        return_list = []
        reset_draw = draw.LeftButton(
            _("[重置回博士]"),
            _("重置回博士"),
            24,
            cmd_func=self.reset_tree_center,
        )
        reset_draw.draw()
        return_list.append(reset_draw.return_text)
        info_draw = draw.NormalDraw()
        info_draw.text = _(
            '　显示上{0}代+下{1}代共4代　夫妇以╤相连并连线到子女　玩家名按父本位置重复显示　超宽时按家族分页　"…"表示尚'
            "有成员/更深代数未显示　点击图中角色可以其为中心重绘\n"
        ).format(pregnancy_constant.UP_GEN, pregnancy_constant.DOWN_GEN)
        info_draw.draw()
        line_feed.draw()

        self.tree_center_id = pregnancy_overview_service.live_id(
            self.tree_center_id
        )

        window_width_int = int(self.width)
        chart_data = family_tree_draw.build_family_tree_chart(
            self.tree_center_id, window_width_int - 2, self.tree_page
        )
        self.tree_page = chart_data["now_page"]
        button_count = 0
        pad_width = max(0, (window_width_int - chart_data["width"]) // 2)
        for row_data in chart_data["rows"]:
            now_col = 0
            for cell in row_data["cells"]:
                target_col = pad_width + cell["col"]
                if target_col > now_col:
                    space_draw = draw.NormalDraw()
                    space_draw.text = " " * (target_col - now_col)
                    space_draw.draw()
                token = cell["token"]
                if token["type"] == "text":
                    text_draw = draw.NormalDraw()
                    text_draw.text = token["text"]
                    if "style" in token:
                        text_draw.style = token["style"]
                    text_draw.draw()
                elif token["is_center"]:
                    center_draw = draw.NormalDraw()
                    center_draw.text = token["text"]
                    center_draw.style = "gold_enrod"
                    center_draw.draw()
                else:
                    button_count += 1
                    button_draw = draw.LeftButton(
                        token["text"],
                        f"tree{button_count}_{token['text']}",
                        text_handle.get_text_index(token["text"]),
                        cmd_func=self.change_tree_center,
                        args=(token["chara_id"],),
                    )
                    button_draw.draw()
                    return_list.append(button_draw.return_text)
                now_col = target_col + text_handle.get_text_index(token["text"])
            line_feed.draw()

        if chart_data["total_page"] > 1:
            line_feed.draw()
            if chart_data["now_page"] > 0:
                prev_draw = draw.LeftButton(
                    _("[上一页]"),
                    _("谱系图上一页"),
                    12,
                    cmd_func=self.change_tree_page,
                    args=(-1,),
                )
                prev_draw.draw()
                return_list.append(prev_draw.return_text)
            page_info_draw = draw.NormalDraw()
            page_info_draw.text = _("　第{0}/{1}页　").format(
                chart_data["now_page"] + 1, chart_data["total_page"]
            )
            page_info_draw.draw()
            if chart_data["now_page"] < chart_data["total_page"] - 1:
                next_draw = draw.LeftButton(
                    _("[下一页]"),
                    _("谱系图下一页"),
                    12,
                    cmd_func=self.change_tree_page,
                    args=(1,),
                )
                next_draw.draw()
                return_list.append(next_draw.return_text)
            line_feed.draw()

        return return_list

    def change_page(self, page_id: int) -> None:
        """
        切换页签
        Keyword arguments:
        page_id -- 页签id
        """
        self.now_page = page_id

    def change_sort_type(self) -> None:
        """切换总览页的排序方向"""
        view.pregnancy_panel_sort_type = 1 - view.pregnancy_panel_sort_type

    def change_filter_type(self, stage_id: int) -> None:
        """
        切换总览页的阶段筛选
        Keyword arguments:
        stage_id -- 阶段枚举值（0为全部）
        """
        view.pregnancy_panel_filter_type = stage_id

    def jump_to_tree(self, character_id: int) -> None:
        """
        从总览页跳转到以某角色为中心的谱系图页
        Keyword arguments:
        character_id -- 角色id
        """
        self.tree_center_id = character_id
        self.tree_page = 0
        self.now_page = 1

    def change_tree_center(self, character_id: int) -> None:
        """
        以某角色为新中心重绘谱系图（页码重置）
        Keyword arguments:
        character_id -- 角色id
        """
        self.tree_center_id = character_id
        self.tree_page = 0

    def change_tree_page(self, delta: int) -> None:
        """
        谱系图家族分页翻页（下限钳位，上限由绘制时按总页数钳位）
        Keyword arguments:
        delta -- 页码增量（±1）
        """
        self.tree_page = max(0, self.tree_page + delta)

    def reset_tree_center(self) -> None:
        """谱系图中心重置回玩家"""
        self.tree_center_id = 0
        self.tree_page = 0

    def draw_abnormal_daughter_page(self) -> list:
        """
        绘制异常女儿排查页：列出因旧版本存档BUG误入本存档的女儿（不在博士血缘名单、也不出现在谱系图里），
        供玩家逐个确认后彻底移除
        Return arguments:
        list -- 监听的按钮返回文本列表
        """
        return_list = []
        self.pending_remove_id = pregnancy_overview_service.live_id(
            self.pending_remove_id
        )
        if self.pending_remove_id:
            confirm_draw = draw.NormalDraw()
            confirm_draw.text = pregnancy_overview_service.remove_confirm_text(
                self.pending_remove_id
            )
            confirm_draw.width = self.width
            confirm_draw.draw()
            line_feed.draw()
            yes_draw = draw.CenterButton(
                _("[确认移除]"),
                _("确认移除"),
                int(self.width / 2),
                cmd_func=self.do_remove_abnormal,
            )
            yes_draw.draw()
            return_list.append(yes_draw.return_text)
            no_draw = draw.CenterButton(
                _("[取消]"),
                _("取消移除"),
                int(self.width / 2),
                cmd_func=self.cancel_remove_abnormal,
            )
            no_draw.draw()
            return_list.append(no_draw.return_text)
            return return_list

        info_draw = draw.NormalDraw()
        info_draw.text = _(
            "　此处排查因旧版本存档BUG而误入本存档的女儿。\n"
            "　博士亲生的每个女儿都会登记进血缘名单；被标记为博士女儿、却不在名单中的，即为其他周目/存档误入的女儿，"
            "她们也不会出现在生育谱系图里。\n"
            "　请确认无误后再移除，移除不可撤销。\n"
        )
        info_draw.width = self.width
        info_draw.draw()
        line_feed.draw()

        count_draw = draw.NormalDraw()
        count_draw.text = pregnancy_overview_service.abnormal_count_text()
        count_draw.width = self.width
        count_draw.draw()
        line_feed.draw()

        abnormal_rows = pregnancy_overview_service.abnormal_rows()
        for character_id, line_text in abnormal_rows:
            remove_draw = draw.LeftButton(
                _("[去除]"),
                f"abnormal_remove_{character_id}",
                8,
                cmd_func=self.ask_remove_abnormal,
                args=(character_id,),
            )
            remove_draw.draw()
            return_list.append(remove_draw.return_text)
            info_draw = draw.NormalDraw()
            info_draw.text = line_text
            info_draw.width = self.width - 8
            info_draw.draw()

        return return_list

    def ask_remove_abnormal(self, character_id: int) -> None:
        """
        点击[去除]：记下待确认移除的女儿id，下次重绘时弹出二次确认
        Keyword arguments:
        character_id -- 角色id
        """
        self.pending_remove_id = character_id

    def do_remove_abnormal(self) -> None:
        """确认移除待处理的疑似误入女儿"""
        if self.pending_remove_id:
            self.tree_center_id = pregnancy_overview_service.remove_abnormal(
                self.pending_remove_id, self.tree_center_id
            )
        self.pending_remove_id = 0

    def cancel_remove_abnormal(self) -> None:
        """取消移除"""
        self.pending_remove_id = 0
