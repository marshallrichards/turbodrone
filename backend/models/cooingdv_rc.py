"""
RC Model for Cooingdv drones (RC UFO, KY UFO, E88 Pro, etc.)

These drones use the cooingdv publisher's mobile apps and communicate
via UDP on port 7099 with RTSP video on port 7070.

Key features:
- Soft landing (distinct from emergency stop)
- Headless mode
- Flip/somersault capability
- Gyro calibration
"""

from __future__ import annotations

from models.base_rc import BaseRCModel
from models.control_profile import ControlProfile
from models.stick_range import StickRange
from control.strategies import IncrementalStrategy


class CooingdvRcModel(BaseRCModel):
    """
    RC model for drones using cooingdv publisher apps (RC UFO, KY UFO, E88 Pro).

    Protocol details from decompiled apps:
    - Stick center: 128 (0x80)
    - Safe operating range: 50-200 (apps use these bounds)
    - The stock apps send control updates every 50 ms (about 20 Hz)
    - The CooingDV family has at least two packet variants: short "TC" and
      extended "GL". This model exposes the shared high-level commands while
      the protocol adapter maps them onto the correct flag layout.
    """

    # Stick range from decompiled FlyController.java
    # Center at 128, safe bounds 50-200 (apps clamp to these)
    STICK_RANGE = StickRange(50, 128, 200)

    PRESETS = {
        # name         accel   decel  expo  immediate-boost
        "normal":     ControlProfile("normal",     2.0, 4.0, 0.5, 0.02),
        "precise":    ControlProfile("precise",    1.2, 5.0, 0.3, 0.01),
        "aggressive": ControlProfile("aggressive", 4.0, 3.0, 1.2, 0.10),
    }

    def __init__(self, profile: str | ControlProfile = "normal") -> None:
        super().__init__(stick_range=self.STICK_RANGE, profile=profile)

        self.strategy = IncrementalStrategy()

        # One-shot command flags
        self.takeoff_flag = False
        self.land_flag = False          # Soft landing (0x02)
        self.stop_flag = False          # Emergency stop (0x04)
        self.flip_flag = False          # Flip/somersault (0x08)
        self.headless_flag = False      # Headless mode (0x10) - toggle state
        self.calibration_flag = False   # Gyro calibration (0x80)

        # Track last motion direction for each axis
        self.last_throttle_dir = 0
        self.last_yaw_dir = 0
        self.last_pitch_dir = 0
        self.last_roll_dir = 0

    # ------------------------------------------------------------------ #
    # BaseRCModel API
    # ------------------------------------------------------------------ #
    def update(self, dt, axes):
        self.strategy.update(self, dt, axes)

    def takeoff(self):
        """Initiate takeoff sequence."""
        self.takeoff_flag = True

    def land(self):
        """
        Initiate soft landing - gradual descent.
        
        This is distinct from emergency_stop() which cuts motors immediately.
        The drone will descend gracefully and land.
        """
        self.land_flag = True

    def emergency_stop(self):
        """
        Emergency motor cutoff - immediate stop.
        
        WARNING: This will cause the drone to fall from the sky!
        Use land() for normal landing operations.
        """
        self.stop_flag = True

    def flip(self):
        """Execute a 360-degree flip/somersault."""
        self.flip_flag = True

    def toggle_headless(self):
        """Toggle headless mode on/off."""
        self.headless_flag = not self.headless_flag

    def calibrate_gyro(self):
        """Initiate gyroscope calibration. Drone should be on flat surface."""
        self.calibration_flag = True

    def get_control_state(self):
        return {
            "throttle": self.throttle,
            "yaw": self.yaw,
            "pitch": self.pitch,
            "roll": self.roll,
            "headless": self.headless_flag,
        }

    def set_strategy(self, strategy) -> None:
        self.strategy = strategy

