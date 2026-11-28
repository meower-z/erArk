"""
妊娠取名回调槽位（pregnancy_hooks）
===================================
本模块维护单个新生儿取名回调槽位，提供登记函数 on_name_input、
查询函数 has_handler、调用入口 ask_name 与回调类型别名 NameInput。
本模块仅导入标准库 collections.abc.Callable，不导入界面、Tk 或输入输出模块。
未登记取名处理函数时，槽位为 None，调用 ask_name 抛出 RuntimeError。
"""

from collections.abc import Callable

type NameInput = Callable[[str], str]
""" 新生儿取名回调函数类型别名，接收询问文本并返回角色名称。 """


_name_input: NameInput | None = None
""" 当前生效的新生儿取名回调槽位，未登记时为 None。 """


def on_name_input(fn: NameInput) -> NameInput:
    """
    登记新生儿取名回调槽位的处理函数，可作为装饰器使用。
    每次调用都会覆盖当前槽位中的处理函数。
    Keyword arguments:
    fn -- NameInput，接收询问文本并返回角色名称的回调函数
    Return arguments:
    NameInput -- 原样返回传入的 fn
    """
    global _name_input
    _name_input = fn
    return fn


def ask_name(ask_text: str) -> str:
    """
    调用当前已登记的取名回调获取新生儿名称，未登记时抛出 RuntimeError。
    Keyword arguments:
    ask_text -- str，展示给玩家的取名询问文本
    Return arguments:
    str -- 回调返回的新生儿名称
    """
    if _name_input is None:
        raise RuntimeError(f"no name input handler for {ask_text!r}")
    return _name_input(ask_text)


def has_handler() -> bool:
    """
    返回当前是否已登记新生儿取名处理函数。
    Return arguments:
    bool -- 已登记处理函数时返回 True，否则返回 False
    """
    return _name_input is not None
