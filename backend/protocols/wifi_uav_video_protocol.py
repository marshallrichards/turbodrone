import socket
import threading
from typing import Optional

from models.video_frame import VideoFrame
from models.wifi_uav_video_model import WifiUavVideoModel
from protocols.base_video_protocol import BaseVideoProtocolAdapter
from utils.wifi_uav_packets import START_STREAM, REQUEST_A, REQUEST_B
from utils.wifi_uav_jpeg import EOI  # only imported so linting sees the module


class WifiUavVideoProtocolAdapter(BaseVideoProtocolAdapter):
    """
    Transport + parser for the "WiFi UAV" Android-app drones.

    Differences to the already supported S2x stream:
      • The drone needs two custom *frame-request* packets (REQUEST_A/B)
        for every single JPEG frame.  Without them the stream stops.
      • Each UDP packet has a 56-byte header and no JPEG headers at all
        – those are added by the VideoModel.
    """

    DEFAULT_DRONE_IP = "192.168.169.1"

    REQUEST_A_OFFSETS = (12, 13)  # two bytes (little-endian)
    REQUEST_B_OFFSETS = (
        12,
        13,
        88,
        89,
        107,
        108,
    )

    count = 0

    def __init__(
        self,
        drone_ip: str = DEFAULT_DRONE_IP,
        control_port: int = 8800,
        video_port: int = 8800,
    ):
        super().__init__(drone_ip, control_port, video_port)

        self.model = WifiUavVideoModel()

        # The single duplex socket (bind once → use for tx & rx)
        self._sock = self._create_duplex_socket()

        # Start the stream
        self.send_start_command()

        # Ask for the first frame
        self._next_frame_id = 0
        self._send_frame_request(self._next_frame_id)
        print("when does init get called?")
        self.count = 0

    # ------------------------------------------------------------------ #
    # Base-class hooks
    # ------------------------------------------------------------------ #
    def create_receiver_socket(self) -> socket.socket:
        # just hand the already created socket to the caller
        return self._sock

    def send_start_command(self) -> None:
        print("Sending start command wifi uav")
        if (self.count == 0):
          self._sock.sendto(START_STREAM, (self.drone_ip, self.control_port))
        else:
          print("Skipping start command wifi uav; already sent.")
        self.count += 1

    def handle_payload(self, payload: bytes) -> Optional[VideoFrame]:
        """
        • Forward packet to the model
        • When we get a complete frame -> request next one immediately
        """
        frame = self.model.ingest_chunk(payload)
        if frame:
            self._next_frame_id = (frame.frame_id + 1) & 0xFFFF
            self._send_frame_request(self._next_frame_id)
            return frame
        return None

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    def _send_frame_request(self, frame_id: int) -> None:
        """
        Build and send REQUEST_A and REQUEST_B with the two-byte, LE
        frame counter written to their multiple required positions.
        """
        frame_bytes = frame_id.to_bytes(2, "little")

        rqst_a = bytearray(REQUEST_A)
        rqst_a[self.REQUEST_A_OFFSETS[0]] = frame_bytes[0]
        rqst_a[self.REQUEST_A_OFFSETS[1]] = frame_bytes[1]

        rqst_b = bytearray(REQUEST_B)
        for off in self.REQUEST_B_OFFSETS:
            rqst_b[off] = frame_bytes[0] if off % 2 == 0 else frame_bytes[1]

        self._sock.sendto(rqst_a, (self.drone_ip, self.control_port))
        self._sock.sendto(rqst_b, (self.drone_ip, self.control_port))

    def _create_duplex_socket(self) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", 0))            # let the OS pick a free local port
        sock.settimeout(1.0)
        return sock

    def _discover_local_ip(self) -> str:
        """
        Same trick used elsewhere: connect() without sending to figure out
        which interface would reach the drone.
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((self.drone_ip, 1))
            return s.getsockname()[0]
        finally:
            s.close()

