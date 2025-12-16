"""
RC Protocol Adapter for Cooingdv drones.

Builds and transmits control packets for drones using cooingdv publisher apps.
Protocol derived from decompiled FlyController.java and verified with test_e88pro.py.

Packet structure (9 bytes total):
  [0]    0x03      - Prefix byte
  [1]    0x66      - Start marker
  [2]    roll      - Roll axis (50-200, center 128)
  [3]    pitch     - Pitch axis (50-200, center 128)
  [4]    throttle  - Throttle axis (50-200, center 128)
  [5]    yaw       - Yaw axis (50-200, center 128)
  [6]    flags     - Command flags (takeoff, land, stop, flip, headless, calibrate)
  [7]    checksum  - XOR of bytes 2-6
  [8]    0x99      - End marker

Heartbeat: Send {0x01, 0x01} every 1 second to keep connection alive.
"""

import socket
import threading
import time
from typing import Final, Optional

from protocols.base_protocol_adapter import BaseProtocolAdapter
from models.cooingdv_rc import CooingdvRcModel


class CooingdvRcProtocolAdapter(BaseProtocolAdapter):
    """
    Protocol adapter for cooingdv drones (RC UFO, KY UFO, E88 Pro).
    
    Handles:
    - Building control packets with proper structure
    - Sending heartbeat packets to maintain connection
    - UDP transmission to drone
    """

    DEFAULT_DRONE_IP: Final = "192.168.1.1"
    DEFAULT_PORT: Final = 7099
    HEARTBEAT_INTERVAL: Final = 1.0  # seconds

    # Packet markers
    PREFIX: Final = 0x03
    START_MARKER: Final = 0x66
    END_MARKER: Final = 0x99

    # Command flag bits
    FLAG_TAKEOFF: Final = 0x01
    FLAG_LAND: Final = 0x02      # Soft landing
    FLAG_STOP: Final = 0x04      # Emergency stop
    FLAG_FLIP: Final = 0x08      # Somersault
    FLAG_HEADLESS: Final = 0x10  # Headless mode
    FLAG_CALIBRATE: Final = 0x80 # Gyro calibration

    def __init__(
        self,
        drone_ip: str = DEFAULT_DRONE_IP,
        control_port: int = DEFAULT_PORT,
    ) -> None:
        self.drone_ip = drone_ip
        self.control_port = control_port

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.debug_packets = False
        self._pkt_counter = 0

        # Heartbeat thread
        self._heartbeat_running = False
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._heartbeat_stop = threading.Event()

        # Start heartbeat automatically
        self.start_heartbeat()

    def start_heartbeat(self) -> None:
        """Start the heartbeat thread to keep connection alive."""
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return

        self._heartbeat_stop.clear()
        self._heartbeat_running = True
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name="CooingdvHeartbeat",
        )
        self._heartbeat_thread.start()

    def stop_heartbeat(self) -> None:
        """Stop the heartbeat thread."""
        self._heartbeat_running = False
        self._heartbeat_stop.set()
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=2.0)
            self._heartbeat_thread = None

    def _heartbeat_loop(self) -> None:
        """Send heartbeat packets every HEARTBEAT_INTERVAL seconds."""
        heartbeat_packet = bytes([0x01, 0x01])
        while self._heartbeat_running and not self._heartbeat_stop.is_set():
            try:
                self.sock.sendto(heartbeat_packet, (self.drone_ip, self.control_port))
                if self.debug_packets:
                    print(f"[cooingdv] heartbeat sent: {heartbeat_packet.hex()}")
            except OSError:
                # Socket may be closed during shutdown
                pass
            self._heartbeat_stop.wait(self.HEARTBEAT_INTERVAL)

    def stop(self) -> None:
        """Clean shutdown of the adapter."""
        self.stop_heartbeat()
        try:
            self.sock.close()
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # BaseProtocolAdapter interface
    # ------------------------------------------------------------------ #
    def build_control_packet(self, drone_model: CooingdvRcModel) -> bytes:
        """
        Build a control packet for the cooingdv protocol.
        
        Packet format (9 bytes):
        [prefix][start][roll][pitch][throttle][yaw][flags][checksum][end]
        """
        pkt = bytearray(9)

        # Markers
        pkt[0] = self.PREFIX
        pkt[1] = self.START_MARKER

        # Control axes - clamp to valid range
        pkt[2] = self._clamp_axis(drone_model.roll)
        pkt[3] = self._clamp_axis(drone_model.pitch)
        pkt[4] = self._clamp_axis(drone_model.throttle)
        pkt[5] = self._clamp_axis(drone_model.yaw)

        # Build command flags
        pkt[6] = self._build_flags(drone_model)

        # Calculate checksum (XOR of bytes 2-6)
        pkt[7] = self._calculate_checksum(pkt[2:7])

        # End marker
        pkt[8] = self.END_MARKER

        # Clear one-shot flags after building packet
        drone_model.takeoff_flag = False
        drone_model.land_flag = False
        drone_model.stop_flag = False
        drone_model.flip_flag = False
        drone_model.calibration_flag = False
        # Note: headless_flag is a toggle state, not cleared

        return bytes(pkt)

    def send_control_packet(self, packet: bytes) -> None:
        """Send a control packet to the drone via UDP."""
        try:
            self.sock.sendto(packet, (self.drone_ip, self.control_port))
        except OSError:
            # Socket may be closed during reconnect
            return

        if self.debug_packets:
            self._pkt_counter += 1
            hex_dump = ' '.join(f'{b:02x}' for b in packet)
            print(f"[cooingdv] #{self._pkt_counter:05d}: {hex_dump}")

            # Decode packet for readability
            if len(packet) >= 9:
                roll, pitch, throttle, yaw = packet[2], packet[3], packet[4], packet[5]
                flags = packet[6]
                print(f"  Controls: R:{roll} P:{pitch} T:{throttle} Y:{yaw}")
                
                # Decode flags
                flag_names = []
                if flags & self.FLAG_TAKEOFF:
                    flag_names.append("TAKEOFF")
                if flags & self.FLAG_LAND:
                    flag_names.append("LAND")
                if flags & self.FLAG_STOP:
                    flag_names.append("STOP")
                if flags & self.FLAG_FLIP:
                    flag_names.append("FLIP")
                if flags & self.FLAG_HEADLESS:
                    flag_names.append("HEADLESS")
                if flags & self.FLAG_CALIBRATE:
                    flag_names.append("CALIBRATE")
                
                if flag_names:
                    print(f"  Flags: {', '.join(flag_names)}")

    def toggle_debug(self) -> bool:
        """Toggle debug packet logging on/off."""
        self.debug_packets = not self.debug_packets
        state = "ON" if self.debug_packets else "OFF"
        print(f"[cooingdv] debug {state}")
        return self.debug_packets

    # ------------------------------------------------------------------ #
    # Helper methods
    # ------------------------------------------------------------------ #
    def _clamp_axis(self, value: float) -> int:
        """Clamp axis value to valid protocol range (0-255)."""
        return max(0, min(255, int(value))) & 0xFF

    def _build_flags(self, model: CooingdvRcModel) -> int:
        """Build the command flags byte from model state."""
        flags = 0

        if model.takeoff_flag:
            flags |= self.FLAG_TAKEOFF
        if model.land_flag:
            flags |= self.FLAG_LAND
        if model.stop_flag:
            flags |= self.FLAG_STOP
        if model.flip_flag:
            flags |= self.FLAG_FLIP
        if model.headless_flag:
            flags |= self.FLAG_HEADLESS
        if model.calibration_flag:
            flags |= self.FLAG_CALIBRATE

        return flags & 0xFF

    def _calculate_checksum(self, data: bytes) -> int:
        """Calculate XOR checksum of the given bytes."""
        checksum = 0
        for b in data:
            checksum ^= b
        return checksum & 0xFF

