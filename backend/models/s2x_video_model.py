from abc import ABC, abstractmethod
from typing import Optional
from models.video_frame import VideoFrame
from models.base_video_model import BaseVideoModel

class S2xVideoModel(BaseVideoModel):
    SYNC_BYTES  = b"\x40\x40"
    SOI_MARKER  = b"\xFF\xD8"
    EOI_MARKER  = b"\xFF\xD9"
    EOS_MARKER  = b"\x23\x23"

    def __init__(self):
        self._cur_fid = None
        self._frags   = {}

    def ingest_slice(self, *, frame_id, slice_id, payload, is_last):
        ...
        return VideoFrame(...) or None