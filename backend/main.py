#!/usr/bin/env python3
import logging
import os

from utils.logging_config import bootstrap_runtime, configure_logging

bootstrap_runtime()

import argparse
import threading
import queue
import signal
import sys

from models.s2x_rc import S2xDroneModel
from protocols.s2x_rc_protocol_adapter import S2xRCProtocolAdapter
from protocols.s2x_video_protocol import S2xVideoProtocolAdapter

from models.wifi_uav_rc import WifiUavRcModel
from protocols.wifi_uav_rc_protocol_adapter import WifiUavRcProtocolAdapter
from protocols.wifi_uav_video_protocol import WifiUavVideoProtocolAdapter

from models.cooingdv_rc import CooingdvRcModel
from protocols.cooingdv_rc_protocol_adapter import CooingdvRcProtocolAdapter
from protocols.cooingdv_video_protocol import CooingdvVideoProtocolAdapter

from services.flight_controller import FlightController
from services.video_receiver import VideoReceiverService
from utils.wifi_uav_variants import WIFI_UAV_DRONE_TYPES, resolve_wifi_uav_variant
from views.cli_rc import CLIView
from views.opencv_video_view import OpenCVVideoView


configure_logging()
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="Drone teleoperation interface")
    parser.add_argument("--drone-type", type=str, default="s2x", 
                        choices=["s2x", "wifi_uav", "wifi_uav_fld", "wifi_uav_uav", "cooingdv"],
                        help="Type of drone to control (s2x, wifi_uav, wifi_uav_fld, wifi_uav_uav, or cooingdv, default: s2x)")
    parser.add_argument("--drone-ip", type=str,
                        help="Drone UDP IP address (default: s2x=172.16.10.1, wifi_uav=192.168.169.1, cooingdv=192.168.1.1)")
    parser.add_argument("--control-port", type=int,
                        help="Drone control port (default: s2x=8080, wifi_uav=8800)")
    parser.add_argument("--video-port", type=int,
                        help="Drone video port (default: s2x=8888, wifi_uav=8800)")
    parser.add_argument("--rate", type=float, default=None,
                        help="Control packets per second (default depends on drone type)")
    parser.add_argument("--with-video", action="store_true",
                        help="Enable video feed")
    parser.add_argument("--dump-frames", action="store_true",
                        help="Dump video frames to files")
    parser.add_argument("--dump-packets", action="store_true",
                        help="Dump raw video packets to files")
    args = parser.parse_args()

    # Create model, protocol adapter, and controller
    if args.drone_type == "s2x":
        logger.info("[main] Using S2X drone implementation.")
        default_ip = "172.16.10.1"
        default_control_port = 8080
        default_video_port = 8888
        default_rate = 80.0
        
        drone_ip = args.drone_ip if args.drone_ip else default_ip
        control_port = args.control_port if args.control_port else default_control_port
        video_port = args.video_port if args.video_port else default_video_port

        drone_model = S2xDroneModel()
        protocol_adapter = S2xRCProtocolAdapter(drone_ip, control_port)
        video_protocol_adapter_class = S2xVideoProtocolAdapter
    elif args.drone_type in WIFI_UAV_DRONE_TYPES:
        wifi_uav_variant = resolve_wifi_uav_variant(args.drone_type)
        logger.info("[main] Using WiFi UAV drone implementation (variant=%s).", wifi_uav_variant)
        default_ip = "192.168.169.1"
        default_control_port = 8800
        default_video_port = 8800 # For WifiUAV, control and video often use the same port
        default_rate = 80.0

        drone_ip = args.drone_ip if args.drone_ip else default_ip
        control_port = args.control_port if args.control_port else default_control_port
        video_port = args.video_port if args.video_port else default_video_port

        drone_model = WifiUavRcModel()
        protocol_adapter = WifiUavRcProtocolAdapter(drone_ip, control_port, variant=wifi_uav_variant)
        video_protocol_adapter_class = WifiUavVideoProtocolAdapter
    elif args.drone_type == "cooingdv":
        logger.info("[main] Using Cooingdv drone implementation (RC UFO, KY UFO, E88 Pro).")
        default_ip = "192.168.1.1"
        default_control_port = 7099
        default_video_port = 7070  # RTSP port for video streaming
        default_rate = 20.0

        drone_ip = args.drone_ip if args.drone_ip else default_ip
        control_port = args.control_port if args.control_port else default_control_port
        video_port = args.video_port if args.video_port else default_video_port

        drone_model = CooingdvRcModel()
        protocol_adapter = CooingdvRcProtocolAdapter(drone_ip, control_port)
        video_protocol_adapter_class = CooingdvVideoProtocolAdapter
    else:
        # Should not happen due to choices in argparse
        logger.error("[main] Unknown drone type: %s", args.drone_type)
        sys.exit(1)

    control_rate = args.rate if args.rate is not None else default_rate
    controller = FlightController(drone_model, protocol_adapter, control_rate)
    

    
    # Start video if requested
    video_view = None
    video_receiver = None
    video_thread = None
    
    if args.with_video:
        # Define the blueprint for the video protocol adapter.
        # The VideoReceiverService will create and manage the instance.
        if args.drone_type == "s2x":
            video_protocol_args = {
                "drone_ip": drone_ip,
                "control_port": control_port,
                "video_port": video_port
            }
        elif args.drone_type in WIFI_UAV_DRONE_TYPES:
            video_protocol_args = {
                "drone_ip": drone_ip,
                "control_port": control_port,
                "video_port": video_port,
                "variant": wifi_uav_variant,
            }
        elif args.drone_type == "cooingdv":
            video_protocol_args = {
                "drone_ip": drone_ip,
                "control_port": control_port,
                "video_port": video_port
            }
        
        frame_queue = queue.Queue(maxsize=100)
        video_receiver = VideoReceiverService(
            video_protocol_adapter_class, # The class to instantiate
            video_protocol_args,          # The arguments for it
            frame_queue,
            dump_frames=args.dump_frames,
            dump_packets=args.dump_packets,
            rc_adapter=protocol_adapter if args.drone_type in WIFI_UAV_DRONE_TYPES else None,
        )
        video_view = OpenCVVideoView(frame_queue)
        
        # Start video receiver service. It now handles the protocol's lifecycle.
        video_receiver.start()
        
        # Run HighGUI in its own, non-daemon thread
        video_thread = threading.Thread(
            target=video_view.run,
            name="OpenCVVideoThread"
        )
        video_thread.start()

    # Start controller
    controller.start()
    
    # Set up signal handler for clean shutdown
    def signal_handler(sig, frame):
        logger.info("[main] Caught signal, shutting down...")
        
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
            logger.warning("[main] Forcing exit due to lingering threads")
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