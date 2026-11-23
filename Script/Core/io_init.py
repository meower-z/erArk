# -*- coding: UTF-8 -*-
"""游戏后端与协议端口之间的 IO 适配层，负责发送渲染操作、清屏、同步前端配置与阻塞请求玩家输入。"""

import secrets
import sys
from collections.abc import Iterable, Iterator
from typing import NoReturn

from Script.Config import game_config, normal_config
from Script.Core import perf_hook
from Script.Protocol import (
    BgColorOp,
    ButtonOp,
    ClearButtonsOp,
    ExitReason,
    FrontendInitConfig,
    ImageBatchOp,
    ImageButtonOp,
    ImageOp,
    RenderOp,
    SessionCancelled,
    StyleDefOp,
    TextOp,
    ThreadedUiPort,
    UiPort,
)

TEXT_LIMIT = sys.maxsize
"""调用 `ask_text` 时传给端口的文本长度上限，取 `sys.maxsize` 表示不限制输入长度。"""
_port: UiPort = ThreadedUiPort(secrets.token_hex(16))


def configure(port: UiPort) -> None:
    """
    替换后端当前使用的通信端口实例

    参数：
    port (UiPort) -- 新的后端通信端口

    返回值类型：None
    """
    global _port
    _port = port


def apply_frontend_config(config: FrontendInitConfig) -> None:
    """
    将前端初始配置中的窗口尺寸、文本宽度与字号写入全局 `normal_config.config_normal`

    参数：
    config (FrontendInitConfig) -- 前端上报的窗口与字号配置

    返回值类型：None
    """
    normal = normal_config.config_normal
    normal.window_width = config.window_width
    normal.window_hight = config.window_height
    normal.text_width = config.text_width
    normal.font_size = config.font_size
    normal.order_font_size = config.font_size - 2


def _count(kind: str = "") -> None:
    if not perf_hook.enabled:
        return
    if not perf_hook.get_mark("flow.screen_first_msg"):
        perf_hook.mark("flow.screen_first_msg")
    perf_hook.hook_count("flow.msg_total")
    if kind:
        perf_hook.hook_count(kind)


def _emit(op: RenderOp, kind: str = "") -> None:
    _count(kind)
    _port.emit_op(op)


def _style(style: str | tuple[str, ...]) -> tuple[str, ...]:
    return (style,) if isinstance(style, str) else tuple(style)


def ask_choice(valid_ids: tuple[str, ...]) -> str:
    """
    标记本屏入队完成并阻塞等待前端从指定合法选项中返回选择

    参数：
    valid_ids (tuple[str, ...]) -- 本次提示允许接受的选项编号元组

    返回值类型：str -- 前端提交的原始选项文本
    """
    perf_hook.mark("flow.enqueue_done")
    return _port.choose(valid_ids).raw_value


def ask_text(allow_empty: bool) -> str:
    """
    标记本屏入队完成、关闭跳过暂停并阻塞等待前端返回自由文本

    参数：
    allow_empty (bool) -- 是否允许前端提交空字符串

    返回值类型：str -- 前端提交的文本内容
    """
    perf_hook.mark("flow.enqueue_done")
    return _port.input_text(TEXT_LIMIT, allow_empty=allow_empty).text


def wait_continue() -> None:
    """
    标记本屏入队完成并调用端口暂停，跳过模式开启且允许跳过时端口会在刷出缓冲后立即返回

    参数：无

    返回值类型：None
    """
    perf_hook.mark("flow.enqueue_done")
    _port.pause()


def set_skip_pauses(enabled: bool) -> None:
    """
    向端口设置跳过可跳过暂停的开关状态

    参数：
    enabled (bool) -- 为 True 时开启跳过暂停，为 False 时关闭

    返回值类型：None
    """
    _port.set_skip_pauses(enabled)


def flush() -> None:
    """
    立即刷出端口中已缓冲的渲染操作

    参数：无

    返回值类型：None
    """
    _port.flush()


def flushing[T](items: Iterable[T]) -> Iterator[T]:
    """
    逐项产出可迭代对象中的元素，并在调用方处理完每一项后调用 `flush()` 立即刷出缓冲输出

    参数：
    items (Iterable[T]) -- 待逐项处理的数据流

    返回值类型：Iterator[T] -- 依次产出 `items` 元素的迭代器
    """
    for item in items:
        yield item
        flush()


