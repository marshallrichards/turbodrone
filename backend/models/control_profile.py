from dataclasses import dataclass

@dataclass(frozen=True)
class ControlProfile:
    """
    Profile parameters expressed as *ratios* of the stick range.
      accel_ratio       – fraction of half-range per second
      decel_ratio       – fraction of half-range per second
      expo_factor       – dimension-less (unchanged)
      immediate_ratio   – fraction of full range for one-shot boost
    """
    name: str
    accel_ratio: float
    decel_ratio: float
    expo_factor: float = 0.0
    immediate_ratio: float = 0.0
