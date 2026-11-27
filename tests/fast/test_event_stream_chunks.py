"""
事件流按条分块输出测试
======================
本模块验证 EventStreamAdapter.render 在绘制单条事件前后各刷出一次协议端口。
测试在事件前预先写入缓冲输出，再依次绘制叙事、数值变化与场景分隔三类事件。
断言前置缓冲输出与每条事件各自发布为独立的 RenderChunk。
"""

from unittest import mock

from Script.Core import io_init
from Script.Modules.tk_ui.event_stream_adapter import STREAM
from Script.Protocol import (
    RenderChunk,
    ScriptedUiPort,
    TextOp,
    default_first_option,
)
from Script.Protocol.delta_events import DeltaEntry, DeltaEvent
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
""" 测试事件共用的最小 EventMeta 示例。 """


def emit_text(self: draw.NormalDraw | draw.LineDraw) -> None:
    """
    将绘制对象的文本与样式经 io_init.era_print 发往协议端口。
    该函数在测试中替代被屏蔽的 draw.NormalDraw.draw 与 draw.LineDraw.draw。
    Keyword arguments:
    self -- draw.NormalDraw | draw.LineDraw，待输出的普通文本或分隔线绘制对象
    Return arguments:
    None -- 无返回值
    """
    io_init.era_print(self.text, self.style)


class ChunkPerEventTest(FastTestCase):
    """验证 STREAM.render 在绘制每条事件前后刷出端口并独立分块的测试类。"""

    def setUp(self) -> None:
        """
        调用父类准备方法以复原测试环境。
        通过 enterContext 将 draw.NormalDraw.draw 与 draw.LineDraw.draw 临时替换为 emit_text。
        创建未设 listener 且采用 default_first_option 应答器的 ScriptedUiPort 存入 self.port。
        经 io_init.configure 将 self.port 接入协议端口。
        Return arguments:
        None -- 无返回值
        """
        super().setUp()
        for cls in (draw.NormalDraw, draw.LineDraw):
            self.enterContext(mock.patch.object(cls, "draw", emit_text))
        self.port = ScriptedUiPort(default_first_option())
        io_init.configure(self.port)

    def chunks(self) -> list[str]:
        """
        按顺序提取 self.port.events 中各 RenderChunk 的文本内容。
        每个 RenderChunk 内部将所有 TextOp 的 text 依次拼接为一个字符串。
        Return arguments:
        list[str] -- 与已发布 RenderChunk 一一对应的文本列表
        """
        return [
            "".join(op.text for op in event.ops if isinstance(op, TextOp))
            for event in self.port.events
            if isinstance(event, RenderChunk)
        ]

    def test_each_event_is_its_own_chunk(self) -> None:
        """
        先经 io_init.era_print 写入前置缓冲文本，模拟事件前残留的面板输出。
        再依次经 STREAM.render 绘制双段落 NarrativeEvent、单项 DeltaEvent 与 SceneBreak。
        每次绘制后在对应子测试中断言末分块文本等于该事件的预期文本。
        最后断言全部已发布分块依次等于前置缓冲文本与三条事件文本。
        Return arguments:
        None -- 无返回值
        """
        events = (
            (
                NarrativeEvent(
                    META,
                    (
                        TextBlock("paragraph", (TextSpan("甲"),)),
                        TextBlock("paragraph", (TextSpan("乙"),)),
                    ),
                ),
                "甲\n乙",
            ),
            (
                DeltaEvent(META, (DeltaEntry("丙", "声望", 1),)),
                "丙 声望：+1\n",
            ),
            (SceneBreak(META, "-"), "-"),
        )
        io_init.era_print("面板\n")
        for event, text in events:
            with self.subTest(type(event).__name__):
                STREAM.render(event)
                self.assertEqual(self.chunks()[-1], text)
        self.assertEqual(
            self.chunks(), ["面板\n", *(text for _, text in events)]
        )
