"""
叙事事件协议的数据类型定义模块，仅导入 Python 标准库。
本模块定义五个不可变数据类与两个字面量类型别名（SpanRole、BlockKind）。
五个数据类依次描述事件元数据、行内文本、文本块、叙事事件与场景分隔，并在构造时校验字段。
"""

import unicodedata
from dataclasses import dataclass
from typing import Literal, get_args

type SpanRole = Literal["plain", "emphasis", "strong", "warning", "accent"]
""" 行内文本的角色字面量类型，取值为 plain、emphasis、strong、warning 或 accent。 """
type BlockKind = Literal["paragraph", "heading", "divider"]
""" 文本块的种类字面量类型，取值为 paragraph、heading 或 divider。 """
_HEX = frozenset("0123456789abcdefABCDEF")
_ZERO_WIDTH = (
    ("\u1160", "\u11ff"),
    ("\u3164", "\u3164"),
    ("\ud7b0", "\ud7ff"),
    ("\uffa0", "\uffa0"),
)


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def _count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _visible(char: object) -> bool:
    return (
        isinstance(char, str)
        and char != ""
        and "<" not in char
        and char.isprintable()
        and all(
            unicodedata.category(c)[0] != "M"
            and not any(low <= c <= high for low, high in _ZERO_WIDTH)
            for c in char
        )
    )


@dataclass(frozen=True, slots=True)
class EventMeta:
    """叙事事件的不可变元数据，包含非负序号 seq、非负游戏时钟 clock 与来源标识 source。"""

    seq: int
    clock: int
    source: str

    def __post_init__(self) -> None:
        """校验 seq 与 clock 为非负非布尔整数且 source 为字符串，不满足时抛出 ValueError。"""
        _require(
            _count(self.seq), f"seq {self.seq!r} is not a non-negative int"
        )
        _require(
            _count(self.clock),
            f"clock {self.clock!r} is not a non-negative int",
        )
        _require(
            isinstance(self.source, str), f"source {self.source!r} is not a str"
        )


@dataclass(frozen=True, slots=True)
class TextSpan:
    """不可变行内文本段，包含文本内容 text、角色 role（默认 plain）与可选十六进制颜色 color。"""

    text: str
    role: SpanRole = "plain"
    color: str | None = None

    def __post_init__(self) -> None:
        """校验 text 为字符串、role 属于 SpanRole 且 color 为 None 或 #RRGGBB，否则抛出 ValueError。"""
        _require(isinstance(self.text, str), f"text {self.text!r} is not a str")
        _require(
            self.role in get_args(SpanRole.__value__),
            f"unknown role {self.role!r}",
        )
        color = self.color
        _require(
            color is None
            or (
                isinstance(color, str)
                and len(color) == 7
                and color[0] == "#"
                and set(color[1:]) <= _HEX
            ),
            f"color {color!r} is not #RRGGBB",
        )


@dataclass(frozen=True, slots=True)
class TextBlock:
    """不可变文本块，由块种类 kind、行内文本元组 spans 与分隔线字符 char（默认 "-"）组成。"""

    kind: BlockKind
    spans: tuple[TextSpan, ...] = ()
    char: str = "-"

    def __post_init__(self) -> None:
        """校验 kind、divider 空 spans、无 "<" 正宽 char 及段落标题非空 TextSpan 元组，否则抛 ValueError。"""
        _require(
            self.kind in get_args(BlockKind.__value__),
            f"unknown kind {self.kind!r}",
        )
        if self.kind == "divider":
            _require(self.spans == (), "a divider has no spans")
            _require(
                _visible(self.char), f"char {self.char!r} has no display width"
            )
        else:
            _require(
                isinstance(self.spans, tuple)
                and self.spans != ()
                and all(isinstance(s, TextSpan) for s in self.spans),
                f"spans {self.spans!r} is not a non-empty tuple of TextSpan",
            )


@dataclass(frozen=True, slots=True)
class NarrativeEvent:
    """
    不可变叙事事件，包含元数据 meta、文本块元组 blocks 与三个可选显示字段。
    pause 表示是否在最后一段非空文本后等待确认。style 指定段落默认样式名。
    use_text_width 表示是否按文本宽度排版。
    """

    meta: EventMeta
    blocks: tuple[TextBlock, ...]
    pause: bool = False
    style: str | None = None
    use_text_width: bool = False

    def __post_init__(self) -> None:
        """校验 meta、非空 blocks、style、布尔开关与暂停末块非 divider，否则抛出 ValueError。"""
        _require(
            isinstance(self.meta, EventMeta),
            f"meta {self.meta!r} is not an EventMeta",
        )
        _require(
            isinstance(self.blocks, tuple)
            and self.blocks != ()
            and all(isinstance(b, TextBlock) for b in self.blocks),
            f"blocks {self.blocks!r} is not a non-empty tuple of TextBlock",
        )
        _require(
            isinstance(self.pause, bool), f"pause {self.pause!r} is not a bool"
        )
        _require(
            not self.pause or self.blocks[-1].kind != "divider",
            "a pausing event ends with text",
        )
        _require(
            self.style is None or isinstance(self.style, str),
            f"style {self.style!r} is not a str",
        )
        _require(
            isinstance(self.use_text_width, bool),
            f"use_text_width {self.use_text_width!r} is not a bool",
        )


@dataclass(frozen=True, slots=True)
class SceneBreak:
    """不可变场景分隔事件，包含元数据 meta 与分隔线字符 char（默认 "-"）。"""

    meta: EventMeta
    char: str = "-"

    def __post_init__(self) -> None:
        """校验 meta 为 EventMeta 且 char 具有正显示宽度，否则抛出 ValueError。"""
        _require(
            isinstance(self.meta, EventMeta),
            f"meta {self.meta!r} is not an EventMeta",
        )
        _require(
            _visible(self.char), f"char {self.char!r} has no display width"
        )
