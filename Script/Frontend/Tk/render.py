"""将 `Script/Protocol` 渲染操作转换为 Tk 文本框插入、标签样式、图片与可点击命令按钮的渲染模块。"""

import time
import uuid
from collections.abc import Callable
from tkinter import END, Event, Text

from Script.Config import normal_config
from Script.Core import perf_hook
from Script.Frontend.Tk import image_cache
from Script.Frontend.Tk.pager import Fit
from Script.Frontend.Tk.tooltip import TAG_PREFIX, Tooltip
from Script.Frontend.Tk.window import Window
from Script.Protocol import (
    BgColorOp,
    ButtonOp,
    ClearButtonsOp,
    ImageBatchOp,
    ImageButtonOp,
    ImageOp,
    RenderOp,
    StyleDefOp,
    TextOp,
)

ANCHOR = "pager.anchor"
"""标记未读输出起点的 Tk 文本框标记名。"""
UNIT = "pager.unit"
"""标记当前渲染块起点的 Tk 文本框标记名。"""
HIDDEN = "pager.hidden"
"""用于以 elide 属性隐藏溢出渲染块的 Tk 文本框标签名。"""


def _timed(key: str, start: float) -> None:
    perf_hook.hook_time(key, time.perf_counter() - start)


class Renderer:
    """Tk 文本框渲染器，负责分发 `RenderOp`、管理按钮与提示绑定、裁剪超限旧文本，并维护分页标记与未读高度测量。"""

    def __init__(
        self, window: Window, tooltip: Tooltip, press: Callable[[str], None]
    ) -> None:
        """
        初始化渲染器，关联主窗口、悬停提示与按钮回调，并在文本框 "1.0" 处设置 `ANCHOR` 与 `UNIT` 标记及 `HIDDEN` 标签

        参数：
        window (Window) -- Tk 主窗口对象
        tooltip (Tooltip) -- 悬停提示浮窗管理器
        press (Callable[[str], None]) -- 点击按钮时以命令编号调用的回调函数

        返回值类型：None
        """
        self._window = window
        self._textbox = window.textbox
        self._tooltip = tooltip
        self._press = press
        self.cmd_tag_map: dict[str, str] = {}
        """当前活跃命令编号到 Tk 文本框按钮标签名的映射。"""
        for mark in (ANCHOR, UNIT):
            self._textbox.mark_set(mark, "1.0")
            self._textbox.mark_gravity(mark, "left")
        self._textbox.tag_configure(HIDDEN, elide=True)
        self._offset = 0
        self._seen = 0

    def render(self, op: RenderOp) -> None:
        """
        执行单条协议渲染操作，当 `TextOp` 文本或 `ButtonOp` 标签包含换行符时检查并裁剪超出上限的旧行

        参数：
        op (RenderOp) -- 协议渲染操作对象

        返回值类型：None
        """
        perf = perf_hook.enabled
        start = time.perf_counter() if perf else 0.0
        match op:
            case TextOp():
                self._print_text(op.text, _tags(op.style), op.tooltip)
                key, label = "gui.now_print", op.text
            case ButtonOp():
                self._print_button(op)
                key, label = "gui.cmd_render", op.label
            case ImageButtonOp():
                self._print_image_button(op)
                key, label = "gui.image_cmd_render", op.asset_id
            case ImageOp():
                self._image(op.asset_id)
                key, label = "gui.image_create", ""
            case ImageBatchOp():
                for asset_id in op.asset_ids:
                    self._image(asset_id)
                key, label = "gui.image_create", ""
            case StyleDefOp():
                self._style(op)
                return
            case BgColorOp():
                self._window.set_background(op.color)
                return
            case ClearButtonsOp():
                self.clear_buttons(op.command_ids)
                return
        if perf:
            _timed(key, start)
        if "\n" in label:
            self._trim()

    def clear_screen(self) -> None:
        """
        清除全部按钮绑定、删除文本框所有内容并清理失效的悬停提示标签

        参数：无

        返回值类型：None
        """
        self.clear_buttons(None)
        start = time.perf_counter()
        self._textbox.delete("1.0", END)
        self._offset = 0
        self._tooltip.drop_stale_tags()
        if perf_hook.enabled:
            _timed("gui.clear_screen_delete", start)

    def clear_buttons(self, command_ids: tuple[str, ...] | None) -> None:
        """
        移除指定命令编号的按钮标签并将对应范围恢复为 `standard` 样式

        参数：
        command_ids (tuple[str, ...] | None) -- 要清除的命令编号元组，为 None 时清除全部按钮

        返回值类型：None
        """
        start = time.perf_counter()
        targets = list(self.cmd_tag_map) if command_ids is None else command_ids
        textbox = self._textbox
        for command_id in targets:
            tag = self.cmd_tag_map.pop(command_id, None)
            if tag is None:
                continue
            ranges = textbox.tag_ranges(tag)
            if len(ranges):
                first, last = ranges[0], ranges[1]
                for tag_name in textbox.tag_names(first):
                    textbox.tag_remove(tag_name, first, last)
                textbox.tag_add("standard", first, last)
            textbox.tag_delete(tag)
        if perf_hook.enabled:
            _timed("gui.clear_cmd", start)
            perf_hook.hook_count("gui.clear_cmd_tags", len(targets))

    def hits_button(self, x_root: int, y_root: int) -> bool:
        """
        判断给定的屏幕坐标是否落在文本框内且命中任一活跃命令按钮标签

        参数：
        x_root (int) -- 事件在屏幕坐标系中的横坐标
        y_root (int) -- 事件在屏幕坐标系中的纵坐标

        返回值类型：bool -- 命中活跃按钮时返回 True，否则返回 False
        """
        textbox = self._textbox
        x = x_root - textbox.winfo_rootx()
        y = y_root - textbox.winfo_rooty()
        if not (
            0 <= x < textbox.winfo_width() and 0 <= y < textbox.winfo_height()
        ):
            return False
        point_tags = set(textbox.tag_names(f"@{x},{y}"))
        return bool(point_tags & set(self.cmd_tag_map.values()))

    def mark_unit(self) -> None:
        """
        将 `UNIT` 标记移至文本框当前内容末尾（"end-1c"）以界定下一渲染块的起点

        参数：无

        返回值类型：None
        """
        self._textbox.mark_set(UNIT, "end-1c")

    def fit(self) -> Fit:
        """
        按 Tk 实际布局测量扣除已显示偏移后的未读高度、块前高度与视口高度。
        若存在已显示偏移且锚点所在显示行高度变化，先清零该偏移使该行从顶展示。
        末尾含换行符时未读高度测至 "end-1c"，否则测至 "end"。

        参数：无

        返回值类型：Fit -- 含 `used`、`before_unit` 与 `viewport` 的像素高度快照
        """
        textbox = self._textbox
        if self._offset and self._line()[1] != self._seen:
            self._offset = 0
        end = "end-1c" if textbox.get("end-2c", "end-1c") == "\n" else "end"
        return Fit(
            _ypixels(textbox, ANCHOR, end) - self._offset,
            _ypixels(textbox, ANCHOR, UNIT) - self._offset,
            self._viewport(),
        )

    def hide_unit(self) -> None:
        """
        为 `UNIT` 标记至文本末尾的范围添加 `HIDDEN` 标签以隐藏溢出渲染块

        参数：无

        返回值类型：None
        """
        self._textbox.tag_add(HIDDEN, UNIT, "end")

    def reveal(self) -> None:
        """
        移除文本框全文范围内的 `HIDDEN` 标签以恢复显示

        参数：无

        返回值类型：None
        """
        self._textbox.tag_remove(HIDDEN, "1.0", "end")

    def pin(self) -> None:
        """
        将文本框视图滚至 `ANCHOR` 所在行置顶，并在行内偏移非零时再下滚对应像素

        参数：无

        返回值类型：None
        """
        self._textbox.yview(ANCHOR)
        if self._offset:
            self._textbox.yview_scroll(self._offset, "pixels")

    def anchor_to_end(self) -> None:
        """
        将 `ANCHOR` 移至 "end-1c" 并清零行内偏移，
        若该位置不在显示行首则将末行像素高度记为已显示偏移

        参数：无

        返回值类型：None
        """
        textbox = self._textbox
        self._anchor("end-1c")
        if textbox.compare(ANCHOR, "!=", f"{ANCHOR} display linestart"):
            self._offset = self._seen = _ypixels(textbox, ANCHOR, "end")

    def anchor_to_unit(self) -> None:
        """
        将 `ANCHOR` 标记移至 `UNIT` 标记所在位置

        参数：无

        返回值类型：None
        """
        self._anchor(UNIT)

    def advance_page(self) -> None:
        """
        定位到 `ANCHOR` 后将锚点推至视口底行并清零偏移，
        若单显示行高于视口则按视口高度递增行内偏移，
        偏移达到行高后移至下一显示行或末行末尾

        参数：无

        返回值类型：None
        """
        textbox = self._textbox
        self.pin()
        bottom = textbox.index(f"@0,{textbox.winfo_height() - 1}")
        if textbox.compare(bottom, ">", ANCHOR):
            self._anchor(bottom)
            return
        following, height = self._line()
        self._offset += self._viewport()
        self._seen = height
        if self._offset < height:
            return
        if following is None:
            self.anchor_to_end()
        else:
            self._anchor(following)

    def _line(self) -> tuple[str | None, int]:
        textbox = self._textbox
        following = textbox.index(f"{ANCHOR} +1 display lines")
        height = _ypixels(textbox, ANCHOR, following)
        if height:
            return following, height
        return None, _ypixels(textbox, ANCHOR, "end")

    def _anchor(self, index: str) -> None:
        self._textbox.mark_set(ANCHOR, index)
        self._offset = 0

    def _viewport(self) -> int:
        textbox = self._textbox
        inset = sum(
            textbox.winfo_pixels(textbox.cget(option))
            for option in ("borderwidth", "highlightthickness", "pady")
        )
        return textbox.winfo_height() - 2 * inset

    def _print_text(
        self, text: str, style: tuple[str, ...], tooltip: str
    ) -> None:
        textbox = self._textbox
        perf = perf_hook.enabled
        start_index = textbox.index("end-1c") if tooltip and text else None
        start = time.perf_counter() if perf else 0.0
        textbox.insert("end", text, style)
        if perf:
            _timed("gui.text_insert", start)
            start = time.perf_counter()
        if start_index is not None:
            end_index = textbox.index("end-1c")
            if textbox.compare(start_index, "<", end_index):
                tag_name = f"{TAG_PREFIX}{uuid.uuid4().hex}"
                textbox.tag_add(tag_name, start_index, end_index)
                self._bind_tooltip(tag_name, tooltip)
            if perf:
                _timed("gui.tooltip_tag", start)
                perf_hook.hook_count("gui.tooltip_tag_created")
        if not text and tooltip:
            self._tooltip.hide()
        self._window.see_end()

    def _bind_tooltip(self, tag_name: str, tooltip: str) -> None:
        textbox = self._textbox

        def enter(event: Event | None = None) -> None:
            coords = (event.x_root, event.y_root) if event is not None else None
            self._tooltip.schedule(tooltip, coords)

        def leave(event: Event | None = None) -> None:
            self._tooltip.hide()

        def motion(event: Event | None = None) -> None:
            if event is not None:
                self._tooltip.move((event.x_root, event.y_root))

        textbox.tag_bind(tag_name, "<Enter>", enter)
        textbox.tag_bind(tag_name, "<Leave>", leave)
        textbox.tag_bind(tag_name, "<Motion>", motion)

    def _new_command_tag(self, command_id: str) -> str:
        tag_name = str(uuid.uuid1())
        self._textbox.tag_configure(tag_name)
        if command_id in self.cmd_tag_map:
            self.clear_buttons((command_id,))
        self.cmd_tag_map[command_id] = tag_name
        return tag_name

    def _bind_command(
        self,
        tag_name: str,
        command_id: str,
        tooltip: str,
        hover: Callable[[bool], None] | None = None,
    ) -> None:
        textbox = self._textbox

        def press(event: Event | None = None) -> None:
            textbox.configure(cursor="")
            self._tooltip.hide()
            self._press(command_id)

        def enter(event: Event | None = None) -> None:
            if hover is not None:
                hover(True)
            if tooltip:
                coords = (
                    (event.x_root, event.y_root) if event is not None else None
                )
                self._tooltip.schedule(tooltip, coords)

        def leave(event: Event | None = None) -> None:
            if hover is not None:
                hover(False)
                textbox.configure(cursor="")
            self._tooltip.hide()

        def motion(event: Event | None = None) -> None:
            if tooltip and event is not None:
                self._tooltip.move((event.x_root, event.y_root))

        textbox.tag_bind(tag_name, "<1>", press)
        textbox.tag_bind(tag_name, "<Enter>", enter)
        textbox.tag_bind(tag_name, "<Leave>", leave)
        textbox.tag_bind(tag_name, "<Motion>", motion)

    def _print_button(self, op: ButtonOp) -> None:
        textbox = self._textbox
        tag_name = self._new_command_tag(op.command_id)
        normal_tags = _tags(op.normal_style)
        hover_tags = _tags(op.hover_style)

        def hover(inside: bool) -> None:
            first, last = textbox.tag_ranges(tag_name)[:2]
            removed, added = (
                (normal_tags, hover_tags)
                if inside
                else (hover_tags, normal_tags)
            )
            for tag in removed:
                textbox.tag_remove(tag, first, last)
            for tag in added:
                textbox.tag_add(tag, first, last)

        self._bind_command(tag_name, op.command_id, op.tooltip, hover)
        textbox.insert("end", op.label, (tag_name, *normal_tags))
        self._window.see_end()

    def _print_image_button(self, op: ImageButtonOp) -> None:
        if op.asset_id not in image_cache.image_data:
            return
        textbox = self._textbox
        tag_name = self._new_command_tag(op.command_id)
        self._bind_command(tag_name, op.command_id, op.tooltip)
        index = textbox.index("end -1c")
        textbox.image_create(index, image=image_cache.image_data[op.asset_id])
        textbox.tag_add(tag_name, index, f"{index} + 1 char")
        self._window.see_end()

    def _image(self, asset_id: str) -> None:
        self._textbox.image_create(
            "end", image=image_cache.image_data[asset_id]
        )

    def _style(self, op: StyleDefOp) -> None:
        modifiers = [
            name
            for name, enabled in (
                ("bold", op.bold),
                ("underline", op.underline),
                ("italic", op.italic),
            )
            if enabled
        ]
        self._textbox.tag_configure(
            op.name.replace(" ", ""),
            foreground=op.fg,
            background=op.bg,
            font=(op.font, op.size, *modifiers),
        )

    def _trim(self) -> None:
        perf = perf_hook.enabled
        start = time.perf_counter() if perf else 0.0
        limit = normal_config.config_normal.text_hight
        if int(self._textbox.index("end-1c").split(".")[0]) > limit * 10:
            if perf:
                perf_hook.hook_count("gui.line_trim_delete")
            end = self._textbox.index(f"{limit * 5}.0")
            if self._textbox.compare(ANCHOR, "<", end):
                end = self._textbox.index(f"{ANCHOR} linestart")
            self._textbox.delete("1.0", end)
            self._tooltip.drop_stale_tags()
        if perf:
            _timed("gui.line_trim_scan", start)


def _ypixels(textbox: Text, start: str, end: str) -> int:
    return textbox.count(start, end, "update", "ypixels") or 0


def _tags(style: tuple[str, ...]) -> tuple[str, ...]:
    if not style:
        return style
    return (style[0].replace(" ", ""), *style[1:])
