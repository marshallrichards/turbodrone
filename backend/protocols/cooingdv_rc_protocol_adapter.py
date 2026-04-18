"""
RC Protocol Adapter for CooingDV drones.

The CooingDV apps share a UDP control plane on port 7099, but they do not all
use the same control packet layout. The apps listen for UDP telemetry, classify
the drone as either a short "TC" packet variant or an extended "GL" packet
variant, and then switch the encoder accordingly.

Shared behavior observed in the apps:
  - Heartbeat {0x01, 0x01} every second
  - RTSP preview at rtsp://192.168.1.1:7070/webcam (handled elsewhere)
  - UDP telemetry on the same socket used for control

Important: {0x08, 0x01} is used by the apps when leaving control mode. It is
not a startup "init" packet.
"""

import os
import socket
import threading
import logging
from typing import Final, Optional

from models.cooingdv_rc import CooingdvRcModel
from protocols.base_protocol_adapter import BaseProtocolAdapter

logger = logging.getLogger(__name__)


class CooingdvRcProtocolAdapter(BaseProtocolAdapter):
    """Protocol adapter for the CooingDV drone family."""

    DEFAULT_DRONE_IP: Final = "192.168.1.1"
    DEFAULT_PORT: Final = 7099
    HEARTBEAT_INTERVAL: Final = 1.0
    RECV_TIMEOUT: Final = 0.25
    RECV_BUFFER_SIZE: Final = 256

    # Packet markers
    PREFIX: Final = 0x03
    START_MARKER: Final = 0x66
    EXTENDED_MARKER: Final = 0x14
    END_MARKER: Final = 0x99

    # Discrete UDP commands
    HEARTBEAT_COMMAND: Final = bytes([0x01, 0x01])
    STOP_COMMAND: Final = bytes([0x08, 0x01])

    # Variant names
    DEVICE_UNKNOWN: Final = "unknown"
    DEVICE_TC: Final = "tc"
    DEVICE_GL: Final = "gl"

    # TC packet flag bits
    FLAG_TAKEOFF: Final = 0x01
    FLAG_LAND: Final = 0x02
    FLAG_STOP: Final = 0x04
    FLAG_FLIP: Final = 0x08
    FLAG_HEADLESS: Final = 0x10
    FLAG_CALIBRATE: Final = 0x80

    # GL packet flag groups
    GL_FLAG_ONE_KEY_ACTION: Final = 0x01
    GL_FLAG_STOP: Final = 0x02
    GL_FLAG_CALIBRATE: Final = 0x04
    GL_FLAG_FLIP: Final = 0x08
    GL_FLAG_HEADLESS: Final = 0x01

    # Resolution / capability IDs seen in the CooingDV apps. The apps use the
    # first byte of received UDP telemetry to decide whether the drone belongs
    # to the GL or TC family.
    GL_RESOLUTION_IDS: Final = frozenset(set(range(90, 102)) | {82, 85, 103, 105})
    KNOWN_RESOLUTION_IDS: Final = frozenset({
        3, 5, 9, 11, 12, 19, 20, 21, 23, 24, 26, 27, 29, 30, 31,
        41, 43, 44, 45, 51, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72,
        80, 81, 82, 83, 84, 85, 86, 87, 90, 91, 92, 93, 94, 95, 96,
        97, 98, 99, 100, 101, 103, 105,
    })

    def __init__(
        self,
        drone_ip: str = DEFAULT_DRONE_IP,
        control_port: int = DEFAULT_PORT,
        variant: Optional[str] = None,
    ) -> None:
        self.drone_ip = drone_ip
        self.control_port = control_port

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Match Java DatagramSocket() semantics by binding to an ephemeral port
        # so replies return to the same socket we use for telemetry detection.
        self.sock.bind(("", 0))
        self.sock.settimeout(self.RECV_TIMEOUT)

        self.debug_packets = False
        self._pkt_counter = 0

        env_variant = os.getenv("COOINGDV_VARIANT")
        self._variant_override = self._normalise_variant(variant or env_variant)
        self._detected_variant: Optional[str] = None
        self.detected_resolution_id: Optional[int] = None
        self.last_rx_packet: bytes = b""
        self.last_rx_addr: Optional[tuple[str, int]] = None
        self._override_mismatch_reported = False

        # Heartbeat thread
        self._heartbeat_running = False
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._heartbeat_stop = threading.Event()

        # Receive thread
        self._receiver_running = False
        self._receiver_thread: Optional[threading.Thread] = None
        self._receiver_stop = threading.Event()

        self.start_receiver()
        self.start_heartbeat()

        active_variant = self._active_variant()
        active_label = active_variant.upper()
        if self._variant_override:
            logger.info(
                "[cooingdv] RC adapter initialized for %s:%s (forced %s, local %s)",
                drone_ip,
                control_port,
                active_label,
                self.sock.getsockname()[1],
            )
        else:
            logger.info(
                "[cooingdv] RC adapter initialized for %s:%s (auto-detect, TC fallback, local %s)",
                drone_ip,
                control_port,
                self.sock.getsockname()[1],
            )

    def start_heartbeat(self) -> None:
        """Start the heartbeat thread to keep the UDP session alive."""
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
        while self._heartbeat_running and not self._heartbeat_stop.is_set():
            try:
                self.sock.sendto(self.HEARTBEAT_COMMAND, (self.drone_ip, self.control_port))
                if self.debug_packets:
                    logger.debug("[cooingdv] heartbeat sent: %s", self.HEARTBEAT_COMMAND.hex())
            except OSError:
                pass
            self._heartbeat_stop.wait(self.HEARTBEAT_INTERVAL)

    def start_receiver(self) -> None:
        """Start the telemetry receiver used for TC/GL auto-detection."""
        if self._receiver_thread and self._receiver_thread.is_alive():
            return

        self._receiver_stop.clear()
        self._receiver_running = True
        self._receiver_thread = threading.Thread(
            target=self._receiver_loop,
            daemon=True,
            name="CooingdvUdpRx",
        )
        self._receiver_thread.start()

    def stop_receiver(self) -> None:
        """Stop the telemetry receiver thread."""
        self._receiver_running = False
        self._receiver_stop.set()
        if self._receiver_thread:
            self._receiver_thread.join(timeout=2.0)
            self._receiver_thread = None

    def _receiver_loop(self) -> None:
        while self._receiver_running and not self._receiver_stop.is_set():
            try:
                packet, addr = self.sock.recvfrom(self.RECV_BUFFER_SIZE)
            except socket.timeout:
                continue
            except OSError:
                if self._receiver_stop.is_set():
                    break
                continue

            if not packet:
                continue

            self.last_rx_packet = packet
            self.last_rx_addr = addr
            self._process_received_packet(packet, addr)

    def _process_received_packet(self, packet: bytes, addr: tuple[str, int]) -> None:
        """Track UDP telemetry and auto-detect the control variant."""
        if self.debug_packets:
            logger.debug(
                "[cooingdv] udp recv %sB from %s:%s: %s",
                len(packet),
                addr[0],
                addr[1],
                packet.hex(),
            )

        variant = self._detect_variant(packet)
        if variant is None:
            return

        resolution_id = packet[0]
        if resolution_id in self.KNOWN_RESOLUTION_IDS:
            self.detected_resolution_id = resolution_id

        if self._variant_override:
            if variant != self._variant_override and not self._override_mismatch_reported:
                logger.warning(
                    "[cooingdv] Ignoring auto-detected %s telemetry; using override %s.",
                    variant.upper(),
                    self._variant_override.upper(),
                )
                self._override_mismatch_reported = True
            return

        if variant == self._detected_variant:
            return

        self._detected_variant = variant
        resolution_text = (
            f" resolution-id={self.detected_resolution_id}"
            if self.detected_resolution_id is not None
            else ""
        )
        logger.info("[cooingdv] Auto-detected %s control variant.%s", variant.upper(), resolution_text)

    def stop(self) -> None:
        """Clean shutdown of the adapter."""
        self.stop_heartbeat()
        try:
            self.sock.sendto(self.STOP_COMMAND, (self.drone_ip, self.control_port))
        except OSError:
            pass
        self.stop_receiver()
        try:
            self.sock.close()
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # BaseProtocolAdapter interface
    # ------------------------------------------------------------------ #
    def build_control_packet(self, drone_model: CooingdvRcModel) -> bytes:
        """Build a control packet for the detected CooingDV variant."""
        variant = self._active_variant()
        if variant == self.DEVICE_GL:
            packet = self._build_gl_control_packet(drone_model)
        else:
            packet = self._build_tc_control_packet(drone_model)

        self._clear_one_shot_flags(drone_model)
        return packet

    def send_control_packet(self, packet: bytes) -> None:
        """Send a control packet to the drone via UDP."""
        try:
            self.sock.sendto(packet, (self.drone_ip, self.control_port))
        except OSError:
            return

        if self.debug_packets:
            self._pkt_counter += 1
            variant = self._active_variant().upper()
            hex_dump = " ".join(f"{b:02x}" for b in packet)
            logger.debug("[cooingdv] #%05d [%s] %s", self._pkt_counter, variant, hex_dump)

            if len(packet) == 9:
                roll, pitch, throttle, yaw = packet[2], packet[3], packet[4], packet[5]
                flags = packet[6]
                logger.debug("  Controls: R:%s P:%s T:%s Y:%s", roll, pitch, throttle, yaw)
                flag_names = self._decode_tc_flags(flags)
                if flag_names:
                    logger.debug("  Flags: %s", ", ".join(flag_names))
            elif len(packet) == 21:
                roll, pitch, throttle, yaw = packet[3], packet[4], packet[5], packet[6]
                flags1, flags2 = packet[7], packet[8]
                logger.debug("  Controls: R:%s P:%s T:%s Y:%s", roll, pitch, throttle, yaw)
                flag_names = self._decode_gl_flags(flags1, flags2)
                if flag_names:
                    logger.debug("  Flags: %s", ", ".join(flag_names))

    def toggle_debug(self) -> bool:
        """Toggle debug packet logging on/off."""
        self.debug_packets = not self.debug_packets
        state = "ON" if self.debug_packets else "OFF"
        logger.info("[cooingdv] debug %s", state)
        return self.debug_packets

    # ------------------------------------------------------------------ #
    # Helper methods
    # ------------------------------------------------------------------ #
    def _active_variant(self) -> str:
        """Return the currently active control variant."""
        if self._variant_override:
            return self._variant_override
        if self._detected_variant:
            return self._detected_variant
        return self.DEVICE_TC

    def _normalise_variant(self, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None

        raw = value.strip().lower()
        if raw in ("", "auto", "detect", "autodetect"):
            return None
        if raw in ("tc", "e88", "short"):
            return self.DEVICE_TC
        if raw in ("gl", "flow", "extended"):
            return self.DEVICE_GL

        logger.warning("[cooingdv] Unknown variant override '%s', using auto-detect.", value)
        return None

    def _detect_variant(self, packet: bytes) -> Optional[str]:
        """Infer the control family from the first telemetry byte."""
        first_byte = packet[0]
        if first_byte in self.GL_RESOLUTION_IDS:
            return self.DEVICE_GL
        if first_byte in self.KNOWN_RESOLUTION_IDS:
            return self.DEVICE_TC
        return None

    def _build_tc_control_packet(self, model: CooingdvRcModel) -> bytes:
        pkt = bytearray(9)
        pkt[0] = self.PREFIX
        pkt[1] = self.START_MARKER
        pkt[2] = self._clamp_axis(model.roll)
        pkt[3] = self._clamp_axis(model.pitch)
        pkt[4] = self._clamp_axis(model.throttle)
        pkt[5] = self._clamp_axis(model.yaw)
        pkt[6] = self._build_tc_flags(model)
        pkt[7] = self._calculate_checksum(pkt[2:7])
        pkt[8] = self.END_MARKER
        return bytes(pkt)

    def _build_gl_control_packet(self, model: CooingdvRcModel) -> bytes:
        roll = self._clamp_axis(model.roll)
        pitch = self._clamp_axis(model.pitch)
        throttle = self._clamp_axis(model.throttle)
        yaw = self._clamp_axis(model.yaw)
        flags1, flags2 = self._build_gl_flags(model)

        inner = bytearray(20)
        inner[0] = self.START_MARKER
        inner[1] = self.EXTENDED_MARKER
        inner[2] = roll
        inner[3] = pitch
        inner[4] = throttle
        inner[5] = yaw
        inner[6] = flags1
        inner[7] = flags2
        inner[18] = self._calculate_checksum(
            bytes([roll, pitch, throttle, yaw, flags1, flags2])
        )
        inner[19] = self.END_MARKER

        return bytes([self.PREFIX]) + bytes(inner)

    def _clamp_axis(self, value: float) -> int:
        """Clamp axis values into the byte range used by the apps."""
        clamped = max(1, min(255, int(value)))
        return clamped & 0xFF

    def _build_tc_flags(self, model: CooingdvRcModel) -> int:
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

    def _build_gl_flags(self, model: CooingdvRcModel) -> tuple[int, int]:
        """
        Build the extended GL flag groups.

        In the decompiled apps, the GL family uses two flag bytes and does not
        expose separate takeoff/land bits. The one-key action bit is reused for
        either button, so we mirror that behavior here.
        """
        flags1 = 0
        flags2 = 0

        if model.takeoff_flag or model.land_flag:
            flags1 |= self.GL_FLAG_ONE_KEY_ACTION
        if model.stop_flag:
            flags1 |= self.GL_FLAG_STOP
        if model.calibration_flag:
            flags1 |= self.GL_FLAG_CALIBRATE
        if model.flip_flag:
            flags1 |= self.GL_FLAG_FLIP
        if model.headless_flag:
            flags2 |= self.GL_FLAG_HEADLESS

        return flags1 & 0xFF, flags2 & 0xFF

    def _clear_one_shot_flags(self, model: CooingdvRcModel) -> None:
        model.takeoff_flag = False
        model.land_flag = False
        model.stop_flag = False
        model.flip_flag = False
        model.calibration_flag = False

    def _decode_tc_flags(self, flags: int) -> list[str]:
        names: list[str] = []
        if flags & self.FLAG_TAKEOFF:
            names.append("TAKEOFF")
        if flags & self.FLAG_LAND:
            names.append("LAND")
        if flags & self.FLAG_STOP:
            names.append("STOP")
        if flags & self.FLAG_FLIP:
            names.append("FLIP")
        if flags & self.FLAG_HEADLESS:
            names.append("HEADLESS")
        if flags & self.FLAG_CALIBRATE:
            names.append("CALIBRATE")
        return names

    def _decode_gl_flags(self, flags1: int, flags2: int) -> list[str]:
        names: list[str] = []
        if flags1 & self.GL_FLAG_ONE_KEY_ACTION:
            names.append("ONE_KEY")
        if flags1 & self.GL_FLAG_STOP:
            names.append("STOP")
        if flags1 & self.GL_FLAG_CALIBRATE:
            names.append("CALIBRATE")
        if flags1 & self.GL_FLAG_FLIP:
            names.append("FLIP")
        if flags2 & self.GL_FLAG_HEADLESS:
            names.append("HEADLESS")
        return names

    def _calculate_checksum(self, data: bytes) -> int:
        checksum = 0
        for b in data:
            checksum ^= b
        return checksum & 0xFF

