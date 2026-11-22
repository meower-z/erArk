from collections.abc import Iterable
from typing import Literal, Required, TypedDict

from openai.types.chat.chat_completion_content_part_text_param import (
    ChatCompletionContentPartTextParam,
)

class ChatCompletionSystemMessageParam(TypedDict, total=False):
    content: Required[str | Iterable[ChatCompletionContentPartTextParam]]
    role: Required[Literal["system"]]
    name: str
