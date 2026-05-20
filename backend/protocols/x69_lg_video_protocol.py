from __future__ import annotations

import logging
import os
import queue
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Final, Optional, Protocol

from models.video_frame import VideoFrame
from protocols.base_video_protocol import BaseVideoProtocolAdapter

logger = logging.getLogger(__name__)


class H265Decoder(Protocol):
    def feed(self, frame: bytes) -> None: ...
    def get_frame(self, timeout: float = 0.0) -> Optional[bytes]: ...
    def stop(self) -> None: ...


class FFmpegH265ToJpegDecoder:
    """Pipe Annex-B H.265 frames through FFmpeg and parse MJPEG output."""

    SOI: Final = b"\xff\xd8"
    EOI: Final = b"\xff\xd9"

    def __init__(self, *, ffmpeg_bin: str = "ffmpeg", jpeg_quality: int = 5) -> None:
        self.ffmpeg_bin = ffmpeg_bin
        self.jpeg_quality = int(jpeg_quality)
        self._proc: Optional[subprocess.Popen] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None
        self._frames: "queue.Queue[bytes]" = queue.Queue(maxsize=2)
        self._stdout_buffer = bytearray()
        self._lock = threading.Lock()

    def feed(self, frame: bytes) -> None:
        proc = self._ensure_started()
        if proc is None or proc.stdin is None:
            return
        try:
            proc.stdin.write(frame)
            proc.stdin.flush()
        except (BrokenPipeError, OSError):
            self.stop()

    def get_frame(self, timeout: float = 0.0) -> Optional[bytes]:
        try:
            return self._frames.get(timeout=timeout)
        except queue.Empty:
            return None

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def stop(self) -> None:
        with self._lock:
            proc = self._proc
            self._proc = None
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
        except OSError:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=1.0)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def _ensure_started(self) -> Optional[subprocess.Popen]:
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return self._proc
            cmd = [
                self.ffmpeg_bin,
                "-hide_banner",
                "-loglevel",
                "error",
                "-fflags",
                "+genpts",
                "-flags2",
                "+showall",
                "-err_detect",
                "ignore_err",
                "-f",
                "hevc",
                "-i",
                "pipe:0",
                "-an",
                "-c:v",
                "mjpeg",
                "-f",
                "image2pipe",
                "-q:v",
                str(self.jpeg_quality),
                "pipe:1",
            ]
            try:
                self._proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=0,
                )
            except OSError as exc:
                logger.warning("[x69-lg-video] failed to start ffmpeg: %s", exc)
                self._proc = None
                return None

            self._reader_thread = threading.Thread(
                target=self._read_stdout,
                args=(self._proc,),
                daemon=True,
                name="X69LgFfmpegStdout",
            )
            self._reader_thread.start()
            self._stderr_thread = threading.Thread(
                target=self._drain_stderr,
                args=(self._proc,),
                daemon=True,
                name="X69LgFfmpegStderr",
            )
            self._stderr_thread.start()
            return self._proc

    def _read_stdout(self, proc: subprocess.Popen) -> None:
        stdout = proc.stdout
        if stdout is None:
            return
        while proc.poll() is None:
            try:
                chunk = stdout.read(4096)
            except OSError:
                break
            if not chunk:
                break
            self._stdout_buffer.extend(chunk)
            self._extract_jpegs()

    def _drain_stderr(self, proc: subprocess.Popen) -> None:
        stderr = proc.stderr
        if stderr is None:
            return
        try:
            for line in iter(stderr.readline, b""):
                if line:
                    logger.warning("[x69-lg-video/ffmpeg] %s", line.decode(errors="ignore").strip())
        except OSError:
            pass

    def _extract_jpegs(self) -> None:
        while True:
            start = self._stdout_buffer.find(self.SOI)
            if start < 0:
                self._stdout_buffer.clear()
                return
            if start > 0:
                del self._stdout_buffer[:start]
            end = self._stdout_buffer.find(self.EOI, 2)
            if end < 0:
                return
            end += len(self.EOI)
            jpeg = bytes(self._stdout_buffer[:end])
            del self._stdout_buffer[:end]
            try:
                self._frames.put_nowait(jpeg)
            except queue.Full:
                try:
                    self._frames.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self._frames.put_nowait(jpeg)
                except queue.Full:
                    pass


