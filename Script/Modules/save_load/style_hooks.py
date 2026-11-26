"""
样式变更回调（style_hooks）
===========================
本模块提供文本样式变更回调的登记与派发入口。
本模块仅导入标准库 collections.abc.Callable。
本模块不导入界面、Tk 或输入输出模块。
未登记回调时，emit_styles_changed 不执行任何操作。
"""

from collections.abc import Callable

type StylesChanged = Callable[[], None]
""" 文本样式变更回调的类型别名。 """
_styles_changed: list[StylesChanged] = []
""" 按登记顺序保存的文本样式变更回调列表。 """


def on_styles_changed(fn: StylesChanged) -> StylesChanged:
    """
    登记一个文本样式变更回调。该函数可作为装饰器使用。
    Keyword arguments:
    fn -- StylesChanged，要登记的回调函数
    Return arguments:
    StylesChanged -- 原样返回传入的 fn
    """
    _styles_changed.append(fn)
    return fn


def emit_styles_changed() -> None:
    """
    按登记顺序无参调用已登记的文本样式变更回调。未登记回调时不执行任何操作。
    Return arguments:
    None -- 无返回值
    """
    for fn in _styles_changed:
        fn()
