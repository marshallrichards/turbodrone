#!/usr/bin/env python3
import socket
import threading
import time
import argparse
import curses

class DroneController:
    def __init__(self, drone_ip, control_port):
        self.drone_ip     = drone_ip
        self.control_port = control_port
        self.sock         = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # stick midpoints = 128.0
        self.yaw      = 128.0
        self.throttle = 128.0
        self.pitch    = 128.0
        self.roll     = 128.0

        # one-shot flags
        self.takeoff     = False
        self.land        = False
        self.stop        = False
        self.headless    = False
        self.calibration = False

        # misc
        self.speed   = 20    # matches 0x14 from dumps
        self.record  = 0     # bit 2 in byte 7
        self.rocker  = 0     # bit 3 in byte 7

        self.running = True

        # how fast to move stick inputs (units/sec)
        self.accel_rate = 200.0
        self.decel_rate = 300.0
        
        # Control range limits (instead of 0-255)
        self.min_control_value = 60.0
        self.max_control_value = 200.0
        self.center_value = 128.0
        
        # Immediate response boost factor
        self.immediate_response = 5.0
        
        # Exponential control factor (higher values = more aggressive response)
        self.expo_factor = 0.8

    def update_axes(self, dt, throttle_dir, yaw_dir, pitch_dir, roll_dir):
        """Apply acceleration or deceleration for each axis."""
        for attr, direction, boost_enabled in (
            ('throttle', throttle_dir, False),
            ('yaw',      yaw_dir,      False),
            ('pitch',    pitch_dir,    True),  
            ('roll',     roll_dir,     True),  # Enable boost for roll and pitch
        ):
            cur = getattr(self, attr)
            
            # Handle exponential control mapping
            if direction > 0:
                # Apply immediate boost on direction change
                if boost_enabled and getattr(self, f"last_{attr}_dir", 0) <= 0:
                    jump = min(self.max_control_value - cur, self.immediate_response)
                    cur += jump
                
                # Calculate acceleration with exponential factor
                distance_to_max = self.max_control_value - cur
                accel = self.accel_rate * dt * (1 + self.expo_factor * distance_to_max / (self.max_control_value - self.center_value))
                new = min(self.max_control_value, cur + accel)
                
            elif direction < 0:
                # Apply immediate boost on direction change
                if boost_enabled and getattr(self, f"last_{attr}_dir", 0) >= 0:
                    jump = min(cur - self.min_control_value, self.immediate_response)
                    cur -= jump
                
                # Calculate acceleration with exponential factor
                distance_to_min = cur - self.min_control_value
                accel = self.accel_rate * dt * (1 + self.expo_factor * distance_to_min / (self.center_value - self.min_control_value))
                new = max(self.min_control_value, cur - accel)
                
            else:
                # Return to center faster from extremes
                if cur > self.center_value:
                    # Exponential return to center
                    distance_from_center = cur - self.center_value
                    decel = self.decel_rate * dt * (1 + 0.5 * distance_from_center / (self.max_control_value - self.center_value))
                    new = max(self.center_value, cur - decel)
                elif cur < self.center_value:
                    # Exponential return to center
                    distance_from_center = self.center_value - cur
                    decel = self.decel_rate * dt * (1 + 0.5 * distance_from_center / (self.center_value - self.min_control_value))
                    new = min(self.center_value, cur + decel)
                else:
                    new = cur
                    
            # Store last direction for detecting direction changes
            setattr(self, f"last_{attr}_dir", direction)
            setattr(self, attr, new)

    def remap_to_full_range(self, value):
        """Remap value from constrained range to full 0-255 range for sending to drone"""
        if value >= self.center_value:
            # Map center...max_control to 128...255
            return 128.0 + (value - self.center_value) * (255.0 - 128.0) / (self.max_control_value - self.center_value)
        else:
            # Map min_control...center to 0...128
            return (value - self.min_control_value) * 128.0 / (self.center_value - self.min_control_value)

    def build_packet_hy(self):
        pkt = bytearray(20)
        pkt[0] = 0x66
        pkt[1] = self.speed & 0xFF

        # Cast floats back to ints with CORRECTED ORDER
        # Remap from our constrained range to full 0-255 range
        pkt[2] = int(self.remap_to_full_range(self.roll))     & 0xFF
        pkt[3] = int(self.remap_to_full_range(self.pitch))    & 0xFF  
        pkt[4] = int(self.remap_to_full_range(self.throttle)) & 0xFF
        pkt[5] = int(self.remap_to_full_range(self.yaw))      & 0xFF

        # FIXED: flags in byte 6 and 7 were reversed compared to mobile app
        # Byte 6 should be 0x00
        pkt[6] = 0x00
        
        # Handle one-shot flags
        if self.takeoff:
            pkt[6] |= 0x01
        if self.land:
            pkt[6] |= 0x02
        if self.stop:
            pkt[6] |= 0x04

        # Byte 7 should be 0x0a
        pkt[7] = 0x0a  # Base value is 0x0a
        
        # record flag
        if self.record:
            pkt[7] |= (self.record << 2)

        # bytes 8-17 = 0 (zero-filled)

        # checksum over bytes 2-17
        chk = 0
        for i in range(2, 18):
            chk ^= pkt[i]
        pkt[18] = chk & 0xFF
        pkt[19] = 0x99

        # clear one-shots
        self.takeoff = self.land = self.stop = False

        return pkt

    def send_loop(self, interval=0.03):
        # debug flag
        self.debug_packets = False
        packet_counter = 0
        
        while self.running:
            buf = self.build_packet_hy()
            self.sock.sendto(buf, (self.drone_ip, self.control_port))
            
            # Log packet details if debug is enabled
            if self.debug_packets:
                packet_counter += 1
                
                # Print full packet hex dump
                hex_dump = ' '.join(f'{b:02x}' for b in buf)
                print(f"Packet #{packet_counter}: {hex_dump}")
                
                # Print decoded controls
                print(f"  Controls: R:{buf[2]} P:{buf[3]} T:{buf[4]} Y:{buf[5]}")
                
                # Print flags
                flags6 = buf[6]
                flags7 = buf[7]
                flags_desc = []
                if flags6 & 0x01: flags_desc.append("TAKEOFF")
                if flags6 & 0x02: flags_desc.append("LAND")
                if flags6 & 0x04: flags_desc.append("STOP")
                if flags7 & 0x01: flags_desc.append("HEADLESS")
                if flags7 & 0x04: flags_desc.append("RECORD")
                
                print(f"  Flags: {flags_desc}")
                print(f"  Checksum: 0x{buf[18]:02x}")
                print()
                
            time.sleep(interval)

    def stop_loop(self):
        self.running = False

    def toggle_debug(self):
        """Toggle debug packet logging"""
        self.debug_packets = not self.debug_packets
        return self.debug_packets


