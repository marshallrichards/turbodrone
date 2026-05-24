#!/usr/bin/env python3
"""
Probe Macrochip S2x (HY + ST3) packets for hidden camera tilt / servo commands.

Hypothesis: stock PL FPV / HiTurbo apps always send HY bytes 8-17 as zero because
they have no tilt UI — firmware may still act on those bytes. This tool tests that
the same way as experimental/cooingdv/gl_tilt_probe.py.

Modes:
  hy   — 20-byte HY frame (66 14 RR PP TT YY F1 F2 [8..17] CHK 99) @ ~20 Hz
  st3  — ff 53 54 33 <param> <value> side commands (also UDP 8080)
  all  — HY reserved sweep, then ST3 param sweep

Examples:
  python s2x_tilt_probe.py
  python s2x_tilt_probe.py --mode hy --auto-sweep --log-file hy_sweep.log
  python s2x_tilt_probe.py --mode st3 --auto-sweep --st3-param-max 64
  python s2x_tilt_probe.py --mode all --video-keepalive
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
# HY packet (UDP port 8080, 20 bytes) — matches TurboDrone s2x_rc_protocol_adapter
#
#   0: 0x66   1: 0x14 (length/id)
#   2-5: roll pitch throttle yaw (neutral 0x80)
#   6-7: flags6 flags7 (stock apps often 7=0x02|0x0a patterns)
#   8-17: "unused" in app — primary probe target
#   18: XOR checksum of bytes 2-17 (TurboDrone / default here)
#   19: 0x99
# ---------------------------------------------------------------------------

START_MARKER = 0x66
LENGTH_BYTE = 0x14
END_MARKER = 0x99
STICK_CENTER = 0x80
DEFAULT_DRONE_IP = "172.16.10.1"
DEFAULT_PORT = 8080
SEND_HZ = 20.0

HY_RESERVED_START = 8
HY_RESERVED_END = 17

ST3_HEADER = bytes([0xFF, 0x53, 0x54, 0x33])  # "ST3"

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

# Byte 6: TurboDrone uses 0x01/0x02/0x04; HiTurbo also documents flip at bit 3
FLAGS6_EXTRA_BITS: tuple[int, ...] = (0x08, 0x10, 0x20, 0x40, 0x80)

# Byte 7: stock sets 0x02 | 0x08(rocker) | record; probe high unused bits
FLAGS7_EXTRA_BITS: tuple[int, ...] = (0x04, 0x10, 0x20, 0x40, 0x80)

# ST3 params seen in decompile (logged, not skipped during sweep)
ST3_KNOWN_PARAMS: dict[int, str] = {
    0: "sd_info",
    16: "camera_index_query",
    18: "lens_switch",  # LOILEY FLY: sendFlowParam(18, 40) on start, (18, 25) lens toggle
    22: "camera_index_query_alt",
}

logger = logging.getLogger("s2x_tilt_probe")


def hy_checksum(pkt: bytearray) -> int:
    """XOR bytes 2-17 — matches TurboDrone s2x adapter and stock app effect."""
    chk = 0
    for i in range(2, 18):
        chk ^= pkt[i] & 0xFF
    return chk & 0xFF


def build_hy_packet(
    *,
    roll: int = STICK_CENTER,
    pitch: int = STICK_CENTER,
    throttle: int = STICK_CENTER,
    yaw: int = STICK_CENTER,
    flags6: int = 0,
    flags7: int = 0x0A,
    reserved: Optional[dict[int, int]] = None,
) -> bytes:
    reserved = reserved or {}
    pkt = bytearray(20)
    pkt[0] = START_MARKER
    pkt[1] = LENGTH_BYTE
    pkt[2] = roll & 0xFF
    pkt[3] = pitch & 0xFF
    pkt[4] = throttle & 0xFF
    pkt[5] = yaw & 0xFF
    pkt[6] = flags6 & 0xFF
    pkt[7] = flags7 & 0xFF
    for idx in range(HY_RESERVED_START, HY_RESERVED_END + 1):
        pkt[idx] = int(reserved.get(idx, 0)) & 0xFF
    pkt[18] = hy_checksum(pkt)
    pkt[19] = END_MARKER
    return bytes(pkt)


def build_st3_packet(param: int, value: int) -> bytes:
    return ST3_HEADER + bytes([param & 0xFF, value & 0xFF])


def format_hex(packet: bytes) -> str:
    return " ".join(f"{b:02x}" for b in packet)


def local_ipv4_for_drone(drone_ip: str, port: int) -> Optional[str]:
    """Pick the interface IP used to reach the drone."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect((drone_ip, port))
        ip = probe.getsockname()[0]
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    finally:
        probe.close()
    return None


