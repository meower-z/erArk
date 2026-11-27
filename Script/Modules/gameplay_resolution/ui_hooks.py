"""
玩法结算界面回调（ui_hooks）
============================
本模块提供十二类回调的登记与调用入口。
十二类回调分别用于输出提示文本、数值变化、图片、分隔线、富文本口上、逐行等待文本、刷出缓冲输出、
切换面板、确认提问、查询隐奸中显示非H指令的开关、调用文本AI处理与主角寻路首段选定。
本模块不直接导入界面、Tk 或输入输出模块。
未登记回调时，emit_notice、emit_delta、emit_image、emit_divider、emit_rich_talk、
emit_line_wait_text、emit_flush、switch_panel 与 choose_route_leg 不执行操作。
未登记回调时，emit_confirm 返回 True。
未登记回调时，hidden_sex_show_non_h 返回 False。
未登记回调时，apply_text_ai 原样返回传入文本。
"""

from collections.abc import Callable
from typing import Protocol, Unpack

from Script.Protocol.delta_events import DeltaEntry
from Script.Protocol.narrative_events import EventFacts
from Script.Protocol.ports import Delta, Notice


class RichTalk(Protocol):
    """富文本口上回调的函数签名协议。"""

    def __call__(
        self,
        text: str,
        *,
        base_style: str,
        wait_flag: bool,
        trailing_wait: bool,
    ) -> None:
        """
        接收一段含富文本标签的口上文本及其显示选项并完成输出。
        Keyword arguments:
        text -- str，要输出的富文本口上文本
        base_style -- str，无行内标签时的基础样式名
        wait_flag -- bool，为真时在换行处等待玩家确认
        trailing_wait -- bool，为真时在末尾追加一次换行并等待玩家确认
        Return arguments:
        None -- 无返回值
        """


class TextAi(Protocol):
    """文本AI处理回调的函数签名协议。"""

    def __call__(
        self,
        character_id: int,
        behavior_id: str,
        original_text: str,
        *,
        translator: bool,
    ) -> str:
        """
        接收对话文本与上下文标识，返回处理后的显示文本。
        Keyword arguments:
        character_id -- int，角色编号
        behavior_id -- str，行为编号
        original_text -- str，待处理的原始文本
        translator -- bool，为真时以翻译模式处理，为假时以生成模式处理
        Return arguments:
        str -- 处理后的显示文本
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
type Divider = Callable[[str], None]
""" 分隔线绘制回调函数类型，接收用于平铺的分隔字符。 """
_dividers: list[Divider] = []
""" 按登记顺序保存的分隔线绘制回调列表。 """
_rich_talks: list[RichTalk] = []
""" 按登记顺序保存的富文本口上回调列表。 """
type LineWaitText = Callable[[str, str], None]
""" 逐行等待文本回调函数类型，接收文本与样式名。 """
_line_wait_texts: list[LineWaitText] = []
""" 按登记顺序保存的逐行等待文本回调列表。 """
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
_text_ais: list[TextAi] = []
""" 按登记顺序保存的文本AI处理回调列表。 """
type Flush = Callable[[], None]
""" 刷出缓冲输出回调函数类型，不接收参数且无返回值。 """
_flushes: list[Flush] = []
""" 按登记顺序保存的刷出缓冲输出回调列表。 """
type RouteLeg = Callable[
    [str, int, int, dict[str, object], dict[str, object] | None], None
]
""" 主角寻路首段选定回调函数类型，按位置接收行为编号、分钟数、角色状态编号、写入字段与附加参数。 """
_route_legs: list[RouteLeg] = []
""" 按登记顺序保存的主角寻路首段选定回调列表。 """


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
    **facts: Unpack[EventFacts],
) -> None:
    """
    按登记顺序调用已登记的提示文本回调，未登记时不执行操作。
    Keyword arguments:
    text -- str，要输出的提示文本
    wait -- bool，为真时等待玩家确认，默认为 False
    style -- str | None，文本样式名，默认为 None
    use_text_width -- bool，为真时按配置的文本宽度排版，默认为 False
    facts -- EventFacts，可选事件事实关键字参数，将调用方传入的键值原样转发给已登记回调
    Return arguments:
    None -- 无返回值
    """
    for fn in _notices:
        fn(text, wait=wait, style=style, use_text_width=use_text_width, **facts)


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
    **facts: Unpack[EventFacts],
) -> None:
    """
    按登记顺序调用已登记的数值变化回调，未登记时不执行操作。
    Keyword arguments:
    entries -- tuple[DeltaEntry, ...]，数值变化项元组
    source -- str，事件来源标识
    summary_text -- str | None，整段显示文本，默认为 None
    wait -- bool，为真时等待玩家确认，默认为 False
    use_text_width -- bool，为真时按配置的文本宽度排版，默认为 False
    facts -- EventFacts，可选事件事实关键字参数，将调用方传入的键值原样转发给已登记回调
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
            **facts,
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


def on_divider(fn: Divider) -> Divider:
    """
    登记一个分隔线绘制回调，可作为装饰器使用。
    Keyword arguments:
    fn -- Divider，要登记的分隔线绘制回调函数
    Return arguments:
    Divider -- 原样返回传入的 fn
    """
    _dividers.append(fn)
    return fn


