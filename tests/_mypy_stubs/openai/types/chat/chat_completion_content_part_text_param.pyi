from typing import Literal, Required, TypedDict

class PromptCacheBreakpoint(TypedDict, total=False):
    mode: Required[Literal["explicit"]]

class ChatCompletionContentPartTextParam(TypedDict, total=False):
    text: Required[str]
    type: Required[Literal["text"]]
    prompt_cache_breakpoint: PromptCacheBreakpoint
