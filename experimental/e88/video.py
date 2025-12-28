from __future__ import annotations

import threading
import time
from typing import Optional

import cv2
import numpy as np

from .config import E88Config


class E88VideoStream:
    def __init__(self, config: E88Config) -> None:
        self._config = config
        self._cap: Optional[cv2.VideoCapture] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._frame_lock = threading.Lock()
        self._frame_ready = threading.Condition(self._frame_lock)
        self._last_frame: Optional[np.ndarray] = None
        self._paused = False
        self._reopen = False

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="E88VideoStream", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        self._release_cap()

    def pause(self, paused: bool) -> None:
        self._paused = paused

    def request_reopen(self) -> None:
        self._reopen = True

    def get_frame(self, timeout: Optional[float] = None) -> Optional[np.ndarray]:
        with self._frame_ready:
            if self._last_frame is None:
                self._frame_ready.wait(timeout=timeout)
            if self._last_frame is None:
                return None
            return self._last_frame.copy()

    def _release_cap(self) -> None:
        if self._cap:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    def _ensure_open(self) -> bool:
        if self._cap and self._cap.isOpened():
            return True
        self._release_cap()
        cap = cv2.VideoCapture(self._config.rtsp_url)
        if not cap.isOpened():
            try:
                cap.release()
            except Exception:
                pass
            return False
        self._cap = cap
        return True

    def _run(self) -> None:
        while not self._stop.is_set():
            if self._paused:
                time.sleep(0.01)
                continue

            if self._reopen:
                self._release_cap()
                time.sleep(self._config.video_reopen_delay_sec)
                self._reopen = False

            if not self._ensure_open():
                time.sleep(1.0)
                continue

            assert self._cap is not None
            ok, frame = self._cap.read()
            if not ok or frame is None:
                self._release_cap()
                time.sleep(0.2)
                continue

            with self._frame_ready:
                self._last_frame = frame
                self._frame_ready.notify_all()

            time.sleep(0.001)

        self._release_cap()
