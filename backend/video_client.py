#!/usr/bin/env python3
import argparse
import queue
import signal
import sys
import os

from protocols.s2x_video_protocol import S2xVideoProtocolAdapter
from protocols.wifi_uav_video_protocol import WifiUavVideoProtocolAdapter
from services.video_receiver import VideoReceiverService
from views.opencv_video_view import OpenCVVideoView

def main():
    parser = argparse.ArgumentParser(
        description="Modular drone video client"
    )
    parser.add_argument("--drone-ip", default="172.16.10.1", help="Drone host address")
    parser.add_argument("--video-port", type=int, default=8888)
    parser.add_argument("--control-port", type=int, default=8080)
    parser.add_argument(
        "--keepalive", type=float, default=1.0,
        help="Re-send start-video every N seconds"
    )
    parser.add_argument(
        "--dump-frames", action="store_true",
        help="Dump every reassembled frame to disk"
    )
    parser.add_argument(
        "--dump-packets", action="store_true",
        help="Dump every raw packet to disk"
    )
    parser.add_argument(
        "--dump-dir", type=str, default=None,
        help="Directory to store dumps (default: dumps_timestamp)"
    )
    args = parser.parse_args()

    # Define the blueprint for our protocol adapter.
    # The VideoReceiverService will use this to create new instances.
    protocol_class = WifiUavVideoProtocolAdapter
    protocol_args = {
        "drone_ip": "192.168.169.1",
        "control_port": 8800,
        "video_port": 8800,
        "debug": True
    }

    # protocol_class = S2xVideoProtocolAdapter
    # protocol_args = {
    #     "drone_ip": "172.16.10.1",
    #     "control_port": 8080,
    #     "video_port": 8888,
    #     "debug": True
    # }
    
    # Create frame queue
    frame_queue = queue.Queue(maxsize=100)
    
    # The service now takes the class and args to manage the protocol's lifecycle.
    receiver = VideoReceiverService(
        protocol_class,
        protocol_args,
        frame_queue,
        dump_frames=args.dump_frames,
        dump_packets=args.dump_packets,
        dump_dir=args.dump_dir
    )
    
    # Create view
    view = OpenCVVideoView(frame_queue)
    
    # Set up signal handler for clean shutdown
    def signal_handler(sig, frame):
        print("\n[main] Caught signal, shutting down...")
        
        # First stop the receiver (which stops the keepalive)
        receiver.stop()
        
        # Then stop the view
        view.stop()
        
        # Exit more forcefully
        os._exit(0)  # Use os._exit instead of sys.exit
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # The receiver service now manages the entire protocol lifecycle.
    # We no longer send the initial start command from here.
    receiver.start()
    
    try:
        view.run()
    finally:
        print("[main] Shutting down...")
        view.stop()
        receiver.stop()

if __name__ == "__main__":
    main() 