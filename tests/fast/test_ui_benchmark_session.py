"""渲染性能基准会话 BenchmarkSession 的快速测试，验证正常完成、渲染异常后超时关窗与主动关窗时的汇总写出及退出码。"""

import json
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from profiling.ui_benchmark_session import BenchmarkSession, BenchmarkState
from Script.Protocol import (
    Cancel,
    Choose,
    Exit,
    SubmitChoice,
    ThreadedUiPort,
)
from tests.fast.base import FastTestCase

TOKEN = "benchmark-token"
"""测试用会话端口的固定鉴权令牌。"""


class FakeRoot:
    """单线程模拟 Tk 根窗口事件循环与毫秒时钟，按到期顺序执行回调并收集回调抛出的异常。"""

    def __init__(self) -> None:
        """初始化模拟时钟、定时器表、异常记录列表与销毁标记。"""
        self.now = 0
        self.timers: dict[str, tuple[int, Callable[[], object]]] = {}
        self.errors: list[Exception] = []
        self.destroyed = False
        self._count = 0

    def after(self, ms: int, func: Callable[[], object], /) -> str:
        """以当前模拟时间加 ms 毫秒登记回调并返回定时器编号。"""
        self._count += 1
        after_id = f"after{self._count}"
        self.timers[after_id] = (self.now + ms, func)
        return after_id

    def after_cancel(self, after_id: str, /) -> None:
        """按定时器编号移除尚未执行的模拟回调。"""
        self.timers.pop(after_id, None)

    def mainloop(self) -> None:
        """按到期时间顺序推进模拟时钟并执行回调，直至定时器为空或窗口销毁。回调抛出的异常记入 errors 后继续循环。"""
        while self.timers and not self.destroyed:
            after_id, (due, func) = min(
                self.timers.items(), key=lambda item: item[1][0]
            )
            del self.timers[after_id]
            self.now = due
            try:
                func()
            except Exception as error:
                self.errors.append(error)

    def destroy(self) -> None:
        """将模拟根窗口标记为已销毁以终止主循环。"""
        self.destroyed = True


class FakeFrontend:
    """连接真实 ThreadedUiPort 的模拟前端，由模拟时钟驱动事件泵并将 Choose 请求转交测试回调处理。"""

    def __init__(
        self,
        port: ThreadedUiPort,
        root: FakeRoot,
        react: Callable[["FakeFrontend", Choose], None],
    ) -> None:
        """附着到协议端口并保存模拟根窗口与 Choose 请求处理回调。"""
        self.port = port
        self.root = root
        self.epoch = port.attach(TOKEN).controller_epoch
        self.closed = False
        self._react = react

    def run(self) -> None:
        """调度首轮事件泵并启动模拟根窗口主循环。"""
        self.root.after(1, self.pump)
        self.root.mainloop()

    def close(self) -> None:
        """首次调用时向端口提交窗口关闭取消应答并销毁模拟根窗口。"""
        if self.closed:
            return
        self.closed = True
        self.port.submit(Cancel(self.epoch, "window closed"))
        self.root.destroy()

    def pump(self) -> None:
        """
        从端口读取一条事件并在遇 Exit 时销毁窗口。非 Exit 事件在遇 Choose 时先调用测试回调，随后继续调度下一轮事件泵。
        """
        event = self.port.receive(self.epoch, 5.0)
        if isinstance(event, Exit):
            self.closed = True
            self.root.destroy()
            return
        if isinstance(event, Choose):
            self._react(self, event)
        self.root.after(1, self.pump)


def answer(frontend: FakeFrontend, request: Choose) -> None:
    """向端口提交选项 "1" 的按钮应答以模拟正常完成单屏渲染。"""
    frontend.port.submit(
        SubmitChoice(frontend.epoch, request.request_id, "1", "button")
    )


def fail_render(frontend: FakeFrontend, request: Choose) -> None:
    """抛出 RuntimeError("render failed") 以模拟渲染回调异常并中断事件泵续订。"""
    raise RuntimeError("render failed")


def close_window(frontend: FakeFrontend, request: Choose) -> None:
    """调用模拟前端 close 方法以模拟窗口被关闭。"""
    frontend.close()


def run_session(
    react: Callable[[FakeFrontend, Choose], None],
) -> tuple[BenchmarkState, dict[str, object], FakeFrontend]:
    """
    以给定的 Choose 处理回调运行一次单屏 BenchmarkSession，在 serve 返回后立即读取临时汇总文件并返回运行状态、
    汇总字典与模拟前端

    参数：
    react (Callable[[FakeFrontend, Choose], None]) -- 收到 Choose 请求时执行的模拟前端处理函数

    返回值类型：tuple[BenchmarkState, dict[str, object], FakeFrontend] -- 会话状态、解析后的汇总字典与模拟前端
    """
    port = ThreadedUiPort(TOKEN)
    frontend = FakeFrontend(port, FakeRoot(), react)
    state: BenchmarkState = {
        "screens_done": 0,
        "screen_wall_times": [],
        "warmup_wall_times": [],
        "warmup_cleared": False,
        "aborted": False,
        "exit_code": 0,
    }
    session = BenchmarkSession(frontend, frontend.root, port, state, 60.0)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "summary.json"

        def report(total_wall: float) -> None:
            """延迟 0.2 秒后将中止标记与总耗时写入临时汇总 JSON，用于验证 serve 等待工作线程写完汇总再返回。"""
            time.sleep(0.2)
            summary = {"aborted": state["aborted"], "total_wall": total_wall}
            path.write_text(json.dumps(summary), encoding="utf-8")

        session.serve(lambda: port.choose(("1",)), report)
        summary = json.loads(path.read_text(encoding="utf-8"))
    return state, summary, frontend


class BenchmarkSessionTest(FastTestCase):
    """验证 BenchmarkSession 在正常应答、渲染异常超时与窗口关闭三种路径下都能回收工作线程并写出准确汇总的测试类。"""

    def test_answered_screen_finishes_with_exit_code_zero(self) -> None:
        """断言单屏正常应答后会话退出码为 0、汇总 aborted 为 False，且模拟主循环未记录异常。"""
        state, summary, frontend = run_session(answer)
        self.assertEqual(state["exit_code"], 0)
        self.assertFalse(summary["aborted"])
        self.assertEqual(frontend.root.errors, [])

    def test_timeout_closes_window_after_render_failure(self) -> None:
        """
        断言渲染回调抛出 "render failed" 中断事件泵后，超时回调关闭前端并销毁窗口。同时断言会话退出码为 1 且汇总
        aborted 为 True。
        """
        state, summary, frontend = run_session(fail_render)
        self.assertEqual(
            [str(error) for error in frontend.root.errors], ["render failed"]
        )
        self.assertTrue(frontend.closed)
        self.assertTrue(frontend.root.destroyed)
        self.assertEqual(state["exit_code"], 1)
        self.assertTrue(summary["aborted"])

    def test_window_close_writes_aborted_summary(self) -> None:
        """断言渲染期间关闭窗口后模拟主循环无异常且窗口已销毁。同时断言会话退出码为 1 且汇总 aborted 为 True。"""
        state, summary, frontend = run_session(close_window)
        self.assertEqual(frontend.root.errors, [])
        self.assertTrue(frontend.root.destroyed)
        self.assertEqual(state["exit_code"], 1)
        self.assertTrue(summary["aborted"])