def build_video_keepalive(drone_ip: str, port: int) -> Optional[bytes]:
    ip = local_ipv4_for_drone(drone_ip, port)
    if not ip:
        return None
    octets = [int(x) & 0xFF for x in ip.split(".")]
    if len(octets) != 4:
        return None
    return bytes([0x08, *octets])


@dataclass
class HyProbeState:
    roll: int = STICK_CENTER
    pitch: int = STICK_CENTER
    throttle: int = STICK_CENTER
    yaw: int = STICK_CENTER
    flags6: int = 0
    flags7: int = 0x0A
    reserved: dict[int, int] = field(default_factory=dict)
    selected_byte: int = HY_RESERVED_START
    value_index: int = 0
    flags6_bit_index: int = 0
    flags7_bit_index: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "roll": self.roll,
                "pitch": self.pitch,
                "throttle": self.throttle,
                "yaw": self.yaw,
                "flags6": self.flags6,
                "flags7": self.flags7,
                "reserved": dict(self.reserved),
            }

    def build(self) -> bytes:
        s = self.snapshot()
        return build_hy_packet(
            roll=s["roll"],
            pitch=s["pitch"],
            throttle=s["throttle"],
            yaw=s["yaw"],
            flags6=s["flags6"],
            flags7=s["flags7"],
            reserved=s["reserved"],
        )

    def clear_all(self) -> str:
        with self._lock:
            self.flags6 = 0
            self.reserved.clear()
            self.flags7 = 0x0A
            self.value_index = 0
        return "neutral (reserved cleared, flags6=0, flags7=0x0a)"

    def select_byte(self, index: int) -> str:
        with self._lock:
            self.selected_byte = index
            cur = self.reserved.get(index, 0)
        return f"selected byte[{index}] current=0x{cur:02x}"

    def cycle_value(self, direction: int) -> str:
        with self._lock:
            self.value_index = (self.value_index + direction) % len(PROBE_VALUES)
            val = PROBE_VALUES[self.value_index]
            idx = self.selected_byte
            if val == 0:
                self.reserved.pop(idx, None)
            else:
                self.reserved[idx] = val
        return f"byte[{idx}] = 0x{val:02x}"

    def clear_byte(self) -> str:
        with self._lock:
            self.reserved.pop(self.selected_byte, None)
        return f"byte[{self.selected_byte}] cleared"

    def toggle_flags6_extra(self) -> str:
        with self._lock:
            bit = FLAGS6_EXTRA_BITS[self.flags6_bit_index % len(FLAGS6_EXTRA_BITS)]
            self.flags6 ^= bit
            on = bool(self.flags6 & bit)
        return f"flags6 toggle 0x{bit:02x} -> {'on' if on else 'off'} (flags6=0x{self.flags6:02x})"

    def toggle_flags7_extra(self) -> str:
        with self._lock:
            bit = FLAGS7_EXTRA_BITS[self.flags7_bit_index % len(FLAGS7_EXTRA_BITS)]
            self.flags7 ^= bit
            on = bool(self.flags7 & bit)
        return f"flags7 toggle 0x{bit:02x} -> {'on' if on else 'off'} (flags7=0x{self.flags7:02x})"

    def next_flags6_bit(self) -> str:
        with self._lock:
            self.flags6_bit_index = (self.flags6_bit_index + 1) % len(FLAGS6_EXTRA_BITS)
            bit = FLAGS6_EXTRA_BITS[self.flags6_bit_index]
        return f"flags6 cursor -> 0x{bit:02x}"

    def next_flags7_bit(self) -> str:
        with self._lock:
            self.flags7_bit_index = (self.flags7_bit_index + 1) % len(FLAGS7_EXTRA_BITS)
            bit = FLAGS7_EXTRA_BITS[self.flags7_bit_index]
        return f"flags7 cursor -> 0x{bit:02x}"


