from openai.types.image import Image

class ImagesResponse:
    created: int
    data: list[Image] | None
