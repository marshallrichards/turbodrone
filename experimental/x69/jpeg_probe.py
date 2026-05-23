#!/usr/bin/env python3
"""
Standalone probe for X69 legacy UDP JPEG (ports 7070 / 7080).

Usage (on drone Wi-Fi):
  python jpeg_probe.py
  python jpeg_probe.py --duration 30 --save-dir dumps_x69_jpeg
"""

from __future__ import annotations

import argparse
import socket
import sys
import time
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from protocols.x69_lg_jpeg_video_protocol import (  # noqa: E402
    CMD_START_STREAM,
    CMD_STOP_STREAM,
    JpegFrameAssembler,
)
from utils.udp_socket import disable_udp_connreset  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="X69 UDP JPEG stream probe")
    parser.add_argument("--drone-ip", default="172.16.11.1")
    parser.add_argument("--local-port", type=int, default=7070)
    parser.add_argument("--cmd-port", type=int, default=7080)
    parser.add_argument("--duration", type=float, default=20.0)
    parser.add_argument("--no-decrypt", action="store_true")
    parser.add_argument("--save-dir", default="")
    args = parser.parse_args()

    save_dir = Path(args.save_dir) if args.save_dir else None
    if save_dir:
        save_dir.mkdir(parents=True, exist_ok=True)

    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    rx.bind(("0.0.0.0", args.local_port))
    disable_udp_connreset(rx)
    rx.settimeout(0.5)

    rx.sendto(CMD_START_STREAM, (args.drone_ip, args.cmd_port))
    print(f"Sent START from :{args.local_port} -> {args.drone_ip}:{args.cmd_port}")

    asm = JpegFrameAssembler(decrypt=not args.no_decrypt)
    frames = 0
    t0 = time.monotonic()

    try:
        while time.monotonic() - t0 < args.duration:
            try:
                packet, addr = rx.recvfrom(65535)
            except socket.timeout:
                continue
            jpeg = asm.ingest(packet)
            if jpeg is None:
                continue
            frames += 1
            w = h = 0
            i = 2
            while i < len(jpeg) - 8:
                if jpeg[i] != 0xFF:
                    i += 1
                    continue
                marker = jpeg[i + 1]
                if marker in (0xC0, 0xC1, 0xC2):
                    h = (jpeg[i + 5] << 8) | jpeg[i + 6]
                    w = (jpeg[i + 7] << 8) | jpeg[i + 8]
                    break
                if marker in (0xD8, 0xD9):
                    i += 2
                    continue
                seg_len = (jpeg[i + 2] << 8) | jpeg[i + 3]
                i += 2 + seg_len
            print(f"frame #{frames} from {addr[0]}:{addr[1]} len={len(jpeg)} ~{w}x{h}")
            if save_dir:
                (save_dir / f"frame_{frames:04d}.jpg").write_bytes(jpeg)
    finally:
        rx.sendto(CMD_STOP_STREAM, (args.drone_ip, args.cmd_port))
        rx.close()

    print(
        f"Done: frames={frames} packets={asm._packets_rx} "
        f"dropped={asm._frames_dropped} duration={args.duration}s"
    )
    return 0 if frames else 1


if __name__ == "__main__":
    raise SystemExit(main())
