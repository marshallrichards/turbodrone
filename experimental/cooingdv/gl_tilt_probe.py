#!/usr/bin/env python3
"""
Interactive GL packet probe for CooingDV camera tilt / servo discovery.

Sends 21-byte GL control packets (03 66 14 ...) with neutral sticks while you
toggle reserved bytes (Wi-Fi indices 9-17) and unused flag bits. Watch the live
camera feed for mechanical tilt; log what you tried.

Run from repo root or this directory:
  python turbodrone/experimental/cooingdv/gl_tilt_probe.py
  python gl_tilt_probe.py --auto-sweep --log-file sweep.log

Safety: drone on a table, props removed if possible, battery connected.
"""

from __future__ import annotations

import argparse
import logging
import socket
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

# ---------------------------------------------------------------------------
# Packet layout (Wi-Fi UDP, 21 bytes total)
#   0: 0x03 prefix
#   1: 0x66 start
#   2: 0x14 extended marker
#   3-6: roll, pitch, throttle, yaw (stick axes)
#   7-8: flags1, flags2
#   9-18: reserved (stock apps send zeros)
#   19: XOR checksum over bytes 3-8 only
#   20: 0x99 end
# ---------------------------------------------------------------------------

PREFIX = 0x03
START_MARKER = 0x66
EXTENDED_MARKER = 0x14
END_MARKER = 0x99
STICK_CENTER = 128

HEARTBEAT = bytes([0x01, 0x01])
DEFAULT_DRONE_IP = "192.168.1.1"
DEFAULT_PORT = 7099
SEND_HZ = 20.0

# Reserved region in Wi-Fi packet indices (inclusive)
RESERVED_START = 9
RESERVED_END = 18

PROBE_VALUES: tuple[int, ...] = (
    0x00,
    0x01,
    0x02,
    0x04,
    0x08,
    0x10,
    0x20,
    0x40,
    0x80,
    0xFF,
)

# Bits not used by TurboDrone's stock GL mapping (see cooingdv.md)
FLAGS1_PROBE_BITS: tuple[int, ...] = (0x10, 0x20, 0x40, 0x80)
FLAGS2_PROBE_BITS: tuple[int, ...] = (0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80)

logger = logging.getLogger("gl_tilt_probe")


def _checksum(roll: int, pitch: int, throttle: int, yaw: int, flags1: int, flags2: int) -> int:
    value = roll ^ pitch ^ throttle ^ yaw ^ flags1 ^ flags2
    return value & 0xFF


def build_gl_packet(
    *,
    roll: int = STICK_CENTER,
    pitch: int = STICK_CENTER,
    throttle: int = STICK_CENTER,
    yaw: int = STICK_CENTER,
    flags1: int = 0,
    flags2: int = 0,
    reserved: Optional[dict[int, int]] = None,
) -> bytes:
    """Build a 21-byte GL Wi-Fi control packet."""
    reserved = reserved or {}
    packet = bytearray(21)
    packet[0] = PREFIX
    packet[1] = START_MARKER
    packet[2] = EXTENDED_MARKER
    packet[3] = roll & 0xFF
    packet[4] = pitch & 0xFF
    packet[5] = throttle & 0xFF
    packet[6] = yaw & 0xFF
    packet[7] = flags1 & 0xFF
    packet[8] = flags2 & 0xFF
    for index in range(RESERVED_START, RESERVED_END + 1):
        packet[index] = int(reserved.get(index, 0)) & 0xFF
    packet[19] = _checksum(packet[3], packet[4], packet[5], packet[6], packet[7], packet[8])
    packet[20] = END_MARKER
    return bytes(packet)


def format_packet(packet: bytes) -> str:
    return " ".join(f"{b:02x}" for b in packet)


