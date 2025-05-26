import ipaddress
import socket
import time
from protocols.base_video_protocol import BaseVideoProtocolAdapter

class S2xVideoProtocolAdapter(BaseVideoProtocolAdapter):
    """Protocol adapter for S2x drone video feed"""
    
    # Constants
    SYNC_BYTES = b"\x40\x40"
    SOI_MARKER = b"\xFF\xD8"
    EOI_MARKER = b"\xFF\xD9"
    EOS_MARKER = b"\x23\x23"
    HEADER_LEN = 8
    
    def __init__(self, drone_ip="172.16.10.1", control_port=8080, video_port=8888):
        super().__init__(drone_ip, control_port, video_port)
        self.local_ip = self._discover_local_ip()
    
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
