import socket
import queue
import threading
import time
from typing import Dict, Optional

from models.video_frame import VideoFrame
from protocols.base_video_protocol import BaseVideoProtocolAdapter
from utils.wifi_uav_packets import START_STREAM, REQUEST_A, REQUEST_B
from utils.wifi_uav_jpeg import generate_jpeg_headers, EOI


class WifiUavVideoProtocolAdapter(BaseVideoProtocolAdapter):
    """
    Protocol adapter for the inexpensive "WiFi UAV" drones.

    Differences to the S2x family:
      • A single duplex UDP socket is used for tx/rx.
      • The drone stops streaming unless it receives two custom
        *frame-request* packets (REQUEST_A / REQUEST_B) for every JPEG.
      • Each UDP datagram has a 56-byte proprietary header that must be
        stripped; the JPEG SOI/APPx headers are completely absent and are
        generated on the client.
    """

    DEFAULT_DRONE_IP = "192.168.169.1"

    REQUEST_A_OFFSETS = (12, 13)          # two-byte LE frame counter
    REQUEST_B_OFFSETS = (12, 13, 88, 89, 107, 108)

    FRAME_TIMEOUT = 0.08          # 80 ms without a full frame → retry sooner
    MAX_RETRIES = 3              # allow one more retry for first-frame reliability
    WATCHDOG_SLEEP = 0.05          # 50 ms between watchdog checks

    # ------------------------------------------------------------------ #
    # life-cycle helpers
    # ------------------------------------------------------------------ #
    def __init__(
        self,
        drone_ip: str = DEFAULT_DRONE_IP,
        control_port: int = 8800,
        video_port: int = 8800,
        jpeg_width: int = 640,
        jpeg_height: int = 360,
        components: int = 3,
        *,
        debug: bool = False,
    ):
        super().__init__(drone_ip, control_port, video_port)

        self.debug = debug
        self._dbg = (lambda *a, **k: print(*a, **k)) if debug else (lambda *a, **k: None)
        self._sock_lock = threading.Lock()

        self._sock = self._create_duplex_socket()

        # Pre-built JPEG header (SOI + quant tables + SOF0 + …)
        self._jpeg_header = generate_jpeg_headers(jpeg_width, jpeg_height, components)

        # State for the current frame being assembled
        # If I send 0 it sends 1, starting with 1 is more reliable.
        self._current_fid: int = 1
        self._fragments: Dict[int, bytes] = {}     # frag_id -> payload
        self._last_req_ts = time.time()
        self._last_rx_ts = time.time()

        # Stats
        self.frames_ok = 0
        self.frames_dropped = 0
        self._dbg(f"[init] adapter ready (control:{control_port}  video:{video_port})")

        # Kick-off the stream and ask for the first frame
        self.send_start_command()
        self._send_frame_request(0) # Request frame 0 to get frame 1
        # During warmup, resend until we see the first frame
        self._first_frame = True
        self._warmup_thread = threading.Thread(target=self._warmup_loop, daemon=True, name="Warmup")
        self._warmup_thread.start()

        # Watchdog for per-frame timeouts
        self._running = True
        self._watchdog = threading.Thread(
            target=self._watchdog_loop, daemon=True, name="FrameWatchdog"
        )
        self._watchdog.start()

        self._retry_cnt       = 0          # retries for *current* frame
        self._had_retry       = False      # did we already retry this frame?
        self.retry_attempts   = 0          # global counter
        self.retry_successes  = 0          # global counter

        self._dbg(f"Main UDP socket created, listening on *:{self._sock.getsockname()[1]}")

    # ------------------------------------------------------------------ #
    # disable keep-alive – one start command is enough for this drone
    # ------------------------------------------------------------------ #
    def start_keepalive(self, interval: float = 1.0) -> None:  # type: ignore[override]
        return

    def stop_keepalive(self) -> None:  # type: ignore[override]
        return

    # ------------------------------------------------------------------ #
    # Base-class hooks
    # ------------------------------------------------------------------ #
    def create_receiver_socket(self) -> socket.socket:
        return self._sock

    def send_start_command(self) -> None:
        self._sock.sendto(START_STREAM, (self.drone_ip, self.control_port))
        print("[wifi-uav] START_STREAM sent")

    def handle_payload(self, payload: bytes) -> Optional[VideoFrame]:
        """
        Collect slices belonging to the requested frame.

        Packet layout (summarised):
        byte  1 : must be 0x01 for video
        bytes 16–17 : little-endian frame counter
        bytes 32–33 : little-endian fragment counter
        byte  2 : 0x38 for continuation, ≠0x38 for last fragment
        bytes 56+ : JPEG payload
        """
        if len(payload) < 56 or payload[1] != 0x01:
            return None

        self._last_rx_ts = time.time()
        self._retry_cnt = 0

        frame_id = int.from_bytes(payload[16:18], "little")

        # resynchronise if the drone skipped ahead
        if frame_id != self._current_fid:
            self.frames_dropped += 1
            self._dbg(f"⚠ skip   expected {self._current_fid:04x} "
                      f"got {frame_id:04x}")
            self._fragments.clear()
            self._current_fid = frame_id

        frag_id = int.from_bytes(payload[32:34], "little")
        self._fragments.setdefault(frag_id, payload[56:])
        self._dbg(f"← FID:{frame_id:04x} FRAG:{frag_id:04x}")

        # not the last fragment? → wait for more
        if payload[2] == 0x38:
            return None

        # last fragment – assemble JPEG
        ordered = [self._fragments[i] for i in sorted(self._fragments)]
        jpeg = self._jpeg_header + b"".join(ordered) + EOI
        frame = VideoFrame(frame_id=frame_id, data=jpeg)

        self.frames_ok += 1

        # ── was this frame finished thanks to a retry? ───────────
        if self._had_retry:
            self.retry_successes += 1
            self._dbg(f"✓ recovery! {frame_id:04x}  "
                      f"SUC:{self.retry_successes}  "
                      f"ATT:{self.retry_attempts}")
            self._had_retry = False
        # ──────────────────────────────────────────────────────────────

        self._dbg(f"✓ {frame_id:04x} ({len(self._fragments)} frags)  "
                  f"OK:{self.frames_ok}  DROP:{self.frames_dropped}")

        # prepare next iteration
        self._fragments.clear()
        self._send_frame_request(frame_id)            # ask for next
        self._current_fid = (frame_id + 1) & 0xFFFF
        self._last_rx_ts = self._last_req_ts = time.time()

        return frame

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    def _warmup_loop(self) -> None:
        """During warmup, periodically resend START_STREAM + frame request
        until the first frame is observed, then exit."""
        while getattr(self, "_first_frame", False):
            try:
                self.send_start_command()
                # Ask for the previous frame id; the drone will respond with next
                self._send_frame_request((self._current_fid - 1) & 0xFFFF)
            except Exception:
                pass
            time.sleep(0.2)
    def _send_frame_request(self, frame_id: int) -> None:
        lo, hi = frame_id & 0xFF, (frame_id >> 8) & 0xFF

        rqst_a = bytearray(REQUEST_A)
        rqst_a[12], rqst_a[13] = lo, hi

        rqst_b = bytearray(REQUEST_B)
        for base in (12, 88, 107):
            rqst_b[base] = lo
            rqst_b[base + 1] = hi

        self._sock.sendto(rqst_a, (self.drone_ip, self.control_port))
        self._sock.sendto(rqst_b, (self.drone_ip, self.control_port))
        self._last_req_ts = time.time()
        self._dbg(f"→ REQ {frame_id:04x}")

    def _create_duplex_socket(self) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", 0))          # let OS choose a free local port
        sock.settimeout(1.0)
        self._dbg(f"Main UDP socket created, listening on *:{sock.getsockname()[1]}")
        return sock

    def get_receiver_socket(self) -> socket.socket:
        """Returns the main socket for the receiver thread to use."""
        with self._sock_lock:
            return self._sock

    def set_rc_adapter(self, rc_adapter) -> None:
        """Provide the RC adapter with our shared UDP socket."""
        try:
            rc_adapter.set_socket(self._sock)
            self._dbg("[wifi-uav] RC adapter socket shared")
        except Exception:
            # If the RC adapter is not ready or doesn't support socket injection,
            # ignore and continue – the receiver loop will still function.
            pass

    # ------------------------------------------------------------------ #
    # Receiver thread API expected by VideoReceiverService
    # ------------------------------------------------------------------ #
    def start(self) -> None:
        if hasattr(self, "_rx_thread") and self._rx_thread and self._rx_thread.is_alive():
            return
        # Small frame buffer; upstream will drop if slow
        self._frame_q: "queue.Queue[VideoFrame]" = queue.Queue(maxsize=2)
        self._pkt_buffer: list[bytes] = []

        def _rx_loop() -> None:
            sock = self.get_receiver_socket()
            while self._running:
                try:
                    payload = self.recv_from_socket(sock)
                    if not payload:
                        continue
                    # Collect raw packet bytes for optional dumping
                    self._pkt_buffer.append(payload)
                    # Try to assemble a frame
                    frame = self.handle_payload(payload)
                    if frame is not None:
                        try:
                            self._frame_q.put(frame, timeout=0.2)
                        except queue.Full:
                            # Drop frame if consumer is slow
                            pass
                except OSError:
                    # Socket likely closed during stop(); exit loop
                    break
                except Exception as e:
                    self._dbg(f"[wifi-uav] rx error: {e}")
                    continue

        self._rx_thread = threading.Thread(target=_rx_loop, daemon=True, name="WifiUavVideoRx")
        self._rx_thread.start()

    def is_running(self) -> bool:
        return bool(self._running and getattr(self, "_rx_thread", None) and self._rx_thread.is_alive())

    def get_frame(self, timeout: float = 1.0) -> Optional[VideoFrame]:
        try:
            frame = self._frame_q.get(timeout=timeout)
            # mark warmup complete on first delivered frame
            if getattr(self, "_first_frame", False):
                self._first_frame = False
            return frame
        except queue.Empty:
            return None

    def get_packets(self) -> list[bytes]:
        packets = getattr(self, "_pkt_buffer", [])
        self._pkt_buffer = []
        return packets

    # ------------------------------------------------------------------ #
    # watchdog
    # ------------------------------------------------------------------ #
    def _watchdog_loop(self) -> None:
        """
        Runs in a daemon thread. If the current frame doesn't finish within
        FRAME_TIMEOUT seconds, resend the request for that frame.
        Link-level reconnection is handled by the VideoReceiverService.
        """
        self._dbg("Watchdog started for per-frame timeouts.")
        while self._running:
            time.sleep(self.WATCHDOG_SLEEP)
            now = time.time()

            if now - self._last_req_ts < self.FRAME_TIMEOUT:
                continue                    # still waiting → nothing to do

            # ----------------------------------------------------------
            # retry or drop?
            # ----------------------------------------------------------
            if self._retry_cnt < self.MAX_RETRIES:
                self._dbg(f"⚠ timeout FID {self._current_fid:04x} – retry "
                          f"({self._retry_cnt +1}/{self.MAX_RETRIES})")
                self._send_frame_request((self._current_fid - 1) & 0xFFFF)
                self._retry_cnt += 1
                self.retry_attempts += 1
                self._had_retry = True
            else:
                self.frames_dropped += 1
                self._dbg(f"✗ drop   FID {self._current_fid:04x} "
                          f"(after {self._retry_cnt} retries)  "
                          f"OK:{self.frames_ok}  DROP:{self.frames_dropped}")

                self._fragments.clear()
                self._retry_cnt  = 0
                self._current_fid = (self._current_fid + 1) & 0xFFFF
                self._send_frame_request((self._current_fid - 1) & 0xFFFF)
                self._had_retry = False

    def stop(self) -> None:
        """Gracefully shut down the adapter and its threads."""
        self._dbg(f"Stopping protocol adapter instance...")
        self._running = False
        try:
            if self._watchdog and self._watchdog.is_alive():
                self._watchdog.join(timeout=0.5)
            if hasattr(self, "_rx_thread") and self._rx_thread and self._rx_thread.is_alive():
                self._rx_thread.join(timeout=0.5)
            self._sock.close()
        except Exception as e:
            self._dbg(f"Ignoring error during shutdown: {e}")

        self._dbg(
            f"[stats] ok:{self.frames_ok}  dropped:{self.frames_dropped}  "
            f"retry_att:{self.retry_attempts}  retry_suc:{self.retry_successes}"
        )

