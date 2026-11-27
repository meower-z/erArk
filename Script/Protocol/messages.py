"""
通信协议消息与异常定义模块。
包含游戏逻辑侧发出的渲染指令与后端事件、前端返回的响应、重连快照、
前端初始化配置以及取消异常 SessionCancelled。
"""

from dataclasses import dataclass
from typing import Literal

type ClearTarget = Literal["screen", "input", "buttons"]
type PanelMode = Literal["pre_game", "pick", "settle"]
type ExitReason = Literal["normal", "error", "cancelled"]


@dataclass(frozen=True, slots=True)
class TextOp:
    """游戏逻辑发出的文本渲染指令，向界面追加一段带样式的文本。"""

    text: str
    style: tuple[str, ...] = ("standard",)
    tooltip: str = ""


@dataclass(frozen=True, slots=True)
class ButtonOp:
    """游戏逻辑发出的文本按钮渲染指令，在界面绘制可点击的命令按钮。"""

    label: str
    command_id: str
    normal_style: tuple[str, ...] = ("standard",)
    hover_style: tuple[str, ...] = ("onbutton",)
    tooltip: str = ""


@dataclass(frozen=True, slots=True)
class ImageOp:
    """游戏逻辑发出的单图渲染指令，向界面显示一张图片。"""

    asset_id: str


@dataclass(frozen=True, slots=True)
class ImageBatchOp:
    """游戏逻辑发出的批量图片渲染指令，按顺序显示一组图片。"""

    asset_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ImageButtonOp:
    """游戏逻辑发出的图片按钮渲染指令，以图片形式绘制可点击的命令按钮。"""

    asset_id: str
    command_id: str
    tooltip: str = ""


@dataclass(frozen=True, slots=True)
class StyleDefOp:
    """游戏逻辑发出的样式定义指令，注册或覆盖指定名称的文字显示样式。"""

    name: str
    fg: str
    bg: str
    font: str
    size: int
    bold: bool
    underline: bool
    italic: bool


@dataclass(frozen=True, slots=True)
class BgColorOp:
    """游戏逻辑发出的背景色指令，设置界面主区域的背景颜色。"""

    color: str


@dataclass(frozen=True, slots=True)
class ClearButtonsOp:
    """游戏逻辑发出的清按钮指令。command_ids 为 None 时清除全部按钮，否则清除其中列出的命令编号对应的按钮。"""

    command_ids: tuple[str, ...] | None = None


type RenderOp = (
    TextOp
    | ButtonOp
    | ImageOp
    | ImageBatchOp
    | ImageButtonOp
    | StyleDefOp
    | BgColorOp
    | ClearButtonsOp
)


@dataclass(frozen=True, slots=True)
class RenderChunk:
    """游戏逻辑通过端口发出的渲染批次事件，携带合并后的渲染指令元组。"""

    session_id: str
    seq: int
    ops: tuple[RenderOp, ...]


@dataclass(frozen=True, slots=True)
class Clear:
    """游戏逻辑发出的区域清理事件，按 target 指定清空屏幕、输入框或按钮区。"""

    session_id: str
    seq: int
    target: ClearTarget


@dataclass(frozen=True, slots=True)
class SyncPanel:
    """游戏逻辑发出的面板同步事件，通知前端将指定面板切换到对应模式。"""

    session_id: str
    seq: int
    panel_id: int
    mode: PanelMode


@dataclass(frozen=True, slots=True)
class SkipPauses:
    """游戏逻辑发出的跳过暂停状态同步事件，通知前端将跳过模式设为 enabled。"""

    session_id: str
    seq: int
    enabled: bool


@dataclass(frozen=True, slots=True)
class Pause:
    """游戏逻辑发出的暂停等待请求。skippable 为 True 时允许跳过模式略过本次等待，line_mode 标记行级暂停。"""

    session_id: str
    seq: int
    controller_epoch: int
    request_id: int
    skippable: bool = True
    line_mode: bool = False


@dataclass(frozen=True, slots=True)
class Choose:
    """游戏逻辑发出的选项选择请求。echo 为 True 时指示前端回显所选输入。"""

    session_id: str
    seq: int
    controller_epoch: int
    request_id: int
    valid_ids: tuple[str, ...]
    echo: bool = False


@dataclass(frozen=True, slots=True)
class InputText:
    """游戏逻辑发出的文本输入请求。allow_empty 控制是否接受空字符串。"""

    session_id: str
    seq: int
    controller_epoch: int
    request_id: int
    max_len: int
    allow_empty: bool = False


type UiRequest = Pause | Choose | InputText


@dataclass(frozen=True, slots=True)
class Exit:
    """游戏逻辑正常结束或端口取消关闭时发出的会话退出事件。save_slot 可选记录关联存档槽位。"""

    session_id: str
    seq: int
    reason: ExitReason
    save_slot: str | None = None


type BackendEvent = (
    RenderChunk | Clear | SyncPanel | SkipPauses | UiRequest | Exit
)


@dataclass(frozen=True, slots=True)
class Continue:
    """前端对 Pause 请求返回的继续响应。skip_pauses 为 True 时同时开启后续可跳过暂停的自动跳过模式。"""

    controller_epoch: int
    request_id: int
    skip_pauses: bool = False


@dataclass(frozen=True, slots=True)
class SubmitChoice:
    """前端对 Choose 请求返回的选择响应。origin 标明输入来源是键盘（"keyboard"）还是按钮点击（"button"）。"""

    controller_epoch: int
    request_id: int
    raw_value: str
    origin: Literal["keyboard", "button"] = "keyboard"


@dataclass(frozen=True, slots=True)
class SubmitText:
    """前端对 InputText 请求返回的文本提交响应。"""

    controller_epoch: int
    request_id: int
    text: str


@dataclass(frozen=True, slots=True)
class Cancel:
    """前端发出的会话取消请求，仅在 controller_epoch 与当前接入代次一致时生效。"""

    controller_epoch: int
    reason: str


type UiResponse = Continue | SubmitChoice | SubmitText | Cancel


@dataclass(frozen=True, slots=True)
class AttachmentSnapshot:
    """
    端口在前端调用 SessionPort.attach 时返回的接入快照。
    watermark_seq 是接入时会话已用过的最后事件序号，
    此后新投递的事件仅在 seq 严格大于该值时入队。
    skip_pauses 记录接入时刻会话的暂停跳过开关状态。
    """

    session_id: str
    controller_epoch: int
    watermark_seq: int
    projection: tuple[RenderChunk | Clear | SyncPanel, ...]
    pending_request: UiRequest | None
    skip_pauses: bool


@dataclass(frozen=True, slots=True)
class FrontendInitConfig:
    """描述前端初始化窗口尺寸、排版参数、背景色与能力集合 capabilities 的不可变配置。"""

    window_width: int
    window_height: int
    text_width: int
    font_size: int
    background: str
    capabilities: frozenset[str] = frozenset()


class SessionCancelled(BaseException):
    """
    会话非开放态或等待期间被取消、关闭时由游戏逻辑侧端口抛出的异常。直接继承自 BaseException 而非 Exception，
    以避免被常规 except Exception 分支捕获。
    """
