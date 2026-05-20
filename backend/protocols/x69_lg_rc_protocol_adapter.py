from __future__ import annotations

import logging
import socket
import threading
from typing import Final

from models.x69_lg_rc import X69LgRcModel
from protocols.base_protocol_adapter import BaseProtocolAdapter

logger = logging.getLogger(__name__)


class X69LgRcProtocolAdapter(BaseProtocolAdapter):
    """Send X69/LG optical-flow RC packets."""

    DEFAULT_DRONE_IP: Final = "172.16.11.1"
    DEFAULT_CONTROL_PORT: Final = 23458
    DEFAULT_LOCAL_PORT: Final = 0

    START_MARKER: Final = 0x66
    LENGTH: Final = 0x14
    END_MARKER: Final = 0x99
    CONTROL_WRAPPER_MAGIC: Final = b"\xca\x47\xd5\x00"
    D1_KEEPALIVE: Final = b"\xca\x47\xd1\x00\x00\x00\x00\x00"

    FLAG_TAKEOFF: Final = 0x01
    FLAG_EMERGENCY_STOP: Final = 0x02
    FLAG_CALIBRATE: Final = 0x04
    FLAG_FLIP: Final = 0x08
    FLAG_LAND: Final = 0x80

    FLAG_TILT_UP: Final = 0x08
    FLAG_TILT_DOWN: Final = 0x10

    def __init__(
        self,
        drone_ip: str = DEFAULT_DRONE_IP,
        control_port: int = DEFAULT_CONTROL_PORT,
        *,
        local_port: int = DEFAULT_LOCAL_PORT,
    ) -> None:
        self.drone_ip = drone_ip
        self.control_port = control_port
        self.local_port = local_port
        self.debug_packets = False
        self.packet_counter = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._bind_socket(local_port)
        self._keepalive_stop = threading.Event()
        self._keepalive_thread = threading.Thread(
            target=self._keepalive_loop,
            daemon=True,
            name="X69LgD1Keepalive",
        )
        self._keepalive_thread.start()
        self.speed_scale_by_index = {
            0: 0.55,
            1: 0.75,
            2: 1.0,
        }

    def build_control_packet(self, drone_model: X69LgRcModel) -> bytes:
        payload = self.build_control_payload(drone_model)
        return self._wrap_control_payload(payload)

    def build_control_payload(self, drone_model: X69LgRcModel) -> bytes:
        packet = bytearray(20)
        packet[0] = self.START_MARKER
        packet[1] = self.LENGTH
        packet[2] = self._axis(self._scale_axis(drone_model.roll, drone_model))
        packet[3] = self._axis(self._scale_axis(drone_model.pitch, drone_model))
        packet[4] = self._axis(drone_model.throttle)
        packet[5] = self._axis(drone_model.yaw)
        packet[6] = self._build_primary_flags(drone_model)
        packet[7] = self._build_secondary_flags(drone_model)
        packet[18] = self._xor(packet[2:18])
        packet[19] = self.END_MARKER
        self._clear_one_shot_flags(drone_model)
        return bytes(packet)

    def send_control_packet(self, packet: bytes) -> None:
        try:
            self.sock.sendto(packet, (self.drone_ip, self.control_port))
        except OSError:
            return

        if self.debug_packets:
            self.packet_counter += 1
            logger.debug("[x69-lg-rc] #%05d %s", self.packet_counter, packet.hex(" "))

    def stop(self) -> None:
        self._keepalive_stop.set()
        if self._keepalive_thread.is_alive():
            self._keepalive_thread.join(timeout=1.0)
        try:
            self.sock.close()
        except OSError:
            pass

    def toggle_debug(self) -> bool:
        self.debug_packets = not self.debug_packets
        logger.info("[x69-lg-rc] debug %s", "ON" if self.debug_packets else "OFF")
        return self.debug_packets

    def _bind_socket(self, local_port: int) -> None:
        if local_port <= 0:
            return
        try:
            self.sock.bind(("", local_port))
        except OSError as exc:
            logger.warning(
                "[x69-lg-rc] could not bind local UDP port %s (%s); using ephemeral port",
                local_port,
                exc,
            )
            self.sock.bind(("", 0))

    def _wrap_control_payload(self, payload: bytes) -> bytes:
        return self.CONTROL_WRAPPER_MAGIC + len(payload).to_bytes(4, "little") + payload

    def _keepalive_loop(self) -> None:
        while not self._keepalive_stop.wait(1.0):
            try:
                self.sock.sendto(self.D1_KEEPALIVE, (self.drone_ip, self.control_port))
            except OSError:
                return

    def _build_primary_flags(self, model: X69LgRcModel) -> int:
        flags = 0
        if model.takeoff_flag:
            flags |= self.FLAG_TAKEOFF
        if model.stop_flag:
            flags |= self.FLAG_EMERGENCY_STOP
        if model.calibration_flag:
            flags |= self.FLAG_CALIBRATE
        if model.flip_flag:
            flags |= self.FLAG_FLIP
        if model.land_flag:
            flags |= self.FLAG_LAND
        return flags & 0xFF

    def _build_secondary_flags(self, model: X69LgRcModel) -> int:
        if model.camera_tilt_state == 2:
            return self.FLAG_TILT_UP
        if model.camera_tilt_state == 1:
            return self.FLAG_TILT_DOWN
        return 0

    def _clear_one_shot_flags(self, model: X69LgRcModel) -> None:
        model.takeoff_flag = False
        model.land_flag = False
        model.stop_flag = False
        model.calibration_flag = False
        model.flip_flag = False

    def _scale_axis(self, value: float, model: X69LgRcModel) -> float:
        scale = self.speed_scale_by_index.get(getattr(model, "speed_index", 1), 0.5)
        if scale >= 1.0:
            return value
        return model.center_value + ((value - model.center_value) * scale)

    def _axis(self, value: float) -> int:
        return max(0, min(255, int(value))) & 0xFF

    def _xor(self, values: bytes | bytearray) -> int:
        checksum = 0
        for value in values:
            checksum ^= value
        return checksum & 0xFF
