from abc import ABC, abstractmethod
import socket
import threading
from typing import Optional

from models.video_frame import VideoFrame


class BaseVideoProtocolAdapter(ABC):
    """
    Owns transport (UDP socket, keep-alives) and converts raw datagrams
    into VideoFrame objects via an inner VideoModel.
    """

    def __init__(self, drone_ip: str, control_port: int, video_port: int):
        self.drone_ip = drone_ip
        self.control_port = control_port
        self.video_port = video_port
        self._keepalive_thread: Optional[threading.Thread] = None

    # ────────── keep-alive helpers ────────── #
    def start_keepalive(self, interval: float = 1.0) -> None:
        if self._keepalive_thread and self._keepalive_thread.is_alive():
            return

        self._stop_evt = threading.Event()
        self._keepalive_thread = threading.Thread(
            target=self._keepalive_loop,
            args=(interval,),
            daemon=True,
        )
        self._keepalive_thread.start()

    def stop_keepalive(self) -> None:
        if hasattr(self, "_stop_evt"):
            self._stop_evt.set()
        if self._keepalive_thread:
            self._keepalive_thread.join()

    def _keepalive_loop(self, interval: float) -> None:
        while not self._stop_evt.is_set():
            self.send_start_command()
            self._stop_evt.wait(interval)

    # ────────── abstract API ────────── #
    @abstractmethod
    def send_start_command(self) -> None:
        """Tell the drone to start/continue sending video."""
        raise NotImplementedError

    @abstractmethod
    def create_receiver_socket(self) -> socket.socket:
        """Return a configured UDP socket bound for recvfrom()."""
        raise NotImplementedError

    @abstractmethod
    def handle_datagram(self, datagram: bytes) -> Optional[VideoFrame]:
        """
        Parse one UDP datagram and return a VideoFrame if (and only if)
        a whole frame is now complete.
        """
        raise NotImplementedError