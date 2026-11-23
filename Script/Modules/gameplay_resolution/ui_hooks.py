"""
玩法结算界面回调（ui_hooks）
============================
为 gameplay_resolution 提供提示文本输出与面板切换两类回调的登记与触发入口。
本模块不直接导入界面、Tk 或输入输出模块。
未登记回调时，触发函数不执行任何操作。
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
