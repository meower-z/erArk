from typing import Literal

class ImageGenPartialImageEvent:
    b64_json: str
    type: Literal["image_generation.partial_image"]
