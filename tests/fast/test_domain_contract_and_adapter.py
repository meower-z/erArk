"""
领域契约与事件流适配器的快速单元测试。
验证独立导入约束、数据校验与只读快照，以及适配器的渲染、暂停与清屏行为。
"""

import subprocess
import sys
from pathlib import Path
from typing import cast

from Script.Modules.tk_ui.event_stream_adapter import EventStreamAdapter, Plan
from Script.Protocol import (
    BoundarySnapshot,
    ChoiceOption,
    ChoicePrompt,
    Clear,
    CommandOutcome,
    DeltaEntry,
    DeltaEvent,
    EventMeta,
    NarrativeEvent,
    Pause,
    RenderChunk,
    SceneBreak,
    ScriptedUiPort,
    SnapshotMeta,
    StyleDefOp,
    TextBlock,
    TextOp,
    TextPrompt,
    TextSpan,
    default_first_option,
)
from tests.fast.base import FastTestCase

ROOT = Path(__file__).resolve().parents[2]
META = EventMeta(actors=(7,), location="office", involves_player=True)
ISOLATION = """
import sys
sys.path.insert(0, sys.argv[1])
sys.modules.update(tkinter=None, PIL=None)
import Script.Protocol.domain_contract
import Script.Modules.tk_ui.event_stream_adapter
loaded = [n for n, module in sys.modules.items() if module is not None and n != "__main__"]
print(sorted(n for n in loaded if n.split(".")[0] not in sys.stdlib_module_names
             and not n.startswith("Script.Protocol")))
"""
ADAPTER_IMPORTS = (
    "['Script', 'Script.Modules', 'Script.Modules.tk_ui', "
    "'Script.Modules.tk_ui.event_stream_adapter']"
)


def _event(rows: int, tag: str) -> NarrativeEvent:
    return NarrativeEvent(META, "\n".join(f"{tag}{i}" for i in range(rows)))


def _trace(port: ScriptedUiPort) -> list[str]:
    trace: list[str] = []
    for event in port.events:
        match event:
            case RenderChunk():
                ops = event.ops
                trace.append(
                    "".join(o.text for o in ops if isinstance(o, TextOp))
                )
            case Pause():
                trace.append("<pause>")
            case Clear():
                trace.append(f"<clear {event.target}>")
    return trace


def _ops(port: ScriptedUiPort) -> list[object]:
    return [
        op for e in port.events if isinstance(e, RenderChunk) for op in e.ops
    ]


def _adapter(
    port: ScriptedUiPort, *, viewport_lines: int = 24, line_width: int = 80
) -> EventStreamAdapter:
    return EventStreamAdapter(
        port,
        font="mono",
        font_size=12,
        viewport_lines=viewport_lines,
        line_width=line_width,
    )


def _run(viewport_lines: int, *heights: int) -> list[str]:
    port = ScriptedUiPort(default_first_option())
    adapter = _adapter(port, viewport_lines=viewport_lines)
    adapter.push_batch([_event(h, f"e{n}.") for n, h in enumerate(heights)])
    port.flush()
    return _trace(port)


def _text(*heights: int) -> str:
    return "".join(
        "\n".join(f"e{n}.{i}" for i in range(h)) + "\n"
        for n, h in enumerate(heights)
        if h
    )


