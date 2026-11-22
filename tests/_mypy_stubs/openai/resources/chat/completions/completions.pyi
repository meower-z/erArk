from collections.abc import Iterable
from typing import Literal, overload

from openai._streaming import Stream
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from openai.types.chat.chat_completion_message_param import (
    ChatCompletionMessageParam,
)

class Completions:
    @overload
    def create(
        self,
        *,
        messages: Iterable[ChatCompletionMessageParam],
        model: str,
        stream: Literal[False] | None = None,
    ) -> ChatCompletion: ...
    @overload
    def create(
        self,
        *,
        messages: Iterable[ChatCompletionMessageParam],
        model: str,
        stream: Literal[True],
    ) -> Stream[ChatCompletionChunk]: ...
    @overload
    def create(
        self,
        *,
        messages: Iterable[ChatCompletionMessageParam],
        model: str,
        stream: bool,
    ) -> ChatCompletion | Stream[ChatCompletionChunk]: ...
