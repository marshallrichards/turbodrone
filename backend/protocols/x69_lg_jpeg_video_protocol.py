"""
UDP JPEG video for X69 / LG drones (legacy com.lg.drone path).

Stock MainActivityNew / MainActivityDecode use h3.j:
  - Bind local UDP 7070 for incoming JPEG fragments
  - Send stream start/stop to drone 172.16.11.1:7080 (cc 5a 01 82 02 36/37 ...)
  - Reassemble multi-packet frames with a single-byte XOR obfuscation step

This is separate from the active MainActivityUDP H.265 path (UDP 1234) and RTSP.
"""

from __future__ import annotations

import logging
import queue
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Final, List, Optional

from models.cooingdv_video_model import CooingdvVideoModel
from models.video_frame import VideoFrame
from protocols.base_video_protocol import BaseVideoProtocolAdapter
from utils.udp_socket import disable_udp_connreset

logger = logging.getLogger(__name__)

JPEG_SOI: Final = bytes([0xFF, 0xD8])
JPEG_EOI: Final = bytes([0xFF, 0xD9])

# h3.j.d(true) / d(false) / e()
CMD_START_STREAM: Final = bytes([0xCC, 0x5A, 0x01, 0x82, 0x02, 0x36, 0xB7])
CMD_STOP_STREAM: Final = bytes([0xCC, 0x5A, 0x01, 0x82, 0x02, 0x37, 0xB6])
CMD_SWITCH: Final = bytes([0xCC, 0x5A, 0x01, 0x82, 0x02, 0x38, 0xB9])

H265_CLOSE_STREAM: Final = bytes.fromhex("a8 8a 21 00 06 00 00 00 01 00 00 00 00 00")
H265_VIDEO_CONTROL_PORT: Final = 23459

HEADER_LEN: Final = 9
_WIN_UDP_RESET = 10054


def decrypt_packet(packet: bytes) -> bytes:
    """Apply MainActivityNew XOR step before reassembly."""
    if len(packet) <= HEADER_LEN:
        return packet
    out = bytearray(packet)
    frame_num = out[0] & 0xFF
    package_num = out[2] & 0xFF
    idx = (((frame_num * package_num) + 10) * 6666) % (len(out) - HEADER_LEN)
    pos = HEADER_LEN + idx
    if 0 <= pos < len(out):
        out[pos] ^= 0xFF
    return bytes(out)


def is_valid_jpeg(data: bytes) -> bool:
    return len(data) > 4 and data[0:2] == JPEG_SOI and data[-2:] == JPEG_EOI


@dataclass
class JpegFrameAssembler:
    """Reassembles MainActivityNew-style UDP JPEG fragments."""

    decrypt: bool = True
    _buffer: bytearray = field(default_factory=bytearray)
    _assembling: bool = False
    _last_package_num: int = 0
    _gap_pending: bool = False
    _gap_frame_num: int = -1
    _frames_complete: int = 0
    _frames_dropped: int = 0
    _packets_rx: int = 0

    def reset(self) -> None:
        self._buffer.clear()
        self._assembling = False
        self._last_package_num = 0
        self._gap_pending = False
        self._gap_frame_num = -1

    def ingest(self, packet: bytes) -> Optional[bytes]:
        if len(packet) < HEADER_LEN:
            return None

        self._packets_rx += 1
        raw = decrypt_packet(packet) if self.decrypt else packet

        is_end = (raw[1] & 0xFF) == 1
        package_num = raw[2] & 0xFF
        frame_num = raw[0] & 0xFF
        payload = raw[HEADER_LEN:]
        if not payload:
            return None

        if package_num != 1 and package_num != self._last_package_num + 1:
            self._gap_pending = True
            self._gap_frame_num = frame_num

        if self._gap_pending and frame_num == self._gap_frame_num:
            self._frames_dropped += 1
            self.reset()
            return None

        self._gap_pending = False
        self._last_package_num = package_num

        if not is_end:
            if package_num == 1:
                self._buffer.clear()
                self._assembling = True
                self._buffer.extend(payload)
            elif self._assembling:
                self._buffer.extend(payload)
            return None

        if self._assembling:
            self._buffer.extend(payload)
        else:
            self._buffer.clear()
            self._buffer.extend(payload)

        self._assembling = False
        frame = bytes(self._buffer)
        self._buffer.clear()
        self._last_package_num = 0

        if not is_valid_jpeg(frame):
            self._frames_dropped += 1
            return None

        self._frames_complete += 1
        return frame


