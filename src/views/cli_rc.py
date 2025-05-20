# Remote Control using curses cli interface

import curses
import time
from services.flight_controller import FlightController

class CLIView:
    """Curses-based CLI view for drone remote control"""
    
    def __init__(self, flight_controller):
        self.controller = flight_controller
        self.sensitivity_mode = 0  # 0=normal, 1=precise, 2=aggressive
        self.sensitivity_labels = ["Normal", "Precise", "Aggressive"]
        self.PRESS_THRESHOLD = 0.4  # threshold for key being held

    def run(self):
        """Start the CLI interface"""
        curses.wrapper(self._ui_loop)
        
    def _ui_loop(self, stdscr):
        """Main curses UI loop"""
        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.keypad(True)
        help_msg = "W/S=throttle  A/D=yaw  Arrows=pitch/roll  T=takeoff  L=land  Q=quit"
        help_msg2 = "R=record  F=debug packets  X=sensitivity mode"

        # direction states and last-press timestamps
        throttle_dir = yaw_dir = pitch_dir = roll_dir = 0
        throttle_ts = yaw_ts = pitch_ts = roll_ts = 0.0

        prev_time = time.time()
        debug_enabled = False

        while self.controller.running:
            now = time.time()
            dt = now - prev_time
            prev_time = now

            c = stdscr.getch()
            if c in (ord('q'), ord('Q')):
                self.controller.stop()
                break

            elif c in (ord('t'), ord('T')):
                self.controller.model.takeoff()
            elif c in (ord('l'), ord('L')):
                self.controller.model.land()
            elif c in (ord('r'), ord('R')):
                self.controller.model.toggle_record()
            elif c in (ord('f'), ord('F')):
                debug_enabled = self.controller.protocol.toggle_debug()
            elif c in (ord('x'), ord('X')):
                # Toggle sensitivity mode
                self.sensitivity_mode = (self.sensitivity_mode + 1) % 3
                self.controller.model.set_sensitivity(self.sensitivity_mode)

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
            active_throttle = throttle_dir if (now - throttle_ts) < self.PRESS_THRESHOLD else 0
            active_yaw = yaw_dir if (now - yaw_ts) < self.PRESS_THRESHOLD else 0
            active_pitch = pitch_dir if (now - pitch_ts) < self.PRESS_THRESHOLD else 0
            active_roll = roll_dir if (now - roll_ts) < self.PRESS_THRESHOLD else 0

            # Update controller with current control directions
            self.controller.set_control_direction('throttle', active_throttle)
            self.controller.set_control_direction('yaw', active_yaw)
            self.controller.set_control_direction('pitch', active_pitch)
            self.controller.set_control_direction('roll', active_roll)

            # Update the UI
            state = self.controller.model.get_control_state()
            stdscr.clear()
            stdscr.addstr(0, 0,
                f"Throttle: {int(state['throttle']):3d}    "
                f"Yaw:      {int(state['yaw']):3d}")
            stdscr.addstr(1, 0,
                f" Pitch:   {int(state['pitch']):3d}    "
                f"Roll:     {int(state['roll']):3d}")
                
            # Add status flags to UI
            status_flags = [f"Mode: {self.sensitivity_labels[self.sensitivity_mode]}"]
            if state['recording']: status_flags.append("RECORD")
            if debug_enabled: status_flags.append("DEBUG")
            status_str = " | ".join(status_flags)
            stdscr.addstr(2, 0, f"Status: {status_str}")
                
            stdscr.addstr(4, 0, help_msg)
            stdscr.addstr(5, 0, help_msg2)
            stdscr.refresh()

            # small sleep to cap UI frame-rate
            time.sleep(0.01)
