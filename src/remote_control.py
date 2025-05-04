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

        # stick midpoints = 128
        self.yaw      = 128
        self.throttle = 128
        self.pitch    = 128
        self.roll     = 128

        # one-shot flags
        self.takeoff     = False
        self.land        = False
        self.stop        = False
        self.headless    = False
        self.calibration = False

        self.speed   = 20    # matches 0x14 from dumps
        self.record  = 0     # bit 2 in byte 7
        self.rocker  = 0     # bit 3 in byte 7

        self.running = True

    def build_packet_hy(self):
        pkt = bytearray(20)

        # 0–1: header & speed
        pkt[0] = 0x66
        pkt[1] = self.speed & 0xFF

        # 2–3: yaw (horiz) / throttle (vert)
        pkt[2] = self.yaw      & 0xFF
        pkt[3] = self.throttle & 0xFF

        # 4–5: pitch / roll
        pkt[4] = self.pitch & 0xFF
        pkt[5] = self.roll  & 0xFF

        # 6: takeoff / land / stop / calibration
        flags6 = 0
        flags6 |= 0x01 if self.takeoff     else 0
        flags6 |= 0x02 if self.land        else 0
        flags6 |= 0x04 if self.stop        else 0
        flags6 |= (self.calibration << 2)   # 0x04 if calibration
        pkt[6] = flags6

        # 7: headless + alive + record + rocker
        flags7 = 0
        flags7 |= 0x01 if self.headless else 0
        flags7 |= 0x02                 # ALWAYS the "alive" bit
        flags7 |= (self.record << 2)
        flags7 |= (self.rocker << 3)
        pkt[7] = flags7

        # 8–17 = 0

        # 18 = XOR of bytes 2–17
        chk = 0
        for i in range(2, 18):
            chk ^= pkt[i]
        pkt[18] = chk & 0xFF

        # 19 = footer
        pkt[19] = 0x99

        # clear one-shot flags
        self.takeoff = self.land = self.stop = False

        return pkt

    def send_loop(self, interval=0.05):
        while self.running:
            buf = self.build_packet_hy()
            self.sock.sendto(buf, (self.drone_ip, self.control_port))
            time.sleep(interval)

    def stop_loop(self):
        self.running = False


def ui_loop(stdscr, controller):
    # configure curses
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.keypad(True)

    help_msg = "W/S=throttle  A/D=yaw  Arrows=pitch/roll  T=takeoff  L=land  Q=quit"

    while controller.running:
        c = stdscr.getch()
        if c in (ord('q'), ord('Q')):
            controller.stop_loop()
            break
        elif c in (ord('t'), ord('T')):
            controller.takeoff = True
        elif c in (ord('l'), ord('L')):
            controller.stop = True
        # throttle: W / S
        elif c in (ord('w'), ord('W')):
            controller.throttle = min(255, controller.throttle + 5)
        elif c in (ord('s'), ord('S')):
            controller.throttle = max(0,   controller.throttle - 5)
        # yaw: A / D
        elif c in (ord('a'), ord('A')):
            controller.yaw = max(0,   controller.yaw - 5)
        elif c in (ord('d'), ord('D')):
            controller.yaw = min(255, controller.yaw + 5)
        # pitch: Up / Down arrows
        elif c == curses.KEY_UP:
            controller.pitch = min(255, controller.pitch + 5)
        elif c == curses.KEY_DOWN:
            controller.pitch = max(0,   controller.pitch - 5)
        # roll: Left / Right arrows
        elif c == curses.KEY_LEFT:
            controller.roll = max(0,   controller.roll - 5)
        elif c == curses.KEY_RIGHT:
            controller.roll = min(255, controller.roll + 5)

        # redraw
        stdscr.clear()
        stdscr.addstr(0, 0, f"Throttle: {controller.throttle:3d}    Yaw:   {controller.yaw:3d}")
        stdscr.addstr(1, 0, f" Pitch:   {controller.pitch:3d}    Roll:  {controller.roll:3d}")
        stdscr.addstr(3, 0, help_msg)
        stdscr.refresh()
        time.sleep(0.02)


def main():
    parser = argparse.ArgumentParser(description="FH‐drone teleop interface")
    parser.add_argument("--drone-ip",    required=True, help="Drone UDP IP address")
    parser.add_argument("--control-port", type=int, default=8080,    help="Drone control port")
    parser.add_argument("--rate",         type=float, default=20.0,   help="Control packets per second")
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
