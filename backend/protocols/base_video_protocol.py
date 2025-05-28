from abc import ABC, abstractmethod
import socket
import threading
from typing import Optional

from models.video_frame import VideoFrame


class BaseVideoProtocolAdapter(ABC):
    """
    Owns transport (UDP or TCP socket, keep-alives) and converts
    raw payloads into VideoFrame objects via an inner VideoModel.
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

    # ────────── transport helpers ────────── #
    def recv_from_socket(self, sock) -> Optional[bytes]:
        """
        Read one payload chunk from `sock`.

        The default implementation assumes UDP; override for TCP.
        """
        try:
            pkt, _ = sock.recvfrom(4096)
            return pkt
        except socket.timeout:
            return None

    # ────────── abstract API ────────── #
    @abstractmethod
    def send_start_command(self) -> None:
        """Tell the drone to start/continue sending video."""
        raise NotImplementedError

    @abstractmethod
    def create_receiver_socket(self) -> socket.socket:
        """Return a configured socket ready for recv()."""
        raise NotImplementedError

    @abstractmethod
    def handle_payload(self, payload: bytes) -> Optional[VideoFrame]:
        """
        Convert one transport payload into a VideoFrame or return None
        if the frame is not yet complete.
        """
        raise NotImplementedError