class DomainContractTest(FastTestCase):
    """验证领域契约模块的独立导入、字段校验与只读边界快照行为。"""

    def test_contract_and_adapter_import_no_ui_or_game_modules(self) -> None:
        """验证屏蔽 tkinter 与 PIL 时导入契约和适配器不加载界面或游戏模块。"""
        command = [sys.executable, "-I", "-S", "-c", ISOLATION, str(ROOT)]
        result = subprocess.run(command, capture_output=True, check=False)
        output = (result.returncode, result.stdout.decode().strip())
        self.assertEqual(output, (0, ADAPTER_IMPORTS), result.stderr)

    def test_rich_text_validates_color_and_heading_level(self) -> None:
        """验证富文本颜色提示格式校验、标题层级范围校验与 TextBlock.plain 构造。"""
        self.assertEqual(
            TextSpan("x", "accent", "#A1b2C3").color_hint, "#A1b2C3"
        )
        for hint in ("red", "#12345", "#1234567", "#GGGGGG", "#ffffff\n"):
            with self.subTest(hint=hint), self.assertRaises(ValueError):
                TextSpan("x", color_hint=hint)
        for level in (0, 7):
            with self.subTest(level=level), self.assertRaises(ValueError):
                TextBlock((), "heading", level)
        plain = TextBlock((TextSpan("hi"),), "paragraph", 1)
        self.assertEqual(TextBlock.plain("hi"), plain)

    def test_events_and_prompts_reject_empty_or_ambiguous_payloads(
        self,
    ) -> None:
        """验证事件、提示与快照元数据拒绝空或非法载荷并校验默认值。"""
        option = ChoiceOption("a", "A")
        disabled = ChoiceOption("a", "A", enabled=False)
        rejected = {
            "narrative without text or blocks": lambda: NarrativeEvent(META),
            "delta event without entries": lambda: DeltaEvent(META, ()),
            "delta entry without field": lambda: DeltaEntry("A", "", delta=1),
            "delta entry without values": lambda: DeltaEntry("A", "hp"),
            "delta entry with blank target": lambda: DeltaEntry(" ", "hp", 1),
            "option without id": lambda: ChoiceOption("", "A"),
            "option without label": lambda: ChoiceOption("a", ""),
            "choice without options": lambda: ChoicePrompt("p", "t", ()),
            "choice without id": lambda: ChoicePrompt("", "t", (option,)),
            "choice with repeated ids": lambda: ChoicePrompt(
                "p", "t", (option, ChoiceOption("a", "B"))
            ),
            "choice with only disabled options": lambda: ChoicePrompt(
                "p", "t", (disabled,)
            ),
            "text prompt without id": lambda: TextPrompt("", "t"),
            "text prompt with zero length": lambda: TextPrompt(
                "p", "t", max_length=0
            ),
            "negative revision": lambda: SnapshotMeta(-1, True, 0, 0),
            "negative day": lambda: SnapshotMeta(0, True, -1, 0),
            "negative time slot": lambda: SnapshotMeta(0, True, 0, -1),
        }
        for name, build in rejected.items():
            with self.subTest(name), self.assertRaises(ValueError):
                build()
        with self.assertRaises(TypeError):
            DeltaEntry(cast(str, 7), "hp", delta=1)
        with self.assertRaises(TypeError):
            DeltaEntry("A", "hp", delta=1, target_id=cast(int, True))
        self.assertEqual(TextPrompt("p", "t", max_length=None).max_length, None)
        cancellable = ChoicePrompt("p", "t", (disabled,), allow_cancel=True)
        self.assertEqual(cancellable.options, (disabled,))
        self.assertEqual(SceneBreak().meta.category, "scene_break")

    def test_boundary_snapshot_data_is_a_deep_read_only_copy(self) -> None:
        """验证边界快照递归冻结嵌套容器、隔离外部修改、拒绝写入与不支持的值类型，且指令结果保留快照与事件。"""
        rooms: dict[str, list[str]] = {"lab": ["a"]}
        tags = {"x"}
        source: dict[str, object] = {"money": 10, "rooms": rooms, "tags": tags}
        snapshot = BoundarySnapshot(SnapshotMeta(3, True, 2, 1), source)
        source["money"] = 99
        rooms["lab"].append("b")
        rooms["dock"] = []
        tags.add("y")
        frozen_rooms = cast(dict[str, object], snapshot.data["rooms"])
        expected = {"money": 10, "rooms": {"lab": ("a",)}, "tags": {"x"}}
        self.assertEqual(dict(snapshot.data), expected)
        with self.assertRaises(TypeError):
            cast(dict[str, object], snapshot.data)["money"] = 0
        with self.assertRaises(TypeError):
            frozen_rooms["dock"] = ()
        with self.assertRaises(TypeError):
            cast(list[object], frozen_rooms["lab"])[0] = "c"
        with self.assertRaises(AttributeError):
            cast(set[str], snapshot.data["tags"]).add("y")
        with self.assertRaises(TypeError):
            BoundarySnapshot(SnapshotMeta(0, True, 0, 0), {"bad": object()})
        delta = DeltaEvent(META, (DeltaEntry("base", "money", delta=-5),))
        outcome = CommandOutcome(True, snapshot, (delta,))
        self.assertEqual((outcome.events, outcome.error), ((delta,), ""))
        self.assertIs(outcome.snapshot.data, snapshot.data)


