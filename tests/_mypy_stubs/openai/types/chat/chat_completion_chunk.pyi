from typing import Literal

class ChoiceDelta:
    content: str | None
    refusal: str | None
    role: Literal["developer", "system", "user", "assistant", "tool"] | None

class Choice:
    delta: ChoiceDelta
    finish_reason: (
        Literal[
            "stop", "length", "tool_calls", "content_filter", "function_call"
        ]
        | None
    )
    index: int

class ChatCompletionChunk:
    id: str
    choices: list[Choice]
    created: int
    model: str
    object: Literal["chat.completion.chunk"]
