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

        self.running = True

    def build_packet(self):
        pkt = bytearray(8)
        pkt[0] = 0x66                   # header
        pkt[1] = self.yaw      & 0xFF
        pkt[2] = self.throttle & 0xFF
        pkt[3] = self.pitch    & 0xFF
        pkt[4] = self.roll     & 0xFF

        # flags byte: bit0=takeoff, bit1=land, bit2=stop, bit4=headless, bit6=alive, bit7=calibration
        flags  = 0x40                # always set "alive" bit
        flags |= 1 if self.takeoff     else 0
        flags |= 2 if self.land        else 0
        flags |= 4 if self.stop        else 0
        flags |= 16 if self.headless   else 0
        flags |= 128 if self.calibration else 0

        pkt[5] = flags & 0xFF

        # simple XOR checksum over bytes 1–5
        chk = flags ^ pkt[1] ^ pkt[2] ^ pkt[3] ^ pkt[4]
        pkt[6] = chk & 0xFF

        pkt[7] = 0x99                # footer

        # clear one-shot flags
        self.takeoff = False
        self.land    = False
        self.stop    = False

        return pkt

    def send_loop(self, interval=0.05):
        """Continuously build & send control packets every interval seconds."""
        while self.running:
            pkt = self.build_packet()
            self.sock.sendto(pkt, (self.drone_ip, self.control_port))
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
            controller.land = True
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
