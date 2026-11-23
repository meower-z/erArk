"""
协议端口共享核心模块。
提供渲染指令字节估算、会话生命周期阶段枚举以及 UiPort 通用状态机基类 PortCore。
"""

import dataclasses
import enum
import threading
from abc import abstractmethod
from typing import override

from Script.Protocol.messages import (
    BackendEvent,
    Cancel,
    Choose,
    Clear,
    ClearTarget,
    Continue,
    Exit,
    ExitReason,
    InputText,
    PanelMode,
    Pause,
    RenderChunk,
    RenderOp,
    SessionCancelled,
    SubmitChoice,
    SubmitText,
    SyncPanel,
    UiRequest,
    UiResponse,
)
from Script.Protocol._projection import Projection
from Script.Protocol.ports import UiPort

MAX_CHUNK_OPS = 256
MAX_CHUNK_BYTES = 32 * 1024

type Answer = Continue | SubmitChoice | SubmitText


def _payload_bytes(value: object) -> int:
    if isinstance(value, str):
        return len(value.encode("utf-8"))
    if isinstance(value, tuple):
        return sum(_payload_bytes(item) for item in value)
    return 8


def op_bytes(op: RenderOp) -> int:
    """
    估算单条渲染指令的负载字节数，用于判断是否触发 RenderChunk 刷新阈值。

    参数：
    op (RenderOp) -- 待估算的渲染指令

    返回值：int -- 按字段累计的估算字节数，字符串取 UTF-8 字节长，元组按元素递归求和，其余类型按 8 字节计
    """
    return sum(
        _payload_bytes(getattr(op, field.name))
        for field in dataclasses.fields(op)
    )


class Phase(enum.Enum):
    """
    会话生命周期阶段枚举。
    包含开放中的 OPEN、已正常结束的 FINISHED 与已关闭或取消的 CLOSED。
    """

    OPEN = enum.auto()
    FINISHED = enum.auto()
    CLOSED = enum.auto()


