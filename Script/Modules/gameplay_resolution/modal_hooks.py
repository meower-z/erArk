"""
模态选项提示槽（modal_hooks）
=============================
本模块维护单个模态选项提示处理函数槽，供前端登记处理函数并供后端发起选项提问。
未登记处理函数时，ask 抛出 RuntimeError。
已登记处理函数返回的 ChoiceResult 会由 ask 校验 prompt_id 与 selected_option_id。
本模块仅导入标准库 Callable 与 Script.Protocol.modal_prompts，不导入界面或 Tk 模块。
"""

from collections.abc import Callable

from Script.Protocol.modal_prompts import ChoicePrompt, ChoiceResult

type AskChoice = Callable[[ChoicePrompt], ChoiceResult]
""" 模态选项提示处理函数类型，接收 ChoicePrompt 并返回 ChoiceResult。 """
_ask: AskChoice | None = None
""" 当前已登记的模态选项提示处理函数，未登记时为 None。 """


def on_choice(fn: AskChoice) -> AskChoice:
    """
    登记模态选项提示处理函数并替换已有登记，可作为装饰器使用。
    Keyword arguments:
    fn -- AskChoice，要登记的模态选项提示处理函数
    Return arguments:
    AskChoice -- 原样返回传入的 fn
    """
    global _ask
    _ask = fn
    return fn


def ask(prompt: ChoicePrompt) -> ChoiceResult:
    """
    调用已登记的模态选项提示处理函数，并校验返回结果的提示标识与所选选项标识。
    未登记处理函数时抛出 RuntimeError。
    返回的 prompt_id 与 prompt 不一致时抛出 ValueError。
    返回的 selected_option_id 不在 prompt.options 中时抛出 ValueError。
    Keyword arguments:
    prompt -- ChoicePrompt，待向玩家展示的选项提示
    Return arguments:
    ChoiceResult -- 通过校验的选择结果
    """
    if _ask is None:
        raise RuntimeError(f"no choice handler for {prompt.prompt_id}")
    result = _ask(prompt)
    if result.prompt_id != prompt.prompt_id:
        raise ValueError(
            f"result for {result.prompt_id} answers {prompt.prompt_id}"
        )
    offered = [option.option_id for option in prompt.options]
    if result.selected_option_id not in offered:
        raise ValueError(f"{result.selected_option_id} is not one of {offered}")
    return result
