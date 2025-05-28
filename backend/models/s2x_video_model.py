from typing import Dict, Optional

from models.video_frame import VideoFrame
from models.base_video_model import BaseVideoModel


class S2xVideoModel(BaseVideoModel):
    """
    Reassembles sliced JPEG frames used by S2x drones.
    """

    SYNC_BYTES  = b"\x40\x40"
    SOI_MARKER  = b"\xFF\xD8"
    EOI_MARKER  = b"\xFF\xD9"
    EOS_MARKER  = b"\x23\x23"

    def __init__(self) -> None:
        self._cur_fid: Optional[int] = None
        self._frags: Dict[int, bytes] = {}

    # ──────────────────────────────────────────────────────────
    # BaseVideoModel interface
    # ──────────────────────────────────────────────────────────
    def ingest_chunk(
        self,
        *,
        stream_id: int | None = None,
        chunk_id: int | None = None,
        payload: bytes,
        is_last: bool | None = None,
    ) -> Optional[VideoFrame]:

        if stream_id is None or chunk_id is None:
            return None   # S2x always provides both ids

        # -------------------------------------------------------
        # Did the frame-id change?  → try to finish previous one
        # -------------------------------------------------------
        frame: Optional[VideoFrame] = None
        if self._cur_fid is None:
            self._cur_fid = stream_id
        elif stream_id != self._cur_fid:
            frame = self._assemble_current()      # may return None
            self._reset(stream_id)

        # store slice (ignore duplicates)
        self._frags.setdefault(chunk_id, payload)   # chunk_id == raw SID

        # explicit "last slice" bit still wins
        if is_last:
            return self._assemble_current()

        return frame     # may be None or a completed frame

    # ──────────────────────────────────────────────────────────
    # helpers
    # ──────────────────────────────────────────────────────────
    def _reset(self, new_fid: Optional[int]) -> None:
        self._cur_fid = new_fid
        self._frags.clear()

    def _assemble_current(self) -> Optional[VideoFrame]:
        if not self._frags:
            return None

        keys = sorted(self._frags)
        complete = len(keys) == keys[-1] - keys[0] + 1
        if not complete:
            missing = (keys[-1] - keys[0] + 1) - len(keys)
            print(f"[s2x-model] Dropping frame {self._cur_fid}: {missing} slices missing")
            return None

        data = b"".join(self._frags[k] for k in keys)

        start = data.find(self.SOI_MARKER)
        end = data.rfind(self.EOI_MARKER)
        if start < 0 or end < 0 or end <= start:
            print(f"[s2x-model] JPEG markers not found on frame {self._cur_fid}")
            return None

        jpeg = data[start : end + len(self.EOI_MARKER)]
        print(f"[s2x-model] Frame {self._cur_fid} OK ({len(jpeg)} bytes, {len(keys)} slices)")
        frame = VideoFrame(self._cur_fid, jpeg, "jpeg")

        # prepare for next frame
        self._reset(None)
        return frame