@dataclass
class ProbeState:
    """Mutable probe state updated by keyboard or auto-sweep."""

    roll: int = STICK_CENTER
    pitch: int = STICK_CENTER
    throttle: int = STICK_CENTER
    yaw: int = STICK_CENTER
    flags1: int = 0
    flags2: int = 0
    reserved: dict[int, int] = field(default_factory=dict)
    selected_byte: int = RESERVED_START
    value_index: int = 0
    flags1_bit_index: int = 0
    flags2_bit_index: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def snapshot(self) -> tuple[int, int, int, int, int, int, dict[int, int]]:
        with self._lock:
            return (
                self.roll,
                self.pitch,
                self.throttle,
                self.yaw,
                self.flags1,
                self.flags2,
                dict(self.reserved),
            )

    def build_packet(self) -> bytes:
        roll, pitch, throttle, yaw, flags1, flags2, reserved = self.snapshot()
        return build_gl_packet(
            roll=roll,
            pitch=pitch,
            throttle=throttle,
            yaw=yaw,
            flags1=flags1,
            flags2=flags2,
            reserved=reserved,
        )

    def clear_all(self) -> str:
        with self._lock:
            self.flags1 = 0
            self.flags2 = 0
            self.reserved.clear()
            self.value_index = 0
        return "neutral (reserved + flags cleared)"

    def set_reserved_byte(self, index: int, value: int) -> str:
        with self._lock:
            self.selected_byte = index
            self.reserved[index] = value & 0xFF
        return f"byte[{index}] = 0x{value:02x}"

    def clear_reserved_byte(self, index: int) -> str:
        with self._lock:
            self.reserved.pop(index, None)
        return f"byte[{index}] cleared"

    def cycle_reserved_value(self, direction: int) -> str:
        with self._lock:
            self.value_index = (self.value_index + direction) % len(PROBE_VALUES)
            value = PROBE_VALUES[self.value_index]
            index = self.selected_byte
            if value == 0:
                self.reserved.pop(index, None)
            else:
                self.reserved[index] = value
        return f"byte[{index}] = 0x{value:02x}"

    def select_byte(self, index: int) -> str:
        with self._lock:
            self.selected_byte = index
            current = self.reserved.get(index, 0)
        return f"selected byte[{index}] (current 0x{current:02x})"

    def toggle_flags1_bit(self) -> str:
        with self._lock:
            bit = FLAGS1_PROBE_BITS[self.flags1_bit_index % len(FLAGS1_PROBE_BITS)]
            self.flags1 ^= bit
            active = bool(self.flags1 & bit)
        return f"flags1 toggle 0x{bit:02x} -> {'on' if active else 'off'} (flags1=0x{self.flags1:02x})"

    def toggle_flags2_bit(self) -> str:
        with self._lock:
            bit = FLAGS2_PROBE_BITS[self.flags2_bit_index % len(FLAGS2_PROBE_BITS)]
            self.flags2 ^= bit
            active = bool(self.flags2 & bit)
        return f"flags2 toggle 0x{bit:02x} -> {'on' if active else 'off'} (flags2=0x{self.flags2:02x})"

    def next_flags1_bit(self) -> str:
        with self._lock:
            self.flags1_bit_index = (self.flags1_bit_index + 1) % len(FLAGS1_PROBE_BITS)
            bit = FLAGS1_PROBE_BITS[self.flags1_bit_index]
        return f"flags1 probe bit cursor -> 0x{bit:02x}"

    def next_flags2_bit(self) -> str:
        with self._lock:
            self.flags2_bit_index = (self.flags2_bit_index + 1) % len(FLAGS2_PROBE_BITS)
            bit = FLAGS2_PROBE_BITS[self.flags2_bit_index]
        return f"flags2 probe bit cursor -> 0x{bit:02x}"


