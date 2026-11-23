"""Tk 文本框悬停提示浮窗的延迟展示、跟随移动与失效标签回收模块。"""

from tkinter import Text, Toplevel, font, ttk

TOOLTIP_DELAY_MS = 350
"""鼠标悬停后弹出提示浮窗的延迟毫秒数。"""
TAG_PREFIX = "text_tooltip_"
"""文本框中悬停提示标签使用的统一名称前缀。"""


class Tooltip:
    """管理单个顶层悬停提示浮窗的定时显示、位置更新、隐藏以及空提示标签清理。"""

    def __init__(self, textbox: Text, family: str, size: int) -> None:
        """
        绑定目标文本框并记录提示文字的字体家族与字号

        参数：
        textbox (Text) -- 悬停提示所属的 Tk 文本框
        family (str) -- 提示文本字体名称
        size (int) -- 提示文本字号

        返回值类型：None
        """
        self._textbox = textbox
        self._family = family
        self._size = size
        self._window: Toplevel | None = None
        self._after_id: str | None = None
        self._text = ""
        self._coords = (0, 0)

    def schedule(self, text: str, coords: tuple[int, int] | None) -> None:
        """
        取消旧定时器并安排在延迟后于给定或当前指针位置显示提示，文本为空时立即隐藏

        参数：
        text (str) -- 提示内容
        coords (tuple[int, int] | None) -- 屏幕坐标，为 None 时读取当前鼠标指针位置

        返回值类型：None
        """
        self._text = text or ""
        self._coords = coords or (
            self._textbox.winfo_pointerx(),
            self._textbox.winfo_pointery(),
        )
        self._cancel()
        if not self._text:
            self._destroy()
            return
        self._after_id = self._textbox.after(TOOLTIP_DELAY_MS, self._show)

    def hide(self) -> None:
        """
        清空提示文本、取消待触发定时器并销毁当前提示浮窗

        参数：无

        返回值类型：None
        """
        self._text = ""
        self._cancel()
        self._destroy()

    def move(self, coords: tuple[int, int]) -> None:
        """
        更新提示坐标并在浮窗已显示时同步移动其位置

        参数：
        coords (tuple[int, int]) -- 新的屏幕坐标

        返回值类型：None
        """
        self._coords = coords
        if self._window is not None:
            self._place()

    def drop_stale_tags(self) -> None:
        """
        删除文本框中以 `TAG_PREFIX` 开头且范围为空的提示标签

        参数：无

        返回值类型：None
        """
        textbox = self._textbox
        for tag_name in textbox.tag_names():
            if tag_name.startswith(TAG_PREFIX) and not textbox.tag_ranges(
                tag_name
            ):
                textbox.tag_delete(tag_name)

    def _cancel(self) -> None:
        if self._after_id is not None and self._textbox.winfo_exists():
            try:
                self._textbox.after_cancel(self._after_id)
            except Exception:
                pass
        self._after_id = None

    def _destroy(self) -> None:
        if self._window is not None:
            try:
                self._window.destroy()
            except Exception:
                pass
        self._window = None

    def _place(self) -> None:
        if self._window is not None:
            x, y = self._coords
            self._window.wm_geometry(f"+{x + 12}+{y + 18}")

    def _show(self) -> None:
        self._after_id = None
        if not self._text:
            return
        self._destroy()
        window = Toplevel(self._textbox)
        window.wm_overrideredirect(True)
        try:
            window.wm_attributes("-topmost", True)
        except Exception:
            pass
        label = ttk.Label(
            window,
            text=self._text,
            justify="left",
            background="#fef3c7",
            foreground="#1f2933",
            relief="solid",
            borderwidth=1,
            padding=(6, 3),
            wraplength=min(self._textbox.winfo_width() // 2, 600),
            font=font.Font(family=self._family, size=self._size),
        )
        label.pack()
        self._window = window
        self._place()
