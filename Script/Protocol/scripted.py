"""
同线程脚本驱动端口与测试应答辅助模块。
提供 ScriptedUiPort 以及构造常见应答器的 reply、script 与 default_first_option 函数。
"""

from collections.abc import Callable, Iterator
from typing import override

from Script.Protocol._core import Phase, PortCore
from Script.Protocol.messages import (
    BackendEvent,
    Choose,
    Continue,
    Exit,
    ExitReason,
    InputText,
    Pause,
    RenderOp,
    SubmitChoice,
    SubmitText,
    UiRequest,
    UiResponse,
)

type Responder = Callable[[UiRequest], UiResponse]


def reply(request: UiRequest, value: str = "") -> UiResponse:
    """
    按请求类型构造匹配当前代次与请求编号的前端响应。

    参数：
    request (UiRequest) -- 待应答的 Pause、Choose 或 InputText 请求
    value (str) -- 用于 Choose 的选项值或 InputText 的输入文本，对 Pause 忽略，默认为空字符串

    返回值：UiResponse -- 与请求对应的 Continue、SubmitChoice 或 SubmitText 实例
    """
    match request:
        case Pause():
            return Continue(request.controller_epoch, request.request_id)
        case Choose():
            return SubmitChoice(
                request.controller_epoch, request.request_id, value
            )
        case InputText():
            return SubmitText(
                request.controller_epoch, request.request_id, value
            )


def script(*steps: str | Responder) -> Responder:
    """
    按顺序消费预设步骤的应答器工厂，步骤耗尽后再次收到请求时抛出 LookupError。

    参数：
    steps (str | Responder) -- 依次对应的字符串答复或自定义应答回调函数

    返回值：Responder -- 每次调用消耗下一个步骤并返回对应 UiResponse 的应答器
    """
    pending: Iterator[str | Responder] = iter(steps)

    def respond(request: UiRequest) -> UiResponse:
        step = next(pending, None)
        if step is None:
            raise LookupError(f"script has no step left for {request!r}")
        return reply(request, step) if isinstance(step, str) else step(request)

    return respond


def default_first_option(
    text: str | Callable[[InputText], str] = "",
) -> Responder:
    """
    构造默认应答器。
    对 Pause 返回 Continue，对非空 Choose 选取首个候选编号，对空 Choose 抛出 ValueError，
    对 InputText 返回指定文本。

    参数：
    text (str | Callable[[InputText], str]) -- 应答文本输入请求的固定字符串或按请求生成文本的回调，
    默认为空字符串

    返回值：Responder -- 可应答各类 UiRequest 的应答器
    """

    def respond(request: UiRequest) -> UiResponse:
        match request:
            case Choose(valid_ids=(first, *_)):
                return reply(request, first)
            case Choose():
                raise ValueError("Choose request offered no valid options")
            case InputText():
                return reply(
                    request, text if isinstance(text, str) else text(request)
                )
        return reply(request)

    return respond


class ScriptedUiPort(PortCore):
    """
    运行在调用方同线程内的 UiPort 实现，不启动后台线程。
    实例初始化后即处于已接入状态且代次为 1。
    未传 listener 时，端口把后端事件按序记入 events 列表。
    传入 listener 时，端口把后端事件直接交给 listener，不写入 events。
    此时 emit_op 仅在缓冲仍有未刷出操作时立即刷出。
    finish 与 close 均先退出开放阶段，再把 Exit 事件交给 listener 或记入 events。
    收到输入请求时，端口同步调用应答器并校验响应。
    响应被拒时端口抛出 ValueError。
    收到 Cancel 或会话关闭时端口抛出 SessionCancelled。
    """

    def __init__(
        self,
        responder: Responder,
        *,
        session_id: str = "scripted",
        listener: Callable[[BackendEvent], None] | None = None,
    ) -> None:
        """
        初始化同线程脚本驱动端口。

        参数：
        responder (Responder) -- 接收 UiRequest 并同步返回 UiResponse 的应答回调
        session_id (str) -- 写入后端事件的会话标识，默认为 "scripted"
        listener (Callable[[BackendEvent], None] | None) -- 接收后端事件的回调，默认为 None

        返回值：None
        """
        super().__init__(session_id)
        self._responder = responder
        self._listener = listener
        self._epoch = 1
        self._attached = True
        self.events: list[BackendEvent] = []

    @override
    def emit_op(self, op: RenderOp) -> None:
        super().emit_op(op)
        if self._listener is not None and self._ops:
            self.flush()

    @override
    def finish(self, reason: ExitReason, save_slot: str | None = None) -> None:
        with self._cond:
            self._require_open()
            self._flush()
            self._require_open()
            exit_event = Exit(
                self._session_id, self._next_seq(), reason, save_slot
            )
            self._exit = exit_event
            self._phase = Phase.FINISHED
            self._publish(exit_event)

    @override
    def _deliver(self, event: BackendEvent) -> None:
        if self._listener is None:
            self.events.append(event)
        else:
            self._listener(event)

    @override
    def _wait_answer(self) -> None:
        request = self._pending
        if request is None:
            return
        response = self._responder(request)
        if not self._accept(response) and self._phase is Phase.OPEN:
            raise ValueError(
                f"responder answered {request!r} with {response!r}"
            )

    @override
    def _cancelled(self, exit_event: Exit) -> None:
        self._phase = Phase.CLOSED
        self._deliver(exit_event)
