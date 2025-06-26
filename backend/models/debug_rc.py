from __future__ import annotations
import logging
from models.base_rc import BaseRCModel
from models.stick_range import StickRange

log = logging.getLogger(__name__)

class DebugRcModel(BaseRCModel):
    """Dummy RC model for debugging purposes."""

    def __init__(self):
        # Using a default stick range, can be customized if needed
        super().__init__(stick_range=StickRange(min_val=0, mid_val=128, max_val=255))
        log.info("Debug RC model initialized.")
        self.throttle = self.yaw = self.pitch = self.roll = 128

    def update(self, dt, axes):
        # This model doesn't need to update state over time, but it must
        # be implemented to satisfy the abstract base class.
        pass

    def get_control_state(self):
        # Return a dictionary of the current control values.
        # This is what gets sent to the protocol adapter.
        return {
            "throttle": self.throttle,
            "yaw": self.yaw,
            "pitch": self.pitch,
            "roll": self.roll,
        }

    def set_throttle(self, value: int):
        log.debug(f"Debug: set_throttle({value})")
        self.throttle = value

    def set_yaw(self, value: int):
        log.debug(f"Debug: set_yaw({value})")
        self.yaw = value

    def set_pitch(self, value: int):
        log.debug(f"Debug: set_pitch({value})")
        self.pitch = value

    def set_roll(self, value: int):
        log.debug(f"Debug: set_roll({value})")
        self.roll = value

    def takeoff(self):
        log.info("Debug: takeoff()")

    def land(self):
        log.info("Debug: land()") 