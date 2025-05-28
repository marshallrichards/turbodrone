import queue
import socket
import threading
import time
import os

class VideoReceiverService:
    """Thread that feeds raw transport payloads to a protocol adapter"""

    def __init__(
        self,
        protocol_adapter,
        frame_queue=None,
        max_queue_size=100,
        dump_frames=False,
        dump_packets=False,
        dump_dir=None,
    ):
        self.protocol = protocol_adapter
        self.frame_queue = frame_queue or queue.Queue(maxsize=max_queue_size)
        self.dump_frames = dump_frames
        self.dump_packets = dump_packets

        if dump_frames or dump_packets:
            self.dump_dir = dump_dir or f"dumps_{int(time.time())}"
            os.makedirs(self.dump_dir, exist_ok=True)
        if self.dump_packets:
            ts = int(time.time() * 1000)
            self._pktlog = open(
                os.path.join(self.dump_dir, f"packets_{ts}.bin"), "wb"
            )

        self._running = threading.Event()
        self._receiver_thread = None

    # ────────── lifecycle ────────── #
    def start(self) -> None:
        if self._receiver_thread and self._receiver_thread.is_alive():
            return

        self._running.set()
        self._receiver_thread = threading.Thread(
            target=self._receiver_loop, name="VideoReceiver", daemon=True
        )
        self._receiver_thread.start()

        self.protocol.start_keepalive()

    def stop(self) -> None:
        self._running.clear()
        if self._receiver_thread:
            self._receiver_thread.join(timeout=1.0)
            self._receiver_thread = None

        self.protocol.stop_keepalive()

        if self.dump_packets and hasattr(self, "_pktlog"):
            self._pktlog.close()

    def get_frame_queue(self):
        return self.frame_queue

    # ────────── internal ────────── #
    def _receiver_loop(self) -> None:
        sock = self.protocol.create_receiver_socket()
        print(f"[receiver] listening on *:{self.protocol.video_port}")

        try:
            while self._running.is_set():
                raw = self.protocol.recv_from_socket(sock)
                if raw is None:
                    continue  # timeout or no data

                if self.dump_packets:
                    self._pktlog.write(raw)

                frame = self.protocol.handle_payload(raw)
                if not frame:
                    continue

                if self.dump_frames and self.dump_dir:
                    ts = int(time.time() * 1000)
                    fname = f"frame_{frame.frame_id:02x}_{ts}.jpg"
                    with open(os.path.join(self.dump_dir, fname), "wb") as f:
                        f.write(frame.data)

                self.frame_queue.put(frame)

        finally:
            sock.close()
            if self.dump_packets and hasattr(self, "_pktlog"):
                self._pktlog.close()
