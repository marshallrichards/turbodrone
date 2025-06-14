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
        self.land_flag = True

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

    # ------------------------------------------------------------------ #
    # helpers – same incremental stick logic as the S2x model
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
            ('yaw',      yaw_dir,      False),
            ('pitch',    pitch_dir,    True),
            ('roll',     roll_dir,     True),
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

            else:   # return to centre
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
