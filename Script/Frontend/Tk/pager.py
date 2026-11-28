"""不依赖 Tk 的分页停顿与跳过状态机模块，负责按测量高度判定分页停顿并跟踪前端跳过开关。"""

from dataclasses import dataclass
from typing import Literal

from Script.Protocol import (
    BackendEvent,
    Choose,
    InputText,
    Pause,
    SkipPauses,
    SyncPanel,
    UiRequest,
)

type Hold = Literal["none", "unit", "page"]
"""分页停顿状态类型别名，取值为 `"none"`（不停顿）、`"unit"`（整块隐藏等待）或 `"page"`（按视口逐页翻看）。"""


@dataclass(frozen=True, slots=True)
class Fit:
    """记录单次分页高度测量结果的不可变数据结构。"""

    used: int
    """从当前未读起点到文本末尾的像素高度。"""
    before_unit: int
    """从未读起点到最近输出块起始位置的像素高度，可为零或负数。"""
    viewport: int
    """输出文本框可视区域的像素高度。"""


class Pager:
    """管理 Tk 前端分页停顿状态、翻页计数与唯一跳过开关的状态机。"""

    def __init__(self) -> None:
        """
        初始化停顿状态为 `"none"`、翻页次数为 0 且跳过开关关闭的分页状态机

        参数：无

        返回值类型：None
        """
        self.hold: Hold = "none"
        """当前分页停顿状态，初始值为 `"none"`。"""
        self.turns = 0
        """通过 `release` 结束分页停顿的累计次数，初始值为 0。"""
        self.skip = False
        """Tk 前端的唯一跳过开关，初始值为 `False`。"""

    def settle(self, fit: Fit) -> Hold:
        """
        按测量结果更新并返回停顿状态，视口非正或内容未超出时为 `"none"`，
        超出且块前有未读内容时为 `"unit"`，否则为 `"page"`

        参数：
        fit (Fit) -- 未读内容与可视区域的高度测量结果

        返回值类型：Hold -- 更新后的停顿状态
        """
        if fit.viewport <= 0 or fit.used <= fit.viewport:
            self.hold = "none"
        elif fit.before_unit > 0:
            self.hold = "unit"
        else:
            self.hold = "page"
        return self.hold

    def release(self) -> Hold:
        """
        结束当前分页停顿并在存在停顿时将翻页计数加一，返回结束前的停顿状态

        参数：无

        返回值类型：Hold -- 释放前的停顿状态，原本未停顿时为 `"none"`
        """
        hold = self.hold
        if hold != "none":
            self.hold = "none"
            self.turns += 1
        return hold

    def right_click(self, request: UiRequest | None) -> None:
        """
        在处于分页停顿、无挂起请求或挂起请求为 `Pause` 时将跳过开关置为 `True`

        参数：
        request (UiRequest | None) -- 当前挂起的后端输入请求，空闲时为 `None`

        返回值类型：None
        """
        if self.hold != "none" or request is None or isinstance(request, Pause):
            self.skip = True

    def observe(self, event: BackendEvent) -> None:
        """
        按后端事件更新跳过开关，`SkipPauses` 按其 `enabled` 赋值，
        `SyncPanel`、`Choose` 与 `InputText` 将其置为 `False`

        参数：
        event (BackendEvent) -- 按流顺序到达的后端事件

        返回值类型：None
        """
        match event:
            case SkipPauses():
                self.skip = event.enabled
            case SyncPanel() | Choose() | InputText():
                self.skip = False
