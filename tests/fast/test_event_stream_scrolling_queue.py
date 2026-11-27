"""
事件流滚动队列测试
==================
- 行数预算（ScrollingQueueTest）：覆盖事件流适配器的行数累计、跨屏自动暂停、整条绘制、
  宽行折行计数、计数清零及默认关闭预算的行为。
"""

from unittest import mock

from Script.Config import normal_config
from Script.Core import flow_handle, io_init
from Script.Modules.tk_ui.event_stream_adapter import STREAM, EventStreamAdapter
from Script.Protocol import (
    BackendEvent,
    Pause,
    ScriptedUiPort,
    default_first_option,
)
from Script.Protocol.narrative_events import (
    EventMeta,
    NarrativeEvent,
    SceneBreak,
    TextBlock,
    TextSpan,
)
from Script.UI.Moudle import draw
from tests.fast.base import FastTestCase

META = EventMeta(0, 0, "test")
""" 测试共用的默认事件元数据。 """
WIDTH = 10
""" 测试中替换 text_width 使用的屏幕列宽。 """
BUDGET = 4
""" 测试中构造带预算适配器使用的屏幕行数上限。 """
WAIT = "|"
""" 测试记录流中用于标记一次暂停请求的符号。 """


def note(text: str, pause: bool = False) -> NarrativeEvent:
    """用默认元数据 META 构造包含单个文本段落的 NarrativeEvent，并按 pause 设置暂停标记。"""
    return NarrativeEvent(
        META, (TextBlock("paragraph", (TextSpan(text),)),), pause=pause
    )


def rows(count: int, mark: str = "行") -> NarrativeEvent:
    """重复双列宽字符 mark 构造在 WIDTH 列宽下占 count 行的单段落 NarrativeEvent。"""
    return note(mark * (WIDTH // 2) * count + "\n")


class ScrollingQueueTest(FastTestCase):
    """EventStreamAdapter 行数预算与自动暂停行为的测试。"""

    def setUp(self) -> None:
        """
        打桩 NormalDraw、WaitDraw 与 LineDraw 的 draw 方法，配置监听暂停的测试端口与列宽 WIDTH，
        并创建预算为 BUDGET 的适配器。
        """
        super().setUp()
        self.parts: list[str] = []
        for cls in (draw.NormalDraw, draw.WaitDraw, draw.LineDraw):
            self.enterContext(
                mock.patch.object(
                    cls, "draw", autospec=True, side_effect=self.record
                )
            )
        io_init.configure(
            ScriptedUiPort(default_first_option(), listener=self.listen)
        )
        self.enterContext(
            mock.patch.object(normal_config.config_normal, "text_width", WIDTH)
        )
        self.queue = EventStreamAdapter(budget=BUDGET)

    def record(self, now: draw.NormalDraw | draw.LineDraw) -> None:
        """记录绘制对象的文本，并在非空 WaitDraw 绘制后调用 flow_handle.askfor_wait() 模拟等待。"""
        self.parts.append(now.text)
        if isinstance(now, draw.WaitDraw) and now.text:
            flow_handle.askfor_wait()

    def listen(self, event: BackendEvent) -> None:
        """监听测试端口收到的事件，遇到 Pause 时向记录列表追加 WAIT 标记。"""
        if isinstance(event, Pause):
            self.parts.append(WAIT)

    def shown(self) -> str:
        """将已记录的绘制文本与暂停标记按顺序拼接为单个字符串返回。"""
        return "".join(self.parts)

    def feed(self, *events: NarrativeEvent | SceneBreak) -> str:
        """将传入事件依次交由 self.queue.render 绘制，并返回当前的拼接记录文本。"""
        for event in events:
            self.queue.render(event)
        return self.shown()

    def test_small_events_fill_the_screen_before_one_pause(self) -> None:
        """
        验证多条单行事件在累计行数未达 BUDGET 前不暂停，将达 BUDGET 时先暂停再绘制，
        且暂停后从新事件自身行数重新累计。
        """
        self.assertEqual(self.shown(), "")
        self.assertEqual(
            self.feed(note("甲\n"), note("乙\n"), note("丙\n")), "甲\n乙\n丙\n"
        )
        self.assertEqual(self.feed(note("丁\n")), "甲\n乙\n丙\n|丁\n")
        self.assertEqual(
            self.feed(note("戊\n"), note("己\n"), note("庚\n")),
            "甲\n乙\n丙\n|丁\n戊\n己\n|庚\n",
        )

    def test_overflowing_event_moves_whole_past_the_pause(self) -> None:
        """验证会超出剩余预算的多行事件先暂停再整条输出，且后续新事件再次触发暂停。"""
        tall = rows(3, "长")
        self.assertEqual(self.feed(note("甲\n")), "甲\n")
        self.assertEqual(
            self.feed(tall, note("乙\n")),
            f"甲\n|{tall.blocks[0].spans[0].text}|乙\n",
        )

    def test_oversized_event_on_an_empty_screen_draws_without_a_pause(
        self,
    ) -> None:
        """验证空屏上超过 BUDGET 的单条事件直接整条绘制且不暂停，下一条事件先暂停而再下一条不暂停。"""
        huge = rows(BUDGET + 2, "巨")
        text = huge.blocks[0].spans[0].text
        self.assertEqual(self.feed(huge), text)
        self.assertEqual(
            self.feed(note("甲\n"), note("乙\n")), f"{text}|甲\n乙\n"
        )

    def test_wrapped_line_counts_every_row(self) -> None:
        """验证超宽文本行按折行后的屏幕行数计入预算，14 列文本在 10 列宽下按 2 行累计。"""
        self.assertEqual(
            self.feed(note("一二三四五六七\n"), note("甲\n")),
            "一二三四五六七\n甲\n",
        )
        self.assertEqual(self.feed(note("乙\n")), "一二三四五六七\n甲\n|乙\n")

    def test_explicit_pause_scene_break_and_reset_start_a_new_screen(
        self,
    ) -> None:
        """验证显式 pause=True、reset() 与 SceneBreak 均会清零已输出行数，使后续三条单行事件无需自动暂停。"""
        three = (note("甲\n"), note("乙\n"), note("丙\n"))
        self.assertEqual(
            self.feed(note("甲\n"), note("乙\n", pause=True), *three),
            "甲\n乙\n|甲\n乙\n丙\n",
        )
        self.parts.clear()
        self.queue.reset()
        self.assertEqual(self.feed(*three), "甲\n乙\n丙\n")
        self.parts.clear()
        self.assertEqual(
            self.feed(SceneBreak(META, "="), *three),
            "=甲\n乙\n丙\n",
        )

    def test_default_adapter_never_adds_a_pause(self) -> None:
        """
        验证默认构造的 EventStreamAdapter() 与模块单例 STREAM 连续绘制 2 倍 text_hight 条单行事件时不插入暂停。
        """
        count = 2 * normal_config.config_normal.text_hight
        many = [note(f"{index}\n") for index in range(count)]
        expected = "".join(f"{index}\n" for index in range(count))
        for adapter in (EventStreamAdapter(), STREAM):
            self.parts.clear()
            with self.subTest(adapter=adapter):
                for event in many:
                    adapter.render(event)
                self.assertEqual(self.shown(), expected)
