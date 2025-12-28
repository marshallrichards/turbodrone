from __future__ import annotations

from dataclasses import dataclass


@dataclass
class E88RcState:
    roll: int = 128
    pitch: int = 128
    throttle: int = 128
    yaw: int = 128
    flags: int = 0


class E88RcPacketBuilder:
    def __init__(self) -> None:
        self._base = bytearray(b"\x66\x80\x80\x80\x80\x00\x00\x99")

    @staticmethod
    def _xor_checksum(bs: bytearray) -> None:
        s = 0
        for byte_value in bs[1:6]:
            s ^= byte_value
        bs[6] = s

    def build_packet(self, state: E88RcState) -> bytes:
        self._base[1] = state.roll & 0xFF
        self._base[2] = state.pitch & 0xFF
        self._base[3] = state.throttle & 0xFF
        self._base[4] = state.yaw & 0xFF
        self._base[5] = state.flags & 0xFF

        pkt = bytearray(self._base)
        self._xor_checksum(pkt)
        return bytes(b"\x03" + pkt)
