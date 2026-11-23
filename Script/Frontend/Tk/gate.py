"""不依赖 Tk 的纯状态输入门控模块，负责跟踪挂起请求、输入就绪状态与右键跳过预排并生成协议应答。"""

from typing import Literal

from Script.Protocol import (
    Choose,
    Continue,
    InputText,
    Pause,
    SubmitChoice,
    SubmitText,
    UiRequest,
    UiResponse,
)


class InputGate:
    """管理单个控制器代次下的挂起请求、就绪门控与右键跳过预排，并将键鼠提交转换为 `UiResponse`。"""

    def __init__(self, epoch: int) -> None:
        """
        按控制器代次初始化无挂起请求、未就绪且未预排跳过的输入门控

        参数：
        epoch (int) -- 当前附着连接的控制器代次编号

        返回值类型：None
        """
        self.epoch = epoch
        """当前门控绑定的控制器代次编号。"""
        self.request: UiRequest | None = None
        """当前等待应答的后端输入请求，空闲时为 `None`。"""
        self.armed = False
        """输入门控当前是否已就绪并允许提交玩家操作。"""
        self.skip_requested = False
        """是否已通过右键预排跳过下一次可跳过暂停。"""

    def offer(self, request: UiRequest) -> Continue | None:
        """
        登记新的后端输入请求并解除就绪，非暂停请求会清除跳过预排，已预排跳过且遇可跳过暂停时直接返回跳过应答

        参数：
        request (UiRequest) -- 后端发来的新输入请求

        返回值类型：Continue | None -- 命中预排跳过时返回带跳过的 `Continue`，否则返回 `None`
        """
        self.request = request
        self.armed = False
        if not isinstance(request, Pause):
            self.skip_requested = False
        return self._queued_skip()

    def arm(self) -> Continue | None:
        """
        尝试开启输入就绪门控，若命中预排的可跳过暂停则直接返回跳过应答而不就绪，否则仅在有挂起请求时置为就绪

        参数：无

        返回值类型：Continue | None -- 命中预排跳过时返回 `Continue`，否则返回 `None`
        """
        answer = self._queued_skip()
        self.armed = answer is None and self.request is not None
        return answer

    def disarm(self) -> None:
        """
        关闭输入就绪门控

        参数：无

        返回值类型：None
        """
        self.armed = False

    def wants_focus(self) -> bool:
        """
        判断当前挂起请求是否需要把焦点切到输入框，请求为 `Choose` 或 `InputText` 时为 `True`

        参数：无

        返回值类型：bool -- 需要聚焦输入框时返回 True，否则返回 False
        """
        return isinstance(self.request, (Choose, InputText))

    def submit(
        self, text: str, origin: Literal["keyboard", "button"]
    ) -> UiResponse | None:
        """
        在门控已就绪时解除就绪并按当前请求类型构造应答，文本不符合要求或未就绪时返回 `None`

        参数：
        text (str) -- 提交的输入文本
        origin (Literal["keyboard", "button"]) -- 触发来源，键盘为 "keyboard"，按钮为 "button"

        返回值类型：UiResponse | None -- 合法时返回对应 `Continue`、`SubmitChoice` 或 `SubmitText`，否则返回 None
        """
        if not self.armed:
            return None
        self.armed = False
        match self.request:
            case Pause() as request if text == "":
                return Continue(self.epoch, request.request_id)
            case Choose() as request:
                return SubmitChoice(
                    self.epoch, request.request_id, text, origin
                )
            case InputText() as request if _fits(request, text):
                return SubmitText(self.epoch, request.request_id, text)
        return None

    def continue_pause(self, skip_pauses: bool) -> Continue | None:
        """
        在门控已就绪且当前请求为 `Pause` 时解除就绪并返回 `Continue` 应答

        参数：
        skip_pauses (bool) -- 是否在应答中请求开启跳过暂停模式

        返回值类型：Continue | None -- 处于就绪暂停状态时返回 `Continue`，否则返回 None
        """
        request = self.request
        if not self.armed or not isinstance(request, Pause):
            return None
        self.armed = False
        return Continue(self.epoch, request.request_id, skip_pauses=skip_pauses)

    def right_click(self) -> None:
        """
        记录右键跳过预排，仅在无挂起请求或当前请求为 `Pause` 时生效

        参数：无

        返回值类型：None
        """
        if self.request is None or isinstance(self.request, Pause):
            self.skip_requested = True

    def accepted(self, response: UiResponse) -> None:
        """
        应答被端口接受后清空挂起请求与就绪状态，若接受的是带跳过标记的 `Continue` 则同步清除跳过预排

        参数：
        response (UiResponse) -- 已被端口接受的应答对象

        返回值类型：None
        """
        self.request = None
        self.armed = False
        if isinstance(response, Continue) and response.skip_pauses:
            self.skip_requested = False

    def rejected(self) -> None:
        """
        应答被端口拒绝时丢弃过期的挂起请求并解除就绪状态

        参数：无

        返回值类型：None
        """
        self.request = None
        self.armed = False

    def _queued_skip(self) -> Continue | None:
        request = self.request
        if (
            self.skip_requested
            and isinstance(request, Pause)
            and request.skippable
        ):
            return Continue(self.epoch, request.request_id, skip_pauses=True)
        return None


def _fits(request: InputText, text: str) -> bool:
    return (request.allow_empty or text != "") and len(text) <= request.max_len
