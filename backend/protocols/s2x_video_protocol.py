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
    HEADER_LEN = 8

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
        1. Validate & strip S2x header (6- or 8-byte variant)
        2. Forward slice to the model
        """
        if len(payload) <= self.HEADER_LEN or payload[:2] != self.SYNC_BYTES:
            return None

        fid     = payload[2]
        sid_raw = payload[5]
        is_last = bool(sid_raw & 0x10)

        # dynamic header length
        hdr_len = 8 if len(payload) >= 8 and payload[6:8] == b"\x78\x05" else 6
        body = payload[hdr_len:]

        # strip optional "##" trailer
        if body.endswith(self.EOS_MARKER):
            body = body[:-len(self.EOS_MARKER)]

        # NOTE: keep the *raw* SID byte to preserve contiguity
        return self.model.ingest_chunk(
            stream_id=fid,
            chunk_id=sid_raw,
            payload=body,
            is_last=is_last,
        )

    # ────────── helpers ────────── #
    def _discover_local_ip(self) -> str:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((self.drone_ip, 1))
            return s.getsockname()[0]
        finally:
            s.close()
