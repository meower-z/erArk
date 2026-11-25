"""
资源交易设置子面板（trade_setting_panel）
=========================================
本模块绘制交易员管理、主交易员任命与自动交易设置三个子界面。
模块承担这三个子界面的布局、按钮回调绑定与输入循环。
"""

from types import FunctionType

from Script.Config import game_config
from Script.Core import flow_handle, get_text
from Script.Modules.domains import economy, warehouse
from Script.Modules.gameplay_resolution import resource_exchange_service as svc
from Script.UI.Moudle import draw
from Script.UI.Panel.resource_exchange_panel import (
    draw_back,
    draw_button,
    draw_text,
    line_feed,
    pad,
    window_width,
)

_: FunctionType = get_text._
""" 翻译api """
STOCK_STEPS = (-1000, -100, -10, -1, 1, 10, 100, 1000)
""" 自动交易目标库存调整按钮的步长元组。 """
PRICE_STEPS = (-20, -5, -1, 1, 5, 20)
""" 自动交易触发价格百分比调整按钮的步长元组。 """


def manage_traders(width: int) -> None:
    """
    绘制交易员管理子界面，处理交易员增减与主交易员任命清空。
    Keyword arguments:
    width -- int，面板绘制宽度
    Return arguments:
    None -- 无返回值
    """
    from Script.Design import basement
    from Script.UI.Panel import manage_basement_panel

    while True:
        basement.update_work_people()
        draw.TitleLineDraw(_("交易员管理"), width).draw()
        keys: list[str] = []
        roster = svc.roster()
        draw_text(_("当前交易相关干员数量：{0}").format(roster.count))
        line_feed.draw()
        adjust_text = _("[交易员增减]")
        draw_button(
            keys,
            adjust_text,
            adjust_text,
            manage_basement_panel.change_npc_work_out,
            (width, [111]),
        )
        line_feed.draw()
        line_feed.draw()
        for res_type, main_name in roster.rows:
            res_type_name = pad(res_type, 8, align="center")
            draw_text(_("{0} 主交易员：{1}").format(res_type_name, main_name))
            args = (res_type,)
            assign = f"assign_{res_type}"
            draw_button(keys, _("[任命]"), assign, assign_main_trader, args)
            clear = f"clear_{res_type}"
            draw_button(keys, _("[清空]"), clear, svc.clear_main_trader, args)
            line_feed.draw()
        line_feed.draw()
        if roster.others:
            names = [
                _("{chara_name}(话术lv{abi_lv})").format(
                    chara_name=name, abi_lv=level
                )
                for name, level in roster.others
            ]
            draw_text(_("副交易员：") + "、".join(names) + "\n")
        else:
            draw_text(_("副交易员：暂无\n"))
        line_feed.draw()
        if draw_back(keys, width):
            break


def assign_main_trader(res_type: str) -> None:
    """
    绘制主交易员选人子界面，供玩家为指定资源类型切换主交易员。
    Keyword arguments:
    res_type -- str，资源类型名称
    Return arguments:
    None -- 无返回值
    """
    from Script.Design import basement
    from Script.UI.Panel import common_select_NPC
    from Script.UI.Moudle import panel

    basement.update_work_people()
    current_main = economy.main_trader(res_type)

    def _make(chara_id: int) -> None:
        """切换指定资源类型主交易员的选人按钮回调。"""
        svc.toggle_main_trader(res_type, chara_id)

    npc_panel: panel.PageHandlePanel = panel.PageHandlePanel(
        [],
        common_select_NPC.CommonSelectNPCButtonList,
        50,
        5,
        window_width,
        True,
        False,
        0,
    )
    select_state: dict[str, int | str] = {}
    while True:
        info_text = _("请选择一名交易员担任【{0}】的主交易员：\n").format(
            _(res_type)
        )
        candidate_list = [
            [npc_id, _make, [current_main]] for npc_id in svc.candidates()
        ]
        if not candidate_list:
            info_text += _(
                "当前没有可任命的交易员，请先安排干员担任贸易相关工作。\n"
            )
        npc_panel.text_list = candidate_list
        return_list, _other_return_list, select_state = (
            common_select_NPC.common_select_npc_button_list_func(
                npc_panel, _("任命主交易员"), info_text, select_state
            )
        )
        if flow_handle.askfor_all(return_list) == _("返回"):
            break
        current_main = economy.main_trader(res_type)


