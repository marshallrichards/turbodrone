import socket
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

    FRAME_TIMEOUT = 0.15          # 150 ms without a full frame → retry
    MAX_RETRIES = 1              # after this we skip the frame
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

        # Kick-off the stream and ask for frame #0
        self.send_start_command()
        self._send_frame_request(self._current_fid)

        # Watchdog
        self._running = True
        self._watchdog = threading.Thread(
            target=self._watchdog_loop, daemon=True
        )
        self._watchdog.start()

        self._retry_cnt       = 0          # retries for *current* frame
        self._had_retry       = False      # did we already retry this frame?
        self.retry_attempts   = 0          # global counter
        self.retry_successes  = 0          # global counter

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
        return sock

    # ------------------------------------------------------------------ #
    # watchdog
    # ------------------------------------------------------------------ #
    def _watchdog_loop(self) -> None:
        """
        Runs in a daemon thread.  If the current frame doesn't finish within
        FRAME_TIMEOUT seconds we resend the request for that frame.
        """
        while self._running:
            time.sleep(self.WATCHDOG_SLEEP)

            now = time.time()
            if now - self._last_req_ts < self.FRAME_TIMEOUT:
                continue                    # still waiting → nothing to do

            # ----------------------------------------------------------
            # retry or drop?
            # ----------------------------------------------------------
            if self._retry_cnt < self.MAX_RETRIES:
                # try again for the SAME frame
                self._dbg(f"⚠ timeout FID {self._current_fid:04x} – retry "
                          f"({self._retry_cnt +1}/{self.MAX_RETRIES})")
                self._send_frame_request((self._current_fid - 1) & 0xFFFF)
                self._retry_cnt += 1
                self.retry_attempts += 1
                self._had_retry = True
            else:
                # give up – skip this frame just like the PoC script
                self.frames_dropped += 1
                self._dbg(f"✗ drop   FID {self._current_fid:04x} "
                          f"(after {self._retry_cnt} retries)  "
                          f"OK:{self.frames_ok}  DROP:{self.frames_dropped}")

                self._fragments.clear()
                self._retry_cnt  = 0
                self._current_fid = (self._current_fid + 1) & 0xFFFF

                # Ask for the *new* previous frame so the drone sends
                # the next one (same convention as before).
                self._send_frame_request((self._current_fid - 1) & 0xFFFF)
                self._had_retry = False

    def stop(self) -> None:
        """Call this from outside when the program shuts down."""
        self._running = False
        try:
            self._sock.close()
        except Exception:
            pass

        self._dbg(
            f"[stats] ok:{self.frames_ok}  dropped:{self.frames_dropped}  "
            f"retry_att:{self.retry_attempts}  retry_suc:{self.retry_successes}"
        )

