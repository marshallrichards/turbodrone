from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar, Dict, List, Union, Optional

from models.stick_range import StickRange
from models.control_profile import ControlProfile


class BaseRCModel(ABC):
    """Common logic for every RC model / protocol implementation."""

    # Sub-classes **must** override or pass a StickRange explicitly.
    STICK_RANGE: ClassVar[Optional[StickRange]] = None

    # Generic fall-back presets – drones override with their own set
    PRESETS: ClassVar[Dict[str, ControlProfile]] = {
        "normal":     ControlProfile("normal",     1.5,  2.5, 0.5, 0.02),
        "precise":    ControlProfile("precise",    1.0,  3.0, 0.3, 0.01),
        "aggressive": ControlProfile("aggressive", 3.0,  2.0, 1.5, 0.10),
    }
    SENSITIVITY_SEQ: ClassVar[List[str]] = ["normal", "precise", "aggressive"]

    # -----------------------------------------------------------------
    def __init__(
        self,
        stick_range: Optional[StickRange] = None,
        profile: Union[str, ControlProfile] = "normal",
    ) -> None:
        # ----- enforce STICK_RANGE -----------------------------------
        if stick_range is None:
            stick_range = self.__class__.STICK_RANGE
        if stick_range is None:
            raise TypeError(
                f"{self.__class__.__name__} must define STICK_RANGE "
                "or pass stick_range to BaseRCModel.__init__()"
            )
        # -------------------------------------------------------------

        if isinstance(profile, str):
            if profile not in self.PRESETS:
                raise ValueError(f"Unknown profile '{profile}'")
            profile = self.PRESETS[profile]

        self.range = stick_range
        self.min_control_value = float(stick_range.min_val)
        self.center_value      = float(stick_range.mid_val)
        self.max_control_value = float(stick_range.max_val)

        self._apply_profile(profile)

        # axes start centred
        self.throttle = self.yaw = self.pitch = self.roll = self.center_value

    # ----- API that concrete models MUST still implement --------------
    @abstractmethod
    def update(self, dt, axes): ...
    @abstractmethod
    def takeoff(self): ...
    @abstractmethod
    def land(self): ...
    @abstractmethod
    def get_control_state(self): ...

    # ----- shared helpers ---------------------------------------------
    def set_profile(self, name: str) -> None:
        if name not in self.PRESETS:
            raise ValueError(f"Unknown profile '{name}'")
        self._apply_profile(self.PRESETS[name])

    def set_sensitivity(self, preset: int) -> None:
        idx = preset % len(self.SENSITIVITY_SEQ)
        self.set_profile(self.SENSITIVITY_SEQ[idx])

    def set_strategy(self, strategy) -> None:
        self.strategy = strategy

    # -----------------------------------------------------------------
    def _apply_profile(self, profile: ControlProfile) -> None:
        half_range = self.max_control_value - self.center_value
        full_range = self.max_control_value - self.min_control_value

        self.profile            = profile
        self.accel_rate         = profile.accel_ratio     * half_range
        self.decel_rate         = profile.decel_ratio     * half_range
        self.expo_factor        = profile.expo_factor
        self.immediate_response = profile.immediate_ratio * full_range

    # existing helper (unchanged)
    def _scale_normalised(self, value: float) -> float:
        """
        Map a normalised [-1 … +1] input to raw protocol units using
        the model's StickRange.
        """
        if value >= 0:
            return self.center_value + value * (self.max_control_value - self.center_value)
        return self.center_value + value * (self.center_value - self.min_control_value)

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
        Apply the shared incremental stick logic used by keyboard-style controls.

        Pitch and roll get a small immediate boost when the pilot reverses
        direction so the craft feels less sluggish during lateral movement.
        """
        for attr, direction, boost_enabled in (
            ("throttle", throttle_dir, False),
            ("yaw", yaw_dir, False),
            ("pitch", pitch_dir, True),
            ("roll", roll_dir, True),
        ):
            cur = getattr(self, attr)
            last_dir_attr = f"last_{attr}_dir"
            last_dir = getattr(self, last_dir_attr, 0)

            if direction > 0:
                if boost_enabled and last_dir <= 0:
                    cur += min(
                        self.max_control_value - cur,
                        self.immediate_response,
                    )
                dist = self.max_control_value - cur
                accel = self.accel_rate * dt * (
                    1 + self.expo_factor * dist
                    / (self.max_control_value - self.center_value)
                )
                new = min(self.max_control_value, cur + accel)

            elif direction < 0:
                if boost_enabled and last_dir >= 0:
                    cur -= min(
                        cur - self.min_control_value,
                        self.immediate_response,
                    )
                dist = cur - self.min_control_value
                accel = self.accel_rate * dt * (
                    1 + self.expo_factor * dist
                    / (self.center_value - self.min_control_value)
                )
                new = max(self.min_control_value, cur - accel)

            else:
                if cur > self.center_value:
                    dist = cur - self.center_value
                    decel = self.decel_rate * dt * (
                        1 + 0.5 * dist
                        / (self.max_control_value - self.center_value)
                    )
                    new = max(self.center_value, cur - decel)
                elif cur < self.center_value:
                    dist = self.center_value - cur
                    decel = self.decel_rate * dt * (
                        1 + 0.5 * dist
                        / (self.center_value - self.min_control_value)
                    )
                    new = min(self.center_value, cur + decel)
                else:
                    new = cur

            setattr(self, attr, new)
            setattr(self, last_dir_attr, direction)

    def _update_axes_direct(self, axes):
        expo = getattr(self, "expo_factor", 0.0)
        for attr, value in axes.items():
            if expo:                              # optional expo curve
                sign  = 1 if value >= 0 else -1
                value = sign * (abs(value) ** (1 + expo))
            setattr(self, attr, self._scale_normalised(value))
