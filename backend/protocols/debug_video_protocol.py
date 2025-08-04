import cv2
import logging
import time
import threading
import queue
from typing import Optional, List

from models.video_frame import VideoFrame
from protocols.base_video_protocol import BaseVideoProtocolAdapter
from utils.dropping_queue import DroppingQueue

log = logging.getLogger(__name__)


class DebugVideoProtocolAdapter(BaseVideoProtocolAdapter):
    """
    Drop-in video protocol adapter that fetches frames from the local
    webcam instead of a network socket.
    """
    def __init__(self, camera_index: int = 0, debug: bool = False, max_queue_size=100):
        super().__init__(drone_ip="localhost", control_port=0, video_port=0)

        self.camera_index = camera_index
        self.debug = debug
        self._cap = None
        self._frame_id = 0
        self._running = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.frame_queue = DroppingQueue(maxsize=max_queue_size)

    def start(self):
        self._cap = cv2.VideoCapture(self.camera_index)
        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open local camera #{self.camera_index}")

        self._running.set()
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        log.info(f"[debug-video] webcam #{self.camera_index} opened")

    def stop(self):
        if not self._running.is_set():
            return
        
        self._running.clear()
        if self._thread:
            self._thread.join(timeout=1.0)
        
        if self._cap and self._cap.isOpened():
            self._cap.release()
        
        log.info("[debug-video] webcam released")

    def is_running(self) -> bool:
        return self._running.is_set()

    def get_frame(self, timeout: float = 1.0) -> Optional[VideoFrame]:
        try:
            return self.frame_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def get_packets(self) -> List[bytes]:
        # Not applicable for webcam, but required by the service
        return []

    def _capture_loop(self):
        while self._running.is_set():
            if not self._cap or not self._cap.isOpened():
                log.error("[debug-video] camera is not open.")
                self._running.clear()
                break

            ret, frame_bgr = self._cap.read()
            if not ret:
                log.warning("[debug-video] failed to grab frame")
                time.sleep(0.1)
                continue

            ok, jpg = cv2.imencode(".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if not ok:
                log.warning("[debug-video] JPEG encode failed")
                continue

            self._frame_id = (self._frame_id + 1) & 0xFFFF
            video_frame = VideoFrame(
                frame_id=self._frame_id,
                data=jpg.tobytes(),
                format_type="jpeg",
            )
            
            try:
                self.frame_queue.put(video_frame)
            except queue.Full:
                # This is expected if the queue is full
                pass

        log.info("[debug-video] capture loop stopped.")

    # --- Stubs for methods that are not used by this adapter ---
    def create_receiver_socket(self):
        return None

    def send_start_command(self):
        pass

    def handle_payload(self, payload: bytes) -> Optional[VideoFrame]:
        return None
