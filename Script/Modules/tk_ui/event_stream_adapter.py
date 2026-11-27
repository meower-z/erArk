"""
叙事事件的 Tk 绘制适配器，通过 draw 绘制类输出 NarrativeEvent、SceneBreak 与 DeltaEvent。
DeltaEvent 先转为单段落 NarrativeEvent。
段落文本在 summary_text 非 None 时取该值，否则按变化项逐行生成。
无 color 的 plain 文本段沿用块基础样式（标题块为 littletitle，段落块为事件 style）。
其余角色或带 color 的文本段经 frame_style_def 注册派生样式。
派生样式保留基础样式的背景与字体，采用配置字号，并合并基础样式与角色的加粗、下划线和斜体标记。
其前景色依次取自 color、角色取色样式或块基础样式。
非末块结尾无换行时补一段换行，使后续块从新行开始。
pause 为真时，适配器在末段非空文本用 WaitDraw，全空时在末段用 WaitDraw。
启用非零行数预算时，若已有输出且新事件使累计行数达到或超过预算，适配器先暂停一次再整条绘制。
SceneBreak、含非空文本的暂停事件或 reset() 清零已输出行数。
"""

import math
from typing import Unpack

from Script.Config import game_config, normal_config
from Script.Core import flow_handle, io_init, text_handle
from Script.Kernel import core
from Script.Protocol.delta_events import DeltaEntry, DeltaEvent, DeltaValue
from Script.Protocol.narrative_events import (
    EventFacts,
    EventMeta,
    NarrativeEvent,
    SceneBreak,
    SpanRole,
    TextBlock,
    TextSpan,
)
from Script.UI.Moudle import draw

HEADING = "littletitle"
""" 标题块的基础样式名，取值为 "littletitle"。 """
ROLE_LOOKS: dict[SpanRole, tuple[str | None, bool, bool]] = {
    "plain": (None, False, False),
    "emphasis": (None, False, True),
    "strong": (None, True, False),
    "warning": ("warning", False, False),
    "accent": ("gold_enrod", False, False),
}
""" 行内角色到（取色样式名、加粗、斜体）三元组的映射。 """
MODIFIERS = ("bold", "underline", "italic")
""" init_style 派生样式名末尾可拆分的字形后缀元组（bold、underline、italic）。 """


def _look(name: str) -> dict[str, object]:
    fonts = game_config.config_font
    base = name
    combo: set[str] = set()
    while (
        base not in game_config.config_font_data
        and base.rpartition("_")[2] in MODIFIERS
    ):
        base, _, modifier = base.rpartition("_")
        combo.add(modifier)
    own = fonts[game_config.config_font_data.get(base, 0)]
    look = {**vars(fonts[0]), **vars(own)}
    if combo:
        look.update((modifier, modifier in combo) for modifier in MODIFIERS)
    return look


def _tag(base: str | None, span: TextSpan) -> str | None:
    if span.role == "plain" and span.color is None:
        return base
    name = base or draw.NormalDraw.style
    tint_name, bold, italic = ROLE_LOOKS[span.role]
    own = _look(name)
    tint = _look(tint_name) if tint_name else own
    color = span.color or str(tint["foreground"])
    tag = f"{name}/{span.role}/{color}"
    io_init.frame_style_def(
        tag,
        color,
        str(own.get("background", "")),
        str(own.get("font") or normal_config.config_normal.font),
        normal_config.config_normal.font_size,
        bool(own.get("bold") or tint.get("bold") or bold),
        bool(own.get("underline") or tint.get("underline")),
        bool(own.get("italic") or tint.get("italic") or italic),
    )
    return tag


def _layout(event: NarrativeEvent) -> list[tuple[str, str | None] | str]:
    items: list[tuple[str, str | None] | str] = []
    for index, block in enumerate(event.blocks):
        if block.kind == "divider":
            items.append(block.char)
            continue
        base = HEADING if block.kind == "heading" else event.style
        pieces = [(span.text, _tag(base, span)) for span in block.spans]
        if block.kind == "heading":
            pieces.append(("\n", HEADING))
        more = index < len(event.blocks) - 1
        if more and not "".join(text for text, _ in pieces).endswith("\n"):
            pieces.append(("\n", base))
        items.extend(pieces)
    return items


def _rows(items: list[tuple[str, str | None] | str], width: int) -> int:
    """
    估算单条事件排版项在给定列宽下占用的屏幕行数。
    函数将各文本项的内容拼接，并将每个分隔线项记为一个换行符，再按换行符分段。
    每段经 text_handle.get_text_index 计算显示列宽，再除以不小于 1 的 width 并向上取整。
    末段之前的每段至少计 1 行。
    末段直接计入取整结果，空串时计 0 行。
    Keyword arguments:
    items -- list[tuple[str, str | None] | str]，_layout 生成的排版项列表
    width -- int，单行显示列宽，小于 1 时按 1 处理
    Return arguments:
    int -- 估算占用的屏幕总行数
    """
    text = "".join(
        item[0] if isinstance(item, tuple) else "\n" for item in items
    )
    span = max(width, 1)
    counts = [
        math.ceil(text_handle.get_text_index(line) / span)
        for line in text.split("\n")
    ]
    return sum(max(1, count) for count in counts[:-1]) + counts[-1]


