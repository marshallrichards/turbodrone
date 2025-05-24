from abc import ABC, abstractmethod
from models.stick_range import StickRange
from models.control_profile import ControlProfile, PRESETS

class BaseRCModel(ABC):
    """
    Base class for every RC model (protocol implementation).
    A concrete model passes its StickRange to super().__init__().
    """

    def __init__(self,
                 stick_range: StickRange,
                 profile: ControlProfile = PRESETS["normal"]):
        self.range  = stick_range
        self.profile = profile

        # raw limits derived from StickRange
        self.min_control_value = float(stick_range.min_val)
        self.center_value      = float(stick_range.mid_val)
        self.max_control_value = float(stick_range.max_val)

        # start each axis at centre (override in subclass if desired)
        self.throttle = self.yaw = self.pitch = self.roll = self.center_value

    # -------- abstract public API ----------------------------------
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
    @abstractmethod
    def set_sensitivity(self, preset): ...
    @abstractmethod
    def set_profile(self, name: str): ...
    @abstractmethod
    def set_strategy(self, strategy): ...

    # -------- helpers ----------------------------------------------
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