class UdpProbe:
    def __init__(
        self,
        drone_ip: str,
        port: int,
        hy_state: HyProbeState,
        send_hz: float,
        video_keepalive: bool,
    ) -> None:
        self.addr = (drone_ip, port)
        self.hy_state = hy_state
        self.interval = 1.0 / send_hz
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("", 0))
        self._stop = threading.Event()
        self._hy_thread: Optional[threading.Thread] = None
        self._video_thread: Optional[threading.Thread] = None
        self.video_pkt = build_video_keepalive(drone_ip, port) if video_keepalive else None
        self.packets_sent = 0

    def start_hy_loop(self) -> None:
        self._stop.clear()
        self._hy_thread = threading.Thread(target=self._hy_loop, name="hy-send", daemon=True)
        self._hy_thread.start()
        if self.video_pkt:
            self._video_thread = threading.Thread(
                target=self._video_loop, name="video-ka", daemon=True
            )
            self._video_thread.start()
        logger.info(
            "HY sender -> %s:%s (local %s)%s",
            self.addr[0],
            self.addr[1],
            self.sock.getsockname()[1],
            " + video keepalive" if self.video_pkt else "",
        )

    def send_once(self, packet: bytes) -> None:
        try:
            self.sock.sendto(packet, self.addr)
            self.packets_sent += 1
        except OSError as exc:
            logger.warning("send failed: %s", exc)

    def send_hy_burst(self, seconds: float) -> None:
        """Send HY at send_hz for a duration (used during ST3 sweep to stay connected)."""
        end = time.monotonic() + seconds
        while time.monotonic() < end and not self._stop.is_set():
            self.send_once(self.hy_state.build())
            time.sleep(self.interval)

    def stop(self) -> None:
        self._stop.set()
        for t in (self._hy_thread, self._video_thread):
            if t:
                t.join(timeout=2.0)
        self.sock.close()

    def _hy_loop(self) -> None:
        while not self._stop.is_set():
            self.send_once(self.hy_state.build())
            self._stop.wait(self.interval)

    def _video_loop(self) -> None:
        while not self._stop.is_set() and self.video_pkt:
            self.send_once(self.video_pkt)
            self._stop.wait(2.0)


def _log(path: Optional[Path], msg: str, packet: Optional[bytes] = None) -> None:
    line = f"{msg} | {format_hex(packet)}" if packet else msg
    logger.info("%s", line)
    if path:
        ts = datetime.now(timezone.utc).isoformat()
        with path.open("a", encoding="utf-8") as f:
            f.write(f"{ts} {line}\n")


HY_PHASES = ("start", "reserved", "flags6", "flags7", "patterns")
_HY_PHASE_ORDER = ("reserved", "flags6", "flags7", "patterns")


