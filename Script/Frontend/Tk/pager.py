"""不依赖 Tk 的纯状态分页器模块，根据未读高度与视口高度决定输出暂停形态，并跟踪右键跳过状态。"""

from dataclasses import dataclass
from typing import Literal

from Script.Protocol import Choose, InputText, Pause, UiRequest

type Hold = Literal["none", "unit", "page"]
"""分页暂停状态类型，取值为 "none"（未暂停）、"unit"（隐藏溢出块暂停）或 "page"（单块超屏逐屏暂停）。"""


@dataclass(frozen=True, slots=True)
class Fit:
    """Tk 文本框未读区域的像素高度快照，供分页器判断是否需要暂停输出。"""

    used: int
    """从未读锚点到文本末尾的像素高度。"""
    before_unit: int
    """从未读锚点到当前输出块起点的像素高度，当前块起点位于锚点上方时为负值。"""
    viewport: int
    """文本框可见内容区的像素高度。"""


class Pager:
    """纯状态视口分页器，管理暂停状态与右键跳过标记并在渲染、右键与请求切换时更新状态。"""

    def __init__(self) -> None:
        """
        初始化为未暂停且未开启跳过的分页器

        参数：无

        返回值类型：None
        """
        self.hold: Hold = "none"
        """当前分页暂停状态，初始为 "none"。"""
        self.skip = False
        """是否处于跳过分页暂停模式，初始为 False。"""
        self.turns = 0
        """已解除分页暂停的累计次数，初始为 0。"""

    def settle(self, fit: Fit) -> Hold:
        """
        根据未读区高度快照判定并记录本次输出后的暂停状态，
        调用方在跳过模式开启时不调用本方法

        参数：
        fit (Fit) -- 当前未读区与视口的像素高度快照

        返回值类型：Hold -- 视口非正或 `used <= viewport` 时为 "none"，
        否则 `before_unit > 0` 时为 "unit"，其余为 "page"
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
        解除当前分页暂停并返回调用前的暂停状态，
        处于暂停时将 `hold` 重置为 "none" 并使 `turns` 加 1，未暂停时不修改状态

        参数：无

        返回值类型：Hold -- 调用前的暂停状态
        """
        hold = self.hold
        if hold != "none":
            self.hold = "none"
            self.turns += 1
        return hold

    def right_click(self, request: UiRequest | None) -> None:
        """
        在处于暂停、无挂起请求或挂起请求为 `Pause` 时开启跳过分页暂停模式

        参数：
        request (UiRequest | None) -- 当前挂起的后端输入请求，空闲时为 None

        返回值类型：None
        """
        if self.hold != "none" or request is None or isinstance(request, Pause):
            self.skip = True

    def asked(self, request: UiRequest) -> None:
        """
        在后端发出 `Choose` 或 `InputText` 请求时关闭跳过分页暂停模式

        参数：
        request (UiRequest) -- 后端发来的输入请求

        返回值类型：None
        """
        if isinstance(request, (Choose, InputText)):
            self.skip = False

    def synced(self) -> None:
        """
        在面板同步时关闭跳过分页暂停模式

        参数：无

        返回值类型：None
        """
        self.skip = False
