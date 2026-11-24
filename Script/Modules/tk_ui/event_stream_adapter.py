"""
位于 Script/Modules/tk_ui 的游戏侧呈现组件，用于将领域事件转为 UiPort 渲染指令并管理暂停与清屏步骤。
该组件运行在游戏工作线程侧，push、push_batch 与 end_turn 经 UiPort 输出指令并可在暂停处阻塞该工作线程。
plan_event、plan_turn_end 与 commit 仅计算和记录暂停、清屏与渲染步骤，不调用端口且不阻塞。
本模块仅依赖标准库与 Script.Protocol，不导入界面控件或游戏核心模块。
"""

import unicodedata
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import Literal

from Script.Protocol import (
    DeltaEntry,
    DeltaEvent,
    DisplayMode,
    DomainEvent,
    NarrativeEvent,
    RenderOp,
    SceneBreak,
    SpanRole,
    StyleDefOp,
    TextBlock,
    TextOp,
    TextSpan,
    UiPort,
)

type PageStep = Literal["pause", "clear_screen"]
type Step = PageStep | RenderOp


@dataclass(frozen=True, slots=True)
class RoleStyle:
    """
    单个富文本语义角色对应的样式描述，记录目标样式名 name 以及粗体、下划线与斜体标记。
    颜色提示样式会复制这些修饰标记，以保持与基础角色样式一致的文字修饰。
    """

    name: str
    bold: bool = False
    underline: bool = False
    italic: bool = False


ROLE_STYLES: dict[SpanRole, RoleStyle] = {
    "plain": RoleStyle("standard"),
    "heading": RoleStyle("littletitle"),
    "emphasis": RoleStyle("standard_italic", italic=True),
    "strong": RoleStyle("standard_bold", bold=True),
    "character_color": RoleStyle("standard"),
    "warning": RoleStyle("warning", underline=True),
    "accent": RoleStyle("gold_enrod"),
}
"""
将语义角色 SpanRole 映射到 RoleStyle 的对照表。
表中的样式名与修饰标记对应字体配置及样式初始化所注册的样式。
"""


@dataclass(frozen=True, slots=True)
class Plan:
    """
    单次事件或回合结束计算出的输出计划，包含有序步骤元组 steps 与执行后的未读行数 unread_lines。
    steps 中的每一步为暂停标记 "pause"、清屏标记 "clear_screen" 或待发送的 RenderOp。
    """

    steps: tuple[Step, ...]
    unread_lines: int


