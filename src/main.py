#!/usr/bin/env python3
import argparse
import threading
import queue
import signal
import sys
import os

from models.s2x_rc import S2xDroneModel
from protocols.s2x_rc_protocol_adapter import S2xRCProtocolAdapter
from protocols.s2x_video_protocol import S2xVideoProtocolAdapter
from services.flight_controller import FlightController
from services.video_receiver import VideoReceiverService
from views.cli_rc import CLIView
from views.opencv_video_view import OpenCVVideoView

def main():
    parser = argparse.ArgumentParser(description="Drone teleoperation interface")
    parser.add_argument("--drone-ip", type=str, default="172.16.10.1", 
                        help="Drone UDP IP address")
    parser.add_argument("--control-port", type=int, default=8080, 
                        help="Drone control port")
    parser.add_argument("--video-port", type=int, default=8888,
                        help="Drone video port")
    parser.add_argument("--rate", type=float, default=20.0, 
                        help="Control packets per second")
    parser.add_argument("--with-video", action="store_true",
                        help="Enable video feed")
    parser.add_argument("--dump-frames", action="store_true",
                        help="Dump video frames to files")
    parser.add_argument("--dump-packets", action="store_true",
                        help="Dump raw video packets to files")
    args = parser.parse_args()

    # Create model, protocol adapter, and controller
    drone_model = S2xDroneModel()
    protocol = S2xRCProtocolAdapter(args.drone_ip, args.control_port)
    controller = FlightController(drone_model, protocol, args.rate)
    
    # Start controller
    controller.start()
    
    # Start video if requested
    video_view = None
    video_receiver = None
    video_thread = None
    
    if args.with_video:
        # Create video components
        video_protocol = S2xVideoProtocolAdapter(
            args.drone_ip, 
            args.control_port,
            args.video_port
        )
        frame_queue = queue.Queue(maxsize=100)
        video_receiver = VideoReceiverService(
            video_protocol,
            frame_queue,
            dump_frames=args.dump_frames,
            dump_packets=args.dump_packets
        )
        video_view = OpenCVVideoView(frame_queue)
        
        # Start video
        video_protocol.send_start_command()
        video_receiver.start()
        
        # Run HighGUI in its own, non-daemon thread
        video_thread = threading.Thread(
            target=video_view.run,
            name="OpenCVVideoThread"
        )
        video_thread.start()
    
    # Set up signal handler for clean shutdown
    def signal_handler(sig, frame):
        print("\n[main] Caught signal, shutting down...")
        
        # First stop video components
        if video_receiver:
            video_receiver.stop()
        if video_view:
            video_view.stop()
        if video_thread:
            video_thread.join(timeout=1.0)
        
        # Then stop controller
        controller.stop()
        
        # Exit more forcefully, but only if threads haven't cleaned up
        if video_thread and video_thread.is_alive():
            print("[main] Forcing exit due to lingering threads")
            os._exit(0)
        else:
            # Normal exit
            sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start CLI view
    try:
        view = CLIView(controller)
        view.run()
    except KeyboardInterrupt:
        pass
    finally:
        # Clean up in reverse order of creation
        controller.stop()
        
        # Clean up video components
        if video_view:
            video_view.stop()
        if video_receiver:
            video_receiver.stop()
        if video_thread:
            video_thread.join()          # wait until the window thread exits

if __name__ == "__main__":
    main()