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
    def toggle_record(self): ...
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

    def _update_axes_incremental(self, dt, dirs):
        # original WASD accel/decel code here (uses self.profile)
        ...

    def _update_axes_direct(self, axes):
        expo = getattr(self, "expo_factor", 0.0)
        for attr, value in axes.items():
            if expo:                              # optional expo curve
                sign  = 1 if value >= 0 else -1
                value = sign * (abs(value) ** (1 + expo))
            setattr(self, attr, self._scale_normalised(value))
