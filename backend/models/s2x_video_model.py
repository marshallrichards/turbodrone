from typing import Dict, Optional

from models.video_frame import VideoFrame
from models.base_video_model import BaseVideoModel


class S2xVideoModel(BaseVideoModel):
    """
    Reassembles sliced JPEG frames used by S2x drones.

    • Ignores the unreliable "is-last-slice" flag.
    • Finishes a frame when the frame-id rolls over.
    """

    SOI_MARKER = b"\xFF\xD8"
    EOI_MARKER = b"\xFF\xD9"

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
        total_chunks: int | None = None,
        payload: bytes,
    ) -> Optional[VideoFrame]:

        if stream_id is None or chunk_id is None:
            return None  # S2x packets always carry both ids

        # frame-id changed? -> finish previous frame. Native VNDK emits as soon
        # as all declared chunks arrive, but this fallback preserves older
        # rollover-based behavior for captures without a usable chunk count.
        completed: Optional[VideoFrame] = None
        if self._cur_fid is None:
            self._cur_fid = stream_id
        elif stream_id != self._cur_fid:
            completed = self._assemble_current()      # may be None
            self._reset(stream_id)

        # stash slice (ignore duplicates)
        self._frags.setdefault(chunk_id, payload)

        if completed is not None:
            return completed

        if total_chunks is not None and 0 < total_chunks <= 100:
            expected = set(range(total_chunks))
            if expected.issubset(self._frags):
                return self._assemble_current(expected)

        return completed

    # ──────────────────────────────────────────────────────────
    # helpers
    # ──────────────────────────────────────────────────────────
    def _reset(self, new_fid: Optional[int]) -> None:
        self._cur_fid = new_fid
        self._frags.clear()

    def _assemble_current(self, keys_to_use: set[int] | None = None) -> Optional[VideoFrame]:
        if not self._frags:
            return None

        if keys_to_use is None:
            keys = sorted(self._frags)
            complete = len(keys) == keys[-1] - keys[0] + 1
            if not complete:
                missing = (keys[-1] - keys[0] + 1) - len(keys)
               # print(f"[s2x-model] Dropping frame {self._cur_fid}: {missing} slices missing")
                return None
        else:
            keys = sorted(keys_to_use)

        data = b"".join(self._frags[k] for k in keys)

        start = data.find(self.SOI_MARKER)
        end   = data.rfind(self.EOI_MARKER)
        if start < 0 or end < 0 or end <= start:
            #print(f"[s2x-model] JPEG markers not found on frame {self._cur_fid}")
            return None

        jpeg = data[start : end + len(self.EOI_MARKER)]
        #print(f"[s2x-model] Frame {self._cur_fid} OK "
        #      f"({len(jpeg)} bytes, {len(keys)} slices)")
        frame = VideoFrame(self._cur_fid, jpeg, "jpeg")

        self._reset(None)          # prepare for next frame
        return frame