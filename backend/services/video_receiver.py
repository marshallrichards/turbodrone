import queue
import socket
import threading
import time
import os
from datetime import datetime
from models.video_frame import VideoFrame

class VideoReceiverService:
    """Service for receiving and reassembling video frames from the drone"""
    
    def __init__(self, protocol_adapter, frame_queue=None, max_queue_size=100, 
                 dump_frames=False, dump_packets=False, dump_dir=None):
        self.protocol = protocol_adapter
        self.frame_queue = frame_queue or queue.Queue(maxsize=max_queue_size)
        self.dump_frames = dump_frames
        self.dump_packets = dump_packets
        
        # Create dump directory if needed
        if dump_frames or dump_packets:
            self.dump_dir = dump_dir or f"dumps_{int(time.time())}"
            os.makedirs(self.dump_dir, exist_ok=True)
        
        # Thread control
        self.receiver_thread = None
        self.running = threading.Event()
        
        # Assembly state
        self._current_frame_id = None
        self._fragments = {}
        
        # Debug logging
        if self.dump_packets:
            ts = int(time.time()*1000)
            self._pktlog = open(os.path.join(self.dump_dir, f"packets_{ts}.bin"), "wb")
    
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
    
    def _reset_frame(self, new_frame_id):
        """Reset frame assembly state for a new frame"""
        self._current_frame_id = new_frame_id
        self._fragments.clear()
    
    def _assemble_frame(self, frame_id):
        """Assemble fragments into a complete frame"""
        if not self._fragments:
            return None
            
        # Check if we have a complete sequence
        keys = sorted(self._fragments)
        if not keys or len(keys) < 1:
            return None
            
        # Simple completeness check - this may need to be protocol-specific
        if len(keys) != (keys[-1] - keys[0] + 1):
            print(f"[receiver] Dropping frame {frame_id}, "
                  f"slices {keys[0]}..{keys[-1]} missing "
                  f"{(keys[-1]-keys[0]+1) - len(keys)}")
            return None
        
        # Stitch slices together in ascending order
        data = b"".join(self._fragments[i] for i in keys)
        
        # Find the real JPEG in the bytes (for S2x protocol)
        # This could be moved to the protocol adapter in a more generic implementation
        start = data.find(self.protocol.SOI_MARKER)
        end = data.rfind(self.protocol.EOI_MARKER)
        if start < 0 or end < 0 or end <= start:
            print(f"[receiver] JPEG markers missing on frame {frame_id}")
            return None
        
        jpeg_data = data[start : end + 2]
        
        # Dump frame if requested
        if self.dump_frames:
            ts = int(time.time() * 1000)
            with open(os.path.join(self.dump_dir, f"frame_{frame_id:02x}_{ts}.jpg"), "wb") as f:
                f.write(jpeg_data)
        
        print(f"[receiver] Frame {frame_id} complete - {len(jpeg_data)} bytes")
        
        # Create frame model
        return VideoFrame(frame_id, jpeg_data, "jpeg")
    
    def _receiver_loop(self):
        """Main receiver thread loop"""
        sock = self.protocol.create_receiver_socket()
        print(f"[receiver] Listening on UDP/*:{self.protocol.video_port}")
        
        try:
            while self.running.is_set():
                try:
                    pkt, addr = sock.recvfrom(2048)
                except socket.timeout:
                    continue
                
                if self.dump_packets and hasattr(self, '_pktlog'):
                    self._pktlog.write(pkt)
                
                # Skip invalid packets
                if not self.protocol.is_valid_packet(pkt):
                    continue
                
                # Parse the packet
                packet_data = self.protocol.parse_packet(pkt)
                if not packet_data:
                    continue
                    
                frame_id = packet_data["frame_id"]
                slice_id = packet_data["slice_id"]
                payload = packet_data["payload"]
                
                if slice_id % 20 == 0:  # Throttle the spam
                    head = payload[:8].hex()
                    ascii_payload = payload[:8].decode('ascii', errors='replace')
                    print(f"[slice] FID=0x{frame_id:02x} SID={slice_id:3d} "
                          f"head={head} ascii={ascii_payload!r}")
                
                # New frame detected?
                if self._current_frame_id is None:
                    self._reset_frame(frame_id)
                
                elif frame_id != self._current_frame_id:
                    # Try to assemble the previous frame
                    frame = self._assemble_frame(self._current_frame_id)
                    if frame:
                        self.frame_queue.put(frame)
                    
                    # Start new frame
                    self._reset_frame(frame_id)
                
                # Stash this slice (ignore dupes)
                if slice_id not in self._fragments:
                    self._fragments[slice_id] = payload
                
                # If this is marked as the last slice, try to assemble immediately
                if packet_data.get("is_last_slice") and len(self._fragments) > 1:
                    frame = self._assemble_frame(frame_id)
                    if frame:
                        self.frame_queue.put(frame)
                        self._reset_frame(None)  # Ready for next frame
        
        finally:
            sock.close() 