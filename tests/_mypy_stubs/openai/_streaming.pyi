from collections.abc import Iterator
from typing import Generic, TypeVar

_T = TypeVar("_T")

class Stream(Generic[_T]):
    def __next__(self) -> _T: ...
    def __iter__(self) -> Iterator[_T]: ...
