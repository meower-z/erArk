from types import TracebackType
from typing import Self

class DefaultHttpxClient:
    def __init__(
        self, *, proxy: str | None = None, timeout: float | None = None
    ) -> None: ...
    def close(self) -> None: ...
    def __enter__(self) -> Self: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None: ...
