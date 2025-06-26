import cv2
import logging
import time
import threading
from typing import Optional

from models.video_frame import VideoFrame
from protocols.base_video_protocol import BaseVideoProtocolAdapter

log = logging.getLogger(__name__)


class DebugVideoProtocolAdapter(BaseVideoProtocolAdapter):
    """
    Drop-in video protocol adapter that fetches frames from the local
    webcam instead of a network socket.  It satisfies every interface
    method the VideoReceiverService relies on, but most of them become
    no-ops or simple stubs.
    """

    # how many seconds the receiver thread may wait before calling us again
    LINK_DEAD_TIMEOUT = 10.0

    def __init__(self, camera_index: int = 0, debug: bool = False):
        # Base class wants drone_ip / ports – give harmless placeholders.
        super().__init__(drone_ip="localhost", control_port=0, video_port=0)

        self.camera_index = camera_index
        self.debug = debug
        self._cap = cv2.VideoCapture(self.camera_index)
        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open local camera #{self.camera_index}")

        self._frame_id = 0
        self._running = True
        # create a dummy socket-like object reference for the receiver
        self._dummy_sock = object()  # any unique instance works

        log.info(f"[debug-video] webcam #{self.camera_index} opened")

    # ------------------------------------------------------------------ #
    # required interface – mostly stubs
    # ------------------------------------------------------------------ #
    def create_receiver_socket(self):  # type: ignore[override]
        return self._dummy_sock

    def get_receiver_socket(self):  # used by VideoReceiverService
        return self._dummy_sock

    # The receiver thread calls this and hands it back to handle_payload().
    # We do nothing except throttle the loop a little and return a token.
    def recv_from_socket(self, sock):  # type: ignore[override]
        time.sleep(1 / 30)  # ≈30 FPS
        return b"\0"  # any non-None value keeps the link "alive"

    def send_start_command(self):  # type: ignore[override]
        # Nothing to start – webcam is always ready.
        return

    def handle_payload(self, payload: bytes) -> Optional[VideoFrame]:  # type: ignore[override]
        """
        Grab one frame from the webcam, JPEG-encode it and wrap it in a
        VideoFrame so that plugins see `format == "jpeg"` and `data`
        contains a binary JPEG just like the real adapters produce.
        """
        ret, frame_bgr = self._cap.read()
        if not ret:
            log.warning("[debug-video] failed to grab frame")
            return None

        ok, jpg = cv2.imencode(".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if not ok:
            log.warning("[debug-video] JPEG encode failed")
            return None

        self._frame_id = (self._frame_id + 1) & 0xFFFF
        return VideoFrame(
            frame_id=self._frame_id,
            data=jpg.tobytes(),
            format_type="jpeg",
        )

    # ------------------------------------------------------------------ #
    # lifecycle helpers
    # ------------------------------------------------------------------ #
    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._cap.isOpened():
            self._cap.release()
        log.info("[debug-video] webcam released")

    # keep-alive threads aren't useful here – override to disable them
    def start_keepalive(self, interval: float = 1.0):  # type: ignore[override]
        return

    def stop_keepalive(self):  # type: ignore[override]
        return 