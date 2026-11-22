from collections.abc import Mapping
from os import PathLike
from typing import IO, TypeAlias

FileContent: TypeAlias = IO[bytes] | bytes | PathLike[str]
FileTypes: TypeAlias = (
    FileContent
    | tuple[str | None, FileContent]
    | tuple[str | None, FileContent, str | None]
    | tuple[str | None, FileContent, str | None, Mapping[str, str]]
)
