from typing import Literal

from openai.types.chat.chat_completion_message import ChatCompletionMessage

class Choice:
    finish_reason: Literal[
        "stop", "length", "tool_calls", "content_filter", "function_call"
    ]
    index: int
    message: ChatCompletionMessage

class ChatCompletion:
    id: str
    choices: list[Choice]
    created: int
    model: str
    object: Literal["chat.completion"]
