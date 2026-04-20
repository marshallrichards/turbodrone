from __future__ import annotations

from typing import Optional

import numpy as np

from e88.drone import E88Drone


class Drone:
    def __init__(self, protocol: str = "E88") -> None:
        self._protocol = protocol.upper()
        self._impl = self._create_impl(self._protocol)

    def connect(self) -> None:
        self._impl.connect()

    def close(self) -> None:
        self._impl.close()

    def get_frame(self, timeout: Optional[float] = None) -> Optional[np.ndarray]:
        return self._impl.get_frame(timeout=timeout)

    def send_cmd(self, *, roll: float = 0.0, pitch: float = 0.0, yaw: float = 0.0, throttle: float = 50.0) -> None:
        self._impl.send_cmd(roll=roll, pitch=pitch, yaw=yaw, throttle=throttle)

    def set_sticks_raw(self, *, roll: Optional[int] = None, pitch: Optional[int] = None, throttle: Optional[int] = None, yaw: Optional[int] = None) -> None:
        self._impl.set_sticks_raw(roll=roll, pitch=pitch, throttle=throttle, yaw=yaw)

    def takeoff(self) -> None:
        self._impl.takeoff()

    def land(self) -> None:
        self._impl.land()

    def calibrate(self) -> None:
        self._impl.calibrate()

    def flip(self) -> None:
        self._impl.flip()

    def toggle_headless(self) -> None:
        self._impl.toggle_headless()

    def switch_camera(self, cam: int) -> None:
        self._impl.switch_camera(cam)

    @staticmethod
    def _create_impl(protocol: str):
        if protocol == "E88":
            return E88Drone()
        raise ValueError(f"Unsupported protocol: {protocol}")
