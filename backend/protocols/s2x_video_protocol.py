import ipaddress
import socket
import threading
import queue
from typing import Optional, List

from models.s2x_video_model import S2xVideoModel
from models.video_frame import VideoFrame
from protocols.base_video_protocol import BaseVideoProtocolAdapter


class S2xVideoProtocolAdapter(BaseVideoProtocolAdapter):
    """Transport + header parser for S2x JPEG stream"""

    SYNC_BYTES = b"\x40\x40"
    EOS_MARKER = b"\x23\x23"
    HEADER_LEN = 8        # S2x packets always use an 8-byte header
    LINK_DEAD_TIMEOUT = 8.0   # camera can stay silent for ~5 s on boot

    def __init__(
        self,
        drone_ip: str = "172.16.10.1",
        control_port: int = 8080,
        video_port: int = 8888,
        debug: bool = False,
    ):
        super().__init__(drone_ip, control_port, video_port)
        self.model = S2xVideoModel()
        self.local_ip = self._discover_local_ip()
        self._sock_lock = threading.Lock()
        self._sock = self.create_receiver_socket()
        self._keepalive_thread: Optional[threading.Thread] = None
        self._keepalive_stop: Optional[threading.Event] = None
        if debug:
            print(f"[s2x] Video socket on *:{self._sock.getsockname()[1]}")
        self._running = threading.Event()
        self._rx_thread: Optional[threading.Thread] = None
        self._frame_q: "queue.Queue[VideoFrame]" = queue.Queue(maxsize=2)
        self._pkt_buffer: List[bytes] = []

    # ────────── BaseVideoProtocolAdapter ────────── #
    def send_start_command(self) -> None:
        payload = b"\x08" + ipaddress.IPv4Address(self.local_ip).packed
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.sendto(payload, (self.drone_ip, self.control_port))
        print(f"[video] Start command sent ({payload.hex(' ')})")

    def start_keepalive(self, interval: float = 2.0) -> None:
        """Starts a thread to periodically send the start command."""
        if self._keepalive_thread is None:
            self._keepalive_stop = threading.Event()
            self._keepalive_thread = threading.Thread(
                target=self._keepalive_loop,
                args=(interval, self._keepalive_stop),
                daemon=True,
                name="S2xVideoKeepAlive",
            )
            self._keepalive_thread.start()

    def stop_keepalive(self) -> None:
        """Stops the keepalive thread."""
        if self._keepalive_stop:
            self._keepalive_stop.set()
        if self._keepalive_thread:
            self._keepalive_thread.join(timeout=1.0)
            self._keepalive_thread = None

    def create_receiver_socket(self) -> socket.socket:
        """UDP socket bound to the drone's video port."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", self.video_port))
        sock.settimeout(1.0)
        return sock

    def get_receiver_socket(self) -> socket.socket:
        """Returns the main data socket, required by the new VideoReceiverService."""
        with self._sock_lock:
            return self._sock

    def recv_from_socket(self, sock: socket.socket) -> Optional[bytes]:
        """Receives from the socket and handles timeouts."""
        try:
            return sock.recv(4096)  # Use a reasonable buffer size
        except socket.timeout:
            return None

    def handle_payload(self, payload: bytes) -> Optional[VideoFrame]:
        """
        1. Validate & strip the fixed 8-byte S2x header
        2. Forward the slice payload to the model
        """
        if len(payload) <= self.HEADER_LEN or payload[:2] != self.SYNC_BYTES:
            return None

        frame_id     = payload[2]
        slice_id_raw = payload[5]

        body = payload[self.HEADER_LEN:]

        # strip optional "##" trailer
        if body.endswith(self.EOS_MARKER):
            body = body[:-len(self.EOS_MARKER)]

        return self.model.ingest_chunk(
            stream_id=frame_id,
            chunk_id=slice_id_raw,
            payload=body,
        )

    def stop(self) -> None:
        """Shuts down the adapter, required by the new VideoReceiverService."""
        print("[s2x] Stopping protocol adapter.")
        self.stop_keepalive()
        self._running.clear()
        if self._rx_thread and self._rx_thread.is_alive():
            self._rx_thread.join(timeout=1.0)
        try:
            self._sock.close()
        except Exception:
            pass

    # ────────── helpers ────────── #
    def _keepalive_loop(self, interval: float, stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            self.send_start_command()
            stop_event.wait(interval)

    # ────────── Receiver thread API (service expects) ────────── #
    def start(self) -> None:
        if self._rx_thread and self._rx_thread.is_alive():
            return
        self._running.set()
        self.start_keepalive(2.0)

        def _rx_loop() -> None:
            sock = self.get_receiver_socket()
            while self._running.is_set():
                try:
                    payload = self.recv_from_socket(sock)
                    if not payload:
                        continue
                    self._pkt_buffer.append(payload)
                    frame = self.handle_payload(payload)
                    if frame is not None:
                        try:
                            self._frame_q.put(frame, timeout=0.2)
                        except queue.Full:
                            pass
                except OSError:
                    break
                except Exception:
                    continue

        self._rx_thread = threading.Thread(target=_rx_loop, daemon=True, name="S2xVideoRx")
        self._rx_thread.start()

    def is_running(self) -> bool:
        return self._running.is_set() and self._rx_thread is not None and self._rx_thread.is_alive()

    def get_frame(self, timeout: float = 1.0) -> Optional[VideoFrame]:
        try:
            return self._frame_q.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_packets(self) -> List[bytes]:
        packets = self._pkt_buffer
        self._pkt_buffer = []
        return packets

    def _discover_local_ip(self) -> str:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((self.drone_ip, 1))
            return s.getsockname()[0]
        finally:
            s.close()
