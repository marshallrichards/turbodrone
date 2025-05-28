import ipaddress
import socket
import time
from typing import Optional, Dict

from models.video_frame import VideoFrame
from protocols.base_video_protocol import BaseVideoProtocolAdapter


class S2xVideoProtocolAdapter(BaseVideoProtocolAdapter):
    """Protocol adapter for S2x drone video feed"""

    # ─── constants ──────────────────────────────────────────
    SYNC_BYTES  = b"\x40\x40"
    SOI_MARKER  = b"\xFF\xD8"
    EOI_MARKER  = b"\xFF\xD9"
    EOS_MARKER  = b"\x23\x23"
    HEADER_LEN  = 8

    def __init__(self, drone_ip="172.16.10.1", control_port=8080, video_port=8888):
        super().__init__(drone_ip, control_port, video_port)
        self.local_ip           = self._discover_local_ip()

        # per-stream assembly state (only used by receiver thread)
        self._current_frame_id  = None
        self._fragments: Dict[int, bytes] = {}

    # ─── public API expected by BaseVideoProtocolAdapter ───
    # (send_start_command, create_receiver_socket, is_valid_packet,
    #  parse_packet) remain unchanged …

    # NEW: re-assembly front door
    def handle_datagram(self, packet: bytes) -> Optional[VideoFrame]:
        """
        Called once per UDP datagram.
        Returns a VideoFrame when a frame is finished,
        or None if more slices are still missing.
        """
        if not self.is_valid_packet(packet):
            return None

        meta = self.parse_packet(packet)
        if not meta:
            return None

        fid     = meta["frame_id"]
        sid     = meta["slice_id"]
        payload = meta["payload"]

        # start a new frame?
        if self._current_frame_id is None:
            self._reset_frame(fid)
        elif fid != self._current_frame_id:
            frame = self._assemble_current_frame()
            self._reset_frame(fid)
            if frame:
                return frame

        # stash this slice (ignore dupes)
        self._fragments.setdefault(sid, payload)

        # some drones set the "last slice" bit
        if meta["is_last_slice"]:
            return self._assemble_current_frame()

        return None            # not done yet

    # ─── helpers (private) ─────────────────────────────────
    def _reset_frame(self, new_fid):
        self._current_frame_id = new_fid
        self._fragments.clear()

    def _assemble_current_frame(self) -> Optional[VideoFrame]:
        if not self._fragments:
            return None

        keys = sorted(self._fragments)
        complete = len(keys) == keys[-1] - keys[0] + 1
        if not complete:
            print(f"[s2x-asm] Dropping frame {self._current_frame_id}, "
                  f"missing { (keys[-1]-keys[0]+1) - len(keys)} slices")
            return None

        data = b"".join(self._fragments[i] for i in keys)

        # extract the actual JPEG
        start = data.find(self.SOI_MARKER)
        end   = data.rfind(self.EOI_MARKER)
        if start < 0 or end < 0 or end <= start:
            print(f"[s2x-asm] JPEG markers not found on frame {self._current_frame_id}")
            return None

        jpeg = data[start : end + len(self.EOI_MARKER)]
        print(f"[s2x-asm] Frame {self._current_frame_id} OK "
              f"({len(jpeg)} bytes, {len(keys)} slices)")

        return VideoFrame(self._current_frame_id, jpeg, "jpeg")

    def _discover_local_ip(self):
        """Discover the IP address that can reach the drone"""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((self.drone_ip, 1))
            return s.getsockname()[0]
        finally:
            s.close()
    
    def send_start_command(self):
        """Send the 5-byte start video command"""
        payload = b"\x08" + ipaddress.IPv4Address(self.local_ip).packed
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.sendto(payload, (self.drone_ip, self.control_port))
        print(f"[video] Start command sent ({payload.hex(' ')})")
    
    def create_receiver_socket(self):
        """Create and configure the UDP socket for receiving video"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", self.video_port))
        sock.settimeout(1.0)
        return sock
    
    def is_valid_packet(self, packet):
        """Check if packet has valid S2x header"""
        return len(packet) > self.HEADER_LEN and packet[:2] == self.SYNC_BYTES
    
    def parse_packet(self, packet):
        """Parse S2x video packet and extract metadata and payload"""
        if not self.is_valid_packet(packet):
            return None
            
        frame_id = packet[2]
        slice_id = packet[5]
        payload = packet[8:]
    
        # Strip end-of-slice marker
        if payload.endswith(self.EOS_MARKER):
            payload = payload[:-len(self.EOS_MARKER)]
            
        return {
            "frame_id": frame_id,
            "slice_id": slice_id,
            "payload": payload,
            "is_last_slice": bool(slice_id & 0x10)
        } 
