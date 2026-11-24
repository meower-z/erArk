"""基地载具管理界面面板 Manage_Vehicle_Panel"""

from collections.abc import Callable
from types import FunctionType
from Script.Core import get_text, flow_handle, constant
from Script.UI.Moudle import draw, view
from Script.Config import game_config, normal_config
from Script.Modules.gameplay_resolution import vehicle_service

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """


def _text(
    text: str,
    width: int,
    style: str = "standard",
    kind: type[draw.NormalDraw] = draw.NormalDraw,
) -> None:
    """按指定文本、宽度、样式与绘制类创建并绘制单个文本对象。"""
    now_draw = kind()
    now_draw.text = text
    now_draw.style = style
    now_draw.width = width
    now_draw.draw()


def _button(
    text: str,
    return_text: str,
    width: int,
    ret: list[str],
    cmd_func: Callable[..., object] | None = None,
    args: tuple = (),
    kind: type[draw.CenterButton] = draw.CenterButton,
) -> draw.CenterButton:
    """创建并绘制按钮，将其返回文本追加到选项列表并返回该按钮对象。"""
    now_draw = kind(text, return_text, width, cmd_func=cmd_func, args=args)
    now_draw.draw()
    ret.append(now_draw.return_text)
    return now_draw


def _choices(
    options: list[str],
    chosen: str,
    width: int,
    cmd_func: Callable[[str], None],
    ret: list[str],
) -> None:
    """等宽绘制一行选项按钮，高亮当前选中项并在行尾换行。"""
    each = int(width / len(options))
    for option in options:
        if option == chosen:
            _text(f"[{option}]", each, "onbutton", draw.CenterDraw)
        else:
            _button(
                f"[{option}]", f"\n{option}", each, ret, cmd_func, (option,)
            )
    line_feed.draw()


class Manage_Vehicle_Panel:
    """
    用于显示载具管理界面面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.now_panel = _("常规载具")
        """ 当前绘制的页面 """
        self.draw_list: list[draw.NormalDraw] = []
        """ 绘制的文本列表 """
        self.send_npc_list: list[int] = []
        """ 派遣人员列表 """
        self.vehicle_count = 0
        """ 当前拥有载具数量 """
        self.sort_by = _("默认")
        """ 当前排序条件名称 """
        self.is_ascending = True
        """ 列表是否按升序排列 """
        self.current_page = 1
        """ 当前载具列表页码 """
        self.items_per_page = 10
        """ 每页显示的载具条数 """

    def change_sort_by(self, sort_by_type: str) -> None:
        """
        切换载具列表的排序条件，并回到第一页
        Keyword arguments:
        sort_by_type -- 排序条件名称
        """
        self.sort_by = sort_by_type
        self.current_page = 1

    def change_sort_order(self) -> None:
        """切换载具列表的升序与降序，并回到第一页"""
        self.is_ascending = not self.is_ascending
        self.current_page = 1

    def change_page(self, target_page: int) -> None:
        """
        切换载具列表当前所在的页数
        Keyword arguments:
        target_page -- 目标页数
        """
        self.current_page = target_page

    def draw(self) -> None:
        """绘制对象"""
        from Script.Design import attr_calculation

        w = self.width
        title_draw = draw.TitleLineDraw(_("载具管理"), w)
        while 1:
            ret: list[str] = []
            title_draw.draw()
            panels = [_("常规载具"), _("特殊载具")]
            _choices(panels, self.now_panel, w, self.change_panel, ret)
            draw.LineDraw("+", w).draw()
            status = vehicle_service.hangar_status()
            self.vehicle_count = status.owned
            _text(vehicle_service.hangar_text(status), w)
            draw.LineDraw("+", w).draw()
            sorts = [_("默认"), _("持有量"), _("价钱"), _("速度"), _("运载量")]
            _choices(sorts, self.sort_by, w, self.change_sort_by, ret)
            order = (
                _("当前排序：升序")
                if self.is_ascending
                else _("当前排序：降序")
            )
            flip = self.change_sort_order
            _button(f"[{order}]", _("\n点击切换升降序"), w, ret, flip)
            line_feed.draw()
            draw.LineDraw("+", w).draw()
            headers = [_("载具名称"), _("外勤中数量/总持有量"), _(" 价钱")]
            headers += [_(" 载具速度"), _(" 运载量"), _(" 特殊效果(未实装)")]
            cell = int((w) / (len(headers)))
            for header in headers:
                _text(header, cell, kind=draw.CenterDraw)
            line_feed.draw()
            draw.LineDraw("~", w).draw()
            rows = vehicle_service.listed_vehicles(
                self.now_panel, self.sort_by, self.is_ascending
            )
            page = vehicle_service.page_of(
                rows, self.current_page, self.items_per_page
            )
            self.current_page = page.page
            for row in page.rows:
                padded = [
                    attr_calculation.pad_display_width(text, cell, "center")
                    for text in vehicle_service.row_cells(row)
                ]
                info, args = self.vehicle_info, (row.cid,)
                text = "".join(padded)
                kind = draw.LeftButton
                _button(text, "\n" + padded[0], w, ret, info, args, kind)
                line_feed.draw()
            for _i in range(self.items_per_page - len(page.rows)):
                line_feed.draw()
            draw.LineDraw("-", w).draw()
            page_text = _(" 第 {0} / {1} 页 ").format(page.page, page.total)
            go, third = self.change_page, int(w / 3)
            if page.total == 1:
                _text(page_text, w, kind=draw.CenterDraw)
            else:
                _button(
                    _("[上一页]"), _("\n上一页"), third, ret, go, (page.prev,)
                )
                _text(page_text, third, kind=draw.CenterDraw)
                _button(
                    _("[下一页]"), _("\n下一页"), third, ret, go, (page.next,)
                )
            line_feed.draw()
            draw.LineDraw("-", w).draw()
            line_feed.draw()
            back_draw = _button(_("[返回]"), _("返回"), window_width, ret)
            yrn = flow_handle.askfor_all(ret)
            if yrn == back_draw.return_text:
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def change_panel(self, building_type: str) -> None:
        """
        切换当前面板显示
        Keyword arguments:
        building_type -- 要切换的面板类型
        """

        self.now_panel = building_type

    def vehicle_info(self, vehicle_id: int) -> None:
        """
        显示载具详细信息
        Keyword arguments:
        vehicle_id -- 载具编号
        """
        w, args = self.width, (vehicle_id,)
        while 1:
            ret: list[str] = []
            draw.TitleLineDraw(_("载具购买"), w).draw()
            trade = vehicle_service.trade_status(vehicle_id, self.vehicle_count)
            _text(vehicle_service.detail_text(vehicle_id, trade), w)
            left = _(" 购买后剩余龙门币数量：{0}").format(trade.money_left)
            _text(left, 0, "warning" if trade.money_left < 0 else "standard")
            line_feed.draw()
            space = _(" 当前剩余载具空间：{0}").format(trade.space_left)
            _text(space, 0, "warning" if trade.space_left <= 0 else "standard")
            line_feed.draw()
            line_feed.draw()
            draw.LineDraw("-", w).draw()
            third = int(w / 3)
            buy, sell = _("【购买载具】"), _("【出售载具】")
            if trade.can_buy:
                back = _("\n【购买载具】")
                _button(buy, back, third, ret, self.buy_vehicle, args)
            else:
                _text(buy, third, "deep_gray", draw.CenterDraw)
            if trade.can_sell:
                back = _("\n【出售载具】")
                _button(sell, back, third, ret, self.sell_vehicle, args)
            else:
                _text(sell, third, "deep_gray", draw.CenterDraw)
            line_feed.draw()
            line_feed.draw()
            back_draw = _button(_("[返回]"), _("返回"), third * 2, ret)
            yrn = flow_handle.askfor_all(ret)
            if yrn == back_draw.return_text:
                break

    def buy_vehicle(self, vehicle_id: int) -> None:
        """
        购买载具
        Keyword arguments:
        vehicle_id -- 载具编号
        """
        from Script.UI.Panel import achievement_panel

        vehicle_data = game_config.config_vehicle[vehicle_id]
        info_draw = draw.WaitDraw()
        info_draw.width = window_width
        if vehicle_service.buy_vehicle(vehicle_id):
            self.vehicle_count += 1
            info_draw.text = _("\n花费 {0} 龙门币购买了一个 {1}\n").format(
                vehicle_data.price, vehicle_data.name
            )
        else:
            info_draw.text = _("\n资金不足，无法购买\n")
            info_draw.style = "red"
        info_draw.draw()
        achievement_panel.achievement_flow(_("载具"))

    def sell_vehicle(self, vehicle_id: int) -> None:
        """
        出售载具
        Keyword arguments:
        vehicle_id -- 载具编号
        """
        price = vehicle_service.sell_vehicle(vehicle_id)
        self.vehicle_count -= 1
        info_draw = draw.WaitDraw()
        info_draw.width = window_width
        info_draw.text = _("\n出售了一个 {0}，获得了 {1} 龙门币\n").format(
            game_config.config_vehicle[vehicle_id].name, price
        )
        info_draw.draw()
