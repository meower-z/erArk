from collections.abc import Iterator

from google.genai.types import GenerateContentConfig, GenerateContentResponse

class Models:
    def generate_content(
        self,
        *,
        model: str,
        contents: str,
        config: GenerateContentConfig | None = None,
    ) -> GenerateContentResponse: ...
    def generate_content_stream(
        self,
        *,
        model: str,
        contents: str,
        config: GenerateContentConfig | None = None,
    ) -> Iterator[GenerateContentResponse]: ...
