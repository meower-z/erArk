"""
Tk 模态选项提示渲染分发（choice_prompts）
=========================================
本模块维护按 prompt_id 索引的 Tk 渲染函数表 RENDERERS。
导入本模块时，ask_choice 会登记到 modal_hooks，并按 prompt.prompt_id 查找对应渲染函数。
未登记对应 prompt_id 时，ask_choice 抛出 KeyError，不提供默认兜底渲染。
本模块不登记内核钩子。
"""

from collections.abc import Callable

from Script.Modules.gameplay_resolution import modal_hooks
from Script.Protocol.modal_prompts import ChoicePrompt, ChoiceResult

type Renderer = Callable[[ChoicePrompt], str]
""" 单个提示的 Tk 渲染函数类型，接收 ChoicePrompt 并返回所选选项的 option_id。 """
RENDERERS: dict[str, Renderer] = {}
""" 按 prompt_id 索引的 Tk 渲染函数映射表。 """


def renderer(prompt_id: str) -> Callable[[Renderer], Renderer]:
    """
    返回将渲染函数按 prompt_id 登记到 RENDERERS 的装饰器。
    Keyword arguments:
    prompt_id -- str，要绑定的选项提示标识
    Return arguments:
    Callable[[Renderer], Renderer] -- 写入 RENDERERS[prompt_id] 并原样返回函数的装饰器
    """

    def register(fn: Renderer) -> Renderer:
        """
        将 fn 写入 RENDERERS[prompt_id] 并原样返回 fn。
        Keyword arguments:
        fn -- Renderer，要登记的 Tk 渲染函数
        Return arguments:
        Renderer -- 原样返回传入的 fn
        """
        RENDERERS[prompt_id] = fn
        return fn

    return register


@modal_hooks.on_choice
def ask_choice(prompt: ChoicePrompt) -> ChoiceResult:
    """
    按 prompt.prompt_id 从 RENDERERS 查找并调用对应渲染函数。
    将渲染函数返回的选项标识包装为 ChoiceResult 返回。
    未登记对应 prompt_id 时抛出 KeyError。
    Keyword arguments:
    prompt -- ChoicePrompt，待展示的选项提示
    Return arguments:
    ChoiceResult -- 包含 prompt.prompt_id 与所选 option_id 的选择结果
    """
    return ChoiceResult(prompt.prompt_id, RENDERERS[prompt.prompt_id](prompt))
