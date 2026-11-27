"""
制作食物面板（make_food_panel）
===============================
绘制制作食物、泡咖啡与调酒的主菜单及筛选排序界面，并分发玩家输入。
"""

from collections.abc import Callable, Container, Iterable
from types import FunctionType
from Script.Core import get_text, flow_handle, constant, py_cmd
from Script.Modules.gameplay_resolution import make_food_service as service
from Script.System.Cooking_System import cooking
from Script.UI.Panel.make_food_confirm_panel import (
    SeeFoodListByFoodNameDraw,
    add_button,
    draw_quality,
    draw_text,
    line_feed,
    window_width,
)
from Script.UI.Moudle import draw, panel, view
from Script.Config import game_config

_: FunctionType = get_text._
""" 翻译api """
MARKED = ("[●{0}]", "[{0}]")
""" 单选按钮在选中与未选中状态下的文本格式模板。 """


def option_row(
    return_list: list[str],
    options: Iterable[tuple[int, str]],
    chosen: Container[int],
    marks: tuple[str, str],
    key: str,
    width: int,
    cmd_func: Callable[[int], None],
) -> None:
    """按给定选项绘制一行单选或切换按钮，并把按钮返回码追加到列表。"""
    for option_id, name in options:
        text = marks[0 if option_id in chosen else 1].format(name)
        add_button(
            return_list,
            text,
            f"{key}_{option_id}",
            width,
            cmd_func=cmd_func,
            args=(option_id,),
        )


def current_filter() -> service.ListFilter:
    """读取界面筛选与排序状态并构造 ListFilter 对象。"""
    return service.ListFilter(
        tuple(view.makefood_filter_type),
        view.makefood_filter_difficulty,
        view.makefood_filter_time,
        view.makefood_sort_type,
        view.makefood_sort_order,
    )


