"""
叙事事件协议与 Tk 绘制适配器测试
================================
- 协议校验（ProtocolTest）：覆盖五个数据类的字段校验与分隔线字符正显示宽度检查。
- 绘制适配（AdapterTest）：验证提示回调、元数据计数、块间换行、修饰样式派生、暂停与分隔线。
- 导入边界（ProtocolBoundaryTest）：验证 narrative_events.py 仅导入 Python 标准库模块。
"""

import ast
import itertools
import os
import sys
from collections.abc import Callable
from typing import get_args
from unittest import mock

from Script.Config import game_config, normal_config
from Script.Core import io_init, text_handle
from Script.Kernel import core
from Script.Modules.gameplay_resolution import ui_hooks
from Script.Modules.tk_ui.event_stream_adapter import STREAM, EventStreamAdapter
from Script.Protocol import (
    BackendEvent,
    RenderChunk,
    ScriptedUiPort,
    StyleDefOp,
    default_first_option,
)
from Script.Protocol.narrative_events import (
    EventMeta,
    NarrativeEvent,
    SceneBreak,
    SpanRole,
    TextBlock,
    TextSpan,
)
from Script.UI.Moudle import draw
from tests.fast.base import FastTestCase
from tests.world import ROOT

META = EventMeta(0, 0, "test")
""" 测试共用的默认事件元数据。 """
BAD_CHARS = (
    "",
    "\n",
    "\u200b",
    "\u0301",
    "\u0903",
    "\u1160",
    "\ufeff",
    "<",
    "<red>",
    "<standard>",
    1,
)
""" 分隔线校验应拒绝的非法值元组（含零宽字符、尖括号文本与非字符串）。 """
ROLES: tuple[SpanRole, ...] = get_args(SpanRole.__value__)
""" SpanRole 定义的全部行内角色元组。 """


def build(
    make: Callable[..., object], *args: object, **kwargs: object
) -> object:
    """以任意位置与关键字参数调用 make，用于在测试中传入非法字段类型。"""
    return make(*args, **kwargs)


def paragraph(*spans: TextSpan) -> TextBlock:
    """将传入的行内文本段组成段落类型的 TextBlock。"""
    return TextBlock("paragraph", spans)


def look(name: str) -> tuple[str, str, str, bool, bool, bool]:
    """按 init_style 的缺省补齐规则返回指定样式的前景色、背景色、字体名与三种字形标记。"""
    standard = game_config.config_font[0]
    row = game_config.config_font[game_config.config_font_data[name]]

    def field(key: str) -> object:
        """读取样式行指定属性，缺省时回退到 standard 样式的同名属性。"""
        return getattr(row, key, getattr(standard, key, ""))

    font = str(field("font")) or normal_config.config_normal.font
    return (
        str(field("foreground")),
        str(field("background")),
        font,
        bool(field("bold")),
        bool(field("underline")),
        bool(field("italic")),
    )


