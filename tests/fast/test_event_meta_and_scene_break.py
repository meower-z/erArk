"""
事件元数据事实字段与分隔线事件流测试
====================================
- 元数据校验（EventMetaTest）：验证 EventMeta 四个事实字段的默认值、位置传参与非法类型校验。
- 回调事件流（EventStreamHookTest）：验证提示与数值回调透传事实而不改变绘制，以及分隔线经 SceneBreak 绘制。
"""

from collections.abc import Callable
from unittest import mock

from Script.Config import normal_config
from Script.Modules.gameplay_resolution import ui_hooks
from Script.Modules.tk_ui import callbacks
from Script.Modules.tk_ui.event_stream_adapter import STREAM
from Script.Protocol.delta_events import DeltaEntry, DeltaEvent
from Script.Protocol.narrative_events import (
    EventMeta,
    NarrativeEvent,
    SceneBreak,
)
from Script.UI.Moudle import draw
from tests.fast.base import FastTestCase

PLACE = "博士办公室"
""" 测试用的示例地点字符串。 """
NEUTRAL = ((), "", False, "")
""" EventMeta 四个事实字段的默认中性值元组。 """
TAGGED = ((0, 7), PLACE, True, "test")
""" 测试用的示例事实字段元组。 """
type Drawn = tuple[str, float, str, str]
""" 一次绘制调用的类名、宽度、样式名与文本。 """
type Rendered = NarrativeEvent | SceneBreak | DeltaEvent
""" STREAM.render 接收的事件联合类型。 """


def build(
    make: Callable[..., object], *args: object, **kwargs: object
) -> object:
    """以任意位置与关键字参数调用 make，供测试动态构造对象或传入非法字段类型。"""
    return make(*args, **kwargs)


def facts(meta: object) -> tuple[object, ...]:
    """按顺序读取 meta 的 actors、location、involves_player 与 category 并返回四元组。"""
    return tuple(
        getattr(meta, name)
        for name in ("actors", "location", "involves_player", "category")
    )


class EventMetaTest(FastTestCase):
    """EventMeta 四个事实字段的默认值与类型校验测试。"""

    def test_facts_default_to_neutral_and_reject_bad_types(self) -> None:
        """验证 EventMeta 事实字段默认取中性值、支持位置传入，并对八种非法类型抛出 ValueError。"""
        self.assertEqual(facts(EventMeta(0, 0, "a")), NEUTRAL)
        self.assertEqual(
            facts(build(EventMeta, 0, 0, "a", (0, 7), PLACE, True, "test")),
            TAGGED,
        )
        cases: tuple[tuple[str, object], ...] = (
            ("actors", [1]),
            ("actors", 1),
            ("actors", (-1,)),
            ("actors", (True,)),
            ("actors", ("1",)),
            ("location", None),
            ("involves_player", 1),
            ("category", None),
        )
        for name, bad in cases:
            with (
                self.subTest(name=name, bad=bad),
                self.assertRaises(ValueError),
            ):
                build(EventMeta, 0, 0, "a", **{name: bad})


