from collections.abc import Callable
from typing import Self

from openai._base_client import DefaultHttpxClient
from openai.resources.chat.chat import Chat
from openai.resources.images import Images

class OpenAI:
    def __init__(
        self,
        *,
        api_key: str | Callable[[], str] | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        http_client: DefaultHttpxClient | None = None,
    ) -> None: ...
    @property
    def chat(self) -> Chat: ...
    @property
    def images(self) -> Images: ...
    def copy(
        self,
        *,
        api_key: str | Callable[[], str] | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        http_client: DefaultHttpxClient | None = None,
    ) -> Self: ...
    with_options = copy