class UdpSender:
    def __init__(self, drone_ip: str, port: int, state: ProbeState, send_hz: float) -> None:
        self._addr = (drone_ip, port)
        self._state = state
        self._interval = 1.0 / send_hz
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind(("", 0))
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._heartbeat_thread: Optional[threading.Thread] = None
        self.packets_sent = 0

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._send_loop, name="gl-send", daemon=True)
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, name="gl-heartbeat", daemon=True
        )
        self._thread.start()
        self._heartbeat_thread.start()
        logger.info(
            "UDP sender ready -> %s:%s (local port %s)",
            self._addr[0],
            self._addr[1],
            self._sock.getsockname()[1],
        )

    def stop(self) -> None:
        self._stop.set()
        for thread in (self._thread, self._heartbeat_thread):
            if thread:
                thread.join(timeout=2.0)
        try:
            self._sock.sendto(bytes([0x08, 0x01]), self._addr)
        except OSError:
            pass
        self._sock.close()

    def _heartbeat_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._sock.sendto(HEARTBEAT, self._addr)
            except OSError:
                pass
            self._stop.wait(1.0)

    def _send_loop(self) -> None:
        while not self._stop.is_set():
            packet = self._state.build_packet()
            try:
                self._sock.sendto(packet, self._addr)
                self.packets_sent += 1
            except OSError as exc:
                logger.warning("send failed: %s", exc)
            self._stop.wait(self._interval)


def _log_probe(
    log_file: Optional[Path],
    message: str,
    packet: Optional[bytes] = None,
) -> None:
    line = message
    if packet is not None:
        line = f"{message} | {format_packet(packet)}"
    logger.info("%s", message if packet is None else line)
    if log_file:
        timestamp = datetime.now(timezone.utc).isoformat()
        with log_file.open("a", encoding="utf-8") as handle:
            handle.write(f"{timestamp} {line}\n")


def run_auto_sweep(
    sender: UdpSender,
    state: ProbeState,
    *,
    hold_seconds: float,
    log_file: Optional[Path],
) -> None:
    """Walk reserved bytes and flag bits automatically."""
    if log_file:
        log_file.write_text("", encoding="utf-8")

    _log_probe(log_file, "=== auto-sweep start ===")
    state.clear_all()
    time.sleep(hold_seconds)

    for byte_index in range(RESERVED_START, RESERVED_END + 1):
        for value in PROBE_VALUES:
            if value == 0:
                state.clear_reserved_byte(byte_index)
            else:
                state.set_reserved_byte(byte_index, value)
            msg = f"sweep reserved byte[{byte_index}]=0x{value:02x}"
            _log_probe(log_file, msg, state.build_packet())
            time.sleep(hold_seconds)
        state.clear_reserved_byte(byte_index)

    state.clear_all()
    for bit in FLAGS1_PROBE_BITS:
        state.flags1 = bit
        msg = f"sweep flags1=0x{bit:02x}"
        _log_probe(log_file, msg, state.build_packet())
        time.sleep(hold_seconds)
    state.flags1 = 0

    for bit in FLAGS2_PROBE_BITS:
        state.flags2 = bit
        msg = f"sweep flags2=0x{bit:02x}"
        _log_probe(log_file, msg, state.build_packet())
        time.sleep(hold_seconds)
    state.flags2 = 0

    # WiFi-UAV-style 2-bit patterns in first reserved bytes
    tilt_patterns = (
        ("tilt-neutral", 0, 0),
        ("tilt-bits-01", 0x40, 0x00),
        ("tilt-bits-10", 0x80, 0x00),
        ("tilt-bits-11", 0xC0, 0x00),
        ("tilt-low-01", 0x01, 0x00),
        ("tilt-low-10", 0x02, 0x00),
    )
    for label, b9, b10 in tilt_patterns:
        state.clear_all()
        if b9:
            state.set_reserved_byte(9, b9)
        if b10:
            state.set_reserved_byte(10, b10)
        msg = f"sweep pattern {label} byte[9]=0x{b9:02x} byte[10]=0x{b10:02x}"
        _log_probe(log_file, msg, state.build_packet())
        time.sleep(hold_seconds)

    state.clear_all()
    _log_probe(log_file, "=== auto-sweep done ===")


