from dataclasses import dataclass

@dataclass
class ControlProfile:
    name: str
    accel_rate: float
    decel_rate: float
    expo_factor: float
    immediate_response: float

PRESETS = {
    "normal":     ControlProfile("normal",   150, 350, 0.5,  3),
    "precise":    ControlProfile("precise",  100, 400, 0.3,  1.5),
    "aggressive": ControlProfile("aggressive", 300, 280, 1.5, 15),
} 