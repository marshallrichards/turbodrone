#!/usr/bin/env python3
"""
Send Macrochip ST / Ruko-style PTZ commands while keeping a neutral S2x HY stream.

Use this on PL-515 / S29 / other `DRONE_TYPE=s2x` hardware when the stock PL FPV app
has no tilt UI but firmware may still accept the ST gimbal side channel (confirmed on
Ruko Drone 1.7.6 — see docs/research/S2x.md).

Keeps `66 14 ... 99` @ ~20 Hz on UDP 8080 (same as TurboDrone) plus optional
`08 <local-ip>` video keepalive. PTZ commands are sent on top without hand-hex.

Examples:
  python s2x_ptz_helper.py --video-keepalive
  python s2x_ptz_helper.py --once st-set --angle 128
  python s2x_ptz_helper.py --once all-set --angle 64 --try-tcp
  python s2x_ptz_helper.py --preset-sweep --video-keepalive -v
"""

from __future__ import annotations

import argparse
import logging
import socket
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

# Reuse HY stream + video keepalive from the existing probe.
try:
    from s2x_tilt_probe import (
        DEFAULT_DRONE_IP,
        DEFAULT_PORT,
        HyProbeState,
        SEND_HZ,
        UdpProbe,
        build_st3_packet,
        format_hex,
    )
except ImportError:
    _here = Path(__file__).resolve().parent
    if str(_here) not in sys.path:
        sys.path.insert(0, str(_here))
    from s2x_tilt_probe import (
        DEFAULT_DRONE_IP,
        DEFAULT_PORT,
        HyProbeState,
        SEND_HZ,
        UdpProbe,
        build_st3_packet,
        format_hex,
    )

DEFAULT_TCP_PORT = 8888
ST_PREFIX = bytes([0xFF, 0x53, 0x54])  # "ST"
FEI_SHA_END = 0x5A
HACK_FLY_HEAD = 0x68

logger = logging.getLogger("s2x_ptz_helper")


# ---------------------------------------------------------------------------
# PTZ packet builders (Ruko / SJBaseApplication — docs/research/S2x.md)
# ---------------------------------------------------------------------------


def st_set_angle(angle: int) -> bytes:
    """Hisi setPTZData: FF 53 54 32 01 <angle> (UDP in practice on Macrochip)."""
    return ST_PREFIX + bytes([32, 1, angle & 0xFF])


def st_get_angle() -> bytes:
    return ST_PREFIX + bytes([21, 1])


def st_ptz_on() -> bytes:
    return ST_PREFIX + bytes([2, 2])


def st_ptz_off() -> bytes:
    return ST_PREFIX + bytes([2, 1])


def st_reset() -> bytes:
    return ST_PREFIX + bytes([18, 0])


def st_trim(roll: int = 128, pitch: int = 128) -> bytes:
    return ST_PREFIX + bytes([16, roll & 0xFF, pitch & 0xFF])


def hackfly_set_angle(angle: int) -> bytes:
    """HACK_FLY setPTZData: 68 07 01 <angle> <xor>; stock app uses TCP 8888."""
    a = angle & 0xFF
    return bytes([HACK_FLY_HEAD, 7, 1, a, a ^ (7 ^ 1)])


def feisha_set_angle(angle: int) -> bytes:
    """FEI_SHA setPTZData: 5A 55 02 14 <angle> <xor>; stock app uses TCP 8888."""
    a = angle & 0xFF
    return bytes([FEI_SHA_END, 0x55, 2, 14, a, a ^ (14 ^ 2)])


@dataclass(frozen=True)
class PtzCommand:
    name: str
    packet: bytes
    transport: str  # "udp" | "tcp"


def all_set_commands(angle: int) -> tuple[PtzCommand, ...]:
    return (
        PtzCommand("st-set", st_set_angle(angle), "udp"),
        PtzCommand("hackfly-set", hackfly_set_angle(angle), "tcp"),
        PtzCommand("feisha-set", feisha_set_angle(angle), "tcp"),
    )


HELP = """
S2x PTZ helper — neutral HY stream + Ruko/Macrochip tilt commands

Watch the camera (UDP 8888 or stock app). Props off, drone on a table.

Angle (0-255, Ruko seek-bar style):
  u / d       angle +5 / -5
  U / D       angle +20 / -20
  0-9         set angle decade (e.g. 1 then 2 -> 12, quick tap for 128: 1 2 8)

Send tilt (current angle):
  s           ST set angle  FF 53 54 32 01 <angle>  (UDP 8080) — try first
  g           ST get angle  FF 53 54 21 01
  o / O       ST PTZ on / off
  r           ST reset gimbal
  k           HACK_FLY set  68 07 01 <angle>  (TCP 8888)
  f           FEI_SHA set   5A 55 02 14 <angle> (TCP 8888)
  t           all three set methods once
  3           ST3 one-shot: ff 53 54 33 <param> <value> (see --st3-param)

  p           print angle + last packets
  n           log neutral HY snapshot
  Esc         quit

One-shot CLI:
  python s2x_ptz_helper.py --once st-set --angle 140 --video-keepalive
  python s2x_ptz_helper.py --preset-sweep --video-keepalive
"""