class EventStreamHookTest(FastTestCase):
    """提示、数值变化与分隔线回调经 STREAM 产出事件并执行 Tk 绘制的测试。"""

    def setUp(self) -> None:
        """
        打桩 NormalDraw、WaitDraw 与 LineDraw 的 draw 方法并包装 STREAM.render 以记录事件。
        将 ui_hooks 提示、数值与分隔线回调设为真实 Tk 回调，并初始化记录列表与文本宽度。
        """
        super().setUp()
        self.drawn: list[Drawn] = []
        self.events: list[Rendered] = []
        for cls in (draw.NormalDraw, draw.WaitDraw, draw.LineDraw):
            self.enterContext(
                mock.patch.object(
                    cls, "draw", autospec=True, side_effect=self.record
                )
            )
        render = STREAM.render
        self.enterContext(
            mock.patch.object(
                STREAM, "render", side_effect=lambda e: self.keep(render, e)
            )
        )
        for name, hook in (
            ("_notices", callbacks.draw_notice),
            ("_deltas", callbacks.draw_delta),
            ("_dividers", callbacks.draw_divider),
        ):
            self.enterContext(mock.patch.object(ui_hooks, name, [hook]))
        self.width = normal_config.config_normal.text_width

    def record(self, now: draw.NormalDraw | draw.LineDraw) -> None:
        """记录一次绘制调用的类名、宽度、样式名与文本内容。"""
        self.drawn.append((type(now).__name__, now.width, now.style, now.text))

    def keep(self, render: Callable[[Rendered], None], event: Rendered) -> None:
        """将收到的事件追加到 self.events，再调用原始 render 完成绘制。"""
        self.events.append(event)
        render(event)

    def take(self) -> tuple[list[Rendered], list[Drawn]]:
        """返回当前收集的事件与绘制记录副本，并清空两份缓存列表。"""
        taken = (self.events[:], self.drawn[:])
        self.events.clear()
        self.drawn.clear()
        return taken

    def test_notice_carries_facts_without_changing_the_drawing(self) -> None:
        """
        验证 emit_notice 不传、全传或仅传 actors 事实时均产出携带对应元数据的 NarrativeEvent。
        同时验证三种调用均绘制相同的单条文本宽度 WaitDraw。
        """
        ui_hooks.emit_notice("提示\n", wait=True, use_text_width=True)
        plain, plain_drawn = self.take()
        ui_hooks.emit_notice(
            "提示\n",
            wait=True,
            use_text_width=True,
            actors=(0, 7),
            location=PLACE,
            involves_player=True,
            category="test",
        )
        tagged, tagged_drawn = self.take()
        ui_hooks.emit_notice(
            "提示\n", wait=True, use_text_width=True, actors=(7,)
        )
        partial, partial_drawn = self.take()
        self.assertEqual(
            [type(event) for event in plain + tagged + partial],
            [NarrativeEvent] * 3,
        )
        self.assertEqual(facts(plain[0].meta), NEUTRAL)
        self.assertEqual(facts(tagged[0].meta), TAGGED)
        self.assertEqual(facts(partial[0].meta), ((7,), "", False, ""))
        self.assertEqual(
            {e.meta.source for e in plain + tagged + partial},
            {"ui_hooks.notice"},
        )
        expected = [("WaitDraw", self.width, "standard", "提示\n")]
        self.assertEqual(plain_drawn, expected)
        self.assertEqual(tagged_drawn, expected)
        self.assertEqual(partial_drawn, expected)

    def test_delta_carries_facts_without_changing_the_drawing(self) -> None:
        """
        验证 emit_delta 不传或传入全部事实时均产出携带对应元数据的 DeltaEvent。
        同时验证两种调用均绘制相同的单条 WaitDraw。
        """
        entries = (DeltaEntry("干员甲", "好感", 5, 1, 6),)
        ui_hooks.emit_delta(entries, source="test.delta", wait=True)
        plain, plain_drawn = self.take()
        ui_hooks.emit_delta(
            entries,
            source="test.delta",
            wait=True,
            actors=(0, 7),
            location=PLACE,
            involves_player=True,
            category="test",
        )
        tagged, tagged_drawn = self.take()
        self.assertEqual(
            [type(event) for event in plain + tagged], [DeltaEvent] * 2
        )
        self.assertEqual(facts(plain[0].meta), NEUTRAL)
        self.assertEqual(facts(tagged[0].meta), TAGGED)
        self.assertEqual(
            {e.meta.source for e in plain + tagged}, {"test.delta"}
        )
        expected = [("WaitDraw", 0, "standard", "干员甲 好感：+5（1 → 6）\n")]
        self.assertEqual(plain_drawn, expected)
        self.assertEqual(tagged_drawn, expected)

    def test_divider_renders_a_scene_break_at_text_width(self) -> None:
        """
        验证 emit_divider 产出默认与指定字符的 SceneBreak（来源 ui_hooks.divider、中性事实）。
        同时验证两条事件均按文本宽度经 LineDraw 绘制对应分隔字符。
        """
        ui_hooks.emit_divider()
        ui_hooks.emit_divider("=")
        events, drawn = self.take()
        self.assertEqual(
            [(type(e), e.meta.source, facts(e.meta)) for e in events],
            [(SceneBreak, "ui_hooks.divider", NEUTRAL)] * 2,
        )
        self.assertEqual(
            drawn,
            [
                ("LineDraw", self.width, "standard", "-"),
                ("LineDraw", self.width, "standard", "="),
            ],
        )
