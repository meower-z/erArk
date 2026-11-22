from typing import TypeAlias

from openai.types.chat.chat_completion_system_message_param import (
    ChatCompletionSystemMessageParam,
)
from openai.types.chat.chat_completion_user_message_param import (
    ChatCompletionUserMessageParam,
)

ChatCompletionMessageParam: TypeAlias = (
    ChatCompletionSystemMessageParam | ChatCompletionUserMessageParam
)