class EventStreamAdapter:
    """
    游戏侧领域事件流适配器，将领域事件转为 UiPort 渲染指令并按显示模式安排暂停与清屏。
    push、push_batch 与 end_turn 运行于游戏工作线程，通过 UiPort 投递指令并可能在暂停时阻塞该工作线程。
    plan_event、plan_turn_end 与 commit 仅规划和提交状态而不调用端口，方便调用方自行执行步骤。
    支持 scrolling_queue 与 page_clear 两种模式，按字符格数贪心折行估算行数且不在单条事件中间暂停。
    """

    def __init__(
        self,
        port: UiPort,
        *,
        font: str,
        font_size: int,
        viewport_lines: int = 24,
        line_width: int = 80,
        mode: DisplayMode = "scrolling_queue",
    ) -> None:
        """
        初始化游戏侧事件流适配器，视口或行宽小于 1、font 为空或 font_size 不大于 0 时抛出 ValueError。

        参数：
        port (UiPort) -- 供游戏工作线程发送渲染指令、暂停与清屏的输出端口
        font (str) -- 写入颜色提示 StyleDefOp 的非空字体名称
        font_size (int) -- 写入颜色提示 StyleDefOp 的正整数字号
        viewport_lines (int) -- 视口可见行数上限，默认为 24
        line_width (int) -- 每行字符宽度格数，默认为 80
        mode (DisplayMode) -- 初始显示模式，取值为 "scrolling_queue" 或 "page_clear"，默认为 "scrolling_queue"

        返回值：None
        """
        if viewport_lines < 1 or line_width < 1:
            raise ValueError("viewport_lines and line_width must be >= 1")
        if not font or font_size <= 0:
            raise ValueError("font must be non-empty and font_size > 0")
        self._port = port
        self._viewport_lines = viewport_lines
        self._line_width = line_width
        self._mode: DisplayMode = mode
        self._font = (font, font_size)
        self._unread_lines = 0
        self._styles: set[str] = set()

    def set_mode(self, mode: DisplayMode) -> None:
        """
        切换后续规划与推送使用的显示模式，不影响已输出内容。

        参数：
        mode (DisplayMode) -- 目标显示模式，取值为 "scrolling_queue" 或 "page_clear"

        返回值：None
        """
        self._mode = mode

    def format_event(self, event: DomainEvent) -> tuple[RenderOp, ...]:
        """
        将单条领域事件转为渲染指令元组，不修改适配器状态。
        带 color_hint 的片段会同时携带角色样式名与提示样式名，并按角色修饰标记和配置的字体字号定义样式。
        已登记或同事件内已出现的颜色提示 StyleDefOp 会被跳过。
        SceneBreak 对应的转换结果为空元组。

        参数：
        event (DomainEvent) -- 待转换的领域事件

        返回值：tuple[RenderOp, ...] -- 按输出顺序排列的渲染指令元组
        """
        ops: Iterable[RenderOp] = ()
        match event:
            case NarrativeEvent():
                lead = (TextBlock.plain(event.text),) if event.text else ()
                ops = self._block_ops((*lead, *event.blocks))
            case DeltaEvent():
                ops = (TextOp(_delta_line(e) + "\n") for e in event.entries)
        return tuple(_new_styles(ops, set(self._styles)))

    def estimate_lines(self, event: DomainEvent) -> int:
        """
        按字符格数贪心折行估算单条领域事件占用的显示行数，至少返回 1。
        该估算将东亚宽字符与全角字符计为 2 格、Unicode 的 Mn 与 Me 标记计为 0 格、其余字符计为 1 格。
        仅当非零宽字符使非空当前行超出 line_width 时才换行，结果不代表像素级排版测量。

        参数：
        event (DomainEvent) -- 待估算行数的领域事件

        返回值：int -- 估算占用的显示行数，最小值为 1
        """
        return _display_lines(self.format_event(event), self._line_width)

    def plan_event(self, event: DomainEvent) -> Plan:
        """
        为单条领域事件计算输出计划，不调用端口、不修改适配器状态且不阻塞。
        遇到 SceneBreak 时，计划在存在未读行时先暂停，随后清屏并将未读行数置 0。
        其他事件在已有未读行且加上本事件估算行数达到视口上限时先安排暂停，在 page_clear 模式下同步安排清屏。
        单条事件的全部渲染指令连续排入计划，不会被暂停拆分。

        参数：
        event (DomainEvent) -- 待规划的领域事件

        返回值：Plan -- 包含有序输出步骤与执行后未读行数的计划对象
        """
        if isinstance(event, SceneBreak):
            return Plan(self._page_turn(clear=True), 0)
        ops = self.format_event(event)
        height = _display_lines(ops, self._line_width)
        unread = self._unread_lines
        if unread and unread + height >= self._viewport_lines:
            page = self._page_turn(clear=self._mode == "page_clear")
            return Plan((*page, *ops), height)
        return Plan(ops, unread + height)

    def plan_turn_end(
        self, *, following_prompt_lines: int = 0, clear_screen: bool = True
    ) -> Plan:
        """
        计算回合结束时的收尾计划，不调用端口、不修改适配器状态且不阻塞。
        若存在未读行且大于 0 的 following_prompt_lines 严格小于视口剩余行数，该方法返回空步骤计划。
        否则该方法在存在未读行时先排入暂停并按 clear_screen 决定是否清屏，且返回的计划均将未读行数置 0。

        参数：
        following_prompt_lines (int) -- 紧随其后的交互提示预计占用行数，默认为 0
        clear_screen (bool) -- 未触发同屏保留时是否安排清屏，默认为 True

        返回值：Plan -- 回合结束收尾步骤及归零后的未读行数计划
        """
        room = self._viewport_lines - self._unread_lines
        if self._unread_lines and 0 < following_prompt_lines < room:
            return Plan((), 0)
        return Plan(self._page_turn(clear=clear_screen), 0)

    def commit(self, plan: Plan) -> None:
        """
        将已执行的输出计划记入适配器内部状态，不调用端口且不阻塞。
        该方法按 plan.unread_lines 更新未读行数，并登记计划中已发出的 StyleDefOp 样式名。

        参数：
        plan (Plan) -- 已由调用方执行完毕的输出计划

        返回值：None
        """
        self._unread_lines = plan.unread_lines
        self._styles.update(
            step.name for step in plan.steps if isinstance(step, StyleDefOp)
        )

    def push(self, event: DomainEvent) -> None:
        """
        在游戏工作线程上规划并向 UiPort 推送单条领域事件，随后提交适配器状态。
        若计划包含暂停步骤，调用 UiPort.pause() 可能阻塞当前游戏工作线程直至前端应答。

        参数：
        event (DomainEvent) -- 待推送的领域事件

        返回值：None
        """
        self._run(self.plan_event(event))

    def push_batch(self, events: Sequence[DomainEvent]) -> None:
        """
        在游戏工作线程上按序列顺序依次调用 push 推送多条领域事件。
        推送期间若触发暂停步骤，可能在 UiPort.pause() 处阻塞当前游戏工作线程。

        参数：
        events (Sequence[DomainEvent]) -- 按顺序待推送的领域事件序列

        返回值：None
        """
        for event in events:
            self.push(event)

    def end_turn(
        self, *, following_prompt_lines: int = 0, clear_screen: bool = True
    ) -> None:
        """
        在游戏工作线程上规划并执行回合结束的收尾步骤，随后提交适配器状态。
        若收尾计划包含暂停步骤，调用 UiPort.pause() 可能阻塞当前游戏工作线程直至前端应答。

        参数：
        following_prompt_lines (int) -- 紧随其后的交互提示预计占用行数，默认为 0
        clear_screen (bool) -- 未触发同屏保留时是否清空屏幕，默认为 True

        返回值：None
        """
        plan = self.plan_turn_end(
            following_prompt_lines=following_prompt_lines,
            clear_screen=clear_screen,
        )
        self._run(plan)

    def _run(self, plan: Plan) -> None:
        for step in plan.steps:
            match step:
                case "pause":
                    self._port.pause()
                case "clear_screen":
                    self._port.clear("screen")
                case _:
                    self._port.emit_op(step)
        self.commit(plan)

    def _page_turn(self, *, clear: bool) -> tuple[PageStep, ...]:
        pause: tuple[PageStep, ...] = ("pause",) if self._unread_lines else ()
        return (*pause, "clear_screen") if clear else pause

    def _block_ops(self, blocks: Iterable[TextBlock]) -> Iterator[RenderOp]:
        for block in blocks:
            if block.kind == "divider":
                yield TextOp("-" * self._line_width + "\n")
                continue
            if block.kind == "quote":
                yield TextOp("> ")
            for span in block.spans:
                heading = block.kind == "heading" and span.role == "plain"
                role = "heading" if heading else span.role
                yield from _span_ops(span, ROLE_STYLES[role], self._font)
            yield TextOp("\n")


