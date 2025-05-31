from abc import ABC, abstractmethod
from typing import Optional
from models.video_frame import VideoFrame

class BaseVideoModel(ABC):
    """
    Stateless interface that turns *chunks* (whatever the protocol
    thinks a chunk is: a JPEG slice, a whole JPEG, a H.264 NALU …)
    into complete VideoFrame objects.
    """

    @abstractmethod
    def ingest_chunk(
        self,
        *,
        stream_id: int | None = None,
        chunk_id: int | None = None,
        payload: bytes,
    ) -> Optional[VideoFrame]:
        """
        Feed one chunk into the model.

        Parameters
        ----------
        stream_id : int | None
            Identifier of the logical stream / frame (e.g. frame number).
        chunk_id  : int | None
            Sequential id of this chunk inside the stream (e.g. slice index).
        payload   : bytes
            Raw codec payload (JPEG slice, NALU, etc.).

        Returns
        -------
        Optional[VideoFrame]
            • VideoFrame when a frame is complete
            • None if more data is required
        """
        raise NotImplementedError