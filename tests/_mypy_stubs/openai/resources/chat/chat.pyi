from openai.resources.chat.completions.completions import Completions

class Chat:
    @property
    def completions(self) -> Completions: ...