class EventStreamAdapterTest(FastTestCase):
    """验证事件流适配器的参数校验、渲染映射、行数估算与暂停清屏规则。"""

    def test_rejects_empty_viewport_line_width_or_font(self) -> None:
        """验证视口行数或行宽小于 1、字体为空或字号不大于 0 时构造适配器抛出 ValueError。"""
        port = ScriptedUiPort(default_first_option())
        with self.assertRaises(ValueError):
            _adapter(port, viewport_lines=0)
        with self.assertRaises(ValueError):
            _adapter(port, line_width=0)
        with self.assertRaises(ValueError):
            EventStreamAdapter(port, font="", font_size=12)
        with self.assertRaises(ValueError):
            EventStreamAdapter(port, font="mono", font_size=0)

    def test_scrolling_queue_pauses_before_event_that_fills_view(self) -> None:
        """验证滚动队列模式在事件填满视口前暂停且不清空屏幕。"""
        trace = _run(10, 4, 5, 1, 3)
        self.assertEqual(trace, [_text(4, 5), "<pause>", _text(0, 0, 1, 3)])

    def test_event_taller_than_view_is_never_split(self) -> None:
        """验证高度超过视口的单条事件完整送出，不在事件中间插入暂停。"""
        trace = _run(5, 8, 3, 8, 1)
        expected = [
            _text(8),
            "<pause>",
            _text(0, 3),
            "<pause>",
            _text(0, 0, 8),
            "<pause>",
            _text(0, 0, 0, 1),
        ]
        self.assertEqual(trace, expected)

    def test_page_clear_mode_clears_after_each_pause(self) -> None:
        """验证切换为翻页清屏模式后在触发暂停时同步清空屏幕。"""
        port = ScriptedUiPort(default_first_option())
        adapter = _adapter(port, viewport_lines=10)
        adapter.push(_event(4, "e0."))
        adapter.set_mode("page_clear")
        adapter.push_batch([_event(5, "e1."), _event(1, "e2.")])
        port.flush()
        expected = [_text(4, 5), "<pause>", "<clear screen>", _text(0, 0, 1)]
        self.assertEqual(_trace(port), expected)

    def test_scene_break_pauses_only_over_unread_lines(self) -> None:
        """验证场景分隔仅在存在未读行时暂停，并在每次遇到时清空屏幕。"""
        port = ScriptedUiPort(default_first_option())
        adapter = _adapter(port)
        adapter.push_batch([SceneBreak(), _event(2, "e0."), SceneBreak()])
        expected = ["<clear screen>", _text(2), "<pause>", "<clear screen>"]
        self.assertEqual(_trace(port), expected)

    def test_end_turn_keeps_prompt_on_screen_only_when_it_fits(self) -> None:
        """验证回合结束仅在后续提示能同屏放下时跳过暂停与清屏。"""
        turn_page = ["<pause>", "<clear screen>"]
        cases = {
            "prompt fits": (3, True, []),
            "prompt fills view": (4, True, turn_page),
            "no prompt": (0, True, turn_page),
            "keep screen": (0, False, ["<pause>"]),
        }
        for name, (prompt_lines, clear_screen, tail) in cases.items():
            port = ScriptedUiPort(default_first_option())
            adapter = _adapter(port, viewport_lines=10)
            adapter.push(_event(6, "e0."))
            adapter.end_turn(
                following_prompt_lines=prompt_lines, clear_screen=clear_screen
            )
            adapter.push(_event(9, "e1."))
            port.flush()
            with self.subTest(name):
                expected = [_text(6), *tail, _text(0, 9)]
                if not tail:
                    expected = [_text(6, 9)]
                self.assertEqual(_trace(port), expected)

    def test_end_turn_on_read_screen_clears_without_pause(self) -> None:
        """验证无未读行时调用回合结束直接清屏而不触发暂停。"""
        port = ScriptedUiPort(default_first_option())
        adapter = _adapter(port)
        adapter.push_batch([_event(2, "e0."), SceneBreak()])
        adapter.end_turn(following_prompt_lines=1)
        trace = [_text(2), "<pause>", "<clear screen>", "<clear screen>"]
        self.assertEqual(_trace(port), trace)

    def test_rich_text_maps_roles_to_styles_and_defines_hints_once(
        self,
    ) -> None:
        """验证富文本语义角色映射、颜色提示样式去重以及引用与分隔线渲染。"""
        port = ScriptedUiPort(default_first_option())
        adapter = _adapter(port, line_width=6)
        hint = TextSpan("Amiya", "character_color", "#FF8800")
        story = NarrativeEvent(
            META,
            "intro",
            (
                TextBlock((TextSpan("Day 1"),), "heading", 2),
                TextBlock(
                    (
                        hint,
                        TextSpan(" says ", "emphasis"),
                        TextSpan("stop", "strong"),
                        TextSpan("!", "warning"),
                        TextSpan("*", "accent"),
                        TextSpan("Boss", "heading", "#00aa00"),
                    )
                ),
                TextBlock((TextSpan("quoted"), hint), "quote"),
                TextBlock((), "divider"),
            ),
        )
        orange = "hint_ff8800_standard"
        green = "hint_00aa00_littletitle"
        self.assertEqual(adapter.estimate_lines(story), 10)
        adapter.push_batch(
            [story, NarrativeEvent(META, blocks=(TextBlock((hint,)),))]
        )
        port.flush()
        expected = [
            TextOp("intro"),
            TextOp("\n"),
            TextOp("Day 1", ("littletitle",)),
            TextOp("\n"),
            StyleDefOp(orange, "#FF8800", "", "mono", 12, False, False, False),
            TextOp("Amiya", ("standard", orange)),
            TextOp(" says ", ("standard_italic",)),
            TextOp("stop", ("standard_bold",)),
            TextOp("!", ("warning",)),
            TextOp("*", ("gold_enrod",)),
            StyleDefOp(green, "#00aa00", "", "mono", 12, False, False, False),
            TextOp("Boss", ("littletitle", green)),
            TextOp("\n"),
            TextOp("> "),
            TextOp("quoted"),
            TextOp("Amiya", ("standard", orange)),
            TextOp("\n"),
            TextOp("------\n"),
            TextOp("Amiya", ("standard", orange)),
            TextOp("\n"),
        ]
        self.assertEqual(_ops(port), expected)

    def test_delta_entries_render_as_one_line_each(self) -> None:
        """验证数值变化事件按每条记录单独渲染一行并正确格式化符号与单位。"""
        port = ScriptedUiPort(default_first_option())
        adapter = _adapter(port)
        entries = (
            DeltaEntry("阿米娅", "favorability", 15, 120, target_id=7),
            DeltaEntry("base", "money", delta=-30, unit="G"),
            DeltaEntry("阿米娅", "mood", new_value="calm", target_id=7),
            DeltaEntry("阿米娅", "fatigue", delta=0.5),
            DeltaEntry("阿米娅", "asleep", delta=True),
        )
        adapter.push(DeltaEvent(META, entries))
        port.flush()
        lines = [
            "阿米娅 favorability +15 -> 120\n",
            "base money -30G\n",
            "阿米娅 mood -> calm\n",
            "阿米娅 fatigue +0.5\n",
            "阿米娅 asleep True\n",
        ]
        self.assertEqual(_ops(port), [TextOp(line) for line in lines])

    def test_estimate_lines_wraps_wide_characters_at_line_width(self) -> None:
        """验证行数估算按行宽折行处理东亚宽字符、组合字符、空行与各类事件。"""
        adapter = _adapter(
            ScriptedUiPort(default_first_option()), line_width=10
        )
        cases = {
            "一二三四五": 1,
            "一二三四五六": 2,
            "abcdefghij": 1,
            "abcdefghijk": 2,
            "é" * 10: 1,
            "a\n\nb": 3,
            "x" * 25: 3,
        }
        for text, lines in cases.items():
            with self.subTest(text=text):
                event = NarrativeEvent(META, text)
                self.assertEqual(adapter.estimate_lines(event), lines)
        entry = DeltaEntry("A", "hp", delta=1)
        self.assertEqual(adapter.estimate_lines(DeltaEvent(META, (entry,))), 1)
        self.assertEqual(adapter.estimate_lines(SceneBreak()), 1)
        narrow = _adapter(ScriptedUiPort(default_first_option()), line_width=5)
        self.assertEqual(
            narrow.estimate_lines(NarrativeEvent(META, "一二三四五")), 3
        )

    def test_estimate_lines_ignores_zero_width_marks(self) -> None:
        """验证行宽为 1 时，行尾紧跟的 Mn 非间距标记与 Me 封闭标记计 0 格且不触发额外换行。"""
        adapter = _adapter(ScriptedUiPort(default_first_option()), line_width=1)
        for text in ("\u4e00\u0301", "a\u20dd"):
            with self.subTest(text=ascii(text)):
                event = NarrativeEvent(META, text)
                self.assertEqual(adapter.estimate_lines(event), 1)

    def test_color_hint_keeps_role_decorations_and_font(self) -> None:
        """验证颜色提示样式保留角色下划线、加粗或斜体修饰与配置字体字号，并在文本指令中组合双样式标签。"""
        port = ScriptedUiPort(default_first_option())
        spans = (
            TextSpan("!", "warning", "#FF0000"),
            TextSpan("b", "strong", "#FF0000"),
            TextSpan("i", "emphasis", "#FF0000"),
        )
        _adapter(port).push(NarrativeEvent(META, blocks=(TextBlock(spans),)))
        port.flush()
        red = "hint_ff0000_"
        expected = [
            StyleDefOp(
                red + "warning", "#FF0000", "", "mono", 12, False, True, False
            ),
            TextOp("!", ("warning", red + "warning")),
            StyleDefOp(
                red + "standard_bold",
                "#FF0000",
                "",
                "mono",
                12,
                True,
                False,
                False,
            ),
            TextOp("b", ("standard_bold", red + "standard_bold")),
            StyleDefOp(
                red + "standard_italic",
                "#FF0000",
                "",
                "mono",
                12,
                False,
                False,
                True,
            ),
            TextOp("i", ("standard_italic", red + "standard_italic")),
            TextOp("\n"),
        ]
        self.assertEqual(_ops(port), expected)

    def test_plans_describe_steps_without_calling_the_port(self) -> None:
        """验证 plan_event、plan_turn_end 与 commit 在不调用端口的情况下准确计算步骤与未读行数。"""
        port = ScriptedUiPort(default_first_option())
        adapter = _adapter(port, viewport_lines=10)
        first = adapter.plan_event(_event(6, "e0."))
        self.assertEqual(first.unread_lines, 6)
        self.assertNotIn("pause", first.steps)
        adapter.commit(first)
        second = adapter.plan_event(_event(5, "e1."))
        self.assertEqual((second.steps[0], second.unread_lines), ("pause", 5))
        self.assertEqual(
            adapter.plan_turn_end(following_prompt_lines=3), Plan((), 0)
        )
        turn_page = adapter.plan_turn_end(following_prompt_lines=4)
        self.assertEqual(turn_page, Plan(("pause", "clear_screen"), 0))
        adapter.commit(second)
        self.assertEqual(adapter.plan_event(SceneBreak()).steps[0], "pause")
        self.assertEqual(port.events, [])
