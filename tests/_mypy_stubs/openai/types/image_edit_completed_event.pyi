from typing import Literal

class ImageEditCompletedEvent:
    b64_json: str
    type: Literal["image_edit.completed"]