def _amount(value: DeltaValue, unit: str, signed: bool = False) -> str:
    """
    将一个数值变化字段格式化为带单位的文本。
    Keyword arguments:
    value -- DeltaValue，待格式化的取值
    unit -- str，数值单位
    signed -- bool，为真时正数前加 "+"，默认为 False
    Return arguments:
    str -- None 时返回 "—"（不带单位），其余返回取值文本加单位
    """
    if value is None:
        return "\u2014"
    if isinstance(value, str):
        return value + unit
    sign = "+" if signed and value > 0 else ""
    return f"{sign}{value}{unit}"


def _delta_text(entries: tuple[DeltaEntry, ...]) -> str:
    """
    按变化项逐行生成显示文本，每行以换行符结尾。
    Keyword arguments:
    entries -- tuple[DeltaEntry, ...]，数值变化项元组
    Return arguments:
    str -- 每项一行的文本，前后值均非 None 时在行尾附加前后值
    """
    lines: list[str] = []
    for entry in entries:
        line = (
            f"{entry.target_label} {entry.field}："
            f"{_amount(entry.delta, entry.unit, signed=True)}"
        )
        if entry.before is not None and entry.after is not None:
            line += (
                f"（{_amount(entry.before, entry.unit)} → "
                f"{_amount(entry.after, entry.unit)}）"
            )
        lines.append(line + "\n")
    return "".join(lines)


class EventStreamAdapter:
    """
    维护事件序号并将叙事事件、场景分隔与数值变化事件绘制到 Tk 文本框的适配器。
    启用非零行数预算时，适配器累计已输出估算行数，并在已有输出且新事件将使累计行数达到或超过预算时先暂停一次。
    """

    def __init__(self, budget: int = 0) -> None:
        """
        初始化适配器，将事件序号与已输出行数计数器均置为 0，并设置屏幕行数预算。
        Keyword arguments:
        budget -- int，屏幕行数预算，默认为 0 表示关闭自动暂停
        Return arguments:
        None -- 无返回值
        """
        self._seq = 0
        self.budget = budget
        self._height = 0

    def reset(self) -> None:
        """
        将已输出行数计数器清零，供调用方在清屏、切换面板或新回合边界重新开始计数。
        Return arguments:
        None -- 无返回值
        """
        self._height = 0

    def meta(self, source: str, **facts: Unpack[EventFacts]) -> EventMeta:
        """
        用当前序号、内核时钟、来源标识与可选事件事实构造 EventMeta，并将内部序号加一。
        Keyword arguments:
        source -- str，事件来源标识
        facts -- EventFacts，可选事件事实关键字参数，未传入的字段取 EventMeta 默认值
        Return arguments:
        EventMeta -- 新生成的不可变事件元数据
        """
        meta = EventMeta(self._seq, core.state().clock, source, **facts)
        self._seq += 1
        return meta

    def render(self, event: NarrativeEvent | SceneBreak | DeltaEvent) -> None:
        """
        将一条叙事事件、场景分隔或数值变化事件经 LineDraw、NormalDraw 或 WaitDraw 绘制到界面。
        数值变化事件先转为不指定样式的单段落叙事事件。
        SceneBreak 绘制分隔线后清零已输出行数，不触发自动暂停。
        叙事事件先经 _layout 排版，非末块结尾无换行时补一次换行。
        随后适配器用 _rows 估算本次行数。
        若 budget 非零且已输出行数大于 0，当已输出行数加本次行数达到或超过 budget 时，
        适配器先调用 flow_handle.askfor_wait() 暂停并清零已输出行数。
        之后适配器累加本次行数并整条绘制事件。
        pause 为真时，适配器在末段非空文本用 WaitDraw 并在绘制后清零行数，各段全空时在末段用 WaitDraw 且不清零行数。
        Keyword arguments:
        event -- NarrativeEvent | SceneBreak | DeltaEvent，待绘制的事件
        Return arguments:
        None -- 无返回值
        """
        if isinstance(event, DeltaEvent):
            text = (
                event.summary_text
                if event.summary_text is not None
                else _delta_text(event.entries)
            )
            event = NarrativeEvent(
                event.meta,
                (TextBlock("paragraph", (TextSpan(text),)),),
                pause=event.pause,
                use_text_width=event.use_text_width,
            )
        width = normal_config.config_normal.text_width
        if isinstance(event, SceneBreak):
            draw.LineDraw(event.char, width).draw()
            self._height = 0
            return
        items = _layout(event)
        height = _rows(items, width)
        if (
            self.budget
            and self._height
            and self._height + height >= self.budget
        ):
            flow_handle.askfor_wait()
            self._height = 0
        self._height += height
        texts = [i for i, item in enumerate(items) if isinstance(item, tuple)]
        filled = [
            i
            for i, item in enumerate(items)
            if isinstance(item, tuple) and item[0]
        ]
        wait_at = (filled or texts)[-1] if event.pause else -1
        for index, item in enumerate(items):
            if isinstance(item, str):
                draw.LineDraw(item, width).draw()
                continue
            text, style = item
            now_draw = (
                draw.WaitDraw() if index == wait_at else draw.NormalDraw()
            )
            if event.use_text_width:
                now_draw.width = width
            now_draw.text = text
            if style is not None:
                now_draw.style = style
            now_draw.draw()
        if event.pause and filled:
            self._height = 0


STREAM = EventStreamAdapter()
""" 游戏线程共用的 EventStreamAdapter 实例。 """
