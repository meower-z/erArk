"""
行为结算界面回调（settle_hooks）
================================
本模块提供行为结算文本与嵌套事件选项回调的登记与派发入口。
本模块仅导入标准库 collections.abc.Callable 与 typing.Protocol。
本模块不导入界面、Tk 或输入输出模块。
未登记回调时，emit_settle_text 与 emit_nested_event_options 不执行任何操作。
"""

from collections.abc import Callable
from typing import Protocol

type SettleText = Callable[[str], None]
""" 行为结算文本回调的类型别名。 """
_settle_texts: list[SettleText] = []
""" 按登记顺序保存的行为结算文本回调列表。 """


class NestedEventOptions(Protocol):
    """嵌套父子事件选项回调的函数签名协议。"""

    def __call__(
        self, character_id: int, parent_child_id: int, parent_value: int
    ) -> None:
        """
        接收角色编号、嵌套父子事件序号与对应数值，处理一次嵌套事件选项展示。
        Keyword arguments:
        character_id -- int，触发嵌套事件的角色编号
        parent_child_id -- int，嵌套父子事件的序号（非事件编号）
        parent_value -- int，该嵌套父子事件的对应数值
        Return arguments:
        None -- 无返回值
        """


_nested_event_options: list[NestedEventOptions] = []
""" 按登记顺序保存的嵌套父子事件选项回调列表。 """


def on_settle_text(fn: SettleText) -> SettleText:
    """
    登记一个行为结算文本回调，可作为装饰器使用。
    Keyword arguments:
    fn -- SettleText，要登记的回调函数
    Return arguments:
    SettleText -- 原样返回传入的 fn
    """
    _settle_texts.append(fn)
    return fn


def emit_settle_text(text: str) -> None:
    """
    按登记顺序调用已登记的行为结算文本回调，未登记时不执行操作。
    Keyword arguments:
    text -- str，要展示的行为结算文本
    Return arguments:
    None -- 无返回值
    """
    for fn in _settle_texts:
        fn(text)


def on_nested_event_options(fn: NestedEventOptions) -> NestedEventOptions:
    """
    登记一个嵌套父子事件选项回调，可作为装饰器使用。
    Keyword arguments:
    fn -- NestedEventOptions，要登记的回调函数
    Return arguments:
    NestedEventOptions -- 原样返回传入的 fn
    """
    _nested_event_options.append(fn)
    return fn


def emit_nested_event_options(
    character_id: int, parent_child_id: int, parent_value: int
) -> None:
    """
    按登记顺序调用已登记的嵌套父子事件选项回调，未登记时不执行操作。
    Keyword arguments:
    character_id -- int，触发嵌套事件的角色编号
    parent_child_id -- int，嵌套父子事件的序号（非事件编号）
    parent_value -- int，该嵌套父子事件的对应数值
    Return arguments:
    None -- 无返回值
    """
    for fn in _nested_event_options:
        fn(character_id, parent_child_id, parent_value)
