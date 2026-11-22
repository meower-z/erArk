from typing import Literal

class ImageGenCompletedEvent:
    b64_json: str
    type: Literal["image_generation.completed"]