def auto_trade_setting(width: int, res_id: int) -> None:
    """
    绘制单个资源的自动交易设置子界面，提供开关、数值调整与预览。
    Keyword arguments:
    width、res_id -- int，面板绘制宽度与资源编号
    Return arguments:
    None -- 无返回值
    """
    data = game_config.config_resouce[res_id]
    while True:
        settings = economy.auto_trade(res_id)
        title = _("自动交易设置 - {0}").format(data.name)
        draw.TitleLineDraw(title, width).draw()
        keys: list[str] = []
        if not economy.main_trader(data.type):
            draw_text(_("当前资源类型尚未任命主交易员，无法配置自动交易。\n"))
            if draw_back(keys, width):
                break
            continue
        stock = warehouse.stock().get(res_id, 0)
        draw_text(_("当前资源：{0}，库存量：{1}\n").format(data.name, stock))
        line_feed.draw()
        for side in _sides():
            _draw_side(keys, res_id, settings, side)
        if draw_back(keys, width):
            break


def _sides() -> tuple[tuple[str, str, str, str, str, str], ...]:
    """按调用时翻译结果返回自动买入与自动卖出两侧的文案元组。"""
    return (
        (
            "buy",
            _("[自动买入：{0}]"),
            _("自动买入目标库存"),
            _("自动买入触发价格"),
            "买入操作预览",
            _(
                "在0点结算时，如果库存低于 {0} 且买价低于基准价的 {1}% 时，买入至库存为 {0} 。\n"
            ),
        ),
        (
            "sell",
            _("[自动卖出：{0}]"),
            _("自动卖出目标库存"),
            _("自动卖出触发价格"),
            "卖出操作预览",
            _(
                "在0点结算时，如果库存高于 {0} 且卖价高于基准价的 {1}% 时，卖出至库存为 {0} 。\n"
            ),
        ),
    )


def _draw_side(
    keys: list[str],
    res_id: int,
    settings: dict[str, bool | int],
    texts: tuple[str, str, str, str, str, str],
) -> None:
    """绘制自动交易单侧的开关按钮、数值调整行与预览说明。"""
    side, toggle, stock_label, price_label, preview, sentence = texts
    on = settings[f"{side}_on"]
    toggle_text = toggle.format(_("开启") if on else _("关闭"))
    draw_button(
        keys,
        toggle_text,
        f"{res_id}_{side}_on_toggle",
        svc.toggle_auto_trade,
        (res_id, f"{side}_on"),
    )
    line_feed.draw()
    if on:
        _value_row(keys, res_id, settings, side, stock_label, False)
        _value_row(keys, res_id, settings, side, price_label, True)
        stock = settings[f"{side}_stock"]
        price = settings[f"{side}_price_percent"]
        preview_text = _("{0}：").format(pad(preview, 20, align="center"))
        draw_text(preview_text + sentence.format(stock, price))
    line_feed.draw()


def _value_row(
    keys: list[str],
    res_id: int,
    settings: dict[str, bool | int],
    side: str,
    label: str,
    percent: bool,
) -> None:
    """绘制单条自动交易数值的标签、步进按钮与重置按钮。"""
    tag = f"{side}_price" if percent else f"{side}_stock"
    key = f"{tag}_percent" if percent else tag
    value = f"{settings[key]}%" if percent else str(settings[key])
    draw_text("{}：".format(pad(label, 20, align="center")) + value)
    for delta in PRICE_STEPS if percent else STOCK_STEPS:
        step = f" [{delta:+}%] " if percent else f" [{delta:+}] "
        draw_button(
            keys,
            _(step),
            f"{res_id}_{tag}_{step.strip()}",
            svc.adjust_auto_trade_value,
            (res_id, key, delta, percent, False),
            len(step) * 2,
        )
    draw_button(
        keys,
        _("[重置]"),
        f"{res_id}_{tag}_reset",
        svc.adjust_auto_trade_value,
        (res_id, key, 100 if percent else 0, percent, True),
    )
    line_feed.draw()
