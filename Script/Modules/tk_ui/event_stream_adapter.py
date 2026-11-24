"""
叙事事件的 Tk 绘制适配器，通过 draw 绘制类输出 NarrativeEvent 与 SceneBreak。
无自定义颜色的 plain 文本段直接沿用块基础样式（标题块为 littletitle，段落块为事件 style）。
其余角色或带 color 的文本段经 frame_style_def 注册派生样式，保留块基础样式的背景与字体。
派生样式采用配置字号并合并基础样式与角色的加粗、下划线和斜体标记。
其前景色依次取自 color、角色取色样式或块基础样式。
非末块文本结尾无换行符时补一段换行，使后续块从新行开始。
pause 为真时，适配器在最后一段非空文本使用 WaitDraw，各段均为空时在末段使用 WaitDraw。
"""

from Script.Config import game_config, normal_config
from Script.Core import io_init
from Script.Kernel import core
from Script.Protocol.narrative_events import (
    EventMeta,
    NarrativeEvent,
    SceneBreak,
    SpanRole,
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


class EventStreamAdapter:
    """维护事件序号并将叙事事件与场景分隔绘制到 Tk 文本框的适配器。"""

    def __init__(self) -> None:
        """初始化适配器并将事件序号计数器置为 0。"""
        self._seq = 0

    def meta(self, source: str) -> EventMeta:
        """
        用当前序号、内核时钟与来源标识构造 EventMeta，并将内部序号加一。
        Keyword arguments:
        source -- str，事件来源标识
        Return arguments:
        EventMeta -- 新生成的不可变事件元数据
        """
        meta = EventMeta(self._seq, core.state().clock, source)
        self._seq += 1
        return meta

    def render(self, event: NarrativeEvent | SceneBreak) -> None:
        """
        将一条叙事事件或场景分隔经 LineDraw、NormalDraw 或 WaitDraw 绘制到界面。
        非末块结尾无换行时补一次换行，pause 为真时在最后一段非空文本（全空时为末段）使用 WaitDraw。
        Keyword arguments:
        event -- NarrativeEvent | SceneBreak，待绘制的叙事事件或场景分隔
        Return arguments:
        None -- 无返回值
        """
        width = normal_config.config_normal.text_width
        if isinstance(event, SceneBreak):
            draw.LineDraw(event.char, width).draw()
            return
        items = _layout(event)
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


STREAM = EventStreamAdapter()
""" 游戏线程共用的 EventStreamAdapter 实例。 """