def ui_loop(stdscr, controller):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.keypad(True)
    help_msg = "W/S=throttle  A/D=yaw  Arrows=pitch/roll  T=takeoff  L=land  Q=quit"
    help_msg2 = "R=record  F=debug packets  X=sensitivity mode"

    # direction states and last-press timestamps
    throttle_dir = yaw_dir = pitch_dir = roll_dir = 0
    throttle_ts = yaw_ts = pitch_ts = roll_ts = 0.0
    PRESS_THRESHOLD = 0.4  # threshold for key being held (increased from 0.2)

    prev_time = time.time()
    debug_enabled = False
    sensitivity_mode = 0  # 0=normal, 1=precise, 2=aggressive
    sensitivity_labels = ["Normal", "Precise", "Aggressive"]

    while controller.running:
        now = time.time()
        dt  = now - prev_time
        prev_time = now

        c = stdscr.getch()
        if c in (ord('q'), ord('Q')):
            controller.stop_loop()
            break

        elif c in (ord('t'), ord('T')):
            controller.takeoff = True
        elif c in (ord('l'), ord('L')):
            controller.land = True
        elif c in (ord('r'), ord('R')):
            controller.record = 1 if controller.record == 0 else 0
        elif c in (ord('f'), ord('F')):
            debug_enabled = controller.toggle_debug()
        elif c in (ord('x'), ord('X')):
            # Toggle sensitivity mode
            sensitivity_mode = (sensitivity_mode + 1) % 3
            
            # Apply sensitivity settings
            if sensitivity_mode == 0:  # Normal (using previous Precise settings)
                controller.accel_rate = 150.0
                controller.decel_rate = 350.0
                controller.expo_factor = 0.5
                controller.immediate_response = 3.0
            elif sensitivity_mode == 1:  # Very Precise (even slower/more precise)
                controller.accel_rate = 100.0
                controller.decel_rate = 400.0
                controller.expo_factor = 0.3
                controller.immediate_response = 1.5
            else:  # Aggressive (unchanged)
                controller.accel_rate = 300.0
                controller.decel_rate = 280.0
                controller.expo_factor = 1.5
                controller.immediate_response = 15.0

        # throttle
        elif c in (ord('w'), ord('W')):
            throttle_dir = +1; throttle_ts = now
        elif c in (ord('s'), ord('S')):
            throttle_dir = -1; throttle_ts = now

        # yaw
        elif c in (ord('a'), ord('A')):
            yaw_dir = -1; yaw_ts = now
        elif c in (ord('d'), ord('D')):
            yaw_dir = +1; yaw_ts = now

        # pitch
        elif c == curses.KEY_UP:
            pitch_dir = +1; pitch_ts = now
        elif c == curses.KEY_DOWN:
            pitch_dir = -1; pitch_ts = now

        # roll
        elif c == curses.KEY_LEFT:
            roll_dir = -1; roll_ts = now
        elif c == curses.KEY_RIGHT:
            roll_dir = +1; roll_ts = now

        # decide if each axis is "still held"
        active_throttle = throttle_dir if (now - throttle_ts) < PRESS_THRESHOLD else 0
        active_yaw      = yaw_dir      if (now - yaw_ts)      < PRESS_THRESHOLD else 0
        active_pitch    = pitch_dir    if (now - pitch_ts)    < PRESS_THRESHOLD else 0
        active_roll     = roll_dir     if (now - roll_ts)     < PRESS_THRESHOLD else 0

        # apply acceleration / deceleration
        controller.update_axes(
            dt,
            active_throttle,
            active_yaw,
            active_pitch,
            active_roll
        )

        # Update the UI
        stdscr.clear()
        stdscr.addstr(0, 0,
            f"Throttle: {int(controller.throttle):3d}    "
            f"Yaw:      {int(controller.yaw):3d}")
        stdscr.addstr(1, 0,
            f" Pitch:   {int(controller.pitch):3d}    "
            f"Roll:     {int(controller.roll):3d}")
            
        # Add status flags to UI
        status_flags = [f"Mode: {sensitivity_labels[sensitivity_mode]}"]
        if controller.record: status_flags.append("RECORD")
        if debug_enabled: status_flags.append("DEBUG")
        status_str = " | ".join(status_flags)
        stdscr.addstr(2, 0, f"Status: {status_str}")
            
        stdscr.addstr(4, 0, help_msg)
        stdscr.addstr(5, 0, help_msg2)
        stdscr.refresh()

        # small sleep to cap UI frame-rate
        time.sleep(0.02)


def main():
    parser = argparse.ArgumentParser(description="FH‐drone teleop interface")
    parser.add_argument("--drone-ip",    type=str, default="172.16.10.1", help="Drone UDP IP address")
    parser.add_argument("--control-port", type=int, default=8080, help="Drone control port")
    parser.add_argument("--rate",         type=float, default=20.0, help="Control packets per second")
    args = parser.parse_args()

    controller = DroneController(args.drone_ip, args.control_port)
    sender = threading.Thread(
        target=controller.send_loop,
        args=(1.0 / args.rate,),
        daemon=True
    )
    sender.start()

    try:
        curses.wrapper(ui_loop, controller)
    except KeyboardInterrupt:
        pass

    controller.stop_loop()
    sender.join()


if __name__ == "__main__":
    main()
