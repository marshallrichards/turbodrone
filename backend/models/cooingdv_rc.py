"""
RC Model for Cooingdv drones (RC UFO, KY UFO, E88 Pro, etc.)

These drones use the cooingdv publisher's mobile apps and communicate
via UDP on port 7099 with RTSP video on port 7070.

Key features:
- Soft landing (distinct from emergency stop)
- Headless mode
- Flip/somersault capability
- Gyro calibration
"""

from __future__ import annotations

from models.base_rc import BaseRCModel
from models.control_profile import ControlProfile
from models.stick_range import StickRange
from control.strategies import IncrementalStrategy


class CooingdvRcModel(BaseRCModel):
    """
    RC model for drones using cooingdv publisher apps (RC UFO, KY UFO, E88 Pro).

    Protocol details from decompiled apps:
    - Stick center: 128 (0x80)
    - Safe operating range: 50-200 (apps use these bounds)
    - Control packet rate: 30-80 Hz recommended

    Command flags (byte 5 in packet):
    - 0x01: Takeoff
    - 0x02: Soft Land (gradual descent)
    - 0x04: Emergency Stop (immediate motor cutoff)
    - 0x08: Flip/Somersault
    - 0x10: Headless Mode toggle
    - 0x80: Gyro Calibration
    """

    # Stick range from decompiled FlyController.java
    # Center at 128, safe bounds 50-200 (apps clamp to these)
    STICK_RANGE = StickRange(50, 128, 200)

    PRESETS = {
        # name         accel   decel  expo  immediate-boost
        "normal":     ControlProfile("normal",     2.0, 4.0, 0.5, 0.02),
        "precise":    ControlProfile("precise",    1.2, 5.0, 0.3, 0.01),
        "aggressive": ControlProfile("aggressive", 4.0, 3.0, 1.2, 0.10),
    }

    def __init__(self, profile: str | ControlProfile = "normal") -> None:
        super().__init__(stick_range=self.STICK_RANGE, profile=profile)

        self.strategy = IncrementalStrategy()

        # One-shot command flags
        self.takeoff_flag = False
        self.land_flag = False          # Soft landing (0x02)
        self.stop_flag = False          # Emergency stop (0x04)
        self.flip_flag = False          # Flip/somersault (0x08)
        self.headless_flag = False      # Headless mode (0x10) - toggle state
        self.calibration_flag = False   # Gyro calibration (0x80)

        # Track last motion direction for each axis
        self.last_throttle_dir = 0
        self.last_yaw_dir = 0
        self.last_pitch_dir = 0
        self.last_roll_dir = 0

    # ------------------------------------------------------------------ #
    # BaseRCModel API
    # ------------------------------------------------------------------ #
    def update(self, dt, axes):
        self.strategy.update(self, dt, axes)

    def takeoff(self):
        """Initiate takeoff sequence."""
        self.takeoff_flag = True

    def land(self):
        """
        Initiate soft landing - gradual descent.
        
        This is distinct from emergency_stop() which cuts motors immediately.
        The drone will descend gracefully and land.
        """
        self.land_flag = True

    def emergency_stop(self):
        """
        Emergency motor cutoff - immediate stop.
        
        WARNING: This will cause the drone to fall from the sky!
        Use land() for normal landing operations.
        """
        self.stop_flag = True

    def flip(self):
        """Execute a 360-degree flip/somersault."""
        self.flip_flag = True

    def toggle_headless(self):
        """Toggle headless mode on/off."""
        self.headless_flag = not self.headless_flag

    def calibrate_gyro(self):
        """Initiate gyroscope calibration. Drone should be on flat surface."""
        self.calibration_flag = True

    def get_control_state(self):
        return {
            "throttle": self.throttle,
            "yaw": self.yaw,
            "pitch": self.pitch,
            "roll": self.roll,
            "headless": self.headless_flag,
        }

    def set_strategy(self, strategy) -> None:
        self.strategy = strategy

    # ------------------------------------------------------------------ #
    # Helpers - same incremental stick logic as other implementations
    # ------------------------------------------------------------------ #
    def _update_axes_incremental(self, dt, axes):
        self.update_axes(
            dt,
            axes.get("throttle", 0),
            axes.get("yaw", 0),
            axes.get("pitch", 0),
            axes.get("roll", 0),
        )

    def update_axes(self, dt, throttle_dir, yaw_dir, pitch_dir, roll_dir):
        """
        Blend acceleration / deceleration with an 'immediate jump' when the
        pilot suddenly changes direction, identical to the S2x implementation.
        """
        for attr, direction, boost_enabled in (
            ('throttle', throttle_dir, False),
            ('yaw', yaw_dir, False),
            ('pitch', pitch_dir, True),
            ('roll', roll_dir, True),
        ):
            cur = getattr(self, attr)
            last_dir_attr = f"last_{attr}_dir"
            last_dir = getattr(self, last_dir_attr)

            if direction > 0:
                if boost_enabled and last_dir <= 0:
                    cur += min(
                        self.max_control_value - cur, self.immediate_response
                    )
                dist = self.max_control_value - cur
                accel = self.accel_rate * dt * (
                    1 + self.expo_factor * dist /
                    (self.max_control_value - self.center_value)
                )
                new = min(self.max_control_value, cur + accel)

            elif direction < 0:
                if boost_enabled and last_dir >= 0:
                    cur -= min(
                        cur - self.min_control_value, self.immediate_response
                    )
                dist = cur - self.min_control_value
                accel = self.accel_rate * dt * (
                    1 + self.expo_factor * dist /
                    (self.center_value - self.min_control_value)
                )
                new = max(self.min_control_value, cur - accel)

            else:  # return to centre
                if cur > self.center_value:
                    dist = cur - self.center_value
                    decel = self.decel_rate * dt * (
                        1 + 0.5 * dist /
                        (self.max_control_value - self.center_value)
                    )
                    new = max(self.center_value, cur - decel)
                elif cur < self.center_value:
                    dist = self.center_value - cur
                    decel = self.decel_rate * dt * (
                        1 + 0.5 * dist /
                        (self.center_value - self.min_control_value)
                    )
                    new = min(self.center_value, cur + decel)
                else:
                    new = cur

            setattr(self, attr, new)
            setattr(self, last_dir_attr, direction)

