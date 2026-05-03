"""
RC protocol adapter for the CooingDV/Jieli CTP backend.

This is the backend used by KY FPV's Jieli DeviceClient path. It keeps the
familiar CooingDV 8-byte TC stick payload, but sends it as decimal BYTE0..BYTE7
fields inside a CTP JSON packet over UDP instead of sending the raw 0x03/0x66
datagram used by the classic CooingDV apps.
"""

from __future__ import annotations

import logging
import socket
import threading
from typing import Final, Optional

from models.cooingdv_rc import CooingdvRcModel
from protocols.base_protocol_adapter import BaseProtocolAdapter
from utils.cooingdv_jieli_ctp import build_ctp_packet

logger = logging.getLogger(__name__)


class CooingdvJieliRcProtocolAdapter(BaseProtocolAdapter):
    """CooingDV Jieli/CTP UDP adapter used by KY FPV Jieli devices."""

    DEFAULT_DRONE_IP: Final = "192.168.8.15"
    DEFAULT_PORT: Final = 2228
    HEARTBEAT_INTERVAL: Final = 1.0

    START_MARKER: Final = 0x66
    END_MARKER: Final = 0x99

    TOPIC_CONTROL_MODE: Final = "CONTROL_MODE"
    TOPIC_FLYING_CTRL: Final = "FLYING_CTRL"
    TOPIC_KEEP_ALIVE: Final = "CTP_KEEP_ALIVE"

    OP_PUT: Final = "PUT"

    FLAG_FAST_FLY: Final = 0x01
    FLAG_FAST_DROP: Final = 0x02
    FLAG_EMERGENCY_STOP: Final = 0x04
    FLAG_CIRCLE_TURN_END: Final = 0x08
    FLAG_HEADLESS: Final = 0x10
    FLAG_UNLOCK_OR_RETURN: Final = 0x20
    FLAG_LIGHT: Final = 0x40
    FLAG_GYRO: Final = 0x80

    def __init__(
        self,
        drone_ip: str = DEFAULT_DRONE_IP,
        control_port: int = DEFAULT_PORT,
        *,
        bind_port: Optional[int] = DEFAULT_PORT,
    ) -> None:
        self.drone_ip = drone_ip
        self.control_port = control_port
        self.debug_packets = False
        self._pkt_counter = 0
        self._heartbeat_running = False
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: Optional[threading.Thread] = None

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # The Android UDPClientImpl binds DatagramSocket(2228). If that port is
        # busy on a development machine, fall back to an ephemeral local port so
        # packet sending still works.
        if bind_port is not None:
            try:
                self.sock.bind(("", bind_port))
            except OSError as exc:
                logger.warning(
                    "[cooingdv-jieli] Could not bind local UDP port %s (%s); using ephemeral port.",
                    bind_port,
                    exc,
                )
                self.sock.bind(("", 0))
        else:
            self.sock.bind(("", 0))

        self.start_heartbeat()
        self._send_control_mode(True)
        logger.info(
            "[cooingdv-jieli] RC adapter initialized for %s:%s (local %s)",
            drone_ip,
            control_port,
            self.sock.getsockname()[1],
        )

    def build_control_packet(self, drone_model: CooingdvRcModel) -> bytes:
        """Build a CTP FLYING_CTRL packet from the shared CooingDV model."""
        payload = self._build_flying_payload(drone_model)
        self._clear_one_shot_flags(drone_model)
        params = {f"BYTE{i}": str(value) for i, value in enumerate(payload)}
        return build_ctp_packet(self.TOPIC_FLYING_CTRL, params)

    def send_control_packet(self, packet: bytes) -> None:
        try:
            self.sock.sendto(packet, (self.drone_ip, self.control_port))
        except OSError:
            return

        if self.debug_packets:
            self._pkt_counter += 1
            logger.debug(
                "[cooingdv-jieli] #%05d %s",
                self._pkt_counter,
                packet.hex(" "),
            )

    def toggle_debug(self) -> bool:
        self.debug_packets = not self.debug_packets
        logger.info("[cooingdv-jieli] debug %s", "ON" if self.debug_packets else "OFF")
        return self.debug_packets

    def stop(self) -> None:
        self.stop_heartbeat()
        self._send_control_mode(False)
        try:
            self.sock.close()
        except OSError:
            pass

    def start_heartbeat(self) -> None:
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return

        self._heartbeat_stop.clear()
        self._heartbeat_running = True
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name="CooingdvJieliHeartbeat",
        )
        self._heartbeat_thread.start()

    def stop_heartbeat(self) -> None:
        self._heartbeat_running = False
        self._heartbeat_stop.set()
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=2.0)
            self._heartbeat_thread = None

    def _heartbeat_loop(self) -> None:
        while self._heartbeat_running and not self._heartbeat_stop.is_set():
            self._send_ctp(self.TOPIC_KEEP_ALIVE, {})
            self._heartbeat_stop.wait(self.HEARTBEAT_INTERVAL)

    def _send_control_mode(self, enabled: bool) -> None:
        self._send_ctp(self.TOPIC_CONTROL_MODE, {"state": "1" if enabled else "0"})

    def _send_ctp(self, topic: str, params: dict[str, str]) -> None:
        packet = build_ctp_packet(topic, params)
        try:
            self.sock.sendto(packet, (self.drone_ip, self.control_port))
        except OSError:
            pass

    def _build_flying_payload(self, model: CooingdvRcModel) -> list[int]:
        b1 = self._clamp_axis(model.roll)
        b2 = self._clamp_axis(model.pitch)
        acc = self._clamp_axis(model.throttle)
        if acc == 1:
            acc = 0
        turn = self._clamp_axis(model.yaw)
        flags = self._build_flags(model)
        checksum = (b1 ^ b2 ^ acc ^ turn ^ flags) & 0xFF
        return [self.START_MARKER, b1, b2, acc, turn, flags, checksum, self.END_MARKER]

    def _build_flags(self, model: CooingdvRcModel) -> int:
        flags = 0
        if model.takeoff_flag:
            flags |= self.FLAG_FAST_FLY
        if model.land_flag:
            flags |= self.FLAG_FAST_DROP
        if model.stop_flag:
            flags |= self.FLAG_EMERGENCY_STOP
        if model.flip_flag:
            flags |= self.FLAG_CIRCLE_TURN_END
        if model.headless_flag:
            flags |= self.FLAG_HEADLESS
        if model.calibration_flag:
            flags |= self.FLAG_GYRO
        return flags & 0xFF

    def _clear_one_shot_flags(self, model: CooingdvRcModel) -> None:
        model.takeoff_flag = False
        model.land_flag = False
        model.stop_flag = False
        model.flip_flag = False
        model.calibration_flag = False

    def _clamp_axis(self, value: float) -> int:
        return max(1, min(255, int(value))) & 0xFF
