from google.genai.models import Models
from google.genai.types import HttpOptions

class Client:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        http_options: HttpOptions | None = None,
    ) -> None: ...
    @property
    def models(self) -> Models: ...