def end_session(reason: ExitReason = "normal") -> NoReturn:
    """
    向端口发送会话结束事件并抛出 `SessionCancelled` 以正常退出游戏流程线程

    参数：
    reason (ExitReason) -- 会话结束原因，默认 "normal"

    返回值类型：NoReturn -- 始终抛出 `SessionCancelled`
    """
    _port.finish(reason)
    raise SessionCancelled(reason)


def era_print(
    string: str, style: str | tuple[str, ...] = "standard", tooltip: str = ""
) -> None:
    """
    向端口发送一条带样式与可选悬停提示的文本渲染操作

    参数：
    string (str) -- 要显示的文本内容
    style (str | tuple[str, ...]) -- 单个样式名或样式名元组
    tooltip (str) -- 鼠标悬停提示文本，为空时不绑定提示

    返回值类型：None
    """
    _emit(TextOp(string, _style(style), tooltip or ""), "flow.msg_text")


def image_print(image_name: str) -> None:
    """
    向端口发送单张图片的渲染操作

    参数：
    image_name (str) -- 图片资源名

    返回值类型：None
    """
    _emit(ImageOp(image_name), "flow.msg_image")


def image_list_print(image_name_list: list[str]) -> None:
    """
    向端口批量发送多张图片的渲染操作，列表为空时直接返回

    参数：
    image_name_list (list[str]) -- 按显示顺序排列的图片资源名列表

    返回值类型：None
    """
    if not image_name_list:
        return
    if perf_hook.enabled:
        perf_hook.hook_count("flow.msg_image", len(image_name_list))
    _emit(ImageBatchOp(tuple(image_name_list)), "flow.msg_image_batch")


def clear_screen() -> None:
    """
    向端口发送清空屏幕内容的指令

    参数：无

    返回值类型：None
    """
    _count()
    _port.clear("screen")


def frame_style_def(
    style_name: str,
    foreground: str,
    background: str,
    font: str,
    fontsize: int,
    bold: bool,
    underline: bool,
    italic: bool,
) -> None:
    """
    向端口发送一条富文本样式定义操作

    参数：
    style_name (str) -- 样式名称
    foreground (str) -- 前景色
    background (str) -- 背景色
    font (str) -- 字体名称
    fontsize (int) -- 字号大小
    bold (bool) -- 是否加粗
    underline (bool) -- 是否加下划线
    italic (bool) -- 是否斜体

    返回值类型：None
    """
    _emit(
        StyleDefOp(
            style_name,
            foreground,
            background,
            font,
            fontsize,
            bold,
            underline,
            italic,
        )
    )


def set_background(color: str) -> None:
    """
    向端口发送修改文本框背景色的操作

    参数：
    color (str) -- 目标背景色字符串

    返回值类型：None
    """
    _emit(BgColorOp(color))


def clear_order() -> None:
    """
    向端口发送清空输入框内容的指令

    参数：无

    返回值类型：None
    """
    _count()
    _port.clear("input")


def io_print_cmd(
    cmd_str: str,
    cmd_number: int | str,
    normal_style: str = "standard",
    on_style: str = "onbutton",
    tooltip: str = "",
) -> None:
    """
    向端口发送一个文本命令按钮的渲染操作

    参数：
    cmd_str (str) -- 按钮显示文字
    cmd_number (int | str) -- 按钮对应的命令编号
    normal_style (str) -- 常态样式名
    on_style (str) -- 鼠标悬停样式名
    tooltip (str) -- 悬停提示文本

    返回值类型：None
    """
    op = ButtonOp(
        cmd_str,
        str(cmd_number),
        _style(normal_style),
        _style(on_style),
        tooltip or "",
    )
    _emit(op, "flow.msg_cmd")


def io_print_image_cmd(
    cmd_str: str, cmd_number: int | str, tooltip: str = ""
) -> None:
    """
    向端口发送一个图片命令按钮的渲染操作

    参数：
    cmd_str (str) -- 按钮图片资源名
    cmd_number (int | str) -- 按钮对应的命令编号
    tooltip (str) -- 悬停提示文本

    返回值类型：None
    """
    _emit(ImageButtonOp(cmd_str, str(cmd_number), tooltip or ""))


