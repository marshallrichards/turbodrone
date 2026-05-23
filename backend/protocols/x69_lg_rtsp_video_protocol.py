"""
RTSP video adapter for X69 / LG drones (com.lg.drone).

The stock app also ships MainActivityRTSP, which plays:
  rtsp://172.16.11.1/live/ch00_1

This path uses OpenCV + FFmpeg (same approach as cooingdv) instead of UDP H.265
reassembly + transcoding.
"""

from __future__ import annotations

import logging
import os
import queue
import threading
import time
from typing import Final, List, Optional

import cv2

from models.cooingdv_video_model import CooingdvVideoModel
from models.video_frame import VideoFrame
from protocols.base_video_protocol import BaseVideoProtocolAdapter

logger = logging.getLogger(__name__)


def build_x69_rtsp_url(
    *,
    drone_ip: str,
    video_port: int,
    rtsp_path: str,
    rtsp_url: str | None = None,
) -> str:
    """Build the RTSP URL, or return a full override from env/args."""
    if rtsp_url:
        return rtsp_url.strip()
    path = rtsp_path if rtsp_path.startswith("/") else f"/{rtsp_path}"
    if video_port in (0, 554):
        return f"rtsp://{drone_ip}{path}"
    return f"rtsp://{drone_ip}:{video_port}{path}"


def _rtsp_capture_options() -> str:
    """
    FFmpeg options for OpenCV's RTSP backend.

    MainActivityRTSP uses fanplayer with rtsp_transport=1 (TCP) and video_bufpktn=1.
    """
    return os.getenv(
        "X69_LG_RTSP_FFMPEG_OPTIONS",
        "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay",
    )


