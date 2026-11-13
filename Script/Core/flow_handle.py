# -*- coding: UTF-8 -*-
"""
命令流程控制：绑定、绘制与清除命令按钮，管理默认流程与结尾命令处理函数，
并请求玩家输入
"""

import time
import os
import psutil
import signal
from types import FunctionType
from typing import Callable, Literal, overload
from Script.Core import (
    text_handle,
    io_init,
    get_text,
    game_type,
    cache_control,
    constant,
)

# 全局缓存
cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """

# 翻译函数
_: FunctionType = get_text._
""" 翻译api """


def null_func() -> None:
    """
    占位用空函数

    参数：无
    返回值类型：无
    功能描述：提供一个什么都不做的函数作为占位符
    """
    return


# 管理flow
default_flow = null_func


def set_default_flow(
    func: Callable[..., object],
    arg: object = (),
    kw: dict[str, object] | None = None,
) -> None:
    """
    设置默认流程

    参数：
    func (function) -- 对应的流程函数
    arg (tuple) -- 传给func的顺序参数
    kw (dict | None) -- 传给func的字典参数，None 视为空字典

    返回值类型：无
    功能描述：设置默认的流程函数，供后续调用
    """
    kw = {} if kw is None else kw
    global default_flow
    if not isinstance(arg, tuple):
        arg = (arg,)
    if func is null_func:
        default_flow = null_func
        return

    def run_func() -> None:
        func(*arg, **kw)

    default_flow = run_func


def call_default_flow() -> None:
    """
    运行默认流程函数

    参数：无
    返回值类型：无
    功能描述：调用之前设置的默认流程函数
    """
    default_flow()


def clear_default_flow() -> None:
    """
    清除当前默认流程函数，并设置为空函数

    参数：无
    返回值类型：无
    功能描述：清除当前默认流程函数
    """
    set_default_flow(null_func)


cmd_map = constant.cmd_map


def default_tail_deal_cmd_func(order: str | int) -> None:
    """
    结尾命令处理空函数，用于占位

    参数：
    order (str) -- 命令文本

    返回值类型：无
    功能描述：默认的结尾命令处理函数，什么都不做
    """
    return


tail_deal_cmd_func: Callable[[int], object] = default_tail_deal_cmd_func


def set_tail_deal_cmd_func(func: Callable[[int], object]) -> None:
    """
    设置结尾命令处理函数

    参数：
    func (function) -- 结尾命令处理函数

    返回值类型：无
    功能描述：设置用于处理结尾命令的函数
    """
    global tail_deal_cmd_func
    tail_deal_cmd_func = func


def deco_set_tail_deal_cmd_func(
    func: Callable[[int], object],
) -> Callable[[int], object]:
    """
    为结尾命令设置函数提供装饰器功能

    参数：
    func (function) -- 结尾命令处理函数

    返回值类型：function
    功能描述：作为装饰器使用，设置结尾命令处理函数
    """
    set_tail_deal_cmd_func(func)
    return func


def bind_cmd(
    cmd_number: int | str,
    cmd_func: Callable[..., object] | None,
    arg: object = (),
    kw: dict[str, object] | None = None,
) -> None:
    """
    绑定命令数字与命令函数

    参数：
    cmd_number (str/int) -- 命令数字
    cmd_func (function) -- 命令函数
    arg (tuple) -- 传给命令函数的顺序参数
    kw (dict | None) -- 传给命令函数的字典参数，None 视为空字典

    返回值类型：无
    功能描述：将命令ID与对应的处理函数绑定
    """
    kw = {} if kw is None else kw
    if not isinstance(arg, tuple):
        arg = (arg,)
    if cmd_func is null_func or cmd_func is None:
        cmd_map[cmd_number] = null_func
        return

    def run_func() -> None:
        cmd_func(*arg, **kw)

    cmd_map[cmd_number] = run_func


def print_cmd(
    cmd_str: str,
    cmd_number: int | str,
    cmd_func: Callable[..., object] | None = null_func,
    arg: object = (),
    kw: dict[str, object] | None = None,
    normal_style: str = "standard",
    on_style: str = "onbutton",
    tooltip: str = "",
) -> str:
    """
    输出命令数字

    参数：
    cmd_str (str) -- 命令对应文字
    cmd_number (str/int) -- 命令数字
    cmd_func (function) -- 命令函数
    arg (tuple) -- 传给命令函数的顺序参数
    kw (dict | None) -- 传给命令函数的字典参数，None 视为空字典
    normal_style (str) -- 正常状态下命令显示样式
    on_style (str) -- 鼠标在其上的时候命令显示样式

    返回值类型：str
    功能描述：创建一个可点击的命令按钮
    """
    kw = {} if kw is None else kw
    bind_cmd(cmd_number, cmd_func, arg, kw)
    io_init.io_print_cmd(cmd_str, cmd_number, normal_style, on_style, tooltip)
    return cmd_str


def print_image_cmd(
    cmd_str: str,
    cmd_number: int | str,
    cmd_func: Callable[..., object] | None = null_func,
    arg: object = (),
    kw: dict[str, object] | None = None,
    tooltip: str = "",
) -> str:
    """
    绘制图片按钮

    参数：
    cmd_str (str) -- 命令对应文字
    cmd_number (str/int) -- 命令数字
    cmd_func (function) -- 命令函数
    arg (tuple) -- 传给命令函数的顺序参数
    kw (dict | None) -- 传给命令函数的字典参数，None 视为空字典

    返回值类型：str
    功能描述：创建一个图片按钮
    """
    kw = {} if kw is None else kw
    bind_cmd(cmd_number, cmd_func, arg, kw)
    io_init.io_print_image_cmd(cmd_str, cmd_number, tooltip)
    return cmd_str


def cmd_clear(*number: int | str) -> None:
    """
    清除绑定命令

    参数：
    number (tuple) -- 清除绑定命令数字，不提供则清除所有

    返回值类型：无
    功能描述：清除指定或所有的命令绑定
    """
    set_tail_deal_cmd_func(default_tail_deal_cmd_func)
    if number:
        for num in number:
            del cmd_map[num]
            io_init.io_clear_cmd(num)
    else:
        cmd_map.clear()
        io_init.io_clear_cmd()


def _cmd_deal(order_number: int | str) -> None:
    """
    执行命令

    参数：
    order_number (str/int) -- 对应命令数字

    返回值类型：无
    功能描述：执行与命令ID绑定的函数
    """
    cmd_map[order_number]()


def _cmd_valid(order_number: int | str) -> bool:
    """
    判断命令数字是否有效

    参数：
    order_number (str/int) -- 对应命令数字

    返回值类型：bool
    功能描述：判断命令ID是否有效
    """
    return cmd_map.get(order_number) not in (null_func, None)


__skip_flag__ = False
exit_flag = False


# 处理输入
@overload
def order_deal(
    flag: Literal["str"],
    print_order: bool = True,
    donot_return_null_str: bool = True,
) -> str: ...


@overload
def order_deal(
    flag: str = "order",
    print_order: bool = True,
    donot_return_null_str: bool = True,
) -> str | None: ...


def order_deal(
    flag: str = "order",
    print_order: bool = True,
    donot_return_null_str: bool = True,
) -> str | None:
    """
    处理命令函数

    参数：
    flag (str) -- 类型，默认为order，如果为console，会执行输入得到的内容
    print_order (bool) -- 是否将输入的order输出到屏幕上
    donot_return_null_str (bool) -- 不接受输入空字符串

    返回值类型：str | None。flag 为 "str" 时返回输入的字符串，纯数字的输入先经 str(int(...)) 规范化。
    flag 为 "order" 时处理这条输入后返回 None。
    donot_return_null_str 为假且 cache.wframe_mouse.w_frame_up 已置位时返回空串。
    功能描述：处理用户输入的命令
    """
    global __skip_flag__
    __skip_flag__ = False
    # 渲染期输入门禁：本次输入等待的一屏内容此时已全部入队，在进入轮询前 push 一次上膛标记。
    # 该标记恒排在本屏内容之后，read_queue 处理到它时才置为已上膛。每次进入 order_deal 只 push 一次，
    # 绝不放进下方轮询循环，避免渲染队列被标记刷屏；askfor_all/askfor_wait 因无效输入重进本函数时
    # 会再次 push，即"重新上膛"，是允许且正确的。
    io_init.arm_input()
    while True:
        time.sleep(0.01)
        if not donot_return_null_str and cache.wframe_mouse.w_frame_up:
            return ""
        while not io_init._order_queue.empty():
            order = io_init.get_order()
            if print_order and order != "":
                io_init.era_print("\n" + order + "\n")
            if flag == "str":
                if order.isdigit():
                    order = str(int(order))
                return order
            if flag == "console":
                exec(order)
            if flag == "order":
                if _cmd_valid(order):
                    _cmd_deal(order)
                    return None
                else:
                    tail_deal_cmd_func(int(order))
                    return None


def askfor_str(
    donot_return_null_str: bool = True, print_order: bool = False
) -> str:
    """
    用于请求一个字符串为结果的输入

    参数：
    donot_return_null_str (bool) -- 不接受输入空字符串
    print_order (bool) -- 是否将输入的order输出到屏幕上

    返回值类型：str
    功能描述：获取用户输入的字符串
    """
    while True:
        if not donot_return_null_str and cache.wframe_mouse.w_frame_up:
            cache.wframe_mouse.w_frame_up = 0
            return ""
        order = order_deal("str", print_order, donot_return_null_str)
        if donot_return_null_str and order != "":
            return order
        elif not donot_return_null_str:
            return order


def askfor_all(input_list: list, print_order: bool = False) -> str:
    """
    用于请求一个位于列表中的输入，如果输入没有在列表中，则告知用户出错。

    参数：
    input_list (list) -- 用于判断的列表内容
    print_order (bool) -- 是否将输入的order输出到屏幕上

    返回值类型：str
    功能描述：获取用户在指定列表中选择的输入
    """
    while 1:
        order = order_deal("str", print_order)
        if order in input_list:
            io_init.era_print(order + "\n")
            if _cmd_valid(order):
                _cmd_deal(order)
            elif order == "999":
                from Script.Core import save_handle

                # 保存到自动存档
                save_handle.establish_save("auto")
                # 退出游戏
                parent = psutil.Process(os.getpid())
                children = parent.children(recursive=True)
                for process in children:
                    process.send_signal(signal.SIGTERM)
                os._exit(0)
            return order
        elif order == "":
            continue
        else:
            io_init.era_print(order + "\n")
            io_init.era_print(_("您输入的选项无效，请重试\n"))
            continue


def askfor_int(list: list, print_order: bool = False) -> str:
    """
    用于请求位于列表中的整数的输入，如果输入没有在列表中，则告知用户出错。

    参数：
    list (list) -- 用于判断的列表内容
    print_order (bool) -- 是否将输入的order输出到屏幕上

    返回值类型：str
    功能描述：获取用户在指定整数列表中的选择
    """
    while True:
        order = order_deal("str", print_order)
        order = text_handle.full_to_half_text(order)
        if order in list:
            io_init.era_print(order + "\n\n")
            return order
        elif order == "":
            continue
        else:
            io_init.era_print(order + "\n")
            io_init.era_print(_("您输入的选项无效，请重试\n"))
            continue


def askfor_wait() -> None:
    """
    用于请求一个暂停动作，输入任何数都可以继续

    参数：无
    返回值类型：无
    功能描述：等待用户任意输入后继续
    """
    # 基准模式下直接跳过等待，避免自动化流程阻塞
    if getattr(cache, "benchmark_mode", False):
        return

    cache.wframe_mouse.w_frame_up = 0
    while not cache.wframe_mouse.w_frame_up:
        re = askfor_str(donot_return_null_str=False)
        if re == "":
            break
    # 等待结束后必须把标志位恢复为1
    # 否则用回车结束等待时 w_frame_up 会遗留为0并跨界面残留（置1的唯一入口在鼠标路径上）
    # 之后一次点在空白处的左键会被 mouse_left_check 的 w==0 分支误判为"推进等待"：
    # 消耗掉一次性的输入许可却不产生任何指令，askfor_all 从此永远收不到输入，游戏静默卡死
    cache.wframe_mouse.w_frame_up = 1