def io_clear_cmd(*cmd_numbers: int | str) -> None:
    """
    向端口发送清除指定或全部命令按钮的操作

    参数：
    cmd_numbers (int | str) -- 要清除的命令编号，不传时清除当前全部按钮

    返回值类型：None
    """
    ids = tuple(str(number) for number in cmd_numbers) if cmd_numbers else None
    _emit(ClearButtonsOp(ids))


def style_def(
    style_name: str,
    foreground: str,
    background: str,
    font: str,
    fontsize: int,
    bold: bool,
    underline: bool,
    italic: bool,
) -> None:
    """
    样式定义占位函数

    参数：
    style_name (str) -- 样式名称
    foreground (str) -- 前景色/字体颜色
    background (str) -- 背景色
    font (str) -- 字体
    fontsize (int) -- 字号
    bold (bool) -- 加粗
    underline (bool) -- 下划线
    italic (bool) -- 斜体

    返回值类型：无
    功能描述：提供一个样式定义的占位函数，会在init_style中被覆盖
    """
    pass


def init_style() -> None:
    """
    富文本样式初始化

    参数：无

    返回值类型：无
    功能描述：初始化所有游戏中使用的样式
    """
    global style_def

    def new_style_def(
        style_name: str,
        foreground: str,
        background: str,
        font: str,
        fontsize: int,
        bold: bool,
        underline: bool,
        italic: bool,
    ) -> None:
        frame_style_def(
            style_name,
            foreground,
            background,
            font,
            fontsize,
            bold,
            underline,
            italic,
        )

    style_def = new_style_def
    style_list = game_config.config_font
    standard_data = style_list[0]
    for style_id in style_list:
        style = style_list[style_id]
        for k in standard_data.__dict__:
            if k not in style.__dict__:
                style.__dict__[k] = standard_data.__dict__[k]
        if "font" not in style.__dict__ or style.font == "":
            style.font = normal_config.config_normal.font
        # data.json 里 bool 列存的是 0/1 整数（buildconfig.py 把 bool 列写成 int），转成 bool 再送出
        style_def(
            style.name,
            style.foreground,
            style.background,
            style.font,
            normal_config.config_normal.font_size,
            bool(style.bold),
            bool(style.underline),
            bool(style.italic),
        )
    # 额外注册三个通用修饰符 tag，便于在文本中单独使用或与基础样式组合：
    # 这些 tag 注册时不改变前景色/背景色/字体，只设置字体属性（bold/underline/italic）
    # 使用空的 foreground/background ("") 以及默认字体，以便只体现修饰符效果
    modifier_font = normal_config.config_normal.font
    modifier_size = normal_config.config_normal.font_size
    # bold
    style_def("bold", "", "", modifier_font, modifier_size, True, False, False)
    # underline
    style_def(
        "underline", "", "", modifier_font, modifier_size, False, True, False
    )
    # italic
    style_def(
        "italic", "", "", modifier_font, modifier_size, False, False, True
    )
    # 为了让修饰符与基础样式组合时也能生效，预先为每个基础样式注册所有修饰符的组合样式。
    # 组合名采用 base_mod1_mod2 形式，例如 "green_bold_italic"，不会包含空格，方便前端作为 tag 使用。
    modifier_names = ["bold", "underline", "italic"]
    # 生成所有非空子集组合（共 2^3 - 1 = 7 种）
    from itertools import combinations

    base_style_names = list(game_config.config_font_data.keys())
    for base in base_style_names:
        # 找到基础样式的数据（若存在于 config_font）以复制颜色/字体设置
        style_obj = None
        if base in game_config.config_font_data:
            base_id = game_config.config_font_data[base]
            if base_id in game_config.config_font:
                style_obj = game_config.config_font[base_id]
        # 若没找到 style_obj，则使用标准样式作为基准
        if style_obj is None:
            style_obj = standard_data

        # 对 1..3 个修饰符的所有组合进行注册
        for r in range(1, len(modifier_names) + 1):
            for combo in combinations(modifier_names, r):
                combo_name = base + "_" + "_".join(combo)
                bold_flag = "bold" in combo
                underline_flag = "underline" in combo
                italic_flag = "italic" in combo
                style_def(
                    combo_name,
                    style_obj.foreground,
                    style_obj.background,
                    (
                        style_obj.font
                        if hasattr(style_obj, "font") and style_obj.font
                        else normal_config.config_normal.font
                    ),
                    normal_config.config_normal.font_size,
                    bold_flag,
                    underline_flag,
                    italic_flag,
                )