class ProtocolTest(FastTestCase):
    """叙事事件协议五个数据类的字段校验测试。"""

    def test_meta_takes_only_non_negative_ints(self) -> None:
        """验证 EventMeta 拒绝非整数、布尔与负数的 seq 和 clock 以及非字符串 source。"""
        self.assertEqual(EventMeta(3, 480, "").clock, 480)
        for bad in (True, -1, 1.0, "1"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    build(EventMeta, bad, 0, "test")
                with self.assertRaises(ValueError):
                    build(EventMeta, 0, bad, "test")
        with self.assertRaises(ValueError):
            build(EventMeta, 0, 0, None)

    def test_span_checks_role_and_hex_color(self) -> None:
        """验证 TextSpan 仅接受合法字符串 text、已知角色 role 与 #RRGGBB 颜色。"""
        self.assertEqual(TextSpan("a", "accent", "#a1B2c3").color, "#a1B2c3")
        for color in (
            "#12345",
            "a1b2c3d",
            "#GGGGGG",
            "#１２３４５６",
            "#12345 ",
            123,
        ):
            with self.subTest(color=color), self.assertRaises(ValueError):
                build(TextSpan, "a", "plain", color)
        with self.assertRaises(ValueError):
            build(TextSpan, "a", "bold")
        with self.assertRaises(ValueError):
            build(TextSpan, None)

    def test_block_shapes(self) -> None:
        """验证 TextBlock 的块种类、分隔线可见字符与段落标题的非空 TextSpan 元组校验。"""
        for char in ("-", "＝", "=-", "~"):
            self.assertEqual(TextBlock("divider", char=char).char, char)
        cases: list[tuple[object, ...]] = [
            ("list", (TextSpan("a"),)),
            ("divider", (TextSpan("a"),)),
            ("paragraph", ()),
            ("heading", [TextSpan("a")]),
            ("heading", ("a",)),
        ]
        cases += [("divider", (), char) for char in BAD_CHARS]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                build(TextBlock, *case)

    def test_every_accepted_divider_char_has_display_width(self) -> None:
        """验证协议接受的全部非代理单字符在 get_text_index 下均具有正显示宽度。"""
        zero = []
        for code in itertools.chain(range(0xD800), range(0xE000, 0x110000)):
            char = chr(code)
            try:
                SceneBreak(META, char)
            except ValueError:
                continue
            if text_handle.get_text_index(char) <= 0:
                zero.append(hex(code))
        self.assertEqual(zero, [])

    def test_event_shapes(self) -> None:
        """验证 NarrativeEvent 与 SceneBreak 的字段类型约束及暂停事件末块不能为分隔线。"""
        text = paragraph(TextSpan("a"))
        line = TextBlock("divider")
        self.assertTrue(NarrativeEvent(META, (line, text), pause=True).pause)
        cases: list[tuple[tuple[object, ...], dict[str, object]]] = [
            ((None, (text,)), {}),
            ((META, ()), {}),
            ((META, [text]), {}),
            ((META, (text,)), {"pause": 1}),
            ((META, (text,)), {"style": 1}),
            ((META, (text,)), {"use_text_width": 1}),
            ((META, (text, line)), {"pause": True}),
        ]
        for args, kwargs in cases:
            with self.subTest(args=args, kwargs=kwargs), self.assertRaises(
                ValueError
            ):
                build(NarrativeEvent, *args, **kwargs)
        for args in ((None,), *((META, char) for char in BAD_CHARS)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                build(SceneBreak, *args)


class AdapterTest(FastTestCase):
    """EventStreamAdapter 经 draw 绘制类输出叙事事件的测试。"""

    def setUp(self) -> None:
        """打桩 NormalDraw、WaitDraw 与 LineDraw 的 draw 方法，并配置收集样式定义的测试端口。"""
        super().setUp()
        self.drawn: list[tuple[str, float, str, str]] = []
        self.styles: dict[str, StyleDefOp] = {}
        for cls in (draw.NormalDraw, draw.WaitDraw, draw.LineDraw):
            self.enterContext(
                mock.patch.object(
                    cls, "draw", autospec=True, side_effect=self.record
                )
            )
        io_init.configure(
            ScriptedUiPort(default_first_option(), listener=self.listen)
        )
        self.width = normal_config.config_normal.text_width

    def record(self, now: draw.NormalDraw | draw.LineDraw) -> None:
        """记录一次绘制调用的类名、宽度、样式名与文本内容。"""
        self.drawn.append((type(now).__name__, now.width, now.style, now.text))

    def listen(self, event: BackendEvent) -> None:
        """从测试端口收到的 RenderChunk 事件中收集 StyleDefOp 样式定义。"""
        if isinstance(event, RenderChunk):
            self.styles.update(
                (op.name, op) for op in event.ops if isinstance(op, StyleDefOp)
            )

    def assert_look(
        self,
        tag: str,
        base: str,
        color: str,
        bold: bool,
        underline: bool,
        italic: bool,
    ) -> None:
        """断言派生样式 tag 保留 base 的背景与字体，并具备期望的前景色、配置字号与字形标记。"""
        _fg, background, font, *_flags = look(base)
        op = self.styles[tag]
        self.assertEqual(
            (op.fg, op.bg, op.font, op.size, op.bold, op.underline, op.italic),
            (
                color,
                background,
                font,
                normal_config.config_normal.font_size,
                bold,
                underline,
                italic,
            ),
        )
        self.assertGreater(op.size, 0)
        self.assertTrue(op.font)

    def test_notice_draws_one_object_per_call(self) -> None:
        """验证 ui_hooks.emit_notice 每次绘制单个 WaitDraw 或 NormalDraw 且不发送样式定义。"""
        for wait, style, use_text_width in itertools.product(
            (False, True), (None, "gold_enrod", "warning"), (False, True)
        ):
            with self.subTest(
                wait=wait, style=style, use_text_width=use_text_width
            ):
                self.drawn.clear()
                ui_hooks.emit_notice(
                    "提示\n",
                    wait=wait,
                    style=style,
                    use_text_width=use_text_width,
                )
                self.assertEqual(
                    self.drawn,
                    [
                        (
                            "WaitDraw" if wait else "NormalDraw",
                            self.width if use_text_width else 0,
                            style or "standard",
                            "提示\n",
                        )
                    ],
                )
        ui_hooks.emit_notice("")
        self.assertEqual(self.drawn[-1], ("NormalDraw", 0, "standard", ""))
        self.assertEqual(self.styles, {})

    def test_meta_counts_up_from_zero_on_the_kernel_clock(self) -> None:
        """验证 meta 从 0 起递增序号并读取内核当前时钟与传入来源标识。"""
        adapter = EventStreamAdapter()
        first, second = adapter.meta("a"), adapter.meta("b")
        self.assertEqual((first.seq, second.seq), (0, 1))
        self.assertEqual(
            (first.clock, second.source), (core.state().clock, "b")
        )

    def test_heading_keeps_littletitle_under_every_role(self) -> None:
        """验证标题块各角色与自定义颜色均保留 littletitle 背景与字体并附带换行。"""
        spans = tuple(TextSpan(role, role) for role in ROLES) + (
            TextSpan("hex", "strong", "#123abc"),
        )
        STREAM.render(
            NarrativeEvent(
                META, (TextBlock("heading", spans),), use_text_width=True
            )
        )
        self.assertEqual(
            [text for _kind, _width, _style, text in self.drawn],
            [*ROLES, "hex", "\n"],
        )
        self.assertEqual({kind for kind, *_rest in self.drawn}, {"NormalDraw"})
        self.assertEqual(
            {width for _kind, width, *_rest in self.drawn}, {self.width}
        )
        tags = {text: style for _kind, _width, style, text in self.drawn}
        self.assertEqual(
            (tags["plain"], tags["\n"]), ("littletitle", "littletitle")
        )
        title = look("littletitle")
        warning, accent = look("warning"), look("gold_enrod")
        self.assert_look(
            tags["emphasis"], "littletitle", title[0], title[3], title[4], True
        )
        self.assert_look(
            tags["strong"], "littletitle", title[0], True, title[4], title[5]
        )
        for role, tint in (("warning", warning), ("accent", accent)):
            flags = (
                title[3] or tint[3],
                title[4] or tint[4],
                title[5] or tint[5],
            )
            self.assert_look(tags[role], "littletitle", tint[0], *flags)
        self.assertTrue(self.styles[tags["warning"]].underline)
        self.assert_look(
            tags["hex"], "littletitle", "#123abc", True, title[4], title[5]
        )
        self.assertEqual(len(set(tags.values())), 6)

    def test_paragraph_roles_build_on_event_style_and_pause_on_last_piece(
        self,
    ) -> None:
        """验证段落行内角色叠加在事件样式上、两段间自动补换行，且暂停仅作用于最后一段非空文本。"""
        spans = (TextSpan("金"), TextSpan("粗", "strong"))
        event = NarrativeEvent(
            META,
            (paragraph(*spans), paragraph(TextSpan("尾\n"))),
            pause=True,
            style="gold_enrod",
        )
        STREAM.render(event)
        self.assertEqual(
            [(kind, width, text) for kind, width, _style, text in self.drawn],
            [
                ("NormalDraw", 0, "金"),
                ("NormalDraw", 0, "粗"),
                ("NormalDraw", 0, "\n"),
                ("WaitDraw", 0, "尾\n"),
            ],
        )
        self.assertEqual(
            {self.drawn[index][2] for index in (0, 2, 3)}, {"gold_enrod"}
        )
        gold = look("gold_enrod")
        self.assert_look(
            self.drawn[1][2], "gold_enrod", gold[0], True, gold[4], gold[5]
        )

    def test_dividers_and_scene_breaks_draw_lines_at_text_width(self) -> None:
        """验证分隔线前的段落自动补换行，且分隔线块与 SceneBreak 均以配置宽度调用 LineDraw。"""
        STREAM.render(
            NarrativeEvent(
                META,
                (paragraph(TextSpan("上")), TextBlock("divider", char="＝")),
            )
        )
        STREAM.render(SceneBreak(META, "~"))
        self.assertEqual(
            self.drawn,
            [
                ("NormalDraw", 0, "standard", "上"),
                ("NormalDraw", 0, "standard", "\n"),
                ("LineDraw", self.width, "standard", "＝"),
                ("LineDraw", self.width, "standard", "~"),
            ],
        )

    def test_each_block_starts_on_a_new_line(self) -> None:
        """验证非末块结尾无换行时自动补换行，已有换行的段落与末块不额外追加换行。"""
        blocks = (
            paragraph(TextSpan("First")),
            paragraph(TextSpan("Second\n")),
            TextBlock("heading", (TextSpan("Title"),)),
            paragraph(TextSpan("Last")),
        )
        STREAM.render(NarrativeEvent(META, blocks))
        self.assertEqual(
            [text for _kind, _width, _style, text in self.drawn],
            ["First", "\n", "Second\n", "Title", "\n", "Last"],
        )

    def test_pause_waits_after_the_last_visible_text(self) -> None:
        """验证暂停事件在末段非空文本用 WaitDraw，全空提示仍绘制单个 WaitDraw。"""
        spans = (TextSpan("看"), TextSpan(""))
        STREAM.render(NarrativeEvent(META, (paragraph(*spans),), pause=True))
        ui_hooks.emit_notice("", wait=True)
        self.assertEqual(
            [(kind, text) for kind, _width, _style, text in self.drawn],
            [("WaitDraw", "看"), ("NormalDraw", ""), ("WaitDraw", "")],
        )

    def test_role_on_a_modifier_style_keeps_its_base_look(self) -> None:
        """验证修饰后缀样式 gold_enrod_bold 叠加 emphasis 时保留基色、背景、字体与加粗并启用斜体。"""
        spans = (TextSpan("斜", "emphasis"),)
        event = NarrativeEvent(
            META, (paragraph(*spans),), style="gold_enrod_bold"
        )
        STREAM.render(event)
        gold = look("gold_enrod")
        self.assert_look(
            self.drawn[0][2], "gold_enrod", gold[0], True, False, True
        )


class ProtocolBoundaryTest(FastTestCase):
    """叙事事件协议模块的导入边界测试。"""

    def test_imports_only_stdlib(self) -> None:
        """验证 Script/Protocol/narrative_events.py 中的全部导入语句仅导入 Python 标准库模块。"""
        path = os.path.join(ROOT, "Script", "Protocol", "narrative_events.py")
        with open(path, encoding="utf-8") as source:
            tree = ast.parse(source.read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add("." * node.level + (node.module or ""))
        self.assertTrue(names)
        self.assertEqual(
            {
                name
                for name in names
                if name.split(".")[0] not in sys.stdlib_module_names
            },
            set(),
        )
