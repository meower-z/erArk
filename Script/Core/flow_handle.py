# -*- coding: UTF-8 -*-
"""
命令流程控制：绑定、绘制与清除命令按钮，管理默认流程与结尾命令处理函数，
并请求玩家输入
"""

from collections.abc import Generator, Sequence
from contextlib import contextmanager
from types import FunctionType
from typing import Callable, Literal, overload
from Script.Core import text_handle, io_init, get_text, constant, input_cache
from Script.Modules.tk_ui import orders

benchmark_mode = False
""" 性能分析脚本置为 True 时，等待暂停立即返回 """

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


exit_flag = False
_offered: tuple[str, ...] | None = None


def _remember(order: str) -> None:
    if order != "":
        if len(input_cache.input_cache) >= input_cache.INPUT_CACHE_LIMIT:
            del input_cache.input_cache[0]
        input_cache.input_cache.append(order)


@contextmanager
def _offering(options: Sequence[object]) -> Generator[None]:
    global _offered
    previous = _offered
    _offered = tuple(str(option) for option in options)
    try:
        yield
    finally:
        _offered = previous


def _next_order(flag: str, donot_return_null_str: bool) -> str:
    if _offered is not None:
        return io_init.ask_choice(_offered)
    if flag == "order":
        return io_init.ask_choice(tuple(str(number) for number in cmd_map))
    return io_init.ask_text(allow_empty=not donot_return_null_str)


@overload
def order_deal(
    flag: Literal["str", "wait"],
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
    经 `io_init` 按输入类型向端口请求玩家输入并分发处理，选项提示期与 `"order"` 模式请求 `Choose`，`"str"` 与
    `"console"` 请求 `InputText`，`"wait"` 请求暂停

    参数：
    flag (str) -- 处理模式，可选 "order"、"str"、"wait" 或 "console"
    print_order (bool) -- 是否将非空输入回显到屏幕
    donot_return_null_str (bool) -- 为 False 时在文本请求中允许空字符串

    返回值类型：str | None -- "wait" 返回空串，"str" 返回规范化字符串，"order" 执行命令后返回 None
    """
    if flag == "wait":
        io_init.wait_continue()
        return ""
    while True:
        order = _next_order(flag, donot_return_null_str)
        _remember(order)
        orders.accept(order)
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
            else:
                tail_deal_cmd_func(int(order))
            return None


def askfor_str(
    donot_return_null_str: bool = True, print_order: bool = False
) -> str:
    """
    循环请求玩家输入字符串，按参数决定是否允许空字符串

    参数：
    donot_return_null_str (bool) -- 为 True 时忽略空输入直到收到非空文本
    print_order (bool) -- 是否将输入内容回显到屏幕

    返回值类型：str -- 玩家输入的字符串
    """
    while True:
        order = order_deal("str", print_order, donot_return_null_str)
        if order != "" or not donot_return_null_str:
            return order


def askfor_all(input_list: list, print_order: bool = False) -> str:
    """
    循环请求玩家从指定选项列表中选择并执行已绑定的命令

    参数：
    input_list (list) -- 允许接受的选项列表
    print_order (bool) -- 是否在底层输入阶段回显输入

    返回值类型：str -- 命中的合法选项文本，输入 "999" 且未另行绑定时自动存档并结束会话
    """
    while 1:
        with _offering(input_list):
            order = order_deal("str", print_order)
        if order in input_list:
            io_init.era_print(order + "\n")
            if _cmd_valid(order):
                _cmd_deal(order)
            elif order == "999":
                from Script.Core import save_handle

                save_handle.establish_save("auto")
                io_init.end_session()
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
        with _offering(list):
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
    暂停流程等待玩家继续，处于基准模式时直接返回，否则通过 `order_deal("wait", False, False)` 经端口处理等待或跳过

    参数：无

    返回值类型：None
    """
    if benchmark_mode:
        return
    order_deal("wait", False, False)


def set_skip_pauses(enabled: bool) -> None:
    """
    委托 `io_init.set_skip_pauses` 开启或关闭跳过暂停模式

    参数：
    enabled (bool) -- 为 True 时跳过后续可跳过暂停，为 False 时恢复正常等待

    返回值类型：None
    """
    io_init.set_skip_pauses(enabled)
