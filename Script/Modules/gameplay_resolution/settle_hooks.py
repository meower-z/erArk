"""
行为结算界面回调（settle_hooks）
================================
本模块提供行为结算文本回调的登记与派发入口，以及普通子事件与多层嵌套子事件的选项询问入口与提示标识常量。
未登记回调时，emit_settle_text 不执行操作。
本模块顶层仅导入标准库 collections.abc.Callable，模块内不导入界面、Tk 或输入输出模块。
emit_event_options 与 emit_nested_event_options 在调用时按需导入 event_option_service 与 modal_hooks。
"""

from collections.abc import Callable

type SettleText = Callable[[str], None]
""" 行为结算文本回调的类型别名。 """
_settle_texts: list[SettleText] = []
""" 按登记顺序保存的行为结算文本回调列表。 """
SON_EVENT_PROMPT_ID = "son_event"
""" 普通子事件选项提问使用的 ChoicePrompt 标识（"son_event"）。 """
NESTED_EVENT_PROMPT_ID = "nested_event"
""" 多层嵌套子事件选项提问使用的 ChoicePrompt 标识（"nested_event"）。 """


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


def emit_nested_event_options(
    character_id: int, parent_child_id: int, parent_value: int
) -> None:
    """
    调用 event_option_service.build_multi_layer_event_prompt 构造多层嵌套子事件选项提示。
    提示为 None 时直接返回，不发起询问。
    提示非空时，函数经 modal_hooks.ask 询问玩家，再调用 event_option_service.apply_event_choice 写入选择结果。
    modal_hooks 未登记选择处理函数时，modal_hooks.ask 抛出 RuntimeError。
    Keyword arguments:
    character_id -- int，触发嵌套事件的角色编号
    parent_child_id -- int，嵌套父子事件的序号（非事件编号）
    parent_value -- int，该嵌套父子事件的对应数值
    Return arguments:
    None -- 无返回值
    """
    from Script.Modules.gameplay_resolution import (
        event_option_service,
        modal_hooks,
    )

    prompt = event_option_service.build_multi_layer_event_prompt(
        character_id, parent_child_id, parent_value
    )
    if prompt is not None:
        event_option_service.apply_event_choice(
            character_id, modal_hooks.ask(prompt)
        )


def emit_event_options(character_id: int) -> None:
    """
    调用 event_option_service.build_son_event_prompt 构造普通子事件选项提示。
    提示为 None 时直接返回，不发起询问。
    提示非空时，函数经 modal_hooks.ask 询问玩家，再调用 event_option_service.apply_event_choice 写入选择结果。
    modal_hooks 未登记选择处理函数时，modal_hooks.ask 抛出 RuntimeError。
    Keyword arguments:
    character_id -- int，需要展示事件选项的角色编号
    Return arguments:
    None -- 无返回值
    """
    from Script.Modules.gameplay_resolution import (
        event_option_service,
        modal_hooks,
    )

    prompt = event_option_service.build_son_event_prompt(character_id)
    if prompt is not None:
        event_option_service.apply_event_choice(
            character_id, modal_hooks.ask(prompt)
        )
