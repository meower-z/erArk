"""
协议端口抽象接口模块。
定义游戏逻辑侧使用的 UiPort 与前端界面侧使用的 SessionPort 两套 typing.Protocol 契约。
"""

from typing import Protocol

from Script.Protocol.messages import (
    AttachmentSnapshot,
    BackendEvent,
    ClearTarget,
    Continue,
    ExitReason,
    PanelMode,
    RenderOp,
    SubmitChoice,
    SubmitText,
    UiResponse,
)


class UiPort(Protocol):
    """
    游戏逻辑工作线程侧使用的输出与输入请求端口协议。
    各传输实现按此契约处理指令缓冲、事件序号、暂停跳过、输入请求与会话取消。
    """

    def emit_op(self, op: RenderOp) -> None:
        """
        缓冲一条渲染指令，达到分块条数或字节阈值时刷出为 RenderChunk。
        若触发刷出且传输队列满，在有控制器接入时阻塞至队列空出、控制器断连或会话关闭。
        会话非开放态或在等待投递期间关闭时抛出 SessionCancelled。

        参数：
        op (RenderOp) -- 待发送的渲染指令

        返回值：None
        """

    def clear(self, target: ClearTarget) -> None:
        """
        先刷出已缓冲的渲染指令，再发出 Clear 事件清理目标区域。
        传输队列满且有控制器接入时阻塞等待空位，会话非开放态或等待期间关闭时抛出 SessionCancelled。

        参数：
        target (ClearTarget) -- 清理目标，取值为 "screen"、"input" 或 "buttons"

        返回值：None
        """

    def sync_panel(self, panel_id: int, mode: PanelMode) -> None:
        """
        先刷出已缓冲的渲染指令并关闭暂停跳过状态，再发出 SyncPanel 事件同步面板状态。
        传输队列满且有控制器接入时阻塞等待空位，会话非开放态或等待期间关闭时抛出 SessionCancelled。

        参数：
        panel_id (int) -- 目标面板编号
        mode (PanelMode) -- 面板模式，取值为 "pre_game"、"pick" 或 "settle"

        返回值：None
        """

    def set_skip_pauses(self, enabled: bool) -> None:
        """
        设置后续可跳过暂停的自动跳过开关，不刷出缓冲且不阻塞。
        会话非开放态时抛出 SessionCancelled。

        参数：
        enabled (bool) -- 为 True 时启用跳过可跳过暂停，为 False 时关闭

        返回值：None
        """

    def pause(
        self, *, skippable: bool = True, line_mode: bool = False
    ) -> Continue:
        """
        先刷出已缓冲的渲染指令，并在需要等待时发出 Pause 请求。
        当 skippable 为 True 且暂停跳过已开启时立即返回跳过态 Continue 且不发事件，
        否则发出 Pause 并等待合法 Continue（跨线程实现阻塞等待前端提交，同线程脚本实现同步调用应答器）。
        会话非开放态或在等待期间被取消、关闭时抛出 SessionCancelled。

        参数：
        skippable (bool) -- 是否允许被暂停跳过模式略过，默认为 True
        line_mode (bool) -- 是否为行级暂停模式，默认为 False

        返回值：Continue -- 前端返回的继续响应或跳过时即时构造的 Continue
        """

    def choose(
        self, valid_ids: tuple[str, ...], *, echo: bool = False
    ) -> SubmitChoice:
        """
        先刷出已缓冲指令并关闭暂停跳过状态，再发出 Choose 事件并等待合法 SubmitChoice（跨线程实现阻塞等待前端提交，
        同线程脚本实现同步调用应答器）。
        会话非开放态或在等待期间被取消、关闭时抛出 SessionCancelled。

        参数：
        valid_ids (tuple[str, ...]) -- 供前端展示与参考的候选命令编号元组
        echo (bool) -- 是否指示前端回显所选输入，默认为 False

        返回值：SubmitChoice -- 前端返回的选择响应
        """

    def input_text(
        self, max_len: int, *, allow_empty: bool = False
    ) -> SubmitText:
        """
        先刷出已缓冲指令并关闭暂停跳过状态，
        再发出 InputText 事件并等待符合长度与非空约束的 SubmitText（跨线程实现阻塞等待前端提交，
        同线程脚本实现同步调用应答器）。
        会话非开放态或在等待期间被取消、关闭时抛出 SessionCancelled。

        参数：
        max_len (int) -- 允许提交文本的最大字符长度
        allow_empty (bool) -- 是否允许提交空字符串，默认为 False

        返回值：SubmitText -- 前端返回的文本输入响应
        """

    def finish(self, reason: ExitReason, save_slot: str | None = None) -> None:
        """
        先刷出已缓冲指令再发出 Exit 事件，并将当前会话标记为已正常结束。
        传输队列满且有控制器接入时阻塞等待空位。
        会话非开放态或等待期间关闭时抛出 SessionCancelled，
        正常结束后再调用除 close 以外的工作侧方法都会抛出 SessionCancelled。

        参数：
        reason (ExitReason) -- 退出原因，取值为 "normal"、"error" 或 "cancelled"
        save_slot (str | None) -- 可选的关联存档槽位名称，默认为 None

        返回值：None
        """

    def close(self, reason: str = "closed") -> None:
        """
        立即关闭会话，不阻塞且不抛出 SessionCancelled。
        若会话仍处于开放态，丢弃已缓冲指令与未送达事件，
        向在线控制器发出取消 Exit 并以 SessionCancelled 唤醒等待中的工作线程。
        若已结束则保留队列内事件，重复调用不会发出多余 Exit。

        参数：
        reason (str) -- 记录在取消异常中的关闭原因，默认为 "closed"

        返回值：None
        """


