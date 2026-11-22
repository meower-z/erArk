from typing import Literal

class ChatCompletionMessage:
    content: str | None
    refusal: str | None
    role: Literal["assistant"]
