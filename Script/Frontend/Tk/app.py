"""Tk 前端主控模块，连接 `SessionPort` 消费后端渲染与控制事件并将键鼠操作回传为协议应答。"""

import time
from collections import deque
from tkinter import Event
from typing import Literal

from Script.Config import normal_config
from Script.Core import perf_hook
from Script.Frontend.Tk import image_cache, warmup
from Script.Frontend.Tk.gate import InputGate
from Script.Frontend.Tk.history import InputHistory
from Script.Frontend.Tk.pager import Pager
from Script.Frontend.Tk.render import Renderer
from Script.Frontend.Tk.tooltip import Tooltip
from Script.Frontend.Tk.window import Window
from Script.Protocol import (
    BackendEvent,
    Cancel,
    Clear,
    Exit,
    FrontendInitConfig,
    RenderChunk,
    SessionPort,
    SkipPauses,
    SyncPanel,
    UiRequest,
    UiResponse,
)

DRAIN_BATCH = 256
"""事件泵单次调用 `port.drain` 最多拉取的后端事件条数，本地待分发队列单批最多缓存此数量的事件。"""


class TkFrontend:
    """Tk 前端应用控制器，负责驱动窗口、渲染器、悬停提示、输入历史及与会话端口的事件交互。"""

    def __init__(self, port: SessionPort, auth_token: str) -> None:
        """
        创建窗口、提示、渲染器与输入历史，设置图片缩放并附着会话端口，同时初始化输入门控与分页器

        参数：
        port (SessionPort) -- 前端侧会话端口
        auth_token (str) -- 附着端口所用的鉴权令牌

        返回值类型：None
        """
        normal = normal_config.config_normal
        self.window = Window(normal)
        """当前前端持有的 Tk 主窗口实例。"""
        self.init_config: FrontendInitConfig = self.window.config
        """主窗口按实际屏幕分辨率算出的前端初始配置。"""
        self._tooltip = Tooltip(
            self.window.textbox, normal.font, self.init_config.font_size
        )
        self.renderer = Renderer(self.window, self._tooltip, self._press)
        """负责将协议渲染操作写入文本框的渲染器实例。"""
        self.history = InputHistory()
        """前端输入框使用的本地输入历史管理器。"""
        image_cache.set_font_scaling(self.window.normal_font.measure("A") / 11)
        self._port = port
        self._attachment = port.attach(auth_token)
        self._epoch = self._attachment.controller_epoch
        self.gate = InputGate(self._epoch)
        """管理当前挂起输入请求与输入就绪状态的 `InputGate` 实例。"""
        self.pager = Pager()
        """管理输出分页停顿状态并持有前端跳过开关的 `Pager` 实例。"""
        self._backlog: deque[BackendEvent] = deque()
        self._arm_id: str | None = None
        self._closed = False
        self._synced = False
        self.window.on_close(self.close)

    def run(self) -> None:
        """
        预热字体并绑定键鼠事件，以已读方式回放附着投影并将未读锚点移至文末。
        随后按附着快照恢复跳过开关、分发挂起请求，并启动事件泵与 Tk 主循环。
        首次视图同步由渲染器就绪后的首轮事件泵执行。

        参数：无

        返回值类型：None
        """
        warmup.warm_up(
            self.window,
            normal_config.config_normal.font,
            self.init_config.font_size,
        )
        root = self.window.root
        root.bind("<ButtonPress-1>", self._left_click)
        root.bind("<ButtonPress-3>", self._right_click)
        root.bind("<Return>", self._enter)
        root.bind("<KP_Enter>", self._enter)
        root.bind("<Up>", self._older)
        root.bind("<Down>", self._newer)
        for event in self._attachment.projection:
            self._dispatch(event, read=True)
        self.renderer.anchor_to_end()
        self.pager.skip = self._attachment.skip_pauses
        if self._attachment.pending_request is not None:
            self._dispatch(self._attachment.pending_request)
        root.after(1, self._pump)
        root.mainloop()

    def close(self) -> None:
        """
        提交窗口关闭取消应答、隐藏提示浮窗并销毁 Tk 根窗口，重复调用无效果

        参数：无

        返回值类型：None
        """
        if self._closed:
            return
        self._closed = True
        self._port.submit(Cancel(self._epoch, "window closed"))
        self._tooltip.hide()
        self.window.root.destroy()

    def submit_input(
        self, origin: Literal["keyboard", "button"] = "keyboard"
    ) -> None:
        """
        在输入已就绪时读取输入框文本、记入前端历史并按当前请求类型向端口提交应答，随后清空输入框

        参数：
        origin (Literal["keyboard", "button"]) -- 触发来源，键盘回车为 "keyboard"，点击按钮为 "button"

        返回值类型：None
        """
        if not self.gate.armed:
            return
        text = self.window.order.get()
        self.history.remember(text)
        response = self.gate.submit(text, origin)
        self.window.order.set("")
        if response is None:
            self._arm_later()
        else:
            self._answer(response)

    def _press(self, command_id: str) -> None:
        if not self.gate.armed:
            return
        self.window.order.set(command_id)
        self.submit_input("button")

    def _answer(self, response: UiResponse) -> None:
        self.gate.drop()
        if self._port.submit(response):
            self.renderer.anchor_to_end()

    def _pump(self) -> None:
        if self._closed:
            return
        perf = perf_hook.enabled
        start = time.perf_counter() if perf else 0.0
        count = 0
        ready = self.renderer.ready()
        moved = False
        if ready and not self._synced:
            self._synced = moved = True
        try:
            while not self._closed:
                if not ready or self.pager.hold != "none":
                    exit_event = self._port.pending_exit(self._epoch)
                    if exit_event is not None:
                        self._dispatch(exit_event)
                    break
                if not self._backlog:
                    events = self._port.drain(self._epoch, DRAIN_BATCH)
                    if not events:
                        break
                    count += len(events)
                    self._backlog.extend(events)
                moved |= self._dispatch(self._backlog.popleft())
        finally:
            if moved and not self._closed:
                self._show()
        if perf and count:
            perf_hook.hook_time("gui.drain_batch", time.perf_counter() - start)
            perf_hook.hook_count("gui.msg_total", count)
        if not self._closed:
            self.window.root.after(1, self._pump)

    def _dispatch(self, event: BackendEvent, read: bool = False) -> bool:
        self.pager.observe(event)
        match event:
            case RenderChunk():
                self._disarm()
                self.renderer.mark_unit()
                for op in event.ops:
                    self.renderer.render(op)
                if read:
                    self.renderer.anchor_to_end()
                else:
                    self._settle()
                return True
            case Clear(target="screen"):
                self._disarm()
                self.renderer.clear_screen()
                return True
            case Clear(target="buttons"):
                self._disarm()
                self.renderer.clear_buttons(None)
                return True
            case Clear():
                self._disarm()
                self.window.order.set("")
            case SyncPanel() | SkipPauses():
                pass
            case Exit():
                self._closed = True
                self._tooltip.hide()
                self.window.root.destroy()
            case _:
                self._on_request(event)
        return False

    def _show(self) -> None:
        held = self.pager.hold != "none"
        self.renderer.sync_view(held)
        self.window.set_hold_cue(held)

    def _settle(self) -> None:
        if self.pager.skip:
            self.renderer.anchor_to_end()
        elif self.pager.settle(self.renderer.fit()) == "unit":
            self.renderer.hide_unit()

    def _release(self) -> bool:
        hold = self.pager.release()
        if hold == "none":
            return False
        renderer = self.renderer
        renderer.reveal()
        if self.pager.skip:
            renderer.anchor_to_end()
        elif hold == "unit":
            renderer.anchor_to_unit()
        else:
            renderer.advance_page()
        self._settle()
        self._show()
        return True

    def _on_request(self, request: UiRequest) -> None:
        answer = self.gate.offer(request, self.pager.skip)
        if answer is None:
            self._arm_later()
        else:
            self._answer(answer)

    def _arm_later(self) -> None:
        if self._arm_id is not None:
            self.window.root.after_cancel(self._arm_id)
        self._arm_id = self.window.root.after_idle(self._do_arm)

    def _disarm(self) -> None:
        self.gate.disarm()
        if self._arm_id is not None:
            self.window.root.after_cancel(self._arm_id)
            self._arm_id = None

    def _do_arm(self) -> None:
        self._arm_id = None
        answer = self.gate.arm(self.pager.skip)
        if answer is not None:
            self._answer(answer)
            return
        if self.gate.wants_focus():
            self.window.focus_input()
        if not perf_hook.enabled:
            return
        now = time.perf_counter()
        extra = {}
        enqueued = perf_hook.get_mark("flow.enqueue_done")
        if enqueued:
            extra["enqueue_to_interactive_ms"] = round(
                (now - enqueued) * 1000, 3
            )
        first = perf_hook.get_mark("flow.screen_first_msg")
        if first:
            extra["screen_total_ms"] = round((now - first) * 1000, 3)
        try:
            perf_hook.hook_value(
                "gui.textbox_tag_count", len(self.window.textbox.tag_names())
            )
        except Exception:
            pass
        perf_hook.flush_screen_report(extra)
        perf_hook.clear_mark("flow.screen_first_msg")

    def _continue_pause(self, skip_pauses: bool) -> bool:
        answer = self.gate.continue_pause(skip_pauses)
        if answer is None:
            return False
        self._answer(answer)
        return True

    def _left_click(self, event: Event) -> None:
        if self._release() or not self.gate.armed:
            return
        self.window.focus_input()
        if self._continue_pause(False):
            return
        if not self.renderer.hits_button(event.x_root, event.y_root):
            self.submit_input()

    def _right_click(self, event: Event) -> None:
        self.pager.right_click(self.gate.request)
        if self._release() or not self.gate.armed:
            return
        if self._continue_pause(True):
            return
        if not self.renderer.hits_button(event.x_root, event.y_root):
            self.submit_input()

    def _enter(self, event: Event | None = None) -> None:
        if not self._release():
            self.submit_input()

    def _older(self, event: Event | None = None) -> None:
        text = self.history.older(self.window.order.get())
        if text is not None:
            self.window.order.set(text)

    def _newer(self, event: Event | None = None) -> None:
        text = self.history.newer()
        if text is not None:
            self.window.order.set(text)