def run_hy_auto_sweep(
    probe: UdpProbe,
    state: HyProbeState,
    *,
    hold_seconds: float,
    log_file: Optional[Path],
    hy_from: str = "start",
    log_append: bool = False,
) -> None:
    phase = hy_from if hy_from in HY_PHASES else "start"
    if phase == "start":
        phase = "reserved"
    start_idx = _HY_PHASE_ORDER.index(phase)

    if log_file and not log_append:
        log_file.write_text("", encoding="utf-8")
    _log(log_file, f"=== HY auto-sweep (from {phase}) ===")
    state.clear_all()
    time.sleep(hold_seconds)

    if start_idx <= 0:
        for idx in range(HY_RESERVED_START, HY_RESERVED_END + 1):
            for val in PROBE_VALUES:
                if val == 0:
                    state.reserved.pop(idx, None)
                else:
                    state.reserved[idx] = val
                msg = f"HY reserved byte[{idx}]=0x{val:02x}"
                _log(log_file, msg, state.build())
                time.sleep(hold_seconds)
            state.reserved.pop(idx, None)

    if start_idx <= 1:
        state.clear_all()
        for bit in FLAGS6_EXTRA_BITS:
            state.flags6 = bit
            _log(log_file, f"HY flags6=0x{bit:02x}", state.build())
            time.sleep(hold_seconds)
        state.flags6 = 0

    if start_idx <= 2:
        base7 = state.flags7
        for bit in FLAGS7_EXTRA_BITS:
            state.flags7 = base7 | bit
            _log(log_file, f"HY flags7=0x{state.flags7:02x}", state.build())
            time.sleep(hold_seconds)
        state.flags7 = base7

    if start_idx <= 3:
        patterns = (
            ("tilt-b8-40", 8, 0x40),
            ("tilt-b8-80", 8, 0x80),
            ("tilt-b8-c0", 8, 0xC0),
            ("tilt-b9-40", 9, 0x40),
            ("tilt-b8b9-01-02", None, None),
        )
        for label, idx, val in patterns:
            state.clear_all()
            if label == "tilt-b8b9-01-02":
                state.reserved[8] = 0x01
                state.reserved[9] = 0x02
            else:
                state.reserved[idx] = val
            _log(log_file, f"HY pattern {label}", state.build())
            time.sleep(hold_seconds)

    state.clear_all()
    _log(log_file, "=== HY auto-sweep done ===")


def run_st3_auto_sweep(
    probe: UdpProbe,
    state: HyProbeState,
    *,
    hold_seconds: float,
    log_file: Optional[Path],
    param_max: int,
    values: tuple[int, ...],
) -> None:
    _log(log_file, "=== ST3 auto-sweep start ===")
    for param in range(param_max + 1):
        label = ST3_KNOWN_PARAMS.get(param, "")
        for val in values:
            pkt = build_st3_packet(param, val)
            msg = f"ST3 param={param} value={val}"
            if label:
                msg += f" ({label})"
            _log(log_file, msg, pkt)
            # Send ST3 once per tick, keep HY neutral stream in background
            end = time.monotonic() + hold_seconds
            while time.monotonic() < end:
                probe.send_once(pkt)
                probe.send_once(state.build())
                time.sleep(probe.interval)
    _log(log_file, "=== ST3 auto-sweep done ===")


HY_HELP = """
S2x tilt probe — mode HY (20-byte 66 14 ... 99 @ ~20 Hz)

Watch UDP video (port 8888) or phone preview for mechanical camera tilt.

Reserved bytes 8-17 (apps send zero — we probe anyway):
  0-9       select byte index 8-17
  +/- [ ]   cycle probe value for selected byte
  c         clear selected byte
  n         neutral

Extra flag bits (not used by TurboDrone s2x adapter):
  1 / 2     toggle flags6 / flags7 probe bit
  q / w     move flags6 / flags7 bit cursor
  f / g     flags6=0 / flags7=0x0a

  p         print packet   h  help   Esc  quit

Auto:  python s2x_tilt_probe.py --mode hy --auto-sweep --log-file hy.log
ST3:   python s2x_tilt_probe.py --mode st3 --auto-sweep
Both:  python s2x_tilt_probe.py --mode all --video-keepalive --log-file all.log
"""