class PortCore(UiPort):
    """
    UiPort 的抽象基类，集中实现渲染指令缓冲分块、事件序号与请求编号递增、暂停跳过状态、
    屏幕投影记录以及响应合法性校验。
    子类通过实现事件投递、等待应答与取消清理三个内部钩子提供具体传输方式。
    """

    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self._cond = threading.Condition()
        self._phase = Phase.OPEN
        self._close_reason = ""
        self._seq = 0
        self._epoch = 0
        self._attached = False
        self._request_id = 0
        self._pending: UiRequest | None = None
        self._answer: Answer | None = None
        self._skip = False
        self._ops: list[RenderOp] = []
        self._ops_bytes = 0
        self._exit: Exit | None = None
        self._projection = Projection(session_id)

    @abstractmethod
    def _deliver(self, event: BackendEvent) -> None:
        raise NotImplementedError

    @abstractmethod
    def _wait_answer(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def _cancelled(self, exit_event: Exit) -> None:
        raise NotImplementedError

    @override
    def emit_op(self, op: RenderOp) -> None:
        with self._cond:
            self._require_open()
            self._ops.append(op)
            self._ops_bytes += op_bytes(op)
            if (
                len(self._ops) >= MAX_CHUNK_OPS
                or self._ops_bytes >= MAX_CHUNK_BYTES
            ):
                self._flush()

    @override
    def flush(self) -> None:
        with self._cond:
            self._require_open()
            self._flush()

    @override
    def clear(self, target: ClearTarget) -> None:
        with self._cond:
            self._require_open()
            self._flush()
            self._publish(Clear(self._session_id, self._next_seq(), target))

    @override
    def sync_panel(self, panel_id: int, mode: PanelMode) -> None:
        with self._cond:
            self._require_open()
            self._flush()
            self._skip = False
            self._publish(
                SyncPanel(self._session_id, self._next_seq(), panel_id, mode)
            )

    @override
    def set_skip_pauses(self, enabled: bool) -> None:
        with self._cond:
            self._require_open()
            self._skip = enabled

    @override
    def pause(
        self, *, skippable: bool = True, line_mode: bool = False
    ) -> Continue:
        with self._cond:
            self._require_open()
            self._flush()
            if skippable and self._skip:
                return Continue(self._epoch, 0, skip_pauses=True)
            request = Pause(
                self._session_id,
                self._next_seq(),
                self._epoch,
                self._next_request_id(),
                skippable,
                line_mode,
            )
            return self._ask(request, Continue)

    @override
    def choose(
        self, valid_ids: tuple[str, ...], *, echo: bool = False
    ) -> SubmitChoice:
        with self._cond:
            self._require_open()
            self._flush()
            self._skip = False
            request = Choose(
                self._session_id,
                self._next_seq(),
                self._epoch,
                self._next_request_id(),
                valid_ids,
                echo,
            )
            return self._ask(request, SubmitChoice)

    @override
    def input_text(
        self, max_len: int, *, allow_empty: bool = False
    ) -> SubmitText:
        with self._cond:
            self._require_open()
            self._flush()
            self._skip = False
            request = InputText(
                self._session_id,
                self._next_seq(),
                self._epoch,
                self._next_request_id(),
                max_len,
                allow_empty,
            )
            return self._ask(request, SubmitText)

    @override
    def finish(self, reason: ExitReason, save_slot: str | None = None) -> None:
        with self._cond:
            self._require_open()
            self._flush()
            exit_event = Exit(
                self._session_id, self._next_seq(), reason, save_slot
            )
            self._exit = exit_event
            self._publish(exit_event)
            self._phase = Phase.FINISHED

    @override
    def close(self, reason: str = "closed") -> None:
        with self._cond:
            self._close(reason)

    def _close(self, reason: str) -> None:
        if self._phase is Phase.OPEN:
            self._ops.clear()
            self._ops_bytes = 0
            self._close_reason = reason
            self._pending = None
            self._exit = Exit(self._session_id, self._next_seq(), "cancelled")
            self._cancelled(self._exit)
        self._phase = Phase.CLOSED
        self._cond.notify_all()

    def _accept(self, response: UiResponse) -> bool:
        if (
            self._phase is not Phase.OPEN
            or not self._attached
            or response.controller_epoch != self._epoch
        ):
            return False
        if isinstance(response, Cancel):
            self._close(response.reason)
            return True
        request = self._pending
        if request is None or response.request_id != request.request_id:
            return False
        match request, response:
            case Pause(), Continue():
                self._skip = self._skip or response.skip_pauses
            case Choose(), SubmitChoice():
                pass
            case InputText(), SubmitText() if _text_fits(request, response):
                pass
            case _:
                return False
        self._pending = None
        self._answer = response
        self._cond.notify_all()
        return True

    def _ask[A: Answer](self, request: UiRequest, kind: type[A]) -> A:
        self._pending = request
        self._publish(request)
        self._wait_answer()
        answer, self._answer = self._answer, None
        if isinstance(answer, kind):
            return answer
        raise SessionCancelled(self._close_reason)

    def _require_open(self) -> None:
        if self._phase is not Phase.OPEN:
            raise SessionCancelled(self._close_reason or self._phase.name)

    def _flush(self) -> None:
        if not self._ops:
            return
        ops = tuple(self._ops)
        self._ops.clear()
        self._ops_bytes = 0
        self._publish(RenderChunk(self._session_id, self._next_seq(), ops))

    def _publish(self, event: BackendEvent) -> None:
        self._projection.record(event)
        self._deliver(event)

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _next_request_id(self) -> int:
        self._request_id += 1
        return self._request_id


def _text_fits(request: InputText, response: SubmitText) -> bool:
    return len(response.text) <= request.max_len and (
        request.allow_empty or response.text != ""
    )
