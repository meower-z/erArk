"""资源交易界面面板"""

from collections.abc import Callable
from types import FunctionType

from Script.Config import game_config, normal_config
from Script.Core import constant, flow_handle, get_text
from Script.Design import attr_calculation
from Script.Modules.domains import economy
from Script.Modules.gameplay_resolution import resource_exchange_service as svc
from Script.UI.Moudle import draw, view

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """
pad = attr_calculation.pad_display_width
""" 按显示宽度对齐文本的辅助函数别名。 """
SKY = "light_sky_blue"
""" 天蓝色高亮样式名称常量。 """
GOLD = "gold_enrod"
""" 金黄色警示与确认样式名称常量。 """


def _types() -> list[str]:
    """按调用时翻译结果返回六类可交易资源类型列表。"""
    return [_("材料"), _("药剂"), _("乳制品"), _("香水"), _("基建"), _("特产")]


def _action(quantity: int) -> str:
    """按交易数量正负返回买入、卖出或无的本地化词。"""
    if quantity > 0:
        return _("买入")
    return _("卖出") if quantity < 0 else _("无")


def _signed(percent: float, zero: str) -> str:
    """将价格波动百分比格式化为带符号标签，零值返回 zero。"""
    if percent > 0:
        return f"(+{percent:.1f}%)"
    if percent < 0:
        return f"({percent:.1f}%)"
    return zero


def draw_text(text: str, style: str = "", width: float = 0) -> None:
    """绘制单段普通文本，仅在指定样式名时设置样式。"""
    text_draw = draw.NormalDraw()
    text_draw.text = text
    text_draw.width = width
    if style:
        text_draw.style = style
    text_draw.draw()


def draw_button(
    keys: list[str],
    text: str,
    key: str,
    func: Callable[..., object] | None = None,
    args: object = (),
    width: float | None = None,
    **style: str,
) -> None:
    """绘制居中按钮并将返回键追加到 keys 列表。"""
    size = len(text) * 2 if width is None else width
    button = draw.CenterButton(
        text, key, size, cmd_func=func, args=args, **style
    )
    keys.append(button.return_text)
    button.draw()


def draw_back(keys: list[str], width: int) -> bool:
    """绘制返回按钮并等待输入，选中返回时返回真。"""
    draw_button(keys, _("[返回]"), _("返回"), width=width)
    line_feed.draw()
    return flow_handle.askfor_all(keys) == _("返回")


class Resource_Exchange_Line_Panel:
    """
    用于资源交易的面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.show_resource_type_dict: dict = dict.fromkeys(_types(), False)
        """ 显示的资源类型 """
        self.now_select_resouce_id = 11
        """ 当前选择的资源id，默认为11号资源（普通药材） """
        self.quantity_of_resouce = 0
        """ 交易数量，默认为0。正数代表买入，负数代表卖出 """

    def draw(self) -> None:
        """绘制对象"""
        title_draw = draw.TitleLineDraw(_("资源交易"), self.width)
        while True:
            line_feed.draw()
            keys: list[str] = []
            title_draw.draw()
            rid, qty = self.now_select_resouce_id, self.quantity_of_resouce
            quote = svc.quote(rid, qty)
            self._draw_assets(keys, quote)
            draw.LineDraw("-", window_width).draw()
            self._draw_traders(keys, quote)
            draw.LineDraw("-", window_width).draw()
            self._draw_budget(quote)
            draw.LineDraw("=", window_width).draw()
            self._draw_adjust(keys, quote)
            draw.LineDraw("=", window_width).draw()
            if draw_back(keys, self.width):
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def _draw_assets(self, keys: list[str], quote: svc.Quote) -> None:
        """绘制主界面的资产、库存与自动交易摘要区块。"""
        third = int(self.width / 3)
        draw_text(_("【 资产与库存 】\n"))
        line_feed.draw()
        draw_text(_("  当前龙门币 : {0}\n").format(quote.money))
        draw_text(pad(_("  交易资源   : {0}").format(quote.name), third))
        text = _(" [更改交易资源] ")
        func = self.select_exchange_resouce
        draw_button(
            keys, _(text), _("{0}").format(text), func, width=len(text) * 2
        )
        line_feed.draw()
        text = _("  库存状态   : 当前 {0} / 上限 {1}\n")
        full = GOLD if quote.stock >= quote.capacity else ""
        draw_text(text.format(quote.stock, quote.capacity), full)
        settings = economy.auto_trade(self.now_select_resouce_id)
        text = _("  自动交易   : ")
        if not quote.main_id:
            draw_text(pad(text + _("未任命主交易员无法设置"), third), GOLD)
            line_feed.draw()
            return
        if settings["buy_on"]:
            text += _("买入至 {0}% / ").format(settings["buy_price_percent"])
        else:
            text += _("未设置自动买入 / ")
        if settings["sell_on"]:
            text += _("卖出至 {0}%").format(settings["sell_price_percent"])
        else:
            text += _("未设置自动卖出")
        draw_text(pad(text, third))
        text = _(" [自动交易设置] ")
        args = (self.now_select_resouce_id,)
        draw_button(keys, text, text, self.auto_trade_setting, args)
        line_feed.draw()

    def _draw_traders(self, keys: list[str], quote: svc.Quote) -> None:
        """绘制主界面的交易员名单、基础加成与综合倍率区块。"""
        draw_text(pad(_("【 交易员与倍率分析 】"), int(self.width / 3)))
        text = _(" [交易员管理] ")
        draw_button(keys, text, text, self.manage_trade_operator)
        line_feed.draw()
        line_feed.draw()
        draw_text(_("  交易种类 : {0}").format(quote.kind))
        line_feed.draw()
        text = _("  主交易员 : {0} (基础加成: +{1:.1f}%)")
        if quote.main_name is None:
            draw_text(text.format(_("空缺"), quote.main_bonus * 100), "warning")
        else:
            draw_text(text.format(quote.main_name, quote.main_bonus * 100))
        line_feed.draw()
        text = _("  副交易员 : 共 {0} 人 (基础加成: +{1:.1f}%)\n")
        text = text.format(len(quote.sub_names), quote.sub_bonus * 100)
        if quote.sub_names:
            text += _("    - {0}\n").format(", ".join(quote.sub_names))
        else:
            text += _("    - 暂无\n")
        draw_text(text)
        line_feed.draw()
        text = _("  综合倍率 : 买入 {0:+.1f}% / 卖出 {1:+.1f}%\n")
        draw_text(text.format(quote.buy_percent, quote.sell_percent))

    def _draw_budget(self, quote: svc.Quote) -> None:
        """绘制主界面的交易数量、单价、总价与余额警示区块。"""
        qty, total, money = abs(quote.quantity), quote.total, quote.money
        draw_text(_("【 交易详情与预算 】"))
        line_feed.draw()
        line_feed.draw()
        draw_text(_("  当前交易数量 : "))
        draw_text(_("{0} {1}\n").format(_action(quote.quantity), qty), SKY)
        draw_text(_("  预计库存变化 : "))
        sign = "+" if quote.quantity >= 0 else "-"
        after = quote.stock + quote.quantity
        text = _("{0} {1} {2}  =>  {3} / {4}\n\n")
        draw_text(text.format(quote.stock, sign, qty, after, quote.capacity))
        text = _("  买入价: {0} 龙门币 {1}")
        buy = _signed(quote.buy_percent, "(0%)")
        style = SKY if quote.quantity > 0 else ""
        draw_text(text.format(quote.buy_price, buy), style)
        draw_text(_("  |  "))
        text = _("卖出价: {0} 龙门币 {1}\n")
        sell = _signed(quote.sell_percent, "(0%)")
        style = SKY if quote.quantity < 0 else ""
        draw_text(text.format(quote.sell_price, sell), style)
        if quote.quantity:
            if quote.quantity > 0:
                draw_text(_("  预计买入总价: "))
                price = quote.buy_price
            else:
                draw_text(_("  预计卖出总价: "))
                price = quote.sell_price
            draw_text(_("{0} * {1} = ").format(price, qty, total))
            draw_text(_("{2} 龙门币").format(price, qty, total), SKY)
        else:
            draw_text(_("  预计交易总价: "))
            draw_text(_("0 * 0 = "))
            draw_text(_("0 龙门币"), SKY)
        line_feed.draw()
        draw_text(_("  交易后剩余龙门币: "))
        left = quote.money_left
        if quote.quantity > 0:
            text = _("{0} - {1} = {2} 龙门币").format(money, total, left)
        elif quote.quantity < 0:
            text = _("{0} + {1} = {2} 龙门币").format(money, total, left)
        else:
            text = _("{0} - 0 = {1} 龙门币").format(money, money)
        draw_text(text)
        line_feed.draw()
        text = ""
        if quote.quantity > 0 and total > money:
            text += _("  ●龙门币不足，无法以当前数量买入")
        if quote.cant_buy:
            text += _("  ●该资源无法购买，只能卖出")
        draw_text(text, GOLD)
        line_feed.draw()

    def _draw_adjust(self, keys: list[str], quote: svc.Quote) -> None:
        """绘制主界面的最大买卖、步进、重置与确认交易按钮区块。"""
        wide, small = self.width / 3 - 3, self.width / 12
        draw_text(_("【 数量调节 】\n  "))
        line_feed.draw()
        text = _("[ ==================== 最大卖出 =================== ] ")
        draw_button(keys, text, _("最大卖出"), self.settle_max_sell, width=wide)
        text = _("    {0} {1}")
        text = text.format(_action(quote.quantity), abs(quote.quantity))
        draw_text(pad(text, int(small)), SKY)
        text = _("  [ =================== 最大买入 =================== ] ")
        draw_button(keys, text, _("最大买入"), self.settle_max_buy, width=wide)
        line_feed.draw()
        line_feed.draw()
        for label in (" [ -1000 ] ", " [ -100 ] ", " [ -10 ] ", " [ -1 ] "):
            self._step_button(keys, label)
        text = _(" [ 重   置 ] ")
        func = self.reset_quantity
        draw_button(keys, _(text), _("{0}").format(text), func, width=small)
        for label in (" [ +1 ] ", " [ +10 ] ", " [ +100 ] ", " [ +1000 ] "):
            self._step_button(keys, label)
        line_feed.draw()
        line_feed.draw()
        if quote.confirm:
            if quote.quantity > 0:
                text, key = _("[确认买入]"), _("确认买入")
            else:
                text, key = _("[确认卖出]"), _("确认卖出")
            func = self.execute_trade
            draw_button(
                keys, text, key, func, width=self.width, normal_style=GOLD
            )
        line_feed.draw()

    def _step_button(self, keys: list[str], label: str) -> None:
        """绘制单个带符号数量步进按钮。"""
        func, width = self.settle_quantity, self.width / 12
        draw_button(
            keys, _(label), _("{0}").format(label), func, (label,), width
        )

    def execute_trade(self) -> None:
        """
        执行资源交易
        输入: 无
        输出: 无
        功能: 根据当前买入/卖出状态和数量，结算资源与龙门币变动
        """
        deal = svc.trade(self.now_select_resouce_id, self.quantity_of_resouce)
        if deal is None:
            return
        info_draw = draw.WaitDraw()
        info_draw.text = deal.text
        info_draw.draw()
        line_feed.draw()
        if deal.done:
            self.quantity_of_resouce = 0

    def manage_trade_operator(self) -> None:
        """交易员管理界面"""
        from Script.UI.Panel import trade_setting_panel

        trade_setting_panel.manage_traders(self.width)

    def auto_trade_setting(self, res_id: int) -> None:
        """调整一种资源的自动交易设置"""
        from Script.UI.Panel import trade_setting_panel

        trade_setting_panel.auto_trade_setting(self.width, res_id)

    def select_exchange_resouce(self) -> None:
        """选择交易资源"""
        while True:
            draw.LineDraw("-", window_width).draw()
            line_feed.draw()
            keys: list[str] = []
            name = game_config.config_resouce[self.now_select_resouce_id].name
            text = _("当前的交易资源为：{0}").format(name)
            draw_text(
                text + _("\n当前可以交易的资源有：\n"), width=window_width
            )
            line_feed.draw()
            types = _types()
            for res_type in types:
                shown = self.show_resource_type_dict[res_type]
                text = f" {'▼' if shown else '▶'}[{res_type}]"
                func = self.settle_show_resource_type
                button = draw.LeftButton(
                    text,
                    res_type,
                    len(text) * 2,
                    cmd_func=func,
                    args=(res_type),
                )
                button.draw()
                keys.append(button.return_text)
                line_feed.draw()
                if shown:
                    self._draw_listings(keys, res_type)
            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            line_feed.draw()
            keys.append(back_draw.return_text)
            choice = flow_handle.askfor_all(keys)
            if choice in keys and choice not in types:
                break

    def _draw_listings(self, keys: list[str], res_type: str) -> None:
        """绘制资源选择页中指定类型下各资源的按钮与价格行。"""
        func = self.settle_now_select_resouce_id
        for item in svc.listings(res_type):
            rid = item.resource_id
            text = f" [{str(rid).rjust(3,'0')}]{item.name}：{item.info}"
            button = draw.LeftButton(
                text, f"\n{rid}", window_width, cmd_func=func, args=(rid)
            )
            button.draw()
            keys.append(button.return_text)
            text = _("\n      当前存量：{0}/{1}")
            text = text.format(item.stock, item.capacity)
            if item.buy is not None:
                price, percent = item.buy
                line = _("   买入:{0}龙门币/1单位 {1}")
                text += line.format(price, _signed(percent, "(0%)"))
            price, percent = item.sell
            line = _("   卖出:{0}龙门币/1单位 {1}\n")
            text += line.format(price, _signed(percent, ""))
            draw_text(text, width=window_width)

    def settle_now_select_resouce_id(self, resouce_id: int) -> None:
        """结算要交易的资源"""
        self.now_select_resouce_id = resouce_id

    def settle_quantity(self, button_text: str) -> None:
        """结算交易数量变更"""
        rid, qty = self.now_select_resouce_id, self.quantity_of_resouce
        self.quantity_of_resouce = svc.step(rid, qty, int(button_text[2:-2]))

    def settle_max_buy(self) -> None:
        """结算最大买入数量"""
        rid, qty = self.now_select_resouce_id, self.quantity_of_resouce
        self.quantity_of_resouce = svc.max_buy(rid, qty)

    def settle_max_sell(self) -> None:
        """结算最大卖出数量"""
        self.quantity_of_resouce = svc.max_sell(self.now_select_resouce_id)

    def reset_quantity(self) -> None:
        """重置资源交易数量"""
        self.quantity_of_resouce = 0

    def settle_show_resource_type(self, resouce_type: str) -> None:
        """设置显示的资源类型"""
        shown = self.show_resource_type_dict[resouce_type]
        self.show_resource_type_dict[resouce_type] = not shown
