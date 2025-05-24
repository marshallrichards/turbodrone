from dataclasses import dataclass

@dataclass(frozen=True)
class StickRange:
    """Drone-specific raw protocol limits."""
    min_val: float   # e.g. 60
    mid_val: float   # e.g. 128
    max_val: float   # e.g. 200