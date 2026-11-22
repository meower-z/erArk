from typing import TypeAlias

from openai.types.image_edit_completed_event import ImageEditCompletedEvent
from openai.types.image_edit_partial_image_event import (
    ImageEditPartialImageEvent,
)

ImageEditStreamEvent: TypeAlias = (
    ImageEditPartialImageEvent | ImageEditCompletedEvent
)
