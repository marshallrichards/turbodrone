import queue
import socket
import threading
import time
import os

from protocols.wifi_uav_video_protocol import WifiUavVideoProtocolAdapter


class VideoReceiverService:
    """
    Creates and manages a protocol adapter, destroying and recreating
    it from scratch if the connection is lost, per the user's experiment.
    """

    def __init__(
        self,
        protocol_adapter_class,
        protocol_adapter_args,
        frame_queue=None,
        max_queue_size=100,
        dump_frames=False,
        dump_packets=False,
        dump_dir=None,
    ):
        self.protocol_adapter_class = protocol_adapter_class
        self.protocol_adapter_args = protocol_adapter_args
        self.frame_queue = frame_queue or queue.Queue(maxsize=max_queue_size)
        self.dump_frames = dump_frames
        self.dump_packets = dump_packets

        self.protocol = None # Will be managed in the receiver loop

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

    def stop(self) -> None:
        self._running.clear()
        if self._receiver_thread:
            self._receiver_thread.join(timeout=2.0)
            self._receiver_thread = None

        if self.protocol:
            if hasattr(self.protocol, "stop_keepalive"):
                self.protocol.stop_keepalive()
            self.protocol.stop()

        if self.dump_packets and hasattr(self, "_pktlog"):
            self._pktlog.close()

    def get_frame_queue(self):
        return self.frame_queue

    # ────────── internal ────────── #
    def _receiver_loop(self) -> None:
        """
        The main loop that receives video data. It creates a protocol
        adapter and will tear it down and rebuild it if the link dies.
        """
        last_packet_time = time.time()
        link_dead_timeout = 3.0 # Default

        while self._running.is_set():
            # --- Create/Re-create Protocol Adapter ---
            if self.protocol is None:
                print("[receiver] Creating new protocol adapter instance...")
                try:
                    self.protocol = self.protocol_adapter_class(**self.protocol_adapter_args)
                    link_dead_timeout = getattr(self.protocol, "LINK_DEAD_TIMEOUT", 3.0)
                    last_packet_time = time.time()

                    if hasattr(self.protocol, "send_start_command"):
                        self.protocol.send_start_command()
                    if hasattr(self.protocol, "start_keepalive"):
                        self.protocol.start_keepalive()

                except Exception as e:
                    print(f"[receiver] Failed to create protocol adapter: {e}. Retrying in 5s...")
                    time.sleep(5)
                    continue

            # --- Check for Dead Link ---
            if time.time() - last_packet_time > link_dead_timeout:
                print(f"[receiver] Link silent for {link_dead_timeout}s. "
                      "Destroying and recreating protocol adapter.")

                if hasattr(self.protocol, "stop_keepalive"):
                    self.protocol.stop_keepalive()

                self.protocol.stop()
                self.protocol = None
                time.sleep(1)
                continue

            # --- Receive Data ---
            try:
                sock = self.protocol.get_receiver_socket()
                raw = self.protocol.recv_from_socket(sock)
                if raw is None:
                    continue  # Standard socket timeout

                # quick debug: show first packet after (re)connect
                if time.time() - last_packet_time > 1.5:
                    print(f"[receiver] got {len(raw)}-byte packet "
                          f"(first after reconnect)")
                last_packet_time = time.time()

            except socket.error as e:
                print(f"[receiver] Socket error: {e}. Recreating adapter.")

                if hasattr(self.protocol, "stop_keepalive"):
                    self.protocol.stop_keepalive()

                self.protocol.stop()
                self.protocol = None
                continue
            except Exception as e:
                print(f"[receiver] Unexpected error: {e}. Terminating.")
                break

            if self.dump_packets:
                self._pktlog.write(raw)

            frame = self.protocol.handle_payload(raw)
            if not frame:
                continue

            if self.dump_frames and self.dump_dir:
                ts = int(time.time() * 1000)
                with open(
                    os.path.join(self.dump_dir, f"frame_{frame.frame_id:04x}_{ts}.jpg"),
                    "wb",
                ) as f:
                    f.write(frame.data)

            self.frame_queue.put(frame)

        print("[receiver] Receiver loop terminated.")
        if self.protocol:
            if hasattr(self.protocol, "stop_keepalive"):
                self.protocol.stop_keepalive()
            self.protocol.stop()
        if self.dump_packets and hasattr(self, "_pktlog"):
            self._pktlog.close()
