"""RC protocol adapter for WiFi_CAM native UDP drones."""

from __future__ import annotations

import logging
import socket
from typing import Final, Literal

from models.wifi_cam_rc import WifiCamRcModel
from protocols.base_protocol_adapter import BaseProtocolAdapter

logger = logging.getLogger(__name__)

CommandMode = Literal["auto", "short", "extended"]


class WifiCamRcProtocolAdapter(BaseProtocolAdapter):
    """Send raw WiFi_CAM stick packets to the native command socket."""

    DEFAULT_DRONE_IP: Final = "192.168.4.153"
    DEFAULT_COMMAND_PORT: Final = 8090

    START_MARKER: Final = 0x66
    END_MARKER: Final = 0x99
    EXTENDED_LENGTH: Final = 0x14

    FLAG_TAKEOFF: Final = 0x01
    FLAG_LAND: Final = 0x02
    FLAG_EMERGENCY: Final = 0x04
    FLAG_ROTATE: Final = 0x08
    FLAG_HEADLESS: Final = 0x10
    FLAG_CALIBRATE: Final = 0x80

    EXT_FLAG_TAKEOFF_OR_LAND: Final = 0x01
    EXT_FLAG_EMERGENCY: Final = 0x02
    EXT_FLAG_CALIBRATE: Final = 0x04
    EXT_FLAG_ROTATE: Final = 0x08
    EXT_FLAG_HEADLESS: Final = 0x01
    EXT_FLAG_ALTITUDE_HOLD: Final = 0x02

    def __init__(
        self,
        drone_ip: str = DEFAULT_DRONE_IP,
        command_port: int = DEFAULT_COMMAND_PORT,
        *,
        command_mode: CommandMode = "auto",
    ) -> None:
        self.drone_ip = drone_ip
        self.command_port = command_port
        self.command_mode = self._normalize_mode(command_mode)
        self.camera_type = 0
        self.debug_packets = False
        self.packet_counter = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("", 0))

    def build_control_packet(self, drone_model: WifiCamRcModel) -> bytes:
        if self._uses_extended_mode():
            packet = self._build_extended_packet(drone_model)
        else:
            packet = self._build_short_packet(drone_model)
        self._clear_one_shot_flags(drone_model)
        return packet

    def send_control_packet(self, packet: bytes) -> None:
        try:
            self.sock.sendto(packet, (self.drone_ip, self.command_port))
        except OSError:
            return

        if self.debug_packets:
            self.packet_counter += 1
            logger.debug("[wifi-cam-rc] #%05d %s", self.packet_counter, packet.hex(" "))

    def set_camera_type(self, camera_type: int) -> None:
        self.camera_type = int(camera_type)
        if self.command_mode == "auto":
            logger.info(
                "[wifi-cam-rc] camera type %s selected %s command mode",
                camera_type,
                "extended" if self._uses_extended_mode() else "short",
            )

    def stop(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass

    def toggle_debug(self) -> bool:
        self.debug_packets = not self.debug_packets
        logger.info("[wifi-cam-rc] debug %s", "ON" if self.debug_packets else "OFF")
        return self.debug_packets

    def _build_short_packet(self, model: WifiCamRcModel) -> bytes:
        packet = bytearray(8)
        packet[0] = self.START_MARKER
        packet[1] = self._right_data(self._axis(model.roll))
        packet[2] = self._right_data(self._axis(model.pitch))
        packet[3] = self._right_data(self._axis(model.throttle))
        packet[4] = self._right_data(self._axis(model.yaw))
        packet[5] = self._build_short_flags(model)
        packet[6] = self._right_data(self._xor(packet[1:6]))
        packet[7] = self.END_MARKER
        return bytes(packet)

    def _build_extended_packet(self, model: WifiCamRcModel) -> bytes:
        packet = bytearray(20)
        packet[0] = self.START_MARKER
        packet[1] = self.EXTENDED_LENGTH
        packet[2] = self._right_data(self._axis(model.roll))
        packet[3] = self._right_data(self._axis(model.pitch))
        packet[4] = self._right_data(self._axis(model.throttle))
        packet[5] = self._right_data(self._axis(model.yaw))
        flags1, flags2 = self._build_extended_flags(model)
        packet[6] = flags1
        packet[7] = flags2
        packet[18] = self._right_data(self._xor(packet[2:18]))
        packet[19] = self.END_MARKER
        return bytes(packet)

    def _build_short_flags(self, model: WifiCamRcModel) -> int:
        flags = 0
        if model.takeoff_flag:
            flags |= self.FLAG_TAKEOFF
        if model.land_flag:
            flags |= self.FLAG_LAND
        if model.stop_flag:
            flags |= self.FLAG_EMERGENCY
        if model.flip_flag:
            flags |= self.FLAG_ROTATE
        if model.headless_flag:
            flags |= self.FLAG_HEADLESS
        if model.calibration_flag:
            flags |= self.FLAG_CALIBRATE
        return flags & 0xFF

    def _build_extended_flags(self, model: WifiCamRcModel) -> tuple[int, int]:
        flags1 = 0
        flags2 = 0
        # The decompiled app maps both one-key fly and land to the same bit.
        if model.takeoff_flag or model.land_flag:
            flags1 |= self.EXT_FLAG_TAKEOFF_OR_LAND
        if model.stop_flag:
            flags1 |= self.EXT_FLAG_EMERGENCY
        if model.calibration_flag:
            flags1 |= self.EXT_FLAG_CALIBRATE
        if model.flip_flag:
            flags1 |= self.EXT_FLAG_ROTATE
        if model.headless_flag:
            flags2 |= self.EXT_FLAG_HEADLESS
        if model.altitude_hold_flag:
            flags2 |= self.EXT_FLAG_ALTITUDE_HOLD
        return flags1 & 0xFF, flags2 & 0xFF

    def _clear_one_shot_flags(self, model: WifiCamRcModel) -> None:
        model.takeoff_flag = False
        model.land_flag = False
        model.stop_flag = False
        model.flip_flag = False
        model.calibration_flag = False

    def _uses_extended_mode(self) -> bool:
        if self.command_mode == "extended":
            return True
        if self.command_mode == "short":
            return False
        return self.camera_type == 2

    def _normalize_mode(self, command_mode: str) -> CommandMode:
        mode = (command_mode or "auto").strip().lower()
        if mode not in {"auto", "short", "extended"}:
            logger.warning("[wifi-cam-rc] Unknown command mode %r; using auto.", command_mode)
            return "auto"
        return mode  # type: ignore[return-value]

    def _axis(self, value: float) -> int:
        return max(0, min(255, int(value))) & 0xFF

    def _right_data(self, value: int) -> int:
        value &= 0xFF
        if value in (self.START_MARKER, self.END_MARKER):
            value = (value + 1) & 0xFF
        return value

    def _xor(self, values: bytes | bytearray) -> int:
        checksum = 0
        for value in values:
            checksum ^= value
        return checksum & 0xFF
