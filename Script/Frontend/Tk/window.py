"""Tk 主窗口创建与控件装配模块，负责根窗口、本地字体、缩放设置、文本框、滚动条与指令输入框。"""

import sys
import time
from collections.abc import Callable
from tkinter import (
    VERTICAL,
    E,
    Entry,
    Event,
    N,
    PhotoImage,
    S,
    StringVar,
    Text,
    Tk,
    W,
    font,
    ttk,
)

from Script.Config import game_config
from Script.Core import game_type, perf_hook, text_handle
from Script.Frontend.Tk import fonts, screen
from Script.Protocol import FrontendInitConfig

CURSOR_TEXT = "~$"
"""指令输入框左侧显示的命令提示符文本。"""


def _enable_dpi_awareness() -> None:
    if sys.platform == "win32":
        try:
            import ctypes

            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except AttributeError:
                ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _order_font(normal: game_type.NormalConfig, font_size: int) -> dict:
    standard = game_config.config_font[0].__dict__
    order = game_config.config_font[1].__dict__
    style = {**standard, **order}
    if not order.get("font"):
        style["font"] = normal.font
    if "font_size" not in order:
        style["font_size"] = font_size - 2
    return style


class Window:
    """封装 Tk 根窗口、输出文本框、指令输入框及批量滚底控制的主窗口类。"""

    def __init__(self, normal: game_type.NormalConfig) -> None:
        """
        仅在 Windows（`sys.platform == "win32"`）下启用 DPI 感知，创建并最大化 Tk 根窗口，加载本地字体、
        计算初始配置与缩放并装配控件

        参数：
        normal (game_type.NormalConfig) -- 游戏基础配置对象

        返回值类型：None
        """
        _enable_dpi_awareness()
        self.root = Tk()
        fonts.load_local_fonts(self.root)
        self.config: FrontendInitConfig = screen.init_config(
            normal,
            self.root.winfo_screenwidth(),
            self.root.winfo_screenheight(),
        )
        self.root.tk.call(
            "tk",
            "scaling",
            screen.scaling(
                getattr(normal, "tk_dpi", 0), self.root.winfo_fpixels("1i")
            ),
        )
        self.root.title(f"{normal.game_name} {normal.verson} -α测")
        if self.root.tk.call("tk", "windowingsystem") == "x11":
            self.root.attributes("-zoomed", True)
        else:
            self.root.state("zoomed")
        self.root.deiconify()
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        frame = ttk.Frame(self.root, borderwidth=2)
        frame.grid(column=0, row=0, sticky=(N, W, E, S))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        self.root.iconphoto(
            True, PhotoImage(file=fonts.resource_path("image/logo.png"))
        )
        self.textbox = self._textbox(frame, normal)
        order_style = _order_font(normal, self.config.font_size)
        self.order = StringVar()
        self.inputbox = self._inputbox(frame, normal, order_style)
        self.normal_font = font.Font(
            family=order_style["font"], size=self.config.font_size
        )
        self._defer_see_end = False
        self._see_end_pending = False

    def _textbox(
        self, frame: ttk.Frame, normal: game_type.NormalConfig
    ) -> Text:
        textbox = Text(
            frame,
            width=normal.textbox_width,
            height=normal.textbox_hight,
            highlightbackground=normal.background,
            bd=0,
            cursor="",
            insertwidth=0,
            selectbackground=normal.background,
            spacing1=1,
            spacing2=1,
            spacing3=1,
        )
        textbox.grid(column=0, row=0, sticky=(N, W, E, S))
        scrollbar = ttk.Scrollbar(frame, orient=VERTICAL, command=textbox.yview)
        textbox.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(column=1, row=0, sticky=(N, E, S), rowspan=2)
        textbox.configure(takefocus=0)
        textbox.bind("<FocusIn>", self._return_focus)
        return textbox

    def _inputbox(
        self, frame: ttk.Frame, normal: game_type.NormalConfig, style: dict
    ) -> Entry:
        holder = Text(
            frame,
            highlightbackground=normal.background,
            background=normal.background,
            bd=0,
        )
        holder.grid(column=0, row=1, sticky=(W, E, S))
        cursor = Text(
            holder,
            width=text_handle.get_text_index(CURSOR_TEXT),
            height=1,
            highlightbackground=style["background"],
            background=style["background"],
            bd=0,
        )
        cursor.grid(column=0, row=0, sticky=(W, E, S))
        cursor.insert("end", CURSOR_TEXT)
        cursor.config(foreground=style["foreground"])
        inputbox = Entry(
            holder,
            borderwidth=0,
            insertborderwidth=0,
            selectborderwidth=0,
            highlightthickness=0,
            bg=style["background"],
            foreground=style["foreground"],
            selectbackground=style["selectbackground"],
            textvariable=self.order,
            font=font.Font(family=style["font"], size=style["font_size"]),
            width=normal.inputbox_width,
        )
        inputbox.grid(column=1, row=0, sticky=(N, E, S))
        return inputbox

    def _return_focus(self, event: Event | None = None) -> None:
        self.inputbox.focus_set()

    def on_close(self, handler: Callable[[], None]) -> None:
        """
        为窗口管理器关闭事件 `WM_DELETE_WINDOW` 绑定处理函数

        参数：
        handler (Callable[[], None]) -- 点击关闭按钮时调用的无参回调

        返回值类型：None
        """
        self.root.protocol("WM_DELETE_WINDOW", handler)

    def focus_input(self) -> None:
        """
        尝试将输入焦点切至指令输入框，异常时静默返回

        参数：无

        返回值类型：None
        """
        try:
            self.inputbox.focus_force()
        except Exception:
            return

    def set_background(self, color: str) -> None:
        """
        设置文本框的背景色、选中背景色与光标背景色

        参数：
        color (str) -- 目标颜色字符串

        返回值类型：None
        """
        self.textbox.config(insertbackground=color)
        self.textbox.configure(background=color, selectbackground=color)

    def defer_see_end(self) -> None:
        """
        开启延迟滚底模式，使后续 `see_end` 调用只做标记而不立即滚动

        参数：无

        返回值类型：None
        """
        self._defer_see_end = True

    def flush_see_end(self) -> None:
        """
        关闭延迟滚底模式并在期间存在待滚底标记时执行一次滚底

        参数：无

        返回值类型：None
        """
        self._defer_see_end = False
        if self._see_end_pending:
            self._see_end_pending = False
            self.see_end()

    def see_end(self) -> None:
        """
        将文本框滚至末尾内容字符（"end-2c"）可见，
        延迟模式下仅记录标记，启用性能埋点时记录滚动耗时

        参数：无

        返回值类型：None
        """
        if self._defer_see_end:
            self._see_end_pending = True
            return
        if perf_hook.enabled:
            start = time.perf_counter()
            self.textbox.see("end-2c")
            perf_hook.hook_time("gui.see_end", time.perf_counter() - start)
            return
        self.textbox.see("end-2c")
