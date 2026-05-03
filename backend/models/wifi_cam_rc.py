"""
RC model for WiFi_CAM native UDP drones.

The stock app uses the same centered 0x80 stick semantics as the CooingDV
family, but sends raw command bytes to a separate UDP command port.
"""

from __future__ import annotations

from control.strategies import IncrementalStrategy
from models.base_rc import BaseRCModel
from models.control_profile import ControlProfile
from models.stick_range import StickRange


class WifiCamRcModel(BaseRCModel):
    """High-level control state for WiFi_CAM drones."""

    STICK_RANGE = StickRange(50, 128, 200)

    PRESETS = {
        "normal": ControlProfile("normal", 2.0, 4.0, 0.5, 0.02),
        "precise": ControlProfile("precise", 1.2, 5.0, 0.3, 0.01),
        "aggressive": ControlProfile("aggressive", 4.0, 3.0, 1.2, 0.10),
    }

    def __init__(self, profile: str | ControlProfile = "normal") -> None:
        super().__init__(stick_range=self.STICK_RANGE, profile=profile)
        self.strategy = IncrementalStrategy()

        self.takeoff_flag = False
        self.land_flag = False
        self.stop_flag = False
        self.flip_flag = False
        self.headless_flag = False
        self.altitude_hold_flag = False
        self.calibration_flag = False

        self.last_throttle_dir = 0
        self.last_yaw_dir = 0
        self.last_pitch_dir = 0
        self.last_roll_dir = 0

    def update(self, dt, axes):
        self.strategy.update(self, dt, axes)

    def takeoff(self):
        self.takeoff_flag = True

    def land(self):
        self.land_flag = True

    def emergency_stop(self):
        self.stop_flag = True

    def flip(self):
        self.flip_flag = True

    def toggle_headless(self):
        self.headless_flag = not self.headless_flag

    def toggle_altitude_hold(self):
        self.altitude_hold_flag = not self.altitude_hold_flag

    def calibrate_gyro(self):
        self.calibration_flag = True

    def get_control_state(self):
        return {
            "throttle": self.throttle,
            "yaw": self.yaw,
            "pitch": self.pitch,
            "roll": self.roll,
            "headless": self.headless_flag,
            "altitude_hold": self.altitude_hold_flag,
        }

    def set_strategy(self, strategy) -> None:
        self.strategy = strategy
