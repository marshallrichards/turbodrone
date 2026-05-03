"""
First-pass video adapter for the CooingDV/Jieli backend.

KY FPV's Jieli path requests video with CTP JSON commands and receives an RTP
stream on local UDP ports. This adapter implements the JPEG RTP path, which is
the safest initial target because the frontend expects JPEG frames.
"""

from __future__ import annotations

import logging
import queue
import socket
import threading
import time
from typing import Final, Optional

from models.video_frame import VideoFrame
from protocols.base_video_protocol import BaseVideoProtocolAdapter
from utils.cooingdv_jieli_ctp import build_ctp_packet
from utils.wifi_uav_jpeg import EOI, generate_jpeg_headers

logger = logging.getLogger(__name__)


class CooingdvJieliVideoProtocolAdapter(BaseVideoProtocolAdapter):
    DEFAULT_DRONE_IP: Final = "192.168.8.15"
    DEFAULT_CONTROL_PORT: Final = 2228
    DEFAULT_VIDEO_PORT: Final = 6666
    DEFAULT_AUDIO_PORT: Final = 1234
    DEFAULT_SDP_PORT: Final = 6789

    TOPIC_OPEN_FRONT_RTS: Final = "OPEN_RT_STREAM"
    TOPIC_CLOSE_FRONT_RTS: Final = "CLOSE_RT_STREAM"

    FORMAT_JPEG: Final = 0
    FORMAT_H264: Final = 1

    def __init__(
        self,
        drone_ip: str = DEFAULT_DRONE_IP,
        control_port: int = DEFAULT_CONTROL_PORT,
        video_port: int = DEFAULT_VIDEO_PORT,
        *,
        audio_port: int = DEFAULT_AUDIO_PORT,
        sdp_port: int = DEFAULT_SDP_PORT,
        width: int = 640,
        height: int = 360,
        fps: int = 30,
        debug: bool = False,
    ) -> None:
        super().__init__(drone_ip, control_port, video_port)
        self.audio_port = audio_port
        self.sdp_port = sdp_port
        self.width = width
        self.height = height
        self.fps = fps
        self.debug = debug

        self._running = threading.Event()
        self._rx_thread: Optional[threading.Thread] = None
        self._sdp_thread: Optional[threading.Thread] = None
        self._rx_sock: Optional[socket.socket] = None
        self._sdp_sock: Optional[socket.socket] = None
        self._control_sock: Optional[socket.socket] = None
        self._frame_q: "queue.Queue[VideoFrame]" = queue.Queue(maxsize=2)
        self._frame_id = 0
        self._rtp_jpeg_buffers: dict[int, bytearray] = {}

    def start(self) -> None:
        if self.is_running():
            return
        self._running.set()
        self._control_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._control_sock.bind(("", 0))
        self._start_sdp_server()
        self._send_open_stream()
        self._rx_thread = threading.Thread(
            target=self._rx_loop,
            daemon=True,
            name="CooingdvJieliVideoRx",
        )
        self._rx_thread.start()
        logger.info(
            "[cooingdv-jieli-video] listening for RTP/JPEG on UDP %s; SDP on TCP %s",
            self.video_port,
            self.sdp_port,
        )

    def stop(self) -> None:
        self._running.clear()
        self._send_close_stream()
        for sock in (self._rx_sock, self._sdp_sock, self._control_sock):
            if sock:
                try:
                    sock.close()
                except OSError:
                    pass
        if self._rx_thread:
            self._rx_thread.join(timeout=1.0)
        if self._sdp_thread:
            self._sdp_thread.join(timeout=1.0)

    def is_running(self) -> bool:
        return self._running.is_set() and self._rx_thread is not None and self._rx_thread.is_alive()

    def get_frame(self, timeout: float = 1.0) -> Optional[VideoFrame]:
        try:
            return self._frame_q.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_packets(self) -> list[bytes]:
        return []

    def send_start_command(self) -> None:
        self._send_open_stream()

    def create_receiver_socket(self):
        return None

    def handle_payload(self, payload: bytes) -> Optional[VideoFrame]:
        self._frame_id = (self._frame_id + 1) & 0xFFFF
        return VideoFrame(self._frame_id, payload, format_type="jpeg")

    def _send_open_stream(self) -> None:
        self._send_ctp(
            self.TOPIC_OPEN_FRONT_RTS,
            {
                "format": str(self.FORMAT_JPEG),
                "w": str(self.width),
                "h": str(self.height),
                "fps": str(self.fps),
            },
        )

    def _send_close_stream(self) -> None:
        self._send_ctp(self.TOPIC_CLOSE_FRONT_RTS, {"status": "1"})

    def _send_ctp(self, topic: str, params: dict[str, str]) -> None:
        sock = self._control_sock
        if sock is None:
            return
        packet = build_ctp_packet(topic, params)
        try:
            sock.sendto(packet, (self.drone_ip, self.control_port))
        except OSError:
            pass

    def _start_sdp_server(self) -> None:
        self._sdp_thread = threading.Thread(
            target=self._sdp_loop,
            daemon=True,
            name="CooingdvJieliSdpServer",
        )
        self._sdp_thread.start()

    def _sdp_loop(self) -> None:
        sdp = (
            "c=IN IP4 127.0.0.1\n"
            f"m=audio {self.audio_port} RTP/AVP 97\n"
            "a=rtpmap:97 L16/8000/1\n"
            "a=ptime:20\n"
            f"m=video {self.video_port} RTP/AVP 26\n"
            "a=rtpmap:26 JPEG/90000\n"
            f"a=framerate:{self.fps}"
        ).encode("utf-8")

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", self.sdp_port))
            sock.listen(1)
            sock.settimeout(0.5)
            self._sdp_sock = sock
        except OSError as exc:
            logger.warning("[cooingdv-jieli-video] SDP server unavailable: %s", exc)
            return

        while self._running.is_set():
            try:
                conn, _ = sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with conn:
                try:
                    conn.sendall(sdp)
                except OSError:
                    pass

    def _rx_loop(self) -> None:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", self.video_port))
            sock.settimeout(0.5)
            self._rx_sock = sock
        except OSError as exc:
            logger.warning("[cooingdv-jieli-video] RTP socket unavailable: %s", exc)
            self._running.clear()
            return

        while self._running.is_set():
            try:
                packet, _ = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break

            frame = self._handle_rtp_packet(packet)
            if frame is None:
                continue
            try:
                self._frame_q.put(frame, timeout=0.1)
            except queue.Full:
                try:
                    self._frame_q.get_nowait()
                    self._frame_q.put(frame, timeout=0.1)
                except (queue.Empty, queue.Full):
                    pass

    def _handle_rtp_packet(self, packet: bytes) -> Optional[VideoFrame]:
        if len(packet) < 12 or (packet[0] >> 6) != 2:
            return self._handle_possible_raw_jpeg(packet)

        csrc_count = packet[0] & 0x0F
        marker = bool(packet[1] & 0x80)
        payload_type = packet[1] & 0x7F
        timestamp = int.from_bytes(packet[4:8], "big")
        offset = 12 + (csrc_count * 4)
        if packet[0] & 0x10:
            if len(packet) < offset + 4:
                return None
            ext_len = int.from_bytes(packet[offset + 2 : offset + 4], "big") * 4
            offset += 4 + ext_len
        payload = packet[offset:]

        if payload_type == 26:
            return self._handle_rtp_jpeg(timestamp, payload, marker)
        return self._handle_possible_raw_jpeg(payload)

    def _handle_rtp_jpeg(self, timestamp: int, payload: bytes, marker: bool) -> Optional[VideoFrame]:
        if len(payload) < 8:
            return None
        fragment_offset = int.from_bytes(payload[1:4], "big")
        width = payload[6] * 8 or self.width
        height = payload[7] * 8 or self.height
        scan = payload[8:]

        if fragment_offset == 0:
            self._rtp_jpeg_buffers[timestamp] = bytearray(generate_jpeg_headers(width, height))

        buf = self._rtp_jpeg_buffers.setdefault(timestamp, bytearray())
        buf.extend(scan)
        if not marker:
            return None

        data = bytes(buf)
        self._rtp_jpeg_buffers.pop(timestamp, None)
        if not data.endswith(EOI):
            data += bytes(EOI)
        return self.handle_payload(data)

    def _handle_possible_raw_jpeg(self, payload: bytes) -> Optional[VideoFrame]:
        start = payload.find(b"\xff\xd8")
        end = payload.rfind(b"\xff\xd9")
        if start >= 0 and end > start:
            return self.handle_payload(payload[start : end + 2])
        if self.debug and payload:
            logger.debug("[cooingdv-jieli-video] ignored payload %sB", len(payload))
        return None
