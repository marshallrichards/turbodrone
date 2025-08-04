import threading
import cv2
import numpy as np
from ultralytics import YOLO

from ..base import Plugin
from .follow_controller import FollowController

class FollowService(Plugin):
    CONFIDENCE_THRESHOLD = 0.5

    def _on_start(self):
        self.model = YOLO("yolov10n.pt")
        self.ctrl = FollowController(self.fc)
        self.loop_thread = threading.Thread(target=self._loop, daemon=True)
        self.loop_thread.start()

    def _on_stop(self):
        if self.loop_thread:
            self.loop_thread.join(timeout=1.0)

    def _loop(self):
        print("[FollowService] Loop started. Waiting for frames...")
        for frame in self.frames:
            if not self.running:
                break

            if hasattr(frame, 'format') and frame.format == "jpeg":
                img = cv2.imdecode(np.frombuffer(frame.data, np.uint8), cv2.IMREAD_COLOR)
                if img is None:
                    continue
            elif isinstance(frame, np.ndarray):
                img = frame
            else:
                continue

            results = self.model(img, stream=True, verbose=False)
            
            persons = []
            for r in results:
                for box in r.boxes:
                    if box.cls == 0 and box.conf > self.CONFIDENCE_THRESHOLD:
                        persons.append(box.xyxy[0])

            if persons:
                # Track the largest person detected
                largest_person = max(persons, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
                x1, y1, x2, y2 = largest_person
                
                w_box = x2 - x1
                h_box = y2 - y1

                # Send overlay
                h, w, _ = img.shape
                norm_box = [float(c) for c in [x1/w, y1/h, x2/w, y2/h]]
                self.send_overlay([{"type": "rect", "coords": norm_box, "color": "lime"}])

                # Update controller
                self.ctrl.update_target((x1, y1, w_box, h_box), img.shape[:2])
                yaw, pitch = self.ctrl.current_commands()
                self.fc.set_axes(throttle=0, yaw=yaw / 100.0, pitch=pitch / 100.0, roll=0)
            else:
                # No person detected
                self.fc.set_axes(throttle=0, yaw=0, pitch=0, roll=0)
                self.send_overlay([])
