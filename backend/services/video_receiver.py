import queue
import socket
import threading
import time
import os

class VideoReceiverService:
    """Protocol-agnostic UDP reader that delegates re-assembly
       to the supplied BaseVideoProtocolAdapter instance."""

    def __init__(self, protocol_adapter, frame_queue=None, max_queue_size=100,
                 dump_frames=False, dump_packets=False, dump_dir=None):
        self.protocol      = protocol_adapter
        self.frame_queue   = frame_queue or queue.Queue(maxsize=max_queue_size)
        self.dump_frames   = dump_frames
        self.dump_packets  = dump_packets

        # optional dumping dirs / files …
        if dump_frames or dump_packets:
            self.dump_dir = dump_dir or f"dumps_{int(time.time())}"
            os.makedirs(self.dump_dir, exist_ok=True)
        if self.dump_packets:
            ts = int(time.time() * 1000)
            self._pktlog = open(os.path.join(self.dump_dir,
                                             f"packets_{ts}.bin"), "wb")

        self.running         = threading.Event()
        self.receiver_thread = None

    def start(self):
        """Start the video receiver thread"""
        if self.receiver_thread and self.receiver_thread.is_alive():
            return
            
        self.running.set()
        self.receiver_thread = threading.Thread(
            target=self._receiver_loop,
            daemon=True
        )
        self.receiver_thread.start()
        
        # Start the protocol keepalive
        self.protocol.start_keepalive()
    
    def stop(self):
        """Stop the video receiver thread"""
        self.running.clear()
        if self.receiver_thread:
            self.receiver_thread.join(timeout=1.0)
            self.receiver_thread = None
        
        # Stop the protocol keepalive
        self.protocol.stop_keepalive()
        
        # Close debug log if open
        if hasattr(self, '_pktlog') and self._pktlog:
            self._pktlog.close()
    
    def get_frame_queue(self):
        """Get the frame queue for consumers"""
        return self.frame_queue
    
    def _receiver_loop(self):
        sock = self.protocol.create_receiver_socket()
        print(f"[receiver] listening on UDP/*:{self.protocol.video_port}")

        try:
            while self.running.is_set():
                try:
                    pkt, _ = sock.recvfrom(2048)
                except socket.timeout:
                    continue

                if self.dump_packets:
                    self._pktlog.write(pkt)

                frame = self.protocol.handle_datagram(pkt)
                if frame:
                    # optional on-disk dump
                    if self.dump_frames:
                        ts = int(time.time() * 1000)
                        fname = f"frame_{frame.frame_id:02x}_{ts}.jpg"
                        with open(os.path.join(self.dump_dir, fname), "wb") as f:
                            f.write(frame.data)

                    # hand over to consumers (blocks if queue is full)
                    self.frame_queue.put(frame)

        finally:
            sock.close()
            if self.dump_packets:
                self._pktlog.close()