HELP_TEXT = """
CooingDV GL tilt probe (21-byte packets @ ~20 Hz)

Watch the camera feed while probing. Props off / drone on table recommended.

Reserved byte (Wi-Fi index 9-17):
  0-8     select byte index (0 -> byte 9, 8 -> byte 17)
  +/-     cycle test value for selected byte
  [ ]     prev / next probe value
  c       clear selected reserved byte
  n       neutral (clear all reserved + flags)

Flag bits (unused in stock TurboDrone GL mapping):
  1 / 2   toggle current flags1 / flags2 probe bit
  q / w   next flags1 / flags2 probe bit cursor
  f / g   clear flags1 / flags2

Other:
  p       print current packet hex
  h       this help
  Esc     quit

Auto mode:  python gl_tilt_probe.py --auto-sweep --log-file sweep.log
"""


def _print_help() -> None:
    print(HELP_TEXT)


def _run_interactive(sender: UdpSender, state: ProbeState) -> None:
    try:
        import msvcrt
    except ImportError:
        logger.error("Interactive mode needs Windows (msvcrt). Use --auto-sweep on other OS.")
        return

    print(HELP_TEXT)
    print("Press keys in this console (focus this window). Esc to quit.\n")

    last_print = 0.0
    while True:
        if msvcrt.kbhit():
            key = msvcrt.getwch()
            message: Optional[str] = None

            if key == "\x1b":
                print("\nQuit.")
                break
            if key in ("h", "H", "?"):
                _print_help()
                continue

            if key.isdigit():
                digit = int(key)
                if digit <= 8:
                    message = state.select_byte(RESERVED_START + digit)
            elif key in ("+", "="):
                message = state.cycle_reserved_value(1)
            elif key == "-":
                message = state.cycle_reserved_value(-1)
            elif key == "]":
                message = state.cycle_reserved_value(1)
            elif key == "[":
                message = state.cycle_reserved_value(-1)
            elif key in ("c", "C"):
                message = state.clear_reserved_byte(state.selected_byte)
            elif key in ("n", "N"):
                message = state.clear_all()
            elif key == "1":
                message = state.toggle_flags1_bit()
            elif key == "2":
                message = state.toggle_flags2_bit()
            elif key in ("q", "Q"):
                message = state.next_flags1_bit()
            elif key in ("w", "W"):
                message = state.next_flags2_bit()
            elif key in ("f", "F"):
                state.flags1 = 0
                message = "flags1 cleared"
            elif key in ("g", "G"):
                state.flags2 = 0
                message = "flags2 cleared"
            elif key in ("p", "P"):
                packet = state.build_packet()
                print(format_packet(packet))
                continue

            if message:
                packet = state.build_packet()
                print(f"{message}")
                print(f"  {format_packet(packet)}")
                last_print = time.time()
        else:
            time.sleep(0.02)

        now = time.time()
        if now - last_print > 2.0:
            reserved = state.snapshot()[6]
            if reserved or state.flags1 or state.flags2:
                packet = state.build_packet()
                print(f"[active] {format_packet(packet)}")
            last_print = now


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe CooingDV GL packets for hidden camera tilt / servo commands.",
    )
    parser.add_argument("--drone-ip", default=DEFAULT_DRONE_IP, help="Drone IP (default 192.168.1.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="UDP control port (default 7099)")
    parser.add_argument("--hz", type=float, default=SEND_HZ, help="Control packet rate (default 20)")
    parser.add_argument(
        "--auto-sweep",
        action="store_true",
        help="Run automated reserved-byte and flag sweep (no keyboard)",
    )
    parser.add_argument(
        "--hold-seconds",
        type=float,
        default=2.5,
        help="Seconds to hold each auto-sweep step (default 2.5)",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Append probe steps to this log file (useful with --auto-sweep)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    state = ProbeState()
    sender = UdpSender(args.drone_ip, args.port, state, args.hz)
    sender.start()

    try:
        if args.auto_sweep:
            run_auto_sweep(sender, state, hold_seconds=args.hold_seconds, log_file=args.log_file)
        else:
            _run_interactive(sender, state)
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        sender.stop()

    logger.info("Packets sent: %s", sender.packets_sent)
    return 0


if __name__ == "__main__":
    sys.exit(main())
