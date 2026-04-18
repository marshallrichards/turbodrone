"""
Video Model for Cooingdv drones.

This model is intentionally simple because cooingdv drones use RTSP streaming,
which delivers complete frames directly. Unlike the S2x and WiFi UAV protocols
that require assembling frames from UDP chunks, RTSP gives us ready-to-use
frames via OpenCV.

The model exists primarily for API consistency with other implementations.
Most of the heavy lifting is done in the video protocol adapter.
"""

from typing import Optional
from models.base_video_model import BaseVideoModel
from models.video_frame import VideoFrame


class CooingdvVideoModel(BaseVideoModel):
    """
    Video model for cooingdv drones using RTSP streaming.
    
    Since RTSP provides complete frames, this model simply wraps the
    incoming data into VideoFrame objects. No assembly or decoding
    is required - OpenCV handles all of that.
    """

    def __init__(self):
        self._frame_counter = 0

    def ingest_chunk(
        self,
        *,
        stream_id: int | None = None,
        chunk_id: int | None = None,
        payload: bytes,
    ) -> Optional[VideoFrame]:
        """
        Process incoming video data.
        
        For RTSP streams, each 'chunk' is actually a complete frame,
        so we simply wrap it in a VideoFrame and return it immediately.
        
        Parameters
        ----------
        stream_id : int | None
            Frame identifier (from RTSP stream)
        chunk_id : int | None
            Not used for RTSP (frames are not chunked)
        payload : bytes
            Complete JPEG frame data
            
        Returns
        -------
        VideoFrame
            Always returns a VideoFrame since RTSP delivers complete frames
        """
        self._frame_counter += 1
        
        # Use provided stream_id or auto-increment
        frame_id = stream_id if stream_id is not None else self._frame_counter
        
        return VideoFrame(
            frame_id=frame_id,
            data=payload,
        )

    def reset(self) -> None:
        """Reset the model state."""
        self._frame_counter = 0

