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
        self.loop_thread = None

    def start(self):
        if self.running:
            return
        self.running = True
        self._on_start()

    def stop(self):
        if not self.running:
            return
        self.running = False
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