class Make_food_Panel:
    """
    用于查看制作食物界面面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int, make_food_type: int = 0) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.now_panel = _("主食")
        """ 当前绘制的食物类型 """
        self.handle_panel: panel.PageHandlePanel
        """ 当前名字列表控制面板make_food_type """
        self.make_food_type = make_food_type
        """ 0普通做饭，1泡咖啡，2酒类 """
        self.special_seasoning = 0
        """ 调味类型 """
        service.check_cook_mode(make_food_type)

    @property
    def cook_mode(self) -> int:
        """通过服务读取当前制作入口的烹饪模式设置。"""
        return service.cook_mode(self.make_food_type)

    @cook_mode.setter
    def cook_mode(self, cook_mode: int) -> None:
        """通过服务保存当前制作入口的烹饪模式设置。"""
        service.set_cook_mode(self.make_food_type, cook_mode)

    def draw(self) -> None:
        """绘制对象"""
        title_draw = draw.TitleLineDraw(_("制作食物"), self.width)
        food_type_list = [_("主食"), _("零食"), _("饮品"), _("酒类")]
        if self.make_food_type == 1:
            food_type_list = [_("咖啡")]
            self.now_panel = _("咖啡")
        elif self.make_food_type == 2:
            food_type_list = [_("酒类")]
            self.now_panel = _("酒类")
        self.handle_panel = panel.PageHandlePanel(
            [], SeeFoodListByFoodNameDraw, 50, 5, self.width, True, True, 0
        )
        while 1:
            view.makefood_data = cooking.build_makefood_data()
            py_cmd.clr_cmd()
            title_draw.draw()
            return_list: list[str] = []
            self.draw_tabs(food_type_list, return_list)
            self.draw_list_options(return_list)
            self.draw_seasonings(return_list)
            self.draw_cook_modes(return_list)
            draw_text(_("○选择要制作的食物：\n"))
            draw.LineDraw("-", self.width).draw()
            self.handle_panel.text_list = self.food_button_texts()
            self.handle_panel.update()
            self.handle_panel.draw()
            draw.LineDraw("-", self.width).draw()
            return_list.extend(self.handle_panel.return_list)
            line_feed.draw()
            back = add_button(return_list, _("[返回]"), _("返回"), window_width)
            line_feed.draw()
            SeeFoodListByFoodNameDraw.last_confirm_result = ""
            yrn = flow_handle.askfor_all(return_list)
            chosen = yrn in self.handle_panel.return_list
            result = SeeFoodListByFoodNameDraw.last_confirm_result
            if chosen and result == _("取消"):
                continue
            if yrn == back or (chosen and result == _("确认")):
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def draw_tabs(self, food_types: list[str], return_list: list[str]) -> None:
        """绘制食物分类页签栏，高亮当前页签并在下方画分隔线。"""
        width = int(self.width / len(food_types))
        for food_type in food_types:
            if food_type != self.now_panel:
                add_button(
                    return_list,
                    f"[{food_type}]",
                    food_type,
                    width,
                    cmd_func=self.change_panel,
                    args=(food_type,),
                )
                continue
            now_draw = draw.CenterDraw()
            now_draw.text = f"[{food_type}]"
            now_draw.style = "onbutton"
            now_draw.width = width
            now_draw.draw()
        line_feed.draw()
        draw.LineDraw("+", self.width).draw()

    def draw_list_options(self, return_list: list[str]) -> None:
        """绘制筛选状态入口、重置按钮以及排序维度与排序顺序按钮行。"""
        draw_text(_("○筛选：\n"))
        filter_text, __ = service.status_text(current_filter())
        draw_text("  ")
        filter_button = draw.LeftButton(
            f"[{filter_text}]",
            _("[筛选]"),
            int(self.width),
            cmd_func=self.open_filter_panel,
        )
        filter_button.draw()
        return_list.append(filter_button.return_text)
        line_feed.draw()
        draw_text("  ")
        add_button(
            return_list,
            _("[重置]"),
            _("重置所有"),
            int(self.width / 16),
            cmd_func=self.clear_filter_and_sort,
        )
        line_feed.draw()
        width = int(self.width / 6)
        draw_text(_("○排序维度："))
        option_row(
            return_list,
            service.sort_type_labels(),
            {view.makefood_sort_type},
            MARKED,
            "sort_type",
            width,
            self.set_sort_type,
        )
        line_feed.draw()
        draw_text(_("○排序顺序："))
        option_row(
            return_list,
            service.sort_order_labels(),
            {view.makefood_sort_order},
            MARKED,
            "sort_order",
            width,
            self.set_sort_order,
        )
        line_feed.draw()

    def draw_seasonings(self, return_list: list[str]) -> None:
        """绘制精液与药物两类可选调味按钮，并高亮当前选中的调味。"""
        draw_text(_("○当前的调味："))
        button_width = int(self.width / 4)
        for seasoning_cid, seasoning in game_config.config_seasoning.items():
            if seasoning_cid <= 10:
                continue
            if seasoning_cid == 11:
                draw_text(_("\n  精液:    "))
            elif seasoning_cid == 102:
                button_width = int(self.width / 8 + 1)
                draw_text(_("\n  药物:    "))
            if not service.seasoning_listed(seasoning_cid):
                continue
            button_style = "standard"
            if self.special_seasoning == seasoning_cid:
                button_style = "gold_enrod"
            button_text = f"[{seasoning.name}]"
            button_draw = draw.CenterButton(
                _(button_text),
                _(button_text),
                button_width,
                normal_style=button_style,
                cmd_func=self.choice_seasoning,
                args=(seasoning_cid,),
            )
            return_list.append(button_draw.return_text)
            button_draw.draw()
        line_feed.draw()

    def draw_cook_modes(self, return_list: list[str]) -> None:
        """绘制标准与精细两种烹饪模式说明按钮，以及主面板品质预测。"""
        width = int(self.width / 6 + 1)
        draw_text(_("○烹饪模式：\n"))
        self.mode_button(0, _("[标准模式]"), _("标准模式"), width, return_list)
        draw_text(
            _(
                "：不考虑细节直接烹饪，烹饪出的食物品质与料理技能相关，品质上限为美味，无法达到绝珍的级别\n"
            )
        )
        self.mode_button(1, _("[精细模式]"), _("精细模式"), width, return_list)
        draw_text(
            _(
                "：仔细考虑烹饪细节，根据细节的处理方式，食物品质能在料理技能的基础上进一步提升，最高可达到绝珍的级别\n"
            )
        )
        draw_text(_("○品质预测："))
        draw_quality(*service.panel_quality(self.cook_mode))
        line_feed.draw()
        line_feed.draw()

    def mode_button(
        self,
        mode: int,
        text: str,
        return_text: str,
        width: int,
        return_list: list[str],
    ) -> None:
        """绘制单个烹饪模式项，选中时高亮显示，未选中时绘制切换按钮。"""
        if self.cook_mode != mode:
            add_button(
                return_list,
                text,
                return_text,
                width,
                cmd_func=self.change_cook_mode,
                args=(mode,),
            )
            return
        now_draw = draw.CenterDraw()
        now_draw.text = text
        now_draw.style = "gold_enrod"
        now_draw.width = width
        now_draw.draw()

    def change_panel(self, food_type: str) -> None:
        """
        切换当前面板显示的食物类型
        Keyword arguments:
        food_type -- 要切换的食物类型
        """
        self.now_panel = food_type
        self.handle_panel = panel.PageHandlePanel(
            self.food_button_texts(),
            SeeFoodListByFoodNameDraw,
            50,
            5,
            self.width,
            True,
            True,
            0,
        )

    def food_button_texts(self) -> list[service.ButtonRow]:
        """调用服务获取当前页签经筛选、排序并补齐整页后的菜谱按钮行。"""
        return service.button_rows(
            view.makefood_data,
            self.now_panel,
            current_filter(),
            self.special_seasoning,
            self.cook_mode,
            self.make_food_type,
        )

    def choice_seasoning(self, seasoning_cid: int) -> None:
        """选择味道"""
        if self.special_seasoning == seasoning_cid:
            self.special_seasoning = 0
        else:
            self.special_seasoning = seasoning_cid

    def change_cook_mode(self, cook_mode: int) -> None:
        """
        切换烹饪模式
        Keyword arguments:
        cook_mode -- 烹饪模式：0标准，1精细
        """
        self.cook_mode = cook_mode

    def open_filter_panel(self) -> None:
        """
        打开筛选设置面板
        """
        type_names = service.type_labels()
        difficulty_options = [(-1, _("不限")), *service.difficulty_labels()]
        time_options = [(-1, _("不限")), *service.time_labels()]
        width = int(self.width / 10)
        while 1:
            py_cmd.clr_cmd()
            return_list: list[str] = []
            draw.TitleLineDraw(_("筛选设置"), self.width).draw()
            draw_text(_("○类型筛选（点击切换）：\n"))
            option_row(
                return_list,
                type_names.items(),
                view.makefood_filter_type,
                ("[√{0}]", "[{0}]"),
                "type",
                width,
                self.toggle_filter_type,
            )
            line_feed.draw()
            line_feed.draw()
            draw_text(_("○难度筛选：\n"))
            option_row(
                return_list,
                difficulty_options,
                {view.makefood_filter_difficulty},
                MARKED,
                "diff",
                width,
                self.set_filter_difficulty,
            )
            line_feed.draw()
            line_feed.draw()
            draw_text(_("○时间筛选：\n"))
            option_row(
                return_list,
                time_options,
                {view.makefood_filter_time},
                ("[● {0}]", "[  {0}]"),
                "time",
                width,
                self.set_filter_time,
            )
            line_feed.draw()
            line_feed.draw()
            half = int(self.width / 2)
            clear = add_button(
                return_list, _("[清除所有筛选]"), _("清除筛选"), half
            )
            back = add_button(return_list, _("[返回]"), _("返回"), half)
            line_feed.draw()
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back:
                break
            if yrn == clear:
                self.clear_filter()

    def toggle_filter_type(self, type_id: int) -> None:
        """切换类型筛选"""
        if type_id in view.makefood_filter_type:
            view.makefood_filter_type.remove(type_id)
        else:
            view.makefood_filter_type.append(type_id)

    def set_filter_difficulty(self, difficulty: int) -> None:
        """设置难度筛选"""
        view.makefood_filter_difficulty = difficulty

    def set_filter_time(self, time_level: int) -> None:
        """设置时间筛选"""
        view.makefood_filter_time = time_level

    def clear_filter(self) -> None:
        """清除所有筛选"""
        view.makefood_filter_type = []
        view.makefood_filter_difficulty = -1
        view.makefood_filter_time = -1

    def clear_filter_and_sort(self) -> None:
        """清除筛选和排序"""
        self.clear_filter()
        view.makefood_sort_type = 0
        view.makefood_sort_order = 0

    def open_sort_panel(self) -> None:
        """
        打开排序设置面板
        """
        sort_type_options = [
            (0, _("无")),
            (1, _("按难度")),
            (2, _("按时间")),
            (3, _("按类型")),
        ]
        width = int(self.width / 10)
        while 1:
            py_cmd.clr_cmd()
            return_list: list[str] = []
            draw.TitleLineDraw(_("排序设置"), self.width).draw()
            draw_text(_("○排序维度：\n"))
            option_row(
                return_list,
                sort_type_options,
                {view.makefood_sort_type},
                MARKED,
                "sort",
                width,
                self.set_sort_type,
            )
            line_feed.draw()
            line_feed.draw()
            draw_text(_("○排序顺序：\n"))
            option_row(
                return_list,
                service.sort_order_labels(),
                {view.makefood_sort_order},
                MARKED,
                "order",
                width,
                self.set_sort_order,
            )
            line_feed.draw()
            line_feed.draw()
            back = add_button(return_list, _("[返回]"), _("返回"), self.width)
            line_feed.draw()
            if flow_handle.askfor_all(return_list) == back:
                break

    def set_sort_type(self, sort_type: int) -> None:
        """设置排序维度"""
        view.makefood_sort_type = sort_type

    def set_sort_order(self, sort_order: int) -> None:
        """设置排序顺序"""
        view.makefood_sort_order = sort_order