class PtzSession:
    def __init__(
        self,
        drone_ip: str,
        udp_port: int,
        tcp_port: int,
        hy_hz: float,
        video_keepalive: bool,
    ) -> None:
        self.drone_ip = drone_ip
        self.udp_addr = (drone_ip, udp_port)
        self.tcp_addr = (drone_ip, tcp_port)
        self._hy_state = HyProbeState()
        self._probe = UdpProbe(drone_ip, udp_port, self._hy_state, hy_hz, video_keepalive)
        self._tcp_sock: Optional[socket.socket] = None
        self._tcp_lock = threading.Lock()
        self.angle = 128
        self.st3_param = 23
        self.st3_value = 1
        self._last_sent: list[tuple[str, bytes]] = []

    def start(self) -> None:
        self._probe.start_hy_loop()

    def stop(self) -> None:
        self._probe.stop()
        with self._tcp_lock:
            if self._tcp_sock:
                try:
                    self._tcp_sock.close()
                except OSError:
                    pass
                self._tcp_sock = None

    def _ensure_tcp(self) -> socket.socket:
        with self._tcp_lock:
            if self._tcp_sock is None:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3.0)
                try:
                    sock.connect(self.tcp_addr)
                except OSError as exc:
                    sock.close()
                    raise OSError(f"TCP connect {self.tcp_addr}: {exc}") from exc
                sock.settimeout(None)
                self._tcp_sock = sock
            return self._tcp_sock

    def send_udp(self, packet: bytes, label: str) -> None:
        self._probe.send_once(packet)
        self._last_sent.append((label, packet))
        logger.info("UDP %s | %s", label, format_hex(packet))

    def send_tcp(self, packet: bytes, label: str) -> None:
        try:
            sock = self._ensure_tcp()
            sock.sendall(packet)
            self._last_sent.append((label, packet))
            logger.info("TCP %s | %s", label, format_hex(packet))
        except OSError as exc:
            logger.warning("TCP %s failed (%s); retrying connect next send", label, exc)
            with self._tcp_lock:
                if self._tcp_sock:
                    try:
                        self._tcp_sock.close()
                    except OSError:
                        pass
                    self._tcp_sock = None
            raise

    def send_command(self, cmd: PtzCommand) -> None:
        if cmd.transport == "udp":
            self.send_udp(cmd.packet, cmd.name)
        else:
            self.send_tcp(cmd.packet, cmd.name)

    def bump_angle(self, delta: int) -> int:
        self.angle = max(0, min(255, self.angle + delta))
        return self.angle

    def set_angle_digit(self, digit: int) -> int:
        """Quick-set: append digit 0-9 (e.g. 1,2,8 -> 128), reset on 0 alone."""
        if digit == 0 and self.angle < 10:
            self.angle = 0
        else:
            self.angle = min(255, self.angle * 10 + digit)
        return self.angle

    def send_st_set(self) -> None:
        self.send_udp(st_set_angle(self.angle), "st-set")

    def send_all_set(self) -> None:
        for cmd in all_set_commands(self.angle):
            try:
                self.send_command(cmd)
            except OSError:
                logger.warning("skipped %s after error", cmd.name)
            time.sleep(0.15)

    def send_st3(self) -> None:
        pkt = build_st3_packet(self.st3_param, self.st3_value)
        self.send_udp(pkt, f"st3-{self.st3_param}-{self.st3_value}")


def _log_file(path: Path, msg: str, packet: Optional[bytes] = None) -> None:
    line = f"{msg} | {format_hex(packet)}" if packet else msg
    ts = datetime.now(timezone.utc).isoformat()
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{ts} {line}\n")
    logger.info("%s", line)


def run_preset_sweep(
    session: PtzSession,
    *,
    angles: tuple[int, ...],
    hold_seconds: float,
    log_file: Optional[Path],
    try_tcp: bool,
) -> None:
    if log_file:
        log_file.write_text("", encoding="utf-8")
    _log_file(log_file, "=== preset sweep start ===") if log_file else None

    for angle in angles:
        session.angle = angle
        cmds = [PtzCommand("st-set", st_set_angle(angle), "udp")]
        if try_tcp:
            cmds.extend(
                [
                    PtzCommand("hackfly-set", hackfly_set_angle(angle), "tcp"),
                    PtzCommand("feisha-set", feisha_set_angle(angle), "tcp"),
                ]
            )
        for cmd in cmds:
            try:
                session.send_command(cmd)
                if log_file:
                    _log_file(log_file, f"sweep angle={angle} {cmd.name}", cmd.packet)
            except OSError as exc:
                logger.warning("sweep %s angle=%s: %s", cmd.name, angle, exc)
            time.sleep(0.2)
        time.sleep(hold_seconds)

    if log_file:
        _log_file(log_file, "=== preset sweep done ===")


