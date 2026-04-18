from __future__ import annotations

from models.base_rc import BaseRCModel
from models.control_profile import ControlProfile
from models.stick_range import StickRange
from control.strategies import IncrementalStrategy


class WifiUavRcModel(BaseRCModel):
    """
    RC model for toy drones that use the "WiFi UAV" mobile app (E58, LH-X20, …).

    RC rate needs to be 50 - 80 Hz to work well.

    Observations from packet captures:

    • All 4 stick axes sit at 0x7F (127) when centred.
    • Min / max values hover around 0x3F (63) and 0xBF (191).
      That is the default range we expose to the user code, but it can
      be tuned per drone via STICK_RANGE.
    """

    #            min, mid, max
    # STICK_RANGE = StickRange(0, 128, 255)
    STICK_RANGE = StickRange(40, 128, 220)

    PRESETS = {
        # name         accel   decel  expo  immediate-boost
        "normal":     ControlProfile("normal",     2.0, 4.0, 0.5, 0.02),
        "precise":    ControlProfile("precise",    1.2, 5.0, 0.3, 0.01),
        "aggressive": ControlProfile("aggressive", 4.0, 3.0, 1.2, 0.10),
    }

    def __init__(self, profile: str | ControlProfile = "normal") -> None:
        super().__init__(stick_range=self.STICK_RANGE, profile=profile)

        self.strategy = IncrementalStrategy()

        # one-shot flags
        self.takeoff_flag     = False
        self.land_flag        = False
        self.stop_flag        = False
        self.calibration_flag = False
        self.headless_flag    = False

        # track last motion direction for each axis
        self.last_throttle_dir = 0
        self.last_yaw_dir      = 0
        self.last_pitch_dir    = 0
        self.last_roll_dir     = 0

    # ------------------------------------------------------------------ #
    # BaseRCModel API
    # ------------------------------------------------------------------ #
    def update(self, dt, axes):          # type: ignore[override]
        self.strategy.update(self, dt, axes)

    def takeoff(self):
        self.takeoff_flag = True

    def land(self):
        """Request the app's normal land / descend action."""
        self.land_flag = True

    def emergency_stop(self):
        """Immediate motor stop, distinct from the normal land action."""
        self.stop_flag = True

    # unsupported – always returns 0
    def toggle_record(self):             # type: ignore[override]
        return 0

    def get_control_state(self):
        return {
            "throttle":  self.throttle,
            "yaw":       self.yaw,
            "pitch":     self.pitch,
            "roll":      self.roll,
            "headless":  self.headless_flag,
        }

    def set_strategy(self, strategy) -> None:
        self.strategy = strategy
