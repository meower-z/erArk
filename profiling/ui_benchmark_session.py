"""渲染性能基准的会话编排模块，在窗口主线程上调度单屏超时、启动重绘工作线程并在关窗后等待线程结束。"""

import contextlib
import threading
import time
import traceback
from collections.abc import Callable
from typing import Protocol, TypedDict

from Script.Protocol import SessionCancelled, UiPort

JOIN_TIMEOUT = 5.0
"""窗口关闭后主线程等待重绘工作线程结束的最大秒数。"""


class BenchmarkState(TypedDict):
    """渲染性能基准运行期间在主线程与工作线程间共享的进度、耗时列表与退出码字典类型。"""

    screens_done: int
    screen_wall_times: list[float]
    warmup_wall_times: list[float]
    warmup_cleared: bool
    aborted: bool
    exit_code: int


class Frontend(Protocol):
    """基准会话依赖的前端窗口协议，声明运行主循环的 run 方法与关闭窗口的 close 方法。"""

    def run(self) -> None:
        """
        运行窗口主循环直至窗口关闭

        参数：无

        返回值类型：None
        """

    def close(self) -> None:
        """
        关闭窗口并取消当前会话

        参数：无

        返回值类型：None
        """


class Clock(Protocol):
    """基准会话依赖的窗口定时调度协议，声明延迟调度 after 与取消调度 after_cancel 方法。"""

    def after(self, ms: int, func: Callable[[], object], /) -> str:
        """
        在窗口线程上延迟指定毫秒后调度回调函数

        参数：
        ms (int) -- 延迟执行的毫秒数
        func (Callable[[], object]) -- 到期后在窗口线程执行的无参回调

        返回值类型：str -- 可用于取消该调度的定时器编号
        """
        ...

    def after_cancel(self, after_id: str, /) -> None:
        """
        取消已通过 after 登记的延迟回调

        参数：
        after_id (str) -- after 返回的定时器编号

        返回值类型：None
        """


def log(msg: str) -> None:
    """
    输出带前缀的日志
    参数:
        msg (str) -- 日志内容
    返回值类型：无
    功能描述：统一日志前缀，便于与游戏自身输出区分
    """
    print(f"[ui_benchmark] {msg}", flush=True)


class BenchmarkSession:
    """单次渲染性能基准的会话控制器，负责在窗口线程调度单屏超时、拉起重绘工作线程并在关窗后回收线程。"""

    def __init__(
        self,
        frontend: Frontend,
        root: Clock,
        port: UiPort,
        state: BenchmarkState,
        seconds: float,
    ) -> None:
        """
        初始化单次渲染性能基准会话并保存前端、时钟、端口、共享状态与单屏超时秒数

        参数：
        frontend (Frontend) -- 负责运行与关闭窗口的前端对象
        root (Clock) -- 在窗口线程上调度超时回调的时钟对象
        port (UiPort) -- 后端与前端通信使用的协议端口
        state (BenchmarkState) -- 主线程与工作线程共享的运行状态字典
        seconds (float) -- 单屏渲染等待的超时秒数

        返回值类型：None
        """
        self._frontend = frontend
        self._root = root
        self._port = port
        self._state = state
        self._seconds = seconds
        self._deadline: str | None = None

    def restart_deadline(self) -> None:
        """
        取消上一轮单屏超时定时器并在窗口线程重新登记下一次超时回调

        参数：无

        返回值类型：None
        """
        if self._deadline is not None:
            self._root.after_cancel(self._deadline)
        self._deadline = self._root.after(
            round(self._seconds * 1000), self.time_out
        )

    def time_out(self) -> None:
        """
        单屏渲染等待超时回调，记录警告日志、标记中止与退出码 1，关闭端口并关闭窗口以退出主循环

        参数：无

        返回值类型：None
        """
        self._deadline = None
        log(
            f"警告：第 {self._state['screens_done'] + 1} 屏等待渲染超时（{self._seconds}s），中止。"
        )
        self._abort()
        self._port.close("screen timeout")
        self._frontend.close()

    def serve(
        self, draw: Callable[[], object], report: Callable[[float], None]
    ) -> None:
        """
        通过窗口时钟启动重绘工作线程与首屏超时后运行前端主循环。窗口关闭后关闭端口并等待工作线程最多 JOIN_TIMEOUT 秒，
        若线程仍存活则记录警告并设退出码为 1。

        参数：
        draw (Callable[[], object]) -- 在工作线程中执行面板重绘循环的回调
        report (Callable[[float], None]) -- 重绘正常结束或遇 SessionCancelled 后接收总墙钟秒数并输出汇总的回调

        返回值类型：None
        """
        worker = threading.Thread(
            target=self._flow,
            args=(draw, report),
            name="ui-benchmark-flow",
            daemon=True,
        )
        self._root.after(0, worker.start)
        self._root.after(0, self.restart_deadline)
        self._frontend.run()
        self._port.close("window closed")
        worker.join(JOIN_TIMEOUT)
        if worker.is_alive():
            log(
                f"警告：窗口关闭后工作线程在 {JOIN_TIMEOUT}s 内未结束，放弃等待。"
            )
            self._state["exit_code"] = 1

    def _flow(
        self, draw: Callable[[], object], report: Callable[[float], None]
    ) -> None:
        start = time.perf_counter()
        try:
            try:
                draw()
            except SessionCancelled:
                self._abort()
            report(time.perf_counter() - start)
        except Exception:
            log("基准执行异常：")
            traceback.print_exc()
            self._state["exit_code"] = 1
        finally:
            with contextlib.suppress(SessionCancelled):
                self._port.finish("normal")

    def _abort(self) -> None:
        self._state["aborted"] = True
        self._state["exit_code"] = 1
