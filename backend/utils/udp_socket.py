"""UDP socket helpers (mainly Windows ICMP / WSAECONNRESET quirks)."""

from __future__ import annotations

import ctypes
import platform
import socket


def disable_udp_connreset(sock: socket.socket) -> None:
    """
    On Windows, ICMP "port unreachable" after sendto() makes the next recv()
    raise WSAECONNRESET (10054). Disable that for connectionless UDP sockets.
    """
    if platform.system() != "Windows":
        return
    SIO_UDP_CONNRESET = 0x9800000C  # noqa: N806
    try:
        sock.ioctl(SIO_UDP_CONNRESET, ctypes.c_ulong(0))
    except OSError:
        pass
