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
        self.record_state = 0  # bit 2 in byte 7

        # Track last direction for each axis
        self.last_throttle_dir = 0
        self.last_yaw_dir = 0
        self.last_pitch_dir = 0
        self.last_roll_dir = 0
    
    def update(self, dt, axes):
        self.strategy.update(self, dt, axes)
    
    def update_axes(self, dt, throttle_dir, yaw_dir, pitch_dir, roll_dir):
        """Apply acceleration or deceleration for each axis."""
        for attr, direction, boost_enabled in (
            ('throttle', throttle_dir, False),
            ('yaw',      yaw_dir,      False),
            ('pitch',    pitch_dir,    True),
            ('roll',     roll_dir,     True),  # Enable boost for roll and pitch
        ):
            cur = getattr(self, attr)
            last_dir_attr = f"last_{attr}_dir"
            last_dir = getattr(self, last_dir_attr)
            
            # Handle exponential control mapping
            if direction > 0:
                # Apply immediate boost on direction change
                if boost_enabled and last_dir <= 0:
                    jump = min(self.max_control_value - cur, self.immediate_response)
                    cur += jump
                
                # Calculate acceleration with exponential factor
                distance_to_max = self.max_control_value - cur
                accel = self.accel_rate * dt * (1 + self.expo_factor * distance_to_max / 
                                                (self.max_control_value - self.center_value))
                new = min(self.max_control_value, cur + accel)
                
            elif direction < 0:
                # Apply immediate boost on direction change
                if boost_enabled and last_dir >= 0:
                    jump = min(cur - self.min_control_value, self.immediate_response)
                    cur -= jump
                
                # Calculate acceleration with exponential factor
                distance_to_min = cur - self.min_control_value
                accel = self.accel_rate * dt * (1 + self.expo_factor * distance_to_min / 
                                               (self.center_value - self.min_control_value))
                new = max(self.min_control_value, cur - accel)
                
            else:
                # Return to center faster from extremes
                if cur > self.center_value:
                    # Exponential return to center
                    distance_from_center = cur - self.center_value
                    decel = self.decel_rate * dt * (1 + 0.5 * distance_from_center / 
                                                   (self.max_control_value - self.center_value))
                    new = max(self.center_value, cur - decel)
                elif cur < self.center_value:
                    # Exponential return to center
                    distance_from_center = self.center_value - cur
                    decel = self.decel_rate * dt * (1 + 0.5 * distance_from_center / 
                                                   (self.center_value - self.min_control_value))
                    new = min(self.center_value, cur + decel)
                else:
                    new = cur
                    
            # Store last direction for detecting direction changes
            setattr(self, last_dir_attr, direction)
            setattr(self, attr, new)
    
    def takeoff(self):
        """Set takeoff flag"""
        self.takeoff_flag = True
    
    def land(self):
        """Set land flag"""
        self.land_flag = True
    
    def toggle_record(self):
        """Toggle recording state"""
        self.record_state = 1 if self.record_state == 0 else 0
        return self.record_state
        
    def get_control_state(self):
        """Get current control state as a dict"""
        return {
            "throttle":  self.throttle,
            "yaw":       self.yaw,
            "pitch":     self.pitch,
            "roll":      self.roll,
            "recording": self.record_state > 0,
        }

    def set_strategy(self, strategy) -> None:
        self.strategy = strategy

    def _update_axes_incremental(self, dt, axes):
        self.update_axes(
            dt,
            axes.get("throttle", 0),
            axes.get("yaw",      0),
            axes.get("pitch",    0),
            axes.get("roll",     0),
        )