"""
基于线程条件变量与按容量等待的队列的跨线程通信端口实现模块。
提供同时实现 UiPort 与 SessionPort 的 ThreadedUiPort。
"""

import dataclasses
import hmac
from collections import deque
from typing import override

from Script.Protocol._core import Phase, PortCore
from Script.Protocol.messages import (
    AttachmentSnapshot,
    BackendEvent,
    Exit,
    SessionCancelled,
    UiResponse,
)
from Script.Protocol.ports import SessionPort


class ThreadedUiPort(PortCore, SessionPort):
    """
    线程安全的双向通信端口，同时实现游戏侧 UiPort 与前端侧 SessionPort。
    内部使用受 threading.Condition 保护的双端队列传递事件，在控制器在线且队列满时对工作线程施加背压等待，
    支持令牌校验接入、控制器切换、断连后继续计算以及带屏幕投影的重连快照。
    """

    def __init__(
        self,
        auth_token: str,
        *,
        session_id: str = "session",
        capacity: int = 1024,
    ) -> None:
        """
        初始化跨线程通信端口，当容量小于 1 时抛出 ValueError。

        参数：
        auth_token (str) -- 前端调用 attach 时必须匹配的认证令牌
        session_id (str) -- 写入后端事件与重连快照的会话标识，默认为 "session"
        capacity (int) -- 控制器在线时待读事件的上限，达到后工作线程等待，默认为 1024

        返回值：None
        """
        if capacity < 1:
            raise ValueError(f"capacity must be positive, got {capacity}")
        super().__init__(session_id)
        self._auth_token = auth_token.encode("utf-8")
        self._capacity = capacity
        self._out: deque[BackendEvent] = deque()
        self._watermark = 0

    @override
    def attach(self, auth_token: str) -> AttachmentSnapshot:
        with self._cond:
            if not hmac.compare_digest(
                auth_token.encode("utf-8"), self._auth_token
            ):
                raise PermissionError("auth token does not match the session")
            self._epoch += 1
            self._attached = True
            self._watermark = self._seq
            self._out.clear()
            if self._pending is not None:
                self._pending = dataclasses.replace(
                    self._pending, controller_epoch=self._epoch
                )
            if self._exit is not None:
                self._out.append(self._exit)
                if self._phase is Phase.OPEN:
                    self._phase = Phase.FINISHED
            self._cond.notify_all()
            return AttachmentSnapshot(
                self._session_id,
                self._epoch,
                self._watermark,
                self._projection.snapshot(),
                self._pending,
                self._skip,
            )

    @override
    def detach(self, controller_epoch: int) -> None:
        with self._cond:
            if self._attached and controller_epoch == self._epoch:
                self._attached = False
                self._out.clear()
                self._cond.notify_all()

    @override
    def drain(
        self, controller_epoch: int, max_events: int = 64
    ) -> list[BackendEvent]:
        with self._cond:
            if not self._controls(controller_epoch):
                return []
            count = min(max_events, len(self._out))
            events = [self._out.popleft() for _ in range(count)]
            if events:
                self._cond.notify_all()
            return events

    @override
    def receive(
        self, controller_epoch: int, timeout: float | None = None
    ) -> BackendEvent | None:
        with self._cond:
            self._cond.wait_for(
                lambda: not self._controls(controller_epoch)
                or bool(self._out)
                or self._phase is Phase.CLOSED,
                timeout,
            )
            if not self._controls(controller_epoch) or not self._out:
                return None
            event = self._out.popleft()
            self._cond.notify_all()
            return event

    @override
    def pending_exit(self, controller_epoch: int) -> Exit | None:
        with self._cond:
            return self._exit if self._controls(controller_epoch) else None

    @override
    def submit(self, response: UiResponse) -> bool:
        with self._cond:
            return self._accept(response)

    def _controls(self, controller_epoch: int) -> bool:
        return self._attached and controller_epoch == self._epoch

    @override
    def _deliver(self, event: BackendEvent) -> None:
        self._cond.wait_for(
            lambda: event.seq <= self._watermark
            or self._phase is Phase.CLOSED
            or not self._attached
            or len(self._out) < self._capacity
        )
        if event.seq <= self._watermark:
            return
        if self._phase is Phase.CLOSED:
            raise SessionCancelled(self._close_reason)
        if self._attached:
            self._out.append(event)
            self._cond.notify_all()

    @override
    def _wait_answer(self) -> None:
        self._cond.wait_for(
            lambda: self._answer is not None or self._phase is not Phase.OPEN
        )

    @override
    def _cancelled(self, exit_event: Exit) -> None:
        self._out.clear()
        if self._attached:
            self._out.append(exit_event)
