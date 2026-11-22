from typing import TypeAlias

from openai.types.image_gen_completed_event import ImageGenCompletedEvent
from openai.types.image_gen_partial_image_event import ImageGenPartialImageEvent

ImageGenStreamEvent: TypeAlias = (
    ImageGenPartialImageEvent | ImageGenCompletedEvent
)
