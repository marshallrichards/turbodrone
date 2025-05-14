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
        self.accel_rate = 100.0   # when you hold a key
        self.decel_rate =  80.0   # when you release it

    def update_axes(self, dt, throttle_dir, yaw_dir, pitch_dir, roll_dir):
        """Apply acceleration or deceleration for each axis."""
        center = 128.0
        for attr, direction in (
            ('throttle', throttle_dir),
            ('yaw',      yaw_dir),
            ('pitch',    pitch_dir),
            ('roll',     roll_dir),
        ):
            cur = getattr(self, attr)
            if direction > 0:
                new = min(255.0, cur + self.accel_rate * dt)
            elif direction < 0:
                new = max(  0.0, cur - self.accel_rate * dt)
            else:
                # return to center
                if cur > center:
                    new = max(center, cur - self.decel_rate * dt)
                elif cur < center:
                    new = min(center, cur + self.decel_rate * dt)
                else:
                    new = cur
            setattr(self, attr, new)

    def build_packet_hy(self):
        pkt = bytearray(20)
        pkt[0] = 0x66
        pkt[1] = self.speed & 0xFF

        # Cast floats back to ints with CORRECTED ORDER
        pkt[2] = int(self.roll)     & 0xFF
        pkt[3] = int(self.pitch)    & 0xFF  
        pkt[4] = int(self.throttle) & 0xFF
        pkt[5] = int(self.yaw)      & 0xFF

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

    def send_loop(self, interval=0.05):
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
    help_msg2 = "R=record  F=debug packets"

    # direction states and last-press timestamps
    throttle_dir = yaw_dir = pitch_dir = roll_dir = 0
    throttle_ts = yaw_ts = pitch_ts = roll_ts = 0.0
    PRESS_THRESHOLD = 0.2  # threshold for key being held

    prev_time = time.time()
    debug_enabled = False

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
        status_flags = []
        if controller.record: status_flags.append("RECORD")
        if debug_enabled: status_flags.append("DEBUG")
        status_str = " | ".join(status_flags) if status_flags else "Normal mode"
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
