from collections.abc import Sequence
from typing import Literal, TypeAlias, overload

from openai._streaming import Stream
from openai._types import FileTypes
from openai.types.image_edit_stream_event import ImageEditStreamEvent
from openai.types.image_gen_stream_event import ImageGenStreamEvent
from openai.types.images_response import ImagesResponse

_Background: TypeAlias = Literal["transparent", "opaque", "auto"] | None
_Fidelity: TypeAlias = Literal["high", "low"] | None
_Format: TypeAlias = Literal["png", "jpeg", "webp"] | None
_EditQuality: TypeAlias = (
    Literal["low", "medium", "high", "xhigh", "max", "auto", "standard"] | None
)
_GenerateQuality: TypeAlias = (
    Literal["low", "medium", "high", "xhigh", "max", "auto", "standard", "hd"]
    | None
)
_Image: TypeAlias = FileTypes | Sequence[FileTypes]

class Images:
    @overload
    def edit(
        self,
        *,
        image: _Image,
        prompt: str,
        background: _Background = None,
        input_fidelity: _Fidelity = None,
        model: str | None = None,
        n: int | None = None,
        output_format: _Format = None,
        quality: _EditQuality = None,
        size: str | None = None,
        stream: Literal[False] | None = None,
    ) -> ImagesResponse: ...
    @overload
    def edit(
        self,
        *,
        image: _Image,
        prompt: str,
        stream: Literal[True],
        background: _Background = None,
        input_fidelity: _Fidelity = None,
        model: str | None = None,
        n: int | None = None,
        output_format: _Format = None,
        quality: _EditQuality = None,
        size: str | None = None,
    ) -> Stream[ImageEditStreamEvent]: ...
    @overload
    def edit(
        self,
        *,
        image: _Image,
        prompt: str,
        stream: bool,
        background: _Background = None,
        input_fidelity: _Fidelity = None,
        model: str | None = None,
        n: int | None = None,
        output_format: _Format = None,
        quality: _EditQuality = None,
        size: str | None = None,
    ) -> ImagesResponse | Stream[ImageEditStreamEvent]: ...
    @overload
    def generate(
        self,
        *,
        prompt: str,
        background: _Background = None,
        model: str | None = None,
        n: int | None = None,
        output_format: _Format = None,
        quality: _GenerateQuality = None,
        size: str | None = None,
        stream: Literal[False] | None = None,
    ) -> ImagesResponse: ...
    @overload
    def generate(
        self,
        *,
        prompt: str,
        stream: Literal[True],
        background: _Background = None,
        model: str | None = None,
        n: int | None = None,
        output_format: _Format = None,
        quality: _GenerateQuality = None,
        size: str | None = None,
    ) -> Stream[ImageGenStreamEvent]: ...
    @overload
    def generate(
        self,
        *,
        prompt: str,
        stream: bool,
        background: _Background = None,
        model: str | None = None,
        n: int | None = None,
        output_format: _Format = None,
        quality: _GenerateQuality = None,
        size: str | None = None,
    ) -> ImagesResponse | Stream[ImageGenStreamEvent]: ...
