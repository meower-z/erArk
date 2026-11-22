class HttpOptions:
    def __init__(
        self, *, base_url: str | None = None, api_version: str | None = None
    ) -> None: ...

class GenerateContentConfig:
    def __init__(self, *, system_instruction: str | None = None) -> None: ...

class GenerateContentResponse:
    @property
    def text(self) -> str | None: ...
