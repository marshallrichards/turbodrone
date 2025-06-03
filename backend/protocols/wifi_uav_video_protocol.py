import socket
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
    ):
        super().__init__(drone_ip, control_port, video_port)

        self._sock = self._create_duplex_socket()

        # Pre-built JPEG header (SOI + quant tables + SOF0 + …)
        self._jpeg_header = generate_jpeg_headers(jpeg_width, jpeg_height, components)

        # State for the current frame being assembled
        # If I send 0 it sends 1, starting with 1 is more reliable.
        self._current_fid: int = 1
        self._fragments: Dict[int, bytes] = {}     # frag_id -> payload

        # Kick-off the stream and ask for frame #0
        self.send_start_command()
        self._send_frame_request(self._current_fid)

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
        print("needing to handle payload")
        if len(payload) < 56 or payload[1] != 0x01:
            return None

        frame_id = int.from_bytes(payload[16:18], "little")

        # Only accept the frame we explicitly requested.
        if frame_id != self._current_fid:
            print("frame_id != self._current_fid")
            print(frame_id)
            return None

        frag_id = int.from_bytes(payload[32:34], "little")
        jpeg_slice = payload[56:]

        # Store if not seen before
        self._fragments.setdefault(frag_id, jpeg_slice)

        is_last_fragment = payload[2] != 0x38
        if not is_last_fragment:
            return None

        print("we have the last fragment; putting stuff together")
        # We have the last fragment – stitch everything together
        ordered = [self._fragments[i] for i in sorted(self._fragments)]
        jpeg_bytes = self._jpeg_header + b"".join(ordered) + EOI
        frame = VideoFrame(frame_id=frame_id, data=jpeg_bytes)

        # ------------------------------------------------------------------
        # Prepare for next frame (the drone sends N+1 after we request N)
        # ------------------------------------------------------------------
        self._fragments.clear()

        # Ask for *this* frame-id; the drone will answer with frame-id + 1
        print(f"sending frame request for frame: {frame_id}")
        time.sleep(0.01)
        self._send_frame_request(frame_id)

        # Expect the next frame in the upcoming packets
        self._current_fid = (frame_id + 1) & 0xFFFF

        return frame

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    def _send_frame_request(self, frame_id: int) -> None:
        lo = frame_id & 0xFF
        hi = (frame_id >> 8) & 0xFF

        rqst_a = bytearray(REQUEST_A)
        rqst_a[12] = lo
        rqst_a[13] = hi

        rqst_b = bytearray(REQUEST_B)
        for base in (12, 88, 107):       # three little-endian copies
            rqst_b[base]     = lo
            rqst_b[base + 1] = hi

        self._sock.sendto(rqst_a, (self.drone_ip, self.control_port))
        self._sock.sendto(rqst_b, (self.drone_ip, self.control_port))

    def _create_duplex_socket(self) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", 0))          # let OS choose a free local port
        sock.settimeout(1.0)
        return sock

