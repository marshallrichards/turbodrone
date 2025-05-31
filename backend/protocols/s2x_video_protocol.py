import ipaddress
import socket
from typing import Optional

from models.s2x_video_model import S2xVideoModel
from models.video_frame import VideoFrame
from protocols.base_video_protocol import BaseVideoProtocolAdapter


class S2xVideoProtocolAdapter(BaseVideoProtocolAdapter):
    """Transport + header parser for S2x JPEG stream"""

    SYNC_BYTES = b"\x40\x40"
    EOS_MARKER = b"\x23\x23"
    HEADER_LEN = 8        # S2x packets always use an 8-byte header

    def __init__(
        self,
        drone_ip: str = "172.16.10.1",
        control_port: int = 8080,
        video_port: int = 8888,
    ):
        super().__init__(drone_ip, control_port, video_port)
        self.model = S2xVideoModel()
        self.local_ip = self._discover_local_ip()

    # ────────── BaseVideoProtocolAdapter ────────── #
    def send_start_command(self) -> None:
        payload = b"\x08" + ipaddress.IPv4Address(self.local_ip).packed
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.sendto(payload, (self.drone_ip, self.control_port))
        print(f"[video] Start command sent ({payload.hex(' ')})")

    def create_receiver_socket(self) -> socket.socket:
        """UDP socket bound to the drone's video port."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", self.video_port))
        sock.settimeout(1.0)
        return sock

    def handle_payload(self, payload: bytes) -> Optional[VideoFrame]:
        """
        1. Validate & strip the fixed 8-byte S2x header
        2. Forward the slice payload to the model
        """
        if len(payload) <= self.HEADER_LEN or payload[:2] != self.SYNC_BYTES:
            return None

        frame_id     = payload[2]
        slice_id_raw = payload[5]

        body = payload[self.HEADER_LEN:]

        # strip optional "##" trailer
        if body.endswith(self.EOS_MARKER):
            body = body[:-len(self.EOS_MARKER)]

        return self.model.ingest_chunk(
            stream_id=frame_id,
            chunk_id=slice_id_raw,
            payload=body,
        )

    # ────────── helpers ────────── #
    def _discover_local_ip(self) -> str:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((self.drone_ip, 1))
            return s.getsockname()[0]
        finally:
            s.close()
