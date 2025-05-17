import argparse
import ipaddress
import queue
import socket
import threading
import time
import os
from datetime import datetime

import cv2
import numpy as np
from ultralytics import YOLO
import math

###############################################################################
# Constants
###############################################################################
DRONE_IP        = "172.16.10.1"
CONTROL_PORT    = 8080        # where we send the 5-byte "start" cmd
VIDEO_PORT      = 8888        # where the drone sends JPEG slices
SOI_MARKER      = b"\xFF\xD8"
EOI_MARKER      = b"\xFF\xD9"
SYNC_BYTES      = b"\x40\x40"

# --------------------------------------------------------------------------- #
# The drone's header (derived from packet dumps)
#
#   0   1   2   3   4   5   6  7    ← byte index
# +---+---+---+---+---+---+---+---+
# |40|40|FID| 2 |22|SID| 78 | 05    <- 0x40 0x40 | frame id | slice id | 78 05 (usually present) | 
# +---+---+---+---+---+---+---+---+
#
# • FID          … increments once per JPEG frame   (0-255, wraps)
# • SID bits 0-3 … slice number inside that frame   (1,2,3…)
#   SID bit  4   … LAST-SLICE flag (1 == this is the final fragment)
#   SID bits 5-7 … always 0
# • bytes 6 & 7    … static header piece (usually starts with 0x78 0x05 )
# • bytes 8+      … payload
# --------------------------------------------------------------------------- #
HEADER_LEN = 8

###############################################################################
# Small helper to discover the IP address of the interface that can reach
# 172.16.10.1  (works on Windows, macOS, Linux)
###############################################################################
def discover_local_ip(remote_ip=DRONE_IP):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # We never actually send anything – connect() is enough for the OS to
        # choose the right outgoing interface.
        s.connect((remote_ip, 1))
        return s.getsockname()[0]
    finally:
        s.close()

###############################################################################
# 1. Control channel – send the 5-byte "start video" command
###############################################################################
def send_start_command(drone_ip: str, my_ip: str):
    """
    Build and send the 5-byte payload:
        0x08 <my_ip as 4 bytes>
    """
    payload = b"\x08" + ipaddress.IPv4Address(my_ip).packed
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(payload, (drone_ip, CONTROL_PORT))
    print(f"[control] start-cmd sent   ({payload.hex(' ')})")

class ControlKeepAlive(threading.Thread):
    """
    Periodically re-send the start-video command so the drone keeps streaming.
    """
    def __init__(self, drone_ip, my_ip, interval=1.0):
        super().__init__(daemon=True)
        self.drone_ip = drone_ip
        self.my_ip    = my_ip
        self.interval = interval
        self._stop    = threading.Event()

    def run(self):
        while not self._stop.is_set():
            send_start_command(self.drone_ip, self.my_ip)
            time.sleep(self.interval)

    def stop(self):
        self._stop.set()

###############################################################################
# 2. Video receiver thread – re-assemble slices into full JPEG frames
###############################################################################
class VideoReceiver(threading.Thread):
    def __init__(
        self,
        frame_queue:  queue.Queue,
        port:          int  = VIDEO_PORT,
        dump_frames:   bool = False,
        dump_packets:  bool = False,
    ):
        super().__init__(daemon=True)
        self.frame_q      = frame_queue
        self.port         = port
        self.dump_frames  = dump_frames
        self.dump_packets = dump_packets

        # control flag for run()
        self.running      = threading.Event()
        self.running.set()

        # assembly state
        self._cur_fid     = None
        self._fragments   = {}     # sid_raw:int -> payload:bytes

        if self.dump_packets:
            ts = int(time.time()*1000)
            self._pktlog = open(f"logged_packets_{ts}.bin", "wb")

    def stop(self):
        self.running.clear()

    def _reset_frame(self, new_fid):
        """Forget the old frame and start a fresh one."""
        self._cur_fid   = new_fid
        self._fragments.clear()

    def _finalise_frame(self, fid, fragments):
        # 1) stitch slices together in ascending order
        data = b"".join(fragments[i] for i in sorted(fragments))

        # 2) find the real JPEG in the bytes
        start = data.find(SOI_MARKER)
        end   = data.rfind(EOI_MARKER)
        if start < 0 or end < 0 or end <= start:
            print(f"[receiver] JPEG markers missing on frame {fid}")
            return

        jpeg = data[start : end + 2]

        # 3) dump & push
        if self.dump_frames:
            ts = int(time.time() * 1000)
            with open(f"frame_{fid:02x}_{ts}.jpg", "wb") as f:
                f.write(jpeg)

        print(f"[receiver] frame {fid} complete – {len(jpeg)} bytes")
        self.frame_q.put(jpeg)

    def run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", self.port))
        sock.settimeout(1.0)
        print(f"[receiver] listening on UDP/*:{self.port}")

        try:
            while self.running.is_set():
                try:
                    pkt, addr = sock.recvfrom(2048)
                except socket.timeout:
                    continue

                if self.dump_packets:
                    self._pktlog.write(pkt)

                # sanity‐check
                if len(pkt) <= HEADER_LEN or pkt[:2] != SYNC_BYTES:
                    continue

                fid     = pkt[2]
                sid_raw = pkt[5]
                # if packet byte 7 and 8 are 0x78 and 0x05 respectively, then strip the 8 bytes
                if pkt[6] == 0x78 and pkt[7] == 0x05:
                    payload = pkt[8:]
                else:
                  payload = pkt[6:]

                # strip trailing 0x23 0x23 if present
                if payload.endswith(b"\x23\x23"):
                    payload = payload[:-2]

                if sid_raw % 20 == 0:   # throttle the spam
                    head = payload[:8].hex()
                    ascii_payload = payload[:8].decode('ascii', errors='replace')
                    print(f"[slice] FID=0x{fid:02x} SID={sid_raw:3d} "
                          f"head={head} ascii={ascii_payload!r}")

                # new frame detected?
                if self._cur_fid is None:
                    self._reset_frame(fid)

                elif fid != self._cur_fid:
                    if self._fragments:
                        keys = sorted(self._fragments)
                        # simple completeness check
                        if len(keys) == (keys[-1] - keys[0] + 1):
                            self._finalise_frame(self._cur_fid, self._fragments)
                        else:
                            print(f"[receiver] dropping frame {self._cur_fid}, "
                                  f"slices {keys[0]}..{keys[-1]} missing "
                                  f"{(keys[-1]-keys[0]+1) - len(keys)}")

                    self._reset_frame(fid)

                # stash this slice (ignore dupes)
                if sid_raw not in self._fragments:
                    self._fragments[sid_raw] = payload

        finally:
            sock.close()
            if self.dump_packets:
                self._pktlog.close()
            print("[receiver] stopped")

