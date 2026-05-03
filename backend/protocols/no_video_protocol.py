import logging
import queue
import threading
import time
from typing import Optional

from models.video_frame import VideoFrame
from protocols.base_video_protocol import BaseVideoProtocolAdapter

logger = logging.getLogger(__name__)


class NoVideoProtocolAdapter(BaseVideoProtocolAdapter):
    """
    Placeholder video adapter for RC backends whose video transport is not yet
    implemented.

    It keeps the web service alive without pretending to decode a stream. The
    logs tell users that the selected drone type currently has RC-only support.
    """

    def __init__(
        self,
        drone_ip: str = "0.0.0.0",
        control_port: int = 0,
        video_port: int = 0,
        *,
        reason: str = "video transport not implemented",
    ) -> None:
        super().__init__(drone_ip, control_port, video_port)
        self.reason = reason
        self._running = threading.Event()

    def start(self) -> None:
        logger.warning("[no-video] %s", self.reason)
        self._running.set()

    def stop(self) -> None:
        self._running.clear()

    def is_running(self) -> bool:
        return self._running.is_set()

    def get_frame(self, timeout: float = 1.0) -> Optional[VideoFrame]:
        if self._running.is_set():
            time.sleep(timeout)
        raise queue.Empty

    def get_packets(self) -> list[bytes]:
        return []

    def send_start_command(self) -> None:
        pass

    def create_receiver_socket(self):
        return None

    def handle_payload(self, payload: bytes) -> Optional[VideoFrame]:
        return None
