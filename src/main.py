#!/usr/bin/env python3
import argparse
import threading
from models.s2x_rc import S2xDroneModel
from protocols.s2x_protocol_adapter import S2xProtocolAdapter
from services.flight_controller import FlightController
from views.cli_rc import CLIView

def main():
    parser = argparse.ArgumentParser(description="Drone teleoperation interface")
    parser.add_argument("--drone-ip", type=str, default="172.16.10.1", 
                        help="Drone UDP IP address")
    parser.add_argument("--control-port", type=int, default=8080, 
                        help="Drone control port")
    parser.add_argument("--rate", type=float, default=20.0, 
                        help="Control packets per second")
    args = parser.parse_args()

    # Create model, protocol adapter, and controller
    drone_model = S2xDroneModel()
    protocol = S2xProtocolAdapter(args.drone_ip, args.control_port)
    controller = FlightController(drone_model, protocol, args.rate)
    
    # Start controller
    controller.start()
    
    # Start CLI view
    try:
        view = CLIView(controller)
        view.run()
    except KeyboardInterrupt:
        pass
    finally:
        controller.stop()

if __name__ == "__main__":
    main()