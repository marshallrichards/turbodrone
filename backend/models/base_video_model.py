from abc import ABC, abstractmethod
from typing import Optional
from models.video_frame import VideoFrame

class BaseVideoModel(ABC):
    @abstractmethod
    def ingest_slice(self, *, frame_id: int, slice_id: int,
                     payload: bytes, is_last: bool) -> Optional[VideoFrame]:
        """
        Feed one video slice into the model.
        Return a VideoFrame only when a full frame is ready.
        """
        ...