"""
面板注册与运行上下文（handle_panel）
====================================
本模块提供面板注册装饰器 add_panel 与面板运行上下文登记函数 on_panel_run。
模块内部的运行上下文槽 _panel_run 默认为返回空上下文的 _plain。
本模块仅导入标准库与 Script.Core.constant。
本模块不导入界面模块。
"""

from contextlib import AbstractContextManager, nullcontext
from functools import wraps
from typing import ParamSpec, TypeVar
from collections.abc import Callable
from Script.Core import constant

PanelParams = ParamSpec("PanelParams")
""" 面板绘制函数的参数 """
PanelReturn = TypeVar("PanelReturn")
""" 面板绘制函数的返回值 """
type PanelRun = Callable[[int], AbstractContextManager[None]]
""" 面板运行上下文函数的类型别名。 """


def _plain(panel: int) -> AbstractContextManager[None]:
    """
    默认的面板运行上下文函数，直接返回空上下文管理器。
    Keyword arguments:
    panel -- int，面板 id，此默认实现不使用该参数
    Return arguments:
    AbstractContextManager[None] -- 空上下文管理器 nullcontext()
    """
    return nullcontext()


_panel_run: PanelRun = _plain
""" 当前生效的面板运行上下文槽，默认为 _plain。 """


def on_panel_run(fn: PanelRun) -> PanelRun:
    """
    登记面板运行上下文函数，将 _panel_run 设为 fn。
    该函数可作为装饰器使用。后续登记会替换先前的函数。
    Keyword arguments:
    fn -- PanelRun，要登记的面板运行上下文函数
    Return arguments:
    PanelRun -- 原样返回传入的 fn
    """
    global _panel_run
    _panel_run = fn
    return fn


def add_panel(
    panel: int,
) -> Callable[
    [Callable[PanelParams, PanelReturn]], Callable[PanelParams, PanelReturn]
]:
    """
    返回用于注册面板绘制函数的装饰器。包装函数在 _panel_run(panel) 返回的上下文中运行面板函数。
    Keyword arguments:
    panel -- int，面板id
    Return arguments:
    Callable -- 包装面板绘制函数、注册到 constant.panel_data[panel] 并返回包装函数的装饰器
    """

    def decoraror(
        func: Callable[PanelParams, PanelReturn],
    ) -> Callable[PanelParams, PanelReturn]:
        @wraps(func)
        def return_wrapper(
            *args: PanelParams.args, **kwargs: PanelParams.kwargs
        ) -> PanelReturn:
            with _panel_run(panel):
                result = func(*args, **kwargs)
            return result

        constant.panel_data[panel] = return_wrapper
        return return_wrapper

    return decoraror
