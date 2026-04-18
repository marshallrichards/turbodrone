# S20 & S29 Controller model

from models.base_rc import BaseRCModel
from models.control_profile import ControlProfile
from control.strategies import IncrementalStrategy
from models.stick_range import StickRange

class S2xDroneModel(BaseRCModel):
    """Model for S2x protocol drones (S20, S29)"""
    
    STICK_RANGE = StickRange(60, 128, 200)   # ← tailorable per drone

    PRESETS = {
        "normal":     ControlProfile("normal",     2.08, 4.86, 0.5, 0.02),
        "precise":    ControlProfile("precise",    1.39, 5.56, 0.3, 0.01),
        "aggressive": ControlProfile("aggressive", 4.17, 3.89, 1.5, 0.11),
    }

    def __init__(self, profile: str | ControlProfile = "normal"):
        # BaseRCModel handles STICK_RANGE, presets and profile application
        super().__init__(stick_range=self.STICK_RANGE, profile=profile)

        self.strategy = IncrementalStrategy()   # default

        # one-shot flags
        self.takeoff_flag = False
        self.land_flag = False
        self.stop_flag = False
        self.headless_flag = False
        self.calibration_flag = False

        # misc
        self.speed = 20    # matches 0x14 from dumps

        # Track last direction for each axis
        self.last_throttle_dir = 0
        self.last_yaw_dir = 0
        self.last_pitch_dir = 0
        self.last_roll_dir = 0
    
    def update(self, dt, axes):
        self.strategy.update(self, dt, axes)
    
    def takeoff(self):
        """Set takeoff flag"""
        self.takeoff_flag = True
    
    def land(self):
        """
        Request the stock app's land action.

        In the HiTurbo app this shares the same one-shot flight bit as takeoff,
        so the protocol adapter maps the semantic intent rather than a distinct
        dedicated land bit.
        """
        self.land_flag = True

    def emergency_stop(self):
        """Set the emergency stop flag."""
        self.stop_flag = True
    
    def get_control_state(self):
        """Get current control state as a dict"""
        return {
            "throttle":  self.throttle,
            "yaw":       self.yaw,
            "pitch":     self.pitch,
            "roll":      self.roll,
        }

    def set_strategy(self, strategy) -> None:
        self.strategy = strategy