class SessionPort(Protocol):
    """
    前端界面侧使用的会话接入、事件读取与响应提交端口协议。
    各前端传输实现按此契约校验令牌与控制器代次，并处理事件消费、响应校验与通过 Cancel 结束会话。
    """

    def attach(self, auth_token: str) -> AttachmentSnapshot:
        """
        校验令牌并接管当前会话控制权，不阻塞。
        令牌不匹配时抛出 PermissionError。
        校验通过后递增 controller_epoch 并使旧控制器失效，唤醒旧控制器的阻塞读取使其返回 None。
        同时清空待读队列、重标挂起请求代次，并在会话已有退出事件时将其重新入队。
        前端收到快照后先清空自身屏幕，按序重放 projection 后再处理后续实时事件。

        参数：
        auth_token (str) -- 前端提供的会话认证令牌

        返回值：AttachmentSnapshot -- 包含新代次、水位序号、屏幕投影与挂起请求的接入快照
        """

    def detach(self, controller_epoch: int) -> None:
        """
        断开当前控制器的接入状态，不阻塞。
        当前已接入且 controller_epoch 匹配时移除控制器并清空待读队列，
        同时唤醒等待队列空位的工作线程以及该控制器阻塞中的 receive 调用（使其返回 None）。
        过期代次不做任何处理。

        参数：
        controller_epoch (int) -- 调用方持有的控制器代次编号

        返回值：None
        """

    def drain(
        self, controller_epoch: int, max_events: int = 64
    ) -> list[BackendEvent]:
        """
        非阻塞地从待读队列头部批量取出后端事件，不抛出 SessionCancelled。
        未接入或 controller_epoch 不是当前代次时立即返回空列表，不消费队列中的事件。
        取出非空批次后会唤醒因队列满而等待的工作线程。

        参数：
        controller_epoch (int) -- 调用方持有的控制器代次编号
        max_events (int) -- 本次最多取出的事件条数，默认为 64

        返回值：list[BackendEvent] -- 先进先出取出的事件列表，无权读取或队空时返回空列表
        """

    def receive(
        self, controller_epoch: int, timeout: float | None = None
    ) -> BackendEvent | None:
        """
        按控制器代次等待并取出下一条后端事件，不抛出 SessionCancelled。
        未接入或 controller_epoch 不是当前代次时立即返回 None，不消费队列事件。
        等待期间若新控制器接入或当前控制器断连，立刻返回 None 而不取走事件。
        否则阻塞至收到事件、等待超时或会话关闭，取出事件后唤醒等待队列空位的工作线程。

        参数：
        controller_epoch (int) -- 调用方持有的控制器代次编号
        timeout (float | None) -- 最长等待秒数，为 None 时不设时限，默认为 None

        返回值：BackendEvent | None -- 取出的下一条事件，失去控制权、超时或已关闭且队空时为 None
        """

    def submit(self, response: UiResponse) -> bool:
        """
        非阻塞地向会话提交前端响应，在锁内校验会话开放态、控制器在线、代次一致以及与当前挂起请求的编号、
        类型和文本约束是否匹配。
        提交合法的 Cancel 会触发会话关闭并使工作侧抛出 SessionCancelled，被拒绝的响应不改变挂起状态。

        参数：
        response (UiResponse) -- 待提交的 Continue、SubmitChoice、SubmitText 或 Cancel 响应

        返回值：bool -- 响应被接受时返回 True，被拒绝时返回 False
        """