class X69LgJpegVideoProtocolAdapter(BaseVideoProtocolAdapter):
    """X69/LG legacy UDP JPEG stream (ports 7070 / 7080)."""

    DEFAULT_DRONE_IP: Final = "172.16.11.1"
    DEFAULT_LOCAL_PORT: Final = 7070
    DEFAULT_CMD_PORT: Final = 7080

    def __init__(
        self,
        drone_ip: str = DEFAULT_DRONE_IP,
        control_port: int = DEFAULT_CMD_PORT,
        video_port: int = DEFAULT_LOCAL_PORT,
        *,
        local_port: int | None = None,
        cmd_port: int | None = None,
        decrypt_packets: bool = True,
        stop_h265_first: bool = True,
        debug: bool = False,
        **_: object,
    ) -> None:
        super().__init__(drone_ip, control_port, video_port)
        self.local_port = int(local_port if local_port is not None else video_port)
        self.cmd_port = int(cmd_port if cmd_port is not None else control_port)
        self.decrypt_packets = decrypt_packets
        self.stop_h265_first = stop_h265_first
        self.debug = debug or logger.isEnabledFor(logging.DEBUG)
        self._dbg = logger.debug if self.debug else (lambda *a, **k: None)

        self.model = CooingdvVideoModel()
        self._assembler = JpegFrameAssembler(decrypt=self.decrypt_packets)

        self._sock: Optional[socket.socket] = None
        self._running = False
        self._rx_thread: Optional[threading.Thread] = None
        self._frame_q: queue.Queue[VideoFrame] = queue.Queue(maxsize=2)
        self._pkt_lock = threading.Lock()
        self._pkt_buffer: List[bytes] = []
        self._frame_id = 0
        self._last_frame_time = time.monotonic()
        self._last_stats_log = time.monotonic()
        self._logged_first_packet = False

    def _send_cmd(self, payload: bytes) -> None:
        """Send stream commands from the bound 7070 socket (matches h3.j)."""
        sock = self._sock
        if sock is None:
            return
        try:
            sock.sendto(payload, (self.drone_ip, self.cmd_port))
            self._dbg("[x69-lg-jpeg] cmd -> %s:%s %s", self.drone_ip, self.cmd_port, payload.hex(" "))
        except OSError as exc:
            logger.warning("[x69-lg-jpeg] cmd send failed: %s", exc)

    def _stop_h265_stream(self) -> None:
        if not self.stop_h265_first:
            return
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.sendto(H265_CLOSE_STREAM, (self.drone_ip, H265_VIDEO_CONTROL_PORT))
        except OSError as exc:
            self._dbg("[x69-lg-jpeg] H.265 close send failed: %s", exc)

    def _open_sockets(self) -> bool:
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
            except OSError:
                pass
            self._sock.bind(("0.0.0.0", self.local_port))
            disable_udp_connreset(self._sock)
            self._sock.settimeout(0.5)
            return True
        except OSError as exc:
            logger.warning("[x69-lg-jpeg] socket setup failed: %s", exc)
            self._close_sockets()
            return False

    def _close_sockets(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
        self._sock = None

    def send_start_command(self) -> None:
        self._send_cmd(CMD_START_STREAM)

    def create_receiver_socket(self) -> socket.socket:
        if self._sock is None:
            raise RuntimeError("JPEG video socket not initialized")
        return self._sock

    def handle_payload(self, payload: bytes) -> Optional[VideoFrame]:
        jpeg = self._assembler.ingest(payload)
        if jpeg is None:
            return None
        self._frame_id = (self._frame_id + 1) & 0xFFFF
        self._last_frame_time = time.monotonic()
        return self.model.ingest_chunk(payload=jpeg)

    def start(self) -> None:
        if self._rx_thread and self._rx_thread.is_alive():
            return

        if not self._open_sockets():
            logger.warning("[x69-lg-jpeg] could not bind UDP %s", self.local_port)
            return

        self._running = True
        self._assembler.reset()
        self._logged_first_packet = False
        self._frame_q = queue.Queue(maxsize=2)
        self._stop_h265_stream()
        self._send_cmd(CMD_START_STREAM)

        self._rx_thread = threading.Thread(
            target=self._rx_loop,
            daemon=True,
            name="X69LgJpegVideoRx",
        )
        self._rx_thread.start()
        self.start_keepalive(interval=1.0)
        logger.info(
            "[x69-lg-jpeg] listening on UDP %s, commands to %s:%s (decrypt=%s)",
            self.local_port,
            self.drone_ip,
            self.cmd_port,
            self.decrypt_packets,
        )

    def _rx_loop(self) -> None:
        sock = self._sock
        if sock is None:
            return
        while self._running:
            try:
                packet, addr = sock.recvfrom(65535)
            except socket.timeout:
                self._maybe_log_stats()
                continue
            except OSError as exc:
                if not self._running:
                    break
                if getattr(exc, "winerror", None) == _WIN_UDP_RESET:
                    self._dbg("[x69-lg-jpeg] ICMP port unreachable; continuing")
                    continue
                logger.warning("[x69-lg-jpeg] recv error: %s", exc)
                break

            if not self._logged_first_packet:
                self._logged_first_packet = True
                logger.info(
                    "[x69-lg-jpeg] first UDP packet from %s:%s (%s bytes)",
                    addr[0],
                    addr[1],
                    len(packet),
                )

            if self.debug:
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

            if self.debug and addr:
                self._dbg(
                    "[x69-lg-jpeg] frame from %s:%s len=%s",
                    addr[0],
                    addr[1],
                    len(frame.data),
                )

    def _maybe_log_stats(self) -> None:
        now = time.monotonic()
        if now - self._last_stats_log < 5.0:
            return
        self._last_stats_log = now
        if now - self._last_frame_time > 2.0:
            self._send_cmd(CMD_START_STREAM)
        logger.info(
            "[x69-lg-jpeg] stats packets=%s frames_ok=%s dropped=%s assembling=%s",
            self._assembler._packets_rx,
            self._assembler._frames_complete,
            self._assembler._frames_dropped,
            self._assembler._assembling,
        )

    def stop(self) -> None:
        self._running = False
        self.stop_keepalive()
        self._send_cmd(CMD_STOP_STREAM)
        if self._rx_thread and self._rx_thread.is_alive():
            self._rx_thread.join(timeout=2.0)
        self._close_sockets()
        self._assembler.reset()
        logger.info(
            "[x69-lg-jpeg] stopped frames_ok=%s dropped=%s",
            self._assembler._frames_complete,
            self._assembler._frames_dropped,
        )

    def is_running(self) -> bool:
        return self._running and self._rx_thread is not None and self._rx_thread.is_alive()

    def get_frame(self, timeout: float = 1.0) -> Optional[VideoFrame]:
        try:
            return self._frame_q.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_packets(self) -> List[bytes]:
        with self._pkt_lock:
            packets = self._pkt_buffer
            self._pkt_buffer = []
            return packets