def run_interactive(session: PtzSession) -> None:
    try:
        import msvcrt
    except ImportError:
        logger.error("Interactive mode needs Windows (msvcrt). Use --once / --preset-sweep.")
        return

    print(HELP)
    session.start()
    while True:
        if msvcrt.kbhit():
            ch = msvcrt.getwch()
            if ch == "\x1b":
                print("\nQuit.")
                break
            try:
                if ch in ("h", "H", "?"):
                    print(HELP)
                    continue
                if ch in ("u", "U"):
                    step = 20 if ch == "U" else 5
                    a = session.bump_angle(step)
                    print(f"angle={a}")
                elif ch in ("d", "D"):
                    step = 20 if ch == "D" else 5
                    a = session.bump_angle(-step)
                    print(f"angle={a}")
                elif ch.isdigit():
                    a = session.set_angle_digit(int(ch))
                    print(f"angle={a}")
                elif ch in ("s", "S"):
                    session.send_st_set()
                elif ch in ("g", "G"):
                    session.send_udp(st_get_angle(), "st-get")
                elif ch == "o":
                    session.send_udp(st_ptz_on(), "st-on")
                elif ch == "O":
                    session.send_udp(st_ptz_off(), "st-off")
                elif ch in ("r", "R"):
                    session.send_udp(st_reset(), "st-reset")
                elif ch in ("k", "K"):
                    session.send_tcp(hackfly_set_angle(session.angle), "hackfly-set")
                elif ch in ("f", "F"):
                    session.send_tcp(feisha_set_angle(session.angle), "feisha-set")
                elif ch in ("t", "T"):
                    session.send_all_set()
                elif ch == "3":
                    session.send_st3()
                elif ch in ("p", "P"):
                    print(f"angle={session.angle}  st3={session.st3_param},{session.st3_value}")
                    print(f"HY {format_hex(session._hy_state.build())}")
                    for label, pkt in session._last_sent[-6:]:
                        print(f"  {label}: {format_hex(pkt)}")
                elif ch in ("n", "N"):
                    pkt = session._hy_state.build()
                    print(f"HY neutral {format_hex(pkt)}")
                else:
                    continue
            except OSError as exc:
                print(f"send error: {exc}")
        else:
            time.sleep(0.02)


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="S2x PTZ helper: neutral HY + Ruko ST/setPTZData commands."
    )
    p.add_argument("--drone-ip", default=DEFAULT_DRONE_IP)
    p.add_argument("--port", type=int, default=DEFAULT_PORT, help="UDP command port")
    p.add_argument("--tcp-port", type=int, default=DEFAULT_TCP_PORT)
    p.add_argument("--hz", type=float, default=SEND_HZ)
    p.add_argument("--angle", type=int, default=128, help="Initial / --once angle")
    p.add_argument(
        "--video-keepalive",
        action="store_true",
        help="Send 08 <local-ip> every 2s on UDP command port",
    )
    p.add_argument(
        "--once",
        choices=("st-set", "st-get", "st-on", "st-off", "st-reset", "hackfly-set", "feisha-set", "all-set"),
        help="Send one command (or all-set trio) then exit",
    )
    p.add_argument(
        "--try-tcp",
        action="store_true",
        help="With --preset-sweep, also try HACK_FLY + FEI_SHA on TCP 8888",
    )
    p.add_argument(
        "--preset-sweep",
        action="store_true",
        help="Try ST set at angles 0,32,64,...,255 with pauses",
    )
    p.add_argument("--hold-seconds", type=float, default=2.5)
    p.add_argument("--log-file", type=Path, default=None)
    p.add_argument("--st3-param", type=int, default=23)
    p.add_argument("--st3-value", type=int, default=1)
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(list(argv) if argv is not None else None)


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    session = PtzSession(
        args.drone_ip,
        args.port,
        args.tcp_port,
        args.hz,
        args.video_keepalive,
    )
    session.angle = max(0, min(255, args.angle))
    session.st3_param = args.st3_param & 0xFF
    session.st3_value = args.st3_value & 0xFF

    try:
        if args.once:
            session.start()
            time.sleep(0.3)
            if args.once == "st-set":
                session.send_st_set()
            elif args.once == "st-get":
                session.send_udp(st_get_angle(), "st-get")
            elif args.once == "st-on":
                session.send_udp(st_ptz_on(), "st-on")
            elif args.once == "st-off":
                session.send_udp(st_ptz_off(), "st-off")
            elif args.once == "st-reset":
                session.send_udp(st_reset(), "st-reset")
            elif args.once == "hackfly-set":
                session.send_tcp(hackfly_set_angle(session.angle), "hackfly-set")
            elif args.once == "feisha-set":
                session.send_tcp(feisha_set_angle(session.angle), "feisha-set")
            elif args.once == "all-set":
                session.send_all_set()
            time.sleep(0.5)
        elif args.preset_sweep:
            session.start()
            angles = tuple(range(0, 256, 32))
            run_preset_sweep(
                session,
                angles=angles,
                hold_seconds=args.hold_seconds,
                log_file=args.log_file,
                try_tcp=args.try_tcp,
            )
        else:
            run_interactive(session)
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        session.stop()

    logger.info("HY packets sent: %s", session._probe.packets_sent)
    return 0


if __name__ == "__main__":
    sys.exit(main())
