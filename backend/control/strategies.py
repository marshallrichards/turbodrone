from abc import ABC, abstractmethod
from typing import Dict

class ControlStrategy(ABC):
    """Maps user intent → raw stick values inside the RC model."""

    @abstractmethod
    def update(self, model, dt: float, axes: Dict[str, float]) -> None:
        """`axes` always ranges  -1 … +1  for throttle, yaw, pitch, roll"""
        ...

# 1. Same behaviour you already have for the CLI keyboard
class IncrementalStrategy(ControlStrategy):
    def update(self, model, dt, axes):
        # axes entries are  -1, 0, +1  (discrete keys)
        model._update_axes_incremental(dt, axes)

# 2. Direct mapping for joysticks / Gamepad API
class DirectStrategy(ControlStrategy):
    """
    Absolute mode: normalised stick position is mapped directly
    to the drone's raw range (optionally with expo curve).
    """
    def update(self, model, dt, axes):
        expo = getattr(model, "expo_factor", 0.0)
        for axis, v in axes.items():
            # optional expo curve
            if expo:
                sign = 1 if v >= 0 else -1
                v = sign * (abs(v) ** (1 + expo))
            setattr(model, axis, model._scale_normalised(v)) 