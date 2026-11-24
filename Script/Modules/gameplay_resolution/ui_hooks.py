"""
玩法结算界面回调（ui_hooks）
============================
本模块提供四类回调的登记与调用入口：输出提示文本、输出分隔线、切换面板、只读查询隐奸中显示非H指令的开关。
本模块不直接导入界面、Tk 或输入输出模块。
未登记回调时，提示输出、分隔线输出与面板切换函数不执行任何操作。
未登记回调时，开关查询函数返回 False。
"""

from collections.abc import Callable
from typing import Protocol


class Notice(Protocol):
    """提示文本回调的函数签名协议。"""

    def __call__(
        self, text: str, *, wait: bool, style: str | None, use_text_width: bool
    ) -> None:
        """
        接收一条提示文本及其显示选项并完成输出。
        Keyword arguments:
        text -- str，要输出的提示文本
        wait -- bool，为真时等待玩家确认
        style -- str | None，文本样式名，为 None 时使用默认样式
        use_text_width -- bool，为真时按配置的文本宽度排版
        Return arguments:
        None -- 无返回值
        """


type PanelSwitch = Callable[[int], None]
""" 面板切换回调函数类型，接收目标面板编号。 """
_notices: list[Notice] = []
""" 按登记顺序保存的提示文本回调列表。 """
_panel_switches: list[PanelSwitch] = []
""" 按登记顺序保存的面板切换回调列表。 """
type Divider = Callable[[str], None]
""" 分隔线回调函数类型，接收分隔线字符。 """
_dividers: list[Divider] = []
""" 按登记顺序保存的分隔线回调列表。 """
type ToggleQuery = Callable[[], bool]
""" 只读开关查询回调函数类型，不接收参数并返回布尔值。 """
_show_non_h_queries: list[ToggleQuery] = []
""" 按登记顺序保存的回调列表，用于只读查询隐奸中显示非H指令的开关。 """


def on_notice(fn: Notice) -> Notice:
    """
    登记一个提示文本回调，可作为装饰器使用。
    Keyword arguments:
    fn -- Notice，要登记的提示文本回调函数
    Return arguments:
    Notice -- 原样返回传入的 fn
    """
    _notices.append(fn)
    return fn


def emit_notice(
    text: str,
    *,
    wait: bool = False,
    style: str | None = None,
    use_text_width: bool = False,
) -> None:
    """
    按登记顺序调用已登记的提示文本回调，未登记时不执行操作。
    Keyword arguments:
    text -- str，要输出的提示文本
    wait -- bool，为真时等待玩家确认，默认为 False
    style -- str | None，文本样式名，默认为 None
    use_text_width -- bool，为真时按配置的文本宽度排版，默认为 False
    Return arguments:
    None -- 无返回值
    """
    for fn in _notices:
        fn(text, wait=wait, style=style, use_text_width=use_text_width)


def on_divider(fn: Divider) -> Divider:
    """
    登记一个分隔线回调，可作为装饰器使用。
    Keyword arguments:
    fn -- Divider，要登记的分隔线回调函数
    Return arguments:
    Divider -- 原样返回传入的 fn
    """
    _dividers.append(fn)
    return fn


def emit_divider(char: str = "-") -> None:
    """
    按登记顺序调用已登记的分隔线回调，未登记时不执行操作。
    Keyword arguments:
    char -- str，分隔线字符，默认为 "-"
    Return arguments:
    None -- 无返回值
    """
    for fn in _dividers:
        fn(char)


def on_panel_switch(fn: PanelSwitch) -> PanelSwitch:
    """
    登记一个面板切换回调，可作为装饰器使用。
    Keyword arguments:
    fn -- PanelSwitch，要登记的面板切换回调函数
    Return arguments:
    PanelSwitch -- 原样返回传入的 fn
    """
    _panel_switches.append(fn)
    return fn


def switch_panel(panel_id: int) -> None:
    """
    按登记顺序调用已登记的面板切换回调，未登记时不执行操作。
    Keyword arguments:
    panel_id -- int，目标面板编号
    Return arguments:
    None -- 无返回值
    """
    for fn in _panel_switches:
        fn(panel_id)


def on_hidden_sex_show_non_h(fn: ToggleQuery) -> ToggleQuery:
    """
    登记一个只读查询回调（用于读取隐奸中显示非H指令的开关），可作为装饰器使用。
    Keyword arguments:
    fn -- ToggleQuery，要登记的开关查询回调函数
    Return arguments:
    ToggleQuery -- 原样返回传入的 fn
    """
    _show_non_h_queries.append(fn)
    return fn


def hidden_sex_show_non_h() -> bool:
    """
    按登记顺序查询隐奸中显示非H指令的开关，未登记回调时返回 False。
    Return arguments:
    bool -- 任一已登记回调返回真值时返回 True，未登记或全部返回假值时返回 False
    """
    return any(fn() for fn in _show_non_h_queries)