@dataclass
class _FrameAssembly:
    frame_len: int
    total_chunks: int
    frame_type: int
    chunks: dict[int, bytes] = field(default_factory=dict)


class X69LgVideoProtocolAdapter(BaseVideoProtocolAdapter):
    """Receive X69/LG H.265 UDP stream and expose JPEG frames."""

    DEFAULT_DRONE_IP: Final = "172.16.11.1"
    DEFAULT_VIDEO_CONTROL_PORT: Final = 23459
    DEFAULT_VIDEO_PORT: Final = 1234
    DEFAULT_LOCAL_CONTROL_PORT: Final = 23459

    OPEN_STREAM: Final = bytes.fromhex("a8 8a 20 00 08 00 00 00 01 00 02 00 00 00 d2 04")
    CLOSE_STREAM: Final = bytes.fromhex("a8 8a 21 00 06 00 00 00 01 00 00 00 00 00")
    IFRAME_REQUEST: Final = bytes.fromhex("a8 8a 24 00 02 00 00 00 01 00")
    STREAM_MAGIC: Final = b"\xc6\x6c\xa5\x5a"
    HEADER_LEN: Final = 32

    def __init__(
        self,
        drone_ip: str = DEFAULT_DRONE_IP,
        control_port: int = DEFAULT_VIDEO_CONTROL_PORT,
        video_port: int = DEFAULT_VIDEO_PORT,
        *,
        local_control_port: int = DEFAULT_LOCAL_CONTROL_PORT,
        decoder: Optional[H265Decoder] = None,
        debug: bool = False,
    ) -> None:
        super().__init__(drone_ip, control_port, video_port)
        self.local_control_port = int(local_control_port)
        self.debug = debug
        self._running = threading.Event()
        self._rx_thread: Optional[threading.Thread] = None
        self._keepalive_thread: Optional[threading.Thread] = None
        self._stream_sock: Optional[socket.socket] = None
        self._control_sock: Optional[socket.socket] = None
        self._frame_q: "queue.Queue[VideoFrame]" = queue.Queue(maxsize=2)
        self._pkt_lock = threading.Lock()
        self._pkt_buffer: list[bytes] = []
        self._assemblies: dict[int, _FrameAssembly] = {}
        self._decoder = decoder or FFmpegH265ToJpegDecoder()
        self._frame_id = 0
        self._last_complete_h265 = time.monotonic()
        self._last_decoded_jpeg = time.monotonic()
        self._last_stats_log = time.monotonic()
        self._packets_rx = 0
        self._bad_packets = 0
        self._h265_frames = 0
        self._jpeg_frames = 0
        self._logged_first_h265 = False
        self._logged_first_config_h265 = False
        self._decoder_ready = False
        self._dump_h265_enabled = os.getenv("X69_LG_DUMP_H265", "false").lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        self._dump_h265_seconds = float(os.getenv("X69_LG_DUMP_H265_SECONDS", "5"))
        self._dump_h265_file = None
        self._dump_h265_path: Optional[Path] = None
        self._dump_h265_start: Optional[float] = None
        self._dump_h265_done = False

    def start(self) -> None:
        if self.is_running():
            return
        self._stream_sock = self.create_receiver_socket()
        self._control_sock = self._create_control_socket()
        self._running.set()
        # Match Android startup: close then open.
        self._send_video_command(self.CLOSE_STREAM)
        self._send_video_command(self.OPEN_STREAM)
        self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True, name="X69LgVideoRx")
        self._rx_thread.start()
        self._keepalive_thread = threading.Thread(
            target=self._keepalive_loop,
            daemon=True,
            name="X69LgVideoKeepalive",
        )
        self._keepalive_thread.start()
        logger.info("[x69-lg-video] listening on UDP %s", self.video_port)

    def stop(self) -> None:
        self._running.clear()
        self._send_video_command(self.CLOSE_STREAM)
        for sock in (self._stream_sock, self._control_sock):
            if sock:
                try:
                    sock.close()
                except OSError:
                    pass
        if self._rx_thread:
            self._rx_thread.join(timeout=1.0)
        if self._keepalive_thread:
            self._keepalive_thread.join(timeout=1.0)
        self._decoder.stop()
        self._close_h265_dump()
        self._stream_sock = None
        self._control_sock = None

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
        self._send_video_command(self.OPEN_STREAM)

    def create_receiver_socket(self) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
        except OSError:
            pass
        sock.bind(("0.0.0.0", self.video_port))
        sock.settimeout(0.5)
        return sock

    def handle_payload(self, payload: bytes) -> Optional[VideoFrame]:
        h265_frame = self._ingest_stream_packet(payload)
        if h265_frame is not None:
            self._last_complete_h265 = time.monotonic()
            if not self._decoder_ready:
                self._decoder_ready = self._has_parameter_set(h265_frame)
                if self._decoder_ready:
                    logger.info(
                        "[x69-lg-video] H.265 parameter set detected; starting decoder feed; nal_types=%s prefix=%s",
                        list(self._iter_h265_nal_types(h265_frame[:512])),
                        h265_frame[:48].hex(" "),
                    )
                else:
                    return None
            self._dump_h265_frame(h265_frame)
            self._decoder.feed(h265_frame)
        return self._next_decoded_frame(timeout=0.01 if h265_frame is not None else 0.0)

    def _rx_loop(self) -> None:
        sock = self._stream_sock
        if sock is None:
            return
        while self._running.is_set():
            try:
                packet, _ = sock.recvfrom(65535)
            except socket.timeout:
                frame = self._next_decoded_frame()
                if frame is not None:
                    self._put_frame(frame)
                continue
            except OSError:
                break

            with self._pkt_lock:
                self._pkt_buffer.append(packet)
            self._packets_rx += 1

            frame = self.handle_payload(packet)
            if frame is not None:
                self._put_frame(frame)
            self._log_stats_if_due()

    def _ingest_stream_packet(self, packet: bytes) -> Optional[bytes]:
        if len(packet) < self.HEADER_LEN or packet[:4] != self.STREAM_MAGIC:
            self._bad_packets += 1
            return None

        frame_len = int.from_bytes(packet[4:8], "little")
        frame_id = int.from_bytes(packet[8:12], "little")
        frame_type = packet[17]
        total_chunks = int.from_bytes(packet[20:22], "little")
        chunk_index = int.from_bytes(packet[22:24], "little")
        payload_offset = int.from_bytes(packet[24:28], "little")
        payload_len = int.from_bytes(packet[28:32], "little")
        chunk = packet[self.HEADER_LEN : self.HEADER_LEN + payload_len]

        if frame_len <= 0 or total_chunks <= 0 or chunk_index >= total_chunks:
            self._bad_packets += 1
            return None
        if payload_len != len(chunk):
            self._bad_packets += 1
            return None

        assembly = self._assemblies.get(frame_id)
        if assembly is None:
            assembly = _FrameAssembly(frame_len=frame_len, total_chunks=total_chunks, frame_type=frame_type)
            self._assemblies[frame_id] = assembly
        assembly.chunks[chunk_index] = chunk

        if len(assembly.chunks) != assembly.total_chunks:
            self._trim_assemblies()
            return None

        frame = bytearray()
        for index in range(assembly.total_chunks):
            part = assembly.chunks.get(index)
            if part is None:
                return None
            frame.extend(part)

        if len(frame) != assembly.frame_len:
            self._bad_packets += 1
            return None

        del self._assemblies[frame_id]
        self._trim_assemblies()
        self._h265_frames += 1
        h265 = bytes(frame)
        if not self._logged_first_h265:
            self._logged_first_h265 = True
            logger.info("[x69-lg-video] first H.265 frame prefix: %s", h265[:32].hex(" "))
        return h265

    def _trim_assemblies(self) -> None:
        if len(self._assemblies) <= 4:
            return
        for frame_id in sorted(self._assemblies)[:-4]:
            self._assemblies.pop(frame_id, None)

    def _next_decoded_frame(self, timeout: float = 0.0) -> Optional[VideoFrame]:
        jpeg = self._decoder.get_frame(timeout=timeout)
        if jpeg is None:
            return None
        self._frame_id = (self._frame_id + 1) & 0xFFFF
        self._jpeg_frames += 1
        self._last_decoded_jpeg = time.monotonic()
        return VideoFrame(self._frame_id, jpeg, format_type="jpeg")

    def _has_parameter_set(self, h265: bytes) -> bool:
        for nal_type in self._iter_h265_nal_types(h265):
            if nal_type in (32, 33, 34):
                return True
        return False

    def _iter_h265_nal_types(self, h265: bytes):
        start = 0
        while True:
            idx = h265.find(b"\x00\x00\x01", start)
            prefix_len = 3
            if idx < 0:
                idx = h265.find(b"\x00\x00\x00\x01", start)
                prefix_len = 4
            if idx < 0:
                return
            header_idx = idx + prefix_len
            if header_idx < len(h265):
                yield (h265[header_idx] >> 1) & 0x3F
            start = header_idx + 1

    def _put_frame(self, frame: VideoFrame) -> None:
        try:
            self._frame_q.put(frame, timeout=0.1)
        except queue.Full:
            try:
                self._frame_q.get_nowait()
                self._frame_q.put(frame, timeout=0.1)
            except (queue.Empty, queue.Full):
                pass

    def _create_control_socket(self) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("", self.local_control_port))
        except OSError as exc:
            logger.warning(
                "[x69-lg-video] could not bind local UDP port %s (%s); using ephemeral port",
                self.local_control_port,
                exc,
            )
            sock.bind(("", 0))
        sock.settimeout(0.5)
        return sock

    def _send_video_command(self, command: bytes) -> None:
        sock = self._control_sock
        if sock is None:
            return
        try:
            sock.sendto(command, (self.drone_ip, self.control_port))
            if self.debug:
                logger.debug("[x69-lg-video] sent command %s", command.hex(" "))
        except OSError:
            pass

    def _dump_h265_frame(self, h265_frame: bytes) -> None:
        if not self._dump_h265_enabled or self._dump_h265_done:
            return
        now = time.monotonic()
        if self._dump_h265_start is None:
            dump_dir = Path(os.getenv("X69_LG_DUMP_DIR", "dumps_x69"))
            dump_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self._dump_h265_path = dump_dir / f"x69_capture_{stamp}.h265"
            self._dump_h265_file = self._dump_h265_path.open("wb")
            self._dump_h265_start = now
            logger.info("[x69-lg-video] dumping raw H.265 to %s", self._dump_h265_path)

        if now - self._dump_h265_start <= self._dump_h265_seconds:
            try:
                self._dump_h265_file.write(h265_frame)
            except OSError as exc:
                logger.warning("[x69-lg-video] H.265 dump write failed: %s", exc)
                self._close_h265_dump()
            return

        self._close_h265_dump()

    def _close_h265_dump(self) -> None:
        if self._dump_h265_file is None:
            return
        try:
            self._dump_h265_file.close()
        finally:
            self._dump_h265_file = None
            self._dump_h265_done = True
            logger.info("[x69-lg-video] H.265 dump complete: %s", self._dump_h265_path)

    def _keepalive_loop(self) -> None:
        while self._running.is_set():
            time.sleep(1.0)
            if not self._running.is_set():
                break
            self._send_video_command(self.OPEN_STREAM)
            if (not self._decoder_ready) or time.monotonic() - self._last_decoded_jpeg > 2.0:
                self._send_video_command(self.IFRAME_REQUEST)
            self._log_stats_if_due()

    def _log_stats_if_due(self) -> None:
        now = time.monotonic()
        if now - self._last_stats_log < 5.0:
            return
        self._last_stats_log = now
        logger.info(
            "[x69-lg-video] stats packets=%s bad=%s h265=%s jpeg=%s partial_frames=%s decoder_alive=%s",
            self._packets_rx,
            self._bad_packets,
            self._h265_frames,
            self._jpeg_frames,
            len(self._assemblies),
            getattr(self._decoder, "is_alive", lambda: None)(),
        )
