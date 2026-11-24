"""
玩法结算界面回调（ui_hooks）
============================
本模块提供六类回调的登记与调用入口。
六类回调用于输出提示文本、输出数值变化、绘制图片、切换面板、向玩家确认提问，以及查询隐奸中显示非H指令的开关。
本模块不直接导入界面、Tk 或输入输出模块。
未登记回调时，提示、数值变化、图片与面板切换四类调用入口不执行任何操作。
未登记回调时，emit_confirm 返回 True。
未登记回调时，hidden_sex_show_non_h 返回 False。
"""

from collections.abc import Callable
from typing import Protocol

from Script.Protocol.delta_events import DeltaEntry


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


class Delta(Protocol):
    """数值变化回调的函数签名协议。"""

    def __call__(
        self,
        entries: tuple[DeltaEntry, ...],
        *,
        source: str,
        summary_text: str | None,
        wait: bool,
        use_text_width: bool,
    ) -> None:
        """
        接收一组数值变化项及其显示选项并完成输出。
        Keyword arguments:
        entries -- tuple[DeltaEntry, ...]，数值变化项元组
        source -- str，事件来源标识
        summary_text -- str | None，整段显示文本，无摘要文本时为 None
        wait -- bool，为真时等待玩家确认
        use_text_width -- bool，为真时按配置的文本宽度排版
        Return arguments:
        None -- 无返回值
        """


type PanelSwitch = Callable[[int], None]
""" 面板切换回调函数类型，接收目标面板编号。 """
_notices: list[Notice] = []
""" 按登记顺序保存的提示文本回调列表。 """
_deltas: list[Delta] = []
""" 按登记顺序保存的数值变化回调列表。 """
type Image = Callable[[str], None]
""" 图片绘制回调函数类型，接收图片名。 """
_images: list[Image] = []
""" 按登记顺序保存的图片绘制回调列表。 """
_panel_switches: list[PanelSwitch] = []
""" 按登记顺序保存的面板切换回调列表。 """
type ToggleQuery = Callable[[], bool]
""" 只读开关查询回调函数类型，不接收参数并返回布尔值。 """
_show_non_h_queries: list[ToggleQuery] = []
""" 按登记顺序保存的回调列表，用于只读查询隐奸中显示非H指令的开关。 """
type Confirm = Callable[[str], bool]
""" 确认提问回调函数类型，接收提问文本，返回布尔值表示是否确认。 """
_confirms: list[Confirm] = []
""" 按登记顺序保存的确认提问回调列表。 """


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


def on_delta(fn: Delta) -> Delta:
    """
    登记一个数值变化回调，可作为装饰器使用。
    Keyword arguments:
    fn -- Delta，要登记的数值变化回调函数
    Return arguments:
    Delta -- 原样返回传入的 fn
    """
    _deltas.append(fn)
    return fn


def emit_delta(
    entries: tuple[DeltaEntry, ...],
    *,
    source: str,
    summary_text: str | None = None,
    wait: bool = False,
    use_text_width: bool = False,
) -> None:
    """
    按登记顺序调用已登记的数值变化回调，未登记时不执行操作。
    Keyword arguments:
    entries -- tuple[DeltaEntry, ...]，数值变化项元组
    source -- str，事件来源标识
    summary_text -- str | None，整段显示文本，默认为 None
    wait -- bool，为真时等待玩家确认，默认为 False
    use_text_width -- bool，为真时按配置的文本宽度排版，默认为 False
    Return arguments:
    None -- 无返回值
    """
    for fn in _deltas:
        fn(
            entries,
            source=source,
            summary_text=summary_text,
            wait=wait,
            use_text_width=use_text_width,
        )


def on_image(fn: Image) -> Image:
    """
    登记一个图片绘制回调，可作为装饰器使用。
    Keyword arguments:
    fn -- Image，要登记的图片绘制回调函数
    Return arguments:
    Image -- 原样返回传入的 fn
    """
    _images.append(fn)
    return fn


def emit_image(img_name: str) -> None:
    """
    按登记顺序调用已登记的图片绘制回调，未登记时不执行操作。
    Keyword arguments:
    img_name -- str，要绘制的图片名
    Return arguments:
    None -- 无返回值
    """
    for fn in _images:
        fn(img_name)


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


def on_confirm(fn: Confirm) -> Confirm:
    """
    登记一个确认提问回调，可作为装饰器使用。
    Keyword arguments:
    fn -- Confirm，要登记的确认提问回调函数
    Return arguments:
    Confirm -- 原样返回传入的 fn
    """
    _confirms.append(fn)
    return fn


def emit_confirm(text: str) -> bool:
    """
    按登记顺序将提问文本传给已登记的确认提问回调，并在首个回调返回假值时停止。
    Keyword arguments:
    text -- str，要向玩家提问的文本
    Return arguments:
    bool -- 未登记回调时返回 True，全部已登记回调返回真值时也返回 True，任一回调返回假值时返回 False
    """
    return all(fn(text) for fn in _confirms)