def _span_ops(
    span: TextSpan, style: RoleStyle, font: tuple[str, int]
) -> Iterator[RenderOp]:
    if span.color_hint is None:
        yield TextOp(span.text, (style.name,))
        return
    name = f"hint_{span.color_hint[1:].lower()}_{style.name}"
    yield StyleDefOp(
        name,
        span.color_hint,
        "",
        *font,
        style.bold,
        style.underline,
        style.italic,
    )
    yield TextOp(span.text, (style.name, name))


def _new_styles(ops: Iterable[RenderOp], seen: set[str]) -> Iterator[RenderOp]:
    for op in ops:
        if isinstance(op, StyleDefOp):
            if op.name in seen:
                continue
            seen.add(op.name)
        yield op


def _delta_line(entry: DeltaEntry) -> str:
    parts = [f"{entry.target} {entry.field}"]
    if entry.delta is not None:
        parts.append(f"{_signed(entry.delta)}{entry.unit}")
    if entry.new_value is not None:
        parts.append(f"-> {entry.new_value}{entry.unit}")
    return " ".join(parts)


def _signed(value: int | float | str | bool) -> str:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return str(value)
    return f"{value:+}"


def _display_lines(ops: Iterable[RenderOp], line_width: int) -> int:
    text = "".join(op.text for op in ops if isinstance(op, TextOp))
    rows = text.removesuffix("\n").split("\n")
    return sum(_wrapped_rows(row, line_width) for row in rows)


def _wrapped_rows(row: str, line_width: int) -> int:
    rows, column = 1, 0
    for char in row:
        width = _char_width(char)
        if width and column and column + width > line_width:
            rows, column = rows + 1, width
        else:
            column += width
    return rows


def _char_width(char: str) -> int:
    if unicodedata.category(char) in ("Mn", "Me"):
        return 0
    return 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
