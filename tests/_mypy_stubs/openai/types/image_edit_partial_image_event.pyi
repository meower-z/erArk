from typing import Literal

class ImageEditPartialImageEvent:
    b64_json: str
    type: Literal["image_edit.partial_image"]
