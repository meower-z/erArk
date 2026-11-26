"""
界面回调刷出钩子测试
====================
HeadlessFlushTest 在无界面子进程中验证 ui_hooks 刷出入口不触碰受限模块。
该测试类验证 emit_flush 在未登记时不触发回调，在登记后按登记顺序调用回调。
TkFlushTest 验证已登记的 Tk 刷出回调经 ui_hooks.emit_flush 将缓冲文本发往协议端口。
"""

from unittest import mock

from Script.Core import io_init
from Script.Modules.gameplay_resolution import ui_hooks
from Script.Protocol import (
    RenderChunk,
    ScriptedUiPort,
    TextOp,
    default_first_option,
)
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import ChildRun, run_ui_free

HEADLESS = """
from Script.Modules.gameplay_resolution import ui_hooks

calls = []
ui_hooks.emit_flush()
payload["unregistered"] = list(calls)
for name in ("first", "second"):
    ui_hooks.on_flush(lambda name=name: calls.append(name))
ui_hooks.emit_flush()
ui_hooks.emit_flush()
payload["registered"] = calls
"""
"""在无界面子进程中执行的测试代码片段，依次记录未登记回调与登记两个回调后调用 emit_flush 的结果。"""


class HeadlessFlushTest(FastTestCase):
    """无界面子进程中的 ui_hooks 刷出回调测试。"""

    child: ChildRun
    """setUpClass 执行 HEADLESS 得到的无界面子进程运行结果。"""

    @classmethod
    def setUpClass(cls) -> None:
        """
        调用父类类级准备并经 run_ui_free 运行 HEADLESS，将结果保存到 cls.child。
        Return arguments:
        None -- 无返回值
        """
        super().setUpClass()
        cls.child = run_ui_free(HEADLESS)

    def test_child_touches_no_ui_module(self) -> None:
        """
        验证无界面子进程未尝试导入也未加载任何默认受限模块。
        Return arguments:
        None -- 无返回值
        """
        self.assertEqual((self.child.attempted, self.child.loaded), ([], []))

    def test_flush_calls_registered_callbacks_in_order(self) -> None:
        """
        验证未登记回调时 emit_flush 不触发调用，登记两个回调后两次调用均按登记顺序执行。
        Return arguments:
        None -- 无返回值
        """
        self.assertEqual(self.child.payload["unregistered"], [])
        self.assertEqual(
            self.child.payload["registered"],
            ["first", "second", "first", "second"],
        )


class TkFlushTest(FastTestCase):
    """已登记 Tk 刷出回调的协议端口输出测试。"""

    def setUp(self) -> None:
        """
        通过 enterContext 托管 io_init._port，使该属性在用例结束后还原。
        创建默认选首项且文本输入返回 "1" 的 ScriptedUiPort 存入 self.port，并经 io_init.configure 接入。
        Return arguments:
        None -- 无返回值
        """
        super().setUp()
        self.enterContext(mock.patch.object(io_init, "_port", io_init._port))
        self.port = ScriptedUiPort(default_first_option("1"))
        io_init.configure(self.port)

    def published(self) -> list[str]:
        """
        按顺序收集 self.port.events 中各 RenderChunk 内所有 TextOp 的文本。
        Return arguments:
        list[str] -- 已发布文本操作中的文本列表
        """
        return [
            op.text
            for event in self.port.events
            if isinstance(event, RenderChunk)
            for op in event.ops
            if isinstance(op, TextOp)
        ]

    def test_emit_flush_publishes_buffered_text(self) -> None:
        """
        验证 io_init.era_print 写入的文本起初未发布，在调用 ui_hooks.emit_flush 后刷出到协议端口。
        Return arguments:
        None -- 无返回值
        """
        io_init.era_print("入睡提示")
        self.assertEqual(self.published(), [])
        ui_hooks.emit_flush()
        self.assertEqual(self.published(), ["入睡提示"])
