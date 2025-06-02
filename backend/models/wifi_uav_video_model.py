from collections import defaultdict
from typing import Dict, Optional

from models.video_frame import VideoFrame
from utils.wifi_uav_jpeg import generate_jpeg_headers, EOI


class WifiUavVideoModel:
    """
    Re-assembles one JPEG frame from the WiFi-UAV stream.

    The drone sends many UDP packets per frame.  Every packet contains a
    56-byte proprietary header and a JPEG fragment:

        • payload[1] == 0x01 … «JPEG» packet marker
        • payload[2] == 0x38 … *not* last fragment
                     != 0x38 … last fragment
        • payload[16:18]      … little-endian frame counter
        • payload[32:34]      … little-endian fragment index
        • payload[56:]        … actual JPEG bytes
    """

    HEADER_LEN = 56

    def __init__(self, width: int = 640, height: int = 360, num_components: int = 3):
        self._jpeg_header = generate_jpeg_headers(width, height, num_components)

        self._current_frame_id: Optional[int] = None
        self._expected_fragments: Optional[int] = None
        self._fragments: Dict[int, bytes] = defaultdict(bytes)

    # --------------------------------------------------------------------- #
    # public API
    # --------------------------------------------------------------------- #
    def ingest_chunk(self, payload: bytes) -> Optional[VideoFrame]:
        """
        Returns a complete `VideoFrame` when all fragments of one JPEG
        have been received; otherwise returns None.
        """

        # 1. Validate basic markers
        if len(payload) <= self.HEADER_LEN or payload[1] != 0x01:
            return None  # not a JPEG packet – ignore

        last_fragment = payload[2] != 0x38
        frame_id = int.from_bytes(payload[16:18], "little")
        fragment_id = int.from_bytes(payload[32:34], "little")
        jpeg_slice = payload[self.HEADER_LEN :]

        # 2. Start a new frame if necessary
        if self._current_frame_id != frame_id:
            self._reset_state(frame_id)

        # 3. Store slice
        self._fragments[fragment_id] = jpeg_slice
        if last_fragment:
            self._expected_fragments = fragment_id + 1

        # 4. Assemble when complete
        if (
            self._expected_fragments is not None
            and len(self._fragments) == self._expected_fragments
        ):
            ordered = (self._fragments[i] for i in range(self._expected_fragments))
            full_jpeg = (
                self._jpeg_header + b"".join(ordered) + bytes(EOI)
            )  # ensure immutable bytes

            # Prepare next frame
            self._reset_state(None)

            return VideoFrame(frame_id, full_jpeg)

        return None

    # ------------------------------------------------------------------ #
    # private helpers
    # ------------------------------------------------------------------ #
    def _reset_state(self, new_frame_id: Optional[int]):
        self._current_frame_id = new_frame_id
        self._expected_fragments = None
        self._fragments.clear()
