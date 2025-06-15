import socket
from typing import Final, List, Optional

from protocols.base_protocol_adapter import BaseProtocolAdapter
from models.wifi_uav_rc import WifiUavRcModel


class WifiUavRcProtocolAdapter(BaseProtocolAdapter):
    """
    Builds and transmits control packets for the WiFi-UAV family.
    Packet layout derived from reverse-engineered Android app traces.
    """

    DEFAULT_DRONE_IP: Final = "192.168.169.1"
    DEFAULT_PORT:     Final = 8800

    # ──────────────────────────────────────────────────────────
    # Static parts (taken 1:1 from packet dumps)
    # ──────────────────────────────────────────────────────────
    _HEADER         = bytes([0xef, 0x02, 0x7c, 0x00, 0x02, 0x02,
                             0x00, 0x01, 0x02, 0x00, 0x00, 0x00])

    _COUNTER1_SUFFIX = bytes([0x00, 0x00, 0x14, 0x00, 0x66, 0x14])
    _CONTROL_SUFFIX  = bytes(10)                            # 10 × 0x00

    _CHECKSUM_SUFFIX = bytes([0x99]) + bytes(44) + bytes([0x32, 0x4b, 0x14, 0x2d, 0x00, 0x00])

    _COUNTER2_SUFFIX = bytes([
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00,
        0x00, 0x00, 0x14, 0x00, 0x00, 0x00,
        0xff, 0xff, 0xff, 0xff
    ])

    _COUNTER3_SUFFIX = bytes([
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x03, 0x00, 0x00, 0x00, 0x10, 0x00,
        0x00, 0x00
    ])

    # ------------------------------------------------------------------ #
    def __init__(self,
                 drone_ip: str = DEFAULT_DRONE_IP,
                 control_port: int = DEFAULT_PORT,
                 shared_sock: Optional[socket.socket] = None) -> None:
        self.drone_ip = drone_ip
        self.control_port = control_port

        self.sock = shared_sock or socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._is_shared_sock = shared_sock is not None
        self.debug_packets = False
        self._pkt_counter = 0

        # rolling 16-bit counters found in the original protocol
        self._ctr1 = 0x0000
        self._ctr2 = 0x0001
        self._ctr3 = 0x0002

    def set_socket(self, sock: socket.socket) -> None:
        """Use an externally managed socket instead of the internal one."""
        # Don't close the old socket if it was created here
        if self.sock and not self._is_shared_sock:
            self.sock.close()
        
        self.sock = sock
        self._is_shared_sock = True

    def stop(self) -> None:
        """Close the socket if it's not shared."""
        if self.sock and not self._is_shared_sock:
            try:
                self.sock.close()
            except Exception:
                pass # Ignore errors on shutdown

    # ------------------------------------------------------------------ #
    # BaseProtocolAdapter
    # ------------------------------------------------------------------ #
    def build_control_packet(self, drone_model: WifiUavRcModel) -> bytes:  # type: ignore[override]
        # ----- counters -------------------------------------------------
        c1 = self._ctr1.to_bytes(2, "little")
        c2 = self._ctr2.to_bytes(2, "little")
        c3 = self._ctr3.to_bytes(2, "little")

        # advance for next call
        self._ctr1 = (self._ctr1 + 1) & 0xFFFF
        self._ctr2 = (self._ctr2 + 1) & 0xFFFF
        self._ctr3 = (self._ctr3 + 1) & 0xFFFF

        # ----- command / headless --------------------------------------
        if drone_model.takeoff_flag:
            command = 0x01
        elif drone_model.stop_flag:
            command = 0x02
        elif drone_model.land_flag:
            command = 0x02
        elif drone_model.calibration_flag:
            command = 0x04
        else:
            command = 0x00

        headless = 0x03 if drone_model.headless_flag else 0x02

        # ----- controls -------------------------------------------------
        controls: List[int] = [
            int(drone_model.roll)     & 0xFF,
            int(drone_model.pitch)    & 0xFF,
            int(drone_model.throttle) & 0xFF,
            int(drone_model.yaw)      & 0xFF,
            command & 0xFF,
            headless & 0xFF,
        ]

        checksum = 0
        for b in controls:
            checksum ^= b

        # ----- assemble -------------------------------------------------
        pkt = bytearray()
        pkt += self._HEADER
        pkt += c1 + self._COUNTER1_SUFFIX
        pkt += bytes(controls)
        pkt += self._CONTROL_SUFFIX
        pkt.append(checksum)
        pkt += self._CHECKSUM_SUFFIX
        pkt += c2 + self._COUNTER2_SUFFIX
        pkt += c3 + self._COUNTER3_SUFFIX

        # one-shot flags → clear
        drone_model.takeoff_flag = False
        drone_model.land_flag = False
        drone_model.stop_flag = False
        drone_model.calibration_flag = False

        return bytes(pkt)

    def send_control_packet(self, packet: bytes):  # type: ignore[override]
        """
        Transmit one RC packet.
        If the video layer has just torn the shared socket down, the send
        will raise OSError(EBADF).  Swallow it and wait until the receiver
        hands us the fresh socket.
        """
        try:
            self.sock.sendto(packet, (self.drone_ip, self.control_port))
        except OSError:
            # Socket was closed during video-reconnect window.
            # Wait for VideoReceiverService to call set_socket(…) with the
            # new descriptor.  Until then we just skip transmitting.
            return

        if self.debug_packets:
            self._pkt_counter += 1
            print(f"[wifi-uav] #{self._pkt_counter:05d}   "
                  f"{' '.join(f'{b:02x}' for b in packet[:40])} …")

    def toggle_debug(self) -> bool:                # type: ignore[override]
        self.debug_packets = not self.debug_packets
        state = "ON" if self.debug_packets else "OFF"
        print(f"[wifi-uav] debug {state}")
        return self.debug_packets