###############################################################################
# 3. Display loop (main thread) – show frames with OpenCV
###############################################################################
def process_frame(frame_bytes):
    """Process frame before display."""
    try:
        # Decode JPEG bytes to numpy array
        arr = np.frombuffer(frame_bytes, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            return None
            
        # Ensure consistent frame size
        target_size = (640, 480)  # Standard size for processing
        frame = cv2.resize(frame, target_size)
        return frame
    except Exception as e:
        print(f"Error processing frame: {e}")
        return None

def display_frames(frame_q: queue.Queue):
    cv2.namedWindow("Drone", cv2.WINDOW_NORMAL)
    cv2.namedWindow("Depth", cv2.WINDOW_NORMAL)  # Add depth window
    
    # Initialize depth estimator
    from vision_system.depth_processor.depth_estimator import DepthEstimator
    depth_estimator = DepthEstimator(max_queue_size=2)  # Small queue for real-time
    depth_estimator.start()

    # Initialize YOLO model
    model = YOLO('yolov8n.pt')

    while True:
        frame_bytes = frame_q.get()
        if frame_bytes is None:
            continue
            
        # Process frame
        frame = process_frame(frame_bytes)
        if frame is None:
            continue

        # Make a copy for depth estimation (original BGR)
        depth_frame = frame.copy()
        
        # Convert to RGB for YOLO
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Run YOLO detection
        results = model(rgb_frame, stream=True)
        
        # Process results and draw boxes
        for r in results:
            # Use the RGB frame for annotations
            annotated_frame = r.plot()
            # Convert back to BGR for display
            annotated_frame = cv2.cvtColor(annotated_frame, cv2.COLOR_RGB2BGR)
            cv2.imshow("Drone", annotated_frame)
            
            # Process depth on original BGR frame
            if depth_estimator.add_frame(depth_frame):
                result = depth_estimator.get_latest_result()
                if result is not None:
                    depth_map, _ = result
                    # Normalize and colorize depth map
                    depth_vis = cv2.normalize(depth_map, None, 0, 255, cv2.NORM_MINMAX)
                    depth_color = cv2.applyColorMap(depth_vis.astype(np.uint8), cv2.COLORMAP_INFERNO)
                    
                    # Add FPS text
                    stats = depth_estimator.get_stats()
                    cv2.putText(depth_color, f"Depth FPS: {stats['fps']:.1f}", (10, 30),
                              cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                    
                    # Show depth window
                    cv2.imshow("Depth", depth_color)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    depth_estimator.stop()
    cv2.destroyAllWindows()

###############################################################################
# Entry-point
###############################################################################
def main():
    parser = argparse.ArgumentParser(
        description="Simple UDP/MJPEG client for FH-style drone"
    )
    parser.add_argument("--drone-ip",   default=DRONE_IP,  help="Drone host address")
    parser.add_argument("--video-port", type=int,      default=VIDEO_PORT)
    parser.add_argument("--control-port", type=int,    default=CONTROL_PORT)
    parser.add_argument(
        "--keepalive", type=float, default=1.0,
        help="Re-send start-video every N seconds"
    )
    parser.add_argument(
        "--dump-frames", action="store_true",
        help="Dump every reassembled JPEG to ./dumped_frames/"
    )
    parser.add_argument(
        "--dump-packets", action="store_true",
        help="Dump every raw UDP packet to ./dumped_packets/"
    )
    args = parser.parse_args()

    my_ip = discover_local_ip(args.drone_ip)
    print(f"[info] local IP that reaches the drone: {my_ip}")

    # 1. Tell the drone to start sending
    send_start_command(args.drone_ip, my_ip)

    # 2. Start keep-alive sender
    keepalive = ControlKeepAlive(args.drone_ip, my_ip, interval=args.keepalive)
    keepalive.start()

    # 3. Start receiver thread (pass dump flags)
    frame_q = queue.Queue(maxsize=100)
    receiver = VideoReceiver(
        frame_q,
        port=args.video_port,
        dump_frames=args.dump_frames,
        dump_packets=args.dump_packets
    )
    receiver.start()

    # 4. UI loop
    try:
        display_frames(frame_q)
    finally:
        print("[main] shutting down …")
        keepalive.stop()
        receiver.stop()
        receiver.join()

if __name__ == "__main__":
    main()