class X69LgRtspVideoProtocolAdapter(BaseVideoProtocolAdapter):
    """X69/LG live view over RTSP → JPEG frames for the MJPEG web pipeline."""

    DEFAULT_DRONE_IP: Final = "172.16.11.1"
    DEFAULT_RTSP_PORT: Final = 554
    DEFAULT_CONTROL_PORT: Final = 23459
    RTSP_PATH: Final = "/live/ch00_1"

    RECONNECT_DELAY: Final = 2.0
    MAX_RECONNECT_ATTEMPTS: Final = 10
    FRAME_TIMEOUT: Final = 5.0
    READ_FAILURE_BACKOFF: Final = 0.05

    def __init__(
        self,
        drone_ip: str = DEFAULT_DRONE_IP,
        control_port: int = DEFAULT_CONTROL_PORT,
        video_port: int = DEFAULT_RTSP_PORT,
        *,
        rtsp_path: str | None = None,
        rtsp_url: str | None = None,
        jpeg_quality: int | None = None,
        debug: bool = False,
        **_: object,
    ) -> None:
        super().__init__(drone_ip, control_port, video_port)
        self.model = CooingdvVideoModel()

        path = rtsp_path or os.getenv("X69_LG_RTSP_PATH", self.RTSP_PATH)
        env_url = (rtsp_url or os.getenv("X69_LG_RTSP_URL", "").strip() or None)
        self.rtsp_url = build_x69_rtsp_url(
            drone_ip=drone_ip,
            video_port=int(video_port),
            rtsp_path=path,
            rtsp_url=env_url,
        )

        # OpenCV JPEG quality is 1–100 (higher = better), unlike FFmpeg -q:v on the UDP path.
        self._jpeg_quality = int(
            jpeg_quality
            if jpeg_quality is not None
            else os.getenv("X69_LG_RTSP_JPEG_QUALITY", "85")
        )

        self.debug = debug or logger.isEnabledFor(logging.DEBUG)
        self._dbg = logger.debug if self.debug else (lambda *a, **k: None)

        self._cap: Optional[cv2.VideoCapture] = None
        self._cap_lock = threading.Lock()
        self._running = False
        self._rx_thread: Optional[threading.Thread] = None
        self._frame_q: queue.Queue[VideoFrame] = queue.Queue(maxsize=2)
        self._pkt_lock = threading.Lock()
        self._pkt_buffer: List[bytes] = []

        self.frames_ok = 0
        self.frames_dropped = 0
        self.reconnect_count = 0
        self._last_frame_time = time.time()
        self._last_stats_log = time.time()

    def _open_stream(self) -> bool:
        with self._cap_lock:
            if self._cap is not None:
                self._cap.release()

            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = _rtsp_capture_options()
            self._dbg("[x69-lg-rtsp] Opening %s", self.rtsp_url)
            self._cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if self._cap.isOpened():
                self._last_frame_time = time.time()
                logger.info("[x69-lg-rtsp] Stream opened: %s", self.rtsp_url)
                return True

            self._cap = None
            logger.warning("[x69-lg-rtsp] Failed to open stream: %s", self.rtsp_url)
            return False

    def _close_stream(self) -> None:
        with self._cap_lock:
            if self._cap is not None:
                self._cap.release()
                self._cap = None

    def _reconnect(self) -> bool:
        self.reconnect_count += 1
        self._close_stream()
        time.sleep(self.RECONNECT_DELAY)
        for attempt in range(self.MAX_RECONNECT_ATTEMPTS):
            if not self._running:
                return False
            if self._open_stream():
                return True
            time.sleep(self.RECONNECT_DELAY)
        return False

    def send_start_command(self) -> None:
        pass

    def create_receiver_socket(self):
        return None

    def handle_payload(self, payload: bytes) -> Optional[VideoFrame]:
        return self.model.ingest_chunk(payload=payload)

    def start(self) -> None:
        if self._rx_thread and self._rx_thread.is_alive():
            return
        self._running = True
        self._frame_q = queue.Queue(maxsize=2)
        if not self._open_stream():
            logger.warning("[x69-lg-rtsp] Could not open stream on start")
        self._rx_thread = threading.Thread(
            target=self._rx_loop,
            daemon=True,
            name="X69LgRtspVideoRx",
        )
        self._rx_thread.start()

    def _rx_loop(self) -> None:
        while self._running:
            with self._cap_lock:
                cap = self._cap

            if cap is None or not cap.isOpened():
                if not self._reconnect():
                    time.sleep(self.RECONNECT_DELAY)
                continue

            try:
                ret, frame = cap.read()
                if not ret or frame is None:
                    if time.time() - self._last_frame_time > self.FRAME_TIMEOUT:
                        self._reconnect()
                    else:
                        time.sleep(self.READ_FAILURE_BACKOFF)
                    continue

                self._last_frame_time = time.time()
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), self._jpeg_quality]
                _, jpeg_data = cv2.imencode(".jpg", frame, encode_param)
                video_frame = self.handle_payload(jpeg_data.tobytes())
                if video_frame is None:
                    continue

                self.frames_ok += 1
                try:
                    self._frame_q.put(video_frame, timeout=0.1)
                except queue.Full:
                    self.frames_dropped += 1
                    try:
                        self._frame_q.get_nowait()
                        self._frame_q.put(video_frame, timeout=0.1)
                    except (queue.Empty, queue.Full):
                        pass

                now = time.monotonic()
                if now - self._last_stats_log >= 5.0:
                    self._last_stats_log = now
                    logger.info(
                        "[x69-lg-rtsp] stats frames_ok=%s dropped=%s reconnects=%s",
                        self.frames_ok,
                        self.frames_dropped,
                        self.reconnect_count,
                    )

            except cv2.error as exc:
                self._dbg("[x69-lg-rtsp] OpenCV error: %s", exc)
                self._reconnect()
            except Exception as exc:
                logger.warning("[x69-lg-rtsp] Unexpected error: %s", exc)
                time.sleep(0.1)

    def stop(self) -> None:
        self._running = False
        if self._rx_thread and self._rx_thread.is_alive():
            self._rx_thread.join(timeout=2.0)
        self._close_stream()
        logger.info(
            "[x69-lg-rtsp] stopped frames_ok=%s dropped=%s reconnects=%s",
            self.frames_ok,
            self.frames_dropped,
            self.reconnect_count,
        )

    def is_running(self) -> bool:
        return self._running and self._rx_thread is not None and self._rx_thread.is_alive()

    def get_frame(self, timeout: float = 1.0) -> Optional[VideoFrame]:
        try:
            return self._frame_q.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_packets(self) -> List[bytes]:
        return []

    def start_keepalive(self, interval: float = 1.0) -> None:
        pass

    def stop_keepalive(self) -> None:
        pass
