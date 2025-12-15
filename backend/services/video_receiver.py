import queue
import socket
import threading
import time
import os

from protocols.wifi_uav_video_protocol import WifiUavVideoProtocolAdapter
from utils.dropping_queue import DroppingQueue
from models.video_frame import VideoFrame


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
        rc_adapter=None,
    ):
        self.protocol_adapter_class = protocol_adapter_class
        self.protocol_adapter_args = protocol_adapter_args
        self.frame_queue = frame_queue or DroppingQueue(maxsize=max_queue_size)
        self.dump_frames = dump_frames
        self.dump_packets = dump_packets
        self.rc_adapter = rc_adapter

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
        if self.protocol:
            self.protocol.stop()

        if self._receiver_thread and self._receiver_thread.is_alive():
            self._receiver_thread.join(timeout=1.0)
        
        if self.dump_packets and self._pktlog:
            self._pktlog.close()

    # ────────── stream access ────────── #
    def get_frame_queue(self) -> queue.Queue:
        return self.frame_queue
    
    # ────────── receiver loop ────────── #
    def _receiver_loop(self) -> None:
        """
        Manages the lifecycle of the video protocol adapter. If the connection
        is lost, it will be destroyed and a new one will be created.
        """
        while self._running.is_set():
            try:
                # 1. Create a new protocol instance
                self.protocol = self.protocol_adapter_class(
                    **self.protocol_adapter_args
                )
                
                # Special handling for WifiUavVideoProtocolAdapter to pass the RC adapter
                if isinstance(self.protocol, WifiUavVideoProtocolAdapter) and self.rc_adapter:
                    self.protocol.set_rc_adapter(self.rc_adapter)

                # 2. Start the protocol's receiver loop
                self.protocol.start()

                # 3. Frame processing loop
                frame_idx = 0
                while self._running.is_set() and self.protocol.is_running():
                    try:
                        frame = self.protocol.get_frame(timeout=1.0)
                        if frame:
                            self.frame_queue.put(frame)

                            if self.dump_frames:
                                frame_idx += 1
                                self._dump_frame(frame, frame_idx)
                        
                        # Packets are dumped inside the protocol adapter
                        if self.dump_packets:
                            packets = self.protocol.get_packets()
                            for p in packets:
                                self._pktlog.write(p)
                                self._pktlog.flush()

                    except queue.Empty:
                        continue # Normal, just means no frame was ready
                    except Exception as e:
                        print(f"[VideoReceiverService] Error processing frame: {e}")
                        break

            except socket.error as e:
                print(f"[VideoReceiverService] Socket error: {e}. Reconnecting...")
            except Exception as e:
                print(f"[VideoReceiverService] An unexpected error occurred: {e}")
                # Optionally, decide if you want to stop the whole loop on certain errors
                # self.stop()
                # break

            finally:
                # Cleanup before the next iteration
                if self.protocol:
                    self.protocol.stop()
                    self.protocol = None

            # Wait before attempting to reconnect
            if self._running.is_set():
                print("[VideoReceiverService] Waiting 5 seconds before reconnecting...")
                time.sleep(5)

        print("[VideoReceiverService] Receiver loop has stopped.")

    # ────────── frame dumping ────────── #
    def _dump_frame(self, frame: "VideoFrame | bytes | bytearray | memoryview", frame_idx: int) -> None:
        """
        Saves a frame to the file system in the dump directory.

        Note: the receiver loop deals in `VideoFrame` objects; we persist the
        underlying encoded bytes (`VideoFrame.data`), not the object itself.
        """
        if isinstance(frame, VideoFrame):
            frame_bytes = frame.data
            ext = "jpg" if getattr(frame, "format", None) in (None, "jpeg", "jpg") else str(frame.format)
        else:
            frame_bytes = frame
            ext = "jpg"

        if not isinstance(frame_bytes, (bytes, bytearray, memoryview)):
            raise TypeError(f"Expected frame bytes, got {type(frame_bytes).__name__}")

        filename = os.path.join(self.dump_dir, f"frame_{frame_idx:04d}.{ext}")
        try:
            with open(filename, "wb") as f:
                f.write(frame_bytes)
        except Exception as e:
            print(f"Error dumping frame: {e}")
