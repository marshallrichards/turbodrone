"""Video protocol adapter for WiFi_CAM native UDP drones."""

from __future__ import annotations

import logging
import queue
import socket
import threading
from typing import Final, Optional

from models.video_frame import VideoFrame
from protocols.base_video_protocol import BaseVideoProtocolAdapter

logger = logging.getLogger(__name__)


class WifiCamVideoProtocolAdapter(BaseVideoProtocolAdapter):
    """Start the WiFi_CAM MJPEG stream and reassemble native JPEG chunks."""

    DEFAULT_DRONE_IP: Final = "192.168.4.153"
    DEFAULT_COMMAND_PORT: Final = 8090
    DEFAULT_VIDEO_PORT: Final = 8080

    START_STREAM: Final = b"\x42\x76"
    STOP_STREAM: Final = b"\x42\x77"
    ROTATE: Final = b"\x42\x78"
    CAMERA_SWITCH: Final = b"\x42\x79"

    NATIVE_PACKET_SIZE: Final = 0x5C0
    HEADER_SIZE: Final = 8
    CHUNK_SIZE: Final = 0x5B8
    SOI: Final = b"\xff\xd8"
    EOI: Final = b"\xff\xd9"

    def __init__(
        self,
        drone_ip: str = DEFAULT_DRONE_IP,
        control_port: int = DEFAULT_COMMAND_PORT,
        video_port: int = DEFAULT_VIDEO_PORT,
        *,
        debug: bool = False,
    ) -> None:
        super().__init__(drone_ip, control_port, video_port)
        self.debug = debug
        self._running = threading.Event()
        self._rx_thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None
        self._frame_q: "queue.Queue[VideoFrame]" = queue.Queue(maxsize=2)
        self._pkt_lock = threading.Lock()
        self._pkt_buffer: list[bytes] = []
        self._rc_adapter = None

        self._current_frame_id: Optional[int] = None
        self._current_chunk_index = 0
        self._frame_buffer = bytearray()
        self._frame_counter = 0
        self.camera_type = 0

    def set_rc_adapter(self, rc_adapter) -> None:
        self._rc_adapter = rc_adapter
        if self.camera_type and hasattr(rc_adapter, "set_camera_type"):
            rc_adapter.set_camera_type(self.camera_type)

    def start(self) -> None:
        if self.is_running():
            return
        self._sock = self.create_receiver_socket()
        self._running.set()
        self.send_start_command()
        self._rx_thread = threading.Thread(
            target=self._rx_loop,
            daemon=True,
            name="WifiCamVideoRx",
        )
        self._rx_thread.start()
        logger.info("[wifi-cam-video] listening on local UDP %s", self._sock.getsockname()[1])

    def stop(self) -> None:
        self._running.clear()
        self._send_command(self.STOP_STREAM)
        sock = self._sock
        if sock:
            try:
                sock.close()
            except OSError:
                pass
        if self._rx_thread:
            self._rx_thread.join(timeout=1.0)
        self._rx_thread = None
        self._sock = None

    def is_running(self) -> bool:
        return self._running.is_set() and self._rx_thread is not None and self._rx_thread.is_alive()

    def get_frame(self, timeout: float = 1.0) -> Optional[VideoFrame]:
        try:
            return self._frame_q.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_packets(self) -> list[bytes]:
        with self._pkt_lock:
            packets = self._pkt_buffer
            self._pkt_buffer = []
            return packets

    def send_start_command(self) -> None:
        self._send_command(self.START_STREAM)

    def create_receiver_socket(self) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # The Android app does not bind to 8080; it receives replies on the
        # same ephemeral local UDP port used to send 42 76 to the drone.
        sock.bind(("", 0))
        sock.settimeout(0.5)
        return sock

    def handle_payload(self, payload: bytes) -> Optional[VideoFrame]:
        camera_type = self._parse_camera_type(payload)
        if camera_type is not None:
            self._set_camera_type(camera_type)
            return None

        if len(payload) < self.HEADER_SIZE:
            return None

        frame_id = payload[0]
        final_marker = payload[1]
        total_chunks = payload[2]
        resolution = payload[3]
        retain = payload[7]
        chunk = payload[self.HEADER_SIZE :]

        if self._current_frame_id != frame_id:
            self._current_frame_id = frame_id
            self._current_chunk_index = 0
            self._frame_buffer = bytearray()

        chunk_index = self._current_chunk_index
        self._frame_buffer.extend(chunk)

        frame = None
        is_final = final_marker == 1 and total_chunks > 0 and chunk_index + 1 == total_chunks
        if is_final:
            frame = self._finish_frame(chunk, chunk_index, resolution, retain)
            self._current_chunk_index = 0
            self._current_frame_id = None
            self._frame_buffer = bytearray()
        else:
            self._current_chunk_index += 1

        return frame

    def switch_camera(self) -> None:
        self._send_command(self.CAMERA_SWITCH)

    def rotate(self) -> None:
        self._send_command(self.ROTATE)

    def _rx_loop(self) -> None:
        sock = self._sock
        if sock is None:
            return
        while self._running.is_set():
            try:
                packet, _ = sock.recvfrom(self.NATIVE_PACKET_SIZE)
            except socket.timeout:
                continue
            except OSError:
                break

            with self._pkt_lock:
                self._pkt_buffer.append(packet)

            frame = self.handle_payload(packet)
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

    def _send_command(self, command: bytes) -> None:
        sock = self._sock
        if sock is None:
            return
        try:
            sock.sendto(command, (self.drone_ip, self.video_port))
        except OSError:
            pass

    def _parse_camera_type(self, payload: bytes) -> Optional[int]:
        if len(payload) != 8 or payload[0] != 0x55 or payload[7] != 0x99:
            return None
        if payload == b"\x55\x00\x01\x00\x00\x00\x01\x99":
            return 1
        if payload == b"\x55\x00\x02\x00\x00\x00\x02\x99":
            return 2
        return 0

    def _set_camera_type(self, camera_type: int) -> None:
        if camera_type == self.camera_type:
            return
        self.camera_type = camera_type
        logger.info("[wifi-cam-video] detected camera type %s", camera_type)
        if self._rc_adapter is not None and hasattr(self._rc_adapter, "set_camera_type"):
            self._rc_adapter.set_camera_type(camera_type)

    def _finish_frame(
        self,
        final_chunk: bytes,
        final_chunk_index: int,
        resolution: int,
        retain: int,
    ) -> Optional[VideoFrame]:
        eoi = final_chunk.find(self.EOI)
        if eoi < 0:
            return None

        frame_len = final_chunk_index * self.CHUNK_SIZE + eoi + len(self.EOI)
        data = bytes(self._frame_buffer[:frame_len])
        if not data.startswith(self.SOI) or not data.endswith(self.EOI):
            if self.debug:
                logger.debug("[wifi-cam-video] rejected malformed JPEG frame")
            return None

        self._frame_counter = (self._frame_counter + 1) & 0xFFFF
        frame = VideoFrame(self._frame_counter, data, format_type="jpeg")
        frame.resolution = resolution  # type: ignore[attr-defined]
        frame.retain = retain  # type: ignore[attr-defined]
        return frame
