import threading
import cv2
import numpy as np
from ultralytics import YOLO
import time
import json
import os

from ..base import Plugin
from .follow_controller import FollowController
from control.strategies import DirectStrategy

class FollowService(Plugin):
    CONFIDENCE_THRESHOLD = 0.65
    FRAME_RATE = 20  # frames per second

    def _on_start(self):
        # Resolve YOLO weights path robustly: env override → file-relative default → name fallback
        weights_env = os.getenv("YOLO_WEIGHTS")
        if weights_env and os.path.exists(weights_env):
            weights_path = weights_env
        else:
            # backend/plugins/follow/ -> backend/yolov10n.pt
            repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            default_weights = os.path.join(repo_root, "yolov10n.pt")
            weights_path = default_weights if os.path.exists(default_weights) else "yolov10n.pt"

        self.model = YOLO(weights_path)
        self.ctrl = FollowController(self.fc)

        # Switch RC model to DirectStrategy for responsive autonomous control
        self._prev_strategy = getattr(self.fc.model, "strategy", None)
        try:
            self.fc.model.set_strategy(DirectStrategy())
        except Exception:
            pass

        self.loop_thread = threading.Thread(target=self._loop, daemon=True)
        self.loop_thread.start()

    def _on_stop(self):
        # Restore previous strategy if we changed it
        try:
            if hasattr(self, "_prev_strategy") and self._prev_strategy is not None:
                self.fc.model.set_strategy(self._prev_strategy)
        except Exception:
            pass

        if self.loop_thread:
            self.loop_thread.join(timeout=1.0)

    def _loop(self):
        print("[FollowService] Loop started. Waiting for frames...")
        last_frame_time = 0
        frame_interval = 1.0 / self.FRAME_RATE

        for frame in self.frames:
            current_time = time.time()
            if current_time - last_frame_time < frame_interval:
                continue
            last_frame_time = current_time

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
                # r.boxes may be empty
                for box in getattr(r, "boxes", []) or []:
                    try:
                        cls_id = int(box.cls[0].item())
                        conf = float(box.conf[0].item())
                        if cls_id == 0 and conf > self.CONFIDENCE_THRESHOLD:
                            # Convert to plain floats [x1, y1, x2, y2]
                            xyxy = box.xyxy[0].tolist()
                            persons.append(xyxy)
                    except Exception:
                        # Skip any malformed detection
                        continue

            if persons:
                # Track the largest person detected
                largest_person = max(persons, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
                x1, y1, x2, y2 = largest_person
                
                w_box = x2 - x1
                h_box = y2 - y1

                # Send overlay
                h, w, _ = img.shape
                norm_box = [float(c) for c in [x1/w, y1/h, x2/w, y2/h]]
                overlay_data = [{"type": "rect", "coords": norm_box, "color": "lime"}]
                self.send_overlay(json.dumps(overlay_data))

                # Update controller
                self.ctrl.update_target((x1, y1, w_box, h_box), img.shape[:2])
                yaw, pitch = self.ctrl.current_commands()
                self.fc.set_axes(throttle=0, yaw=yaw / 100.0, pitch=pitch / 100.0, roll=0)
            else:
                # No person detected
                self.fc.set_axes(throttle=0, yaw=0, pitch=0, roll=0)
                self.send_overlay(json.dumps([]))