def run_hy_interactive(probe: UdpProbe, state: HyProbeState) -> None:
    try:
        import msvcrt
    except ImportError:
        logger.error("Interactive mode needs Windows (msvcrt). Use --auto-sweep.")
        return

    print(HY_HELP)
    probe.start_hy_loop()
    while True:
        if msvcrt.kbhit():
            ch = msvcrt.getwch()
            if ch == "\x1b":
                print("\nQuit.")
                break
            msg: Optional[str] = None
            if ch in ("h", "H", "?"):
                print(HY_HELP)
                continue
            if ch.isdigit():
                d = int(ch)
                if d <= 9:
                    msg = state.select_byte(8 + d)
            elif ch in ("+", "="):
                msg = state.cycle_value(1)
            elif ch == "-":
                msg = state.cycle_value(-1)
            elif ch in ("]", "["):
                msg = state.cycle_value(1 if ch == "]" else -1)
            elif ch in ("c", "C"):
                msg = state.clear_byte()
            elif ch in ("n", "N"):
                msg = state.clear_all()
            elif ch == "1":
                msg = state.toggle_flags6_extra()
            elif ch == "2":
                msg = state.toggle_flags7_extra()
            elif ch in ("q", "Q"):
                msg = state.next_flags6_bit()
            elif ch in ("w", "W"):
                msg = state.next_flags7_bit()
            elif ch in ("f", "F"):
                state.flags6 = 0
                msg = "flags6=0"
            elif ch in ("g", "G"):
                state.flags7 = 0x0A
                msg = "flags7=0x0a"
            elif ch in ("p", "P"):
                print(format_hex(state.build()))
                continue
            if msg:
                print(msg)
                print(f"  {format_hex(state.build())}")
        else:
            time.sleep(0.02)


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Probe S2x HY/ST3 packets for camera tilt.")
    p.add_argument("--drone-ip", default=DEFAULT_DRONE_IP)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--hz", type=float, default=SEND_HZ)
    p.add_argument(
        "--mode",
        choices=("hy", "st3", "all"),
        default="hy",
        help="hy=20-byte frame, st3=ff535433 commands, all=both sweeps",
    )
    p.add_argument("--auto-sweep", action="store_true")
    p.add_argument("--hold-seconds", type=float, default=2.5)
    p.add_argument("--log-file", type=Path, default=None)
    p.add_argument(
        "--video-keepalive",
        action="store_true",
        help="Send 08 <local-ip> every 2s (Macrochip video start shape)",
    )
    p.add_argument(
        "--st3-param-max",
        type=int,
        default=48,
        help="Max ST3 param byte for auto-sweep (default 48)",
    )
    p.add_argument(
        "--st3-values",
        default="0,1,2,25,40,255",
        help="Comma-separated ST3 value bytes to try per param (25/40 = LOILEY FLY lens)",
    )
    p.add_argument(
        "--hy-from",
        choices=HY_PHASES,
        default="start",
        help="Resume HY auto-sweep: start=full, flags6/flags7/patterns=skip earlier phases",
    )
    p.add_argument(
        "--log-append",
        action="store_true",
        help="Append to --log-file instead of overwriting (use with --hy-from)",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(list(argv) if argv is not None else None)


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    st3_values = tuple(
        int(x.strip(), 0) & 0xFF for x in args.st3_values.split(",") if x.strip()
    )
    state = HyProbeState()
    probe = UdpProbe(
        args.drone_ip,
        args.port,
        state,
        args.hz,
        args.video_keepalive or args.mode == "all",
    )

    try:
        if args.auto_sweep:
            if args.mode in ("hy", "all"):
                probe.start_hy_loop()
                run_hy_auto_sweep(
                    probe,
                    state,
                    hold_seconds=args.hold_seconds,
                    log_file=args.log_file,
                    hy_from=args.hy_from,
                    log_append=args.log_append,
                )
            if args.mode in ("st3", "all"):
                if args.mode == "st3" and not probe._hy_thread:
                    probe.start_hy_loop()
                run_st3_auto_sweep(
                    probe,
                    state,
                    hold_seconds=args.hold_seconds,
                    log_file=args.log_file,
                    param_max=args.st3_param_max,
                    values=st3_values,
                )
        else:
            if args.mode != "hy":
                logger.error("Interactive mode only supports --mode hy. Use --auto-sweep for st3/all.")
                return 1
            run_hy_interactive(probe, state)
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        probe.stop()

    logger.info("Packets sent: %s", probe.packets_sent)
    return 0


if __name__ == "__main__":
    sys.exit(main())
