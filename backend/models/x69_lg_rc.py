from __future__ import annotations

from control.strategies import IncrementalStrategy
from models.base_rc import BaseRCModel
from models.control_profile import ControlProfile
from models.stick_range import StickRange


class X69LgRcModel(BaseRCModel):
    """High-level control state for the X69/LG UDP protocol."""

    STICK_RANGE = StickRange(0, 128, 255)

    PRESETS = {
        "normal": ControlProfile("normal", 1.8, 4.2, 0.45, 0.02),
        "precise": ControlProfile("precise", 1.0, 5.0, 0.30, 0.01),
        "aggressive": ControlProfile("aggressive", 3.5, 3.0, 1.00, 0.08),
    }

    def __init__(self, profile: str | ControlProfile = "normal") -> None:
        super().__init__(stick_range=self.STICK_RANGE, profile=profile)
        self.strategy = IncrementalStrategy()

        self.takeoff_flag = False
        self.land_flag = False
        self.stop_flag = False
        self.calibration_flag = False
        self.flip_flag = False

        # Frontend-compatible tilt state: 0=neutral, 1=down, 2=up.
        self.camera_tilt_state = 0

        # The stock X69 app has low/medium/full style stick scaling. Default to
        # medium because its Java default speed value is the middle tier.
        self.speed_index = 1

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

    def calibrate_gyro(self):
        self.calibration_flag = True

    def flip(self):
        self.flip_flag = True

    def set_camera_tilt_state(self, state: int) -> None:
        self.camera_tilt_state = max(0, min(2, int(state)))

    def set_speed_index(self, speed_index: int) -> None:
        self.speed_index = max(0, min(2, int(speed_index)))

    def get_control_state(self):
        return {
            "throttle": self.throttle,
            "yaw": self.yaw,
            "pitch": self.pitch,
            "roll": self.roll,
            "camera_tilt": self.camera_tilt_state,
            "speed_index": self.speed_index,
        }

    def set_strategy(self, strategy) -> None:
        self.strategy = strategy
