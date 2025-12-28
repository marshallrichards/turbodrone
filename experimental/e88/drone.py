from __future__ import annotations

import socket
import threading
import time
from typing import Optional

import numpy as np

from .config import E88Config
from .rc import E88RcPacketBuilder, E88RcState
from .video import E88VideoStream


class E88Drone:
    SOMERSAULT = 8
    HEADLESS = 16

    def __init__(self, config: Optional[E88Config] = None) -> None:
        self._config = config or E88Config()
        self._sock: Optional[socket.socket] = None
        self._builder = E88RcPacketBuilder()
        self._state = E88RcState()
        self._state_lock = threading.Lock()
        self._stop = threading.Event()
        self._control_thread: Optional[threading.Thread] = None
        self._video = E88VideoStream(self._config)

        self._headless = False
        self._flip_one_shot = False

    def connect(self, *, start_video: bool = True, start_control: bool = True) -> None:
        self._ensure_socket()
        self._send_raw(b"\x08\x01")
        if start_video:
            self._video.start()
        if start_control:
            self.start_control_loop()

    def close(self) -> None:
        self.stop_control_loop()
        self._video.stop()
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def start_control_loop(self) -> None:
        if self._control_thread and self._control_thread.is_alive():
            return
        self._stop.clear()
        self._control_thread = threading.Thread(target=self._control_loop, name="E88ControlLoop", daemon=True)
        self._control_thread.start()

    def stop_control_loop(self) -> None:
        self._stop.set()
        if self._control_thread:
            self._control_thread.join(timeout=1.0)

    def get_frame(self, timeout: Optional[float] = None) -> Optional[np.ndarray]:
        return self._video.get_frame(timeout=timeout)

    def set_sticks_raw(self, *, roll: Optional[int] = None, pitch: Optional[int] = None, throttle: Optional[int] = None, yaw: Optional[int] = None) -> None:
        with self._state_lock:
            if roll is not None:
                self._state.roll = int(max(0, min(255, roll)))
            if pitch is not None:
                self._state.pitch = int(max(0, min(255, pitch)))
            if throttle is not None:
                self._state.throttle = int(max(0, min(255, throttle)))
            if yaw is not None:
                self._state.yaw = int(max(0, min(255, yaw)))

    def send_cmd(self, *, roll: float = 0.0, pitch: float = 0.0, yaw: float = 0.0, throttle: float = 50.0) -> None:
        self.set_sticks_raw(
            roll=self._axis_to_byte(roll),
            pitch=self._axis_to_byte(pitch),
            yaw=self._axis_to_byte(yaw),
            throttle=self._throttle_to_byte(throttle),
        )

    def takeoff(self) -> None:
        with self._state_lock:
            self._state.flags = 1

    def land(self) -> None:
        with self._state_lock:
            self._state.flags = 2

    def calibrate(self) -> None:
        with self._state_lock:
            self._state.flags = 128

    def flip(self) -> None:
        self._flip_one_shot = True

    def toggle_headless(self) -> None:
        self._headless = not self._headless

    def switch_camera(self, cam: int) -> None:
        self._video.pause(True)
        time.sleep(1.0)
        self._send_raw(bytes([0x06, cam & 0xFF]))
        time.sleep(1.0)
        self._video.pause(False)
        self._video.request_reopen()

    def _ensure_socket(self) -> None:
        if self._sock is not None:
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except (AttributeError, OSError):
            pass
        try:
            sock.bind(("", self._config.source_port))
        except OSError:
            pass
        self._sock = sock

    def _send_raw(self, payload: bytes) -> None:
        self._ensure_socket()
        assert self._sock is not None
        try:
            self._sock.sendto(payload, (self._config.drone_ip, self._config.drone_port))
        except OSError:
            pass

    def _control_loop(self) -> None:
        while not self._stop.is_set():
            flags = 0
            if self._headless:
                flags |= self.HEADLESS
            if self._flip_one_shot:
                flags |= self.SOMERSAULT
                self._flip_one_shot = False

            with self._state_lock:
                self._state.flags = (self._state.flags | flags) & 0xFF
                packet = self._builder.build_packet(self._state)
                self._state.flags = 0

            self._send_raw(packet)
            time.sleep(self._config.control_interval_sec)

    @staticmethod
    def _axis_to_byte(v: float) -> int:
        v = max(-1.0, min(1.0, float(v)))
        return int(round(128 + (127 * v)))

    @staticmethod
    def _throttle_to_byte(v: float) -> int:
        v = max(0.0, min(100.0, float(v)))
        return int(round(255 * (v / 100.0)))
