from abc import ABC, abstractmethod
from typing import Iterator
from services.flight_controller import FlightController
from models.video_frame import VideoFrame

class Plugin(ABC):
    """
    Base class all runtime plug-ins must inherit from.
    `frame_source` is ANY iterator that yields either:
      • backend.models.video_frame.VideoFrame  (format == "jpeg"),
      • or an np.ndarray BGR/RGB image.
    """

    def __init__(self,
                 name: str,
                 flight_controller: FlightController,
                 frame_source: Iterator,
                 overlay_queue = None,
                 **kwargs):
        self.name   = name
        self.fc     = flight_controller
        self.frames = frame_source
        self.overlays = overlay_queue
        self.running = False
        # Lifecycle guards: make stop() idempotent and ensure cleanup runs
        # even if subclasses flip `running` directly.
        self._started = False
        self._stopped = False
        self.loop_thread = None

    def start(self):
        if self.running:
            return
        self.running = True
        self._started = True
        self._stopped = False
        self._on_start()

    def stop(self):
        # Idempotent stop: allow cleanup to run once even if `running` was
        # already set False by a subclass or background thread.
        if self._stopped:
            return
        self.running = False
        self._stopped = True
        if self._started:
            self._on_stop()

    @abstractmethod
    def _on_start(self):
        ...

    def _on_stop(self):
        pass

    def send_overlay(self, data: list):
        if self.overlays:
            try:
                self.overlays.put_nowait(data)
            except:
                pass 