def emit_divider(char: str = "-") -> None:
    """
    按登记顺序调用已登记的分隔线绘制回调，未登记时不执行操作。
    Keyword arguments:
    char -- str，分隔线平铺字符，默认为 "-"
    Return arguments:
    None -- 无返回值
    """
    for fn in _dividers:
        fn(char)


def on_rich_talk(fn: RichTalk) -> RichTalk:
    """
    登记一个富文本口上回调，可作为装饰器使用。
    Keyword arguments:
    fn -- RichTalk，要登记的富文本口上回调函数
    Return arguments:
    RichTalk -- 原样返回传入的 fn
    """
    _rich_talks.append(fn)
    return fn


def emit_rich_talk(
    text: str,
    *,
    base_style: str = "standard",
    wait_flag: bool = True,
    trailing_wait: bool = False,
) -> None:
    """
    按登记顺序调用已登记的富文本口上回调，未登记时不执行操作。
    Keyword arguments:
    text -- str，要输出的富文本口上文本
    base_style -- str，无行内标签时的基础样式名，默认为 "standard"
    wait_flag -- bool，为真时在换行处等待玩家确认，默认为 True
    trailing_wait -- bool，为真时在末尾追加一次换行并等待玩家确认，默认为 False
    Return arguments:
    None -- 无返回值
    """
    for fn in _rich_talks:
        fn(
            text,
            base_style=base_style,
            wait_flag=wait_flag,
            trailing_wait=trailing_wait,
        )


def on_line_wait_text(fn: LineWaitText) -> LineWaitText:
    """
    登记一个逐行等待文本回调，可作为装饰器使用。
    Keyword arguments:
    fn -- LineWaitText，要登记的逐行等待文本回调函数
    Return arguments:
    LineWaitText -- 原样返回传入的 fn
    """
    _line_wait_texts.append(fn)
    return fn


def emit_line_wait_text(text: str, style: str = "standard") -> None:
    """
    按登记顺序调用已登记的逐行等待文本回调，未登记时不执行操作。
    Keyword arguments:
    text -- str，要输出的文本
    style -- str，文本样式名，默认为 "standard"
    Return arguments:
    None -- 无返回值
    """
    for fn in _line_wait_texts:
        fn(text, style)


def on_text_ai(fn: TextAi) -> TextAi:
    """
    登记一个文本AI处理回调，可作为装饰器使用。
    Keyword arguments:
    fn -- TextAi，要登记的文本AI处理回调函数
    Return arguments:
    TextAi -- 原样返回传入的 fn
    """
    _text_ais.append(fn)
    return fn


def apply_text_ai(
    character_id: int,
    behavior_id: str,
    original_text: str,
    *,
    translator: bool = False,
) -> str:
    """
    按登记顺序依次调用已登记的文本AI处理回调，每个回调接收前一个回调的返回值。未登记回调时原样返回 original_text。
    Keyword arguments:
    character_id -- int，角色编号
    behavior_id -- str，行为编号
    original_text -- str，待处理的原始文本
    translator -- bool，为真时以翻译模式处理，默认为 False
    Return arguments:
    str -- 最后一个回调的返回值，未登记回调时返回 original_text
    """
    text = original_text
    for fn in _text_ais:
        text = fn(character_id, behavior_id, text, translator=translator)
    return text


def on_flush(fn: Flush) -> Flush:
    """
    登记一个刷出缓冲输出回调，可作为装饰器使用。
    Keyword arguments:
    fn -- Flush，要登记的刷出缓冲输出回调函数
    Return arguments:
    Flush -- 原样返回传入的 fn
    """
    _flushes.append(fn)
    return fn


def emit_flush() -> None:
    """
    按登记顺序调用已登记的刷出缓冲输出回调，未登记时不执行操作。
    Return arguments:
    None -- 无返回值
    """
    for fn in _flushes:
        fn()


def on_route_leg(fn: RouteLeg) -> RouteLeg:
    """
    登记一个主角寻路首段选定回调，可作为装饰器使用。
    Keyword arguments:
    fn -- RouteLeg，要登记的主角寻路首段选定回调函数
    Return arguments:
    RouteLeg -- 原样返回传入的 fn
    """
    _route_legs.append(fn)
    return fn


def choose_route_leg(
    behavior_id: str,
    minutes: int,
    *,
    state: int,
    fields: dict[str, object],
    args: dict[str, object] | None,
) -> None:
    """
    按登记顺序调用已登记的主角寻路首段选定回调，未登记时不执行操作。
    Keyword arguments:
    behavior_id -- str，本段移动使用的行为编号
    minutes -- int，本段移动所需的分钟数
    state -- int，本段移动开始时写入的角色状态编号
    fields -- dict[str, object]，本段移动开始时写入主角数据的字段映射
    args -- dict[str, object] | None，行动附加参数字典，无附加参数时为 None
    Return arguments:
    None -- 无返回值
    """
    for fn in _route_legs:
        fn(behavior_id, minutes, state, fields, args)
