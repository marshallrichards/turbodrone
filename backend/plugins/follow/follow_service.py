import threading
import cv2
import numpy as np
import os

from ..base import Plugin
from .follow_controller import FollowController
from .person_detector import PersonDetector
from .kcf_tracker import KCFTracker

class FollowService(Plugin):
    def _on_start(self):
        plugin_dir = os.path.dirname(__file__)
        assets_dir = os.path.join(plugin_dir, "assets")
        proto_path = os.path.join(assets_dir, "net_clp.prototxt")
        weights_path = os.path.join(assets_dir, "weights_person_300_0205.caffemodel")

        self.detector = PersonDetector(proto_path, weights_path)
        self.tracker  = KCFTracker()
        self.ctrl     = FollowController(self.fc)

        self.loop_thread = threading.Thread(target=self._loop, daemon=True)
        self.loop_thread.start()

    def _on_stop(self):
        if self.loop_thread:
            self.loop_thread.join(timeout=1.0)

    def _loop(self):
        for frame in self.frames:
            if not self.running:
                break

            if hasattr(frame, 'format') and frame.format == "jpeg":
                img = cv2.imdecode(np.frombuffer(frame.data, np.uint8), cv2.IMREAD_COLOR)
                if img is None: continue
            elif isinstance(frame, np.ndarray):
                img = frame
            else:
                continue

            if self.tracker.tracker is None:
                boxes = self.detector.detect(img)
                if boxes:
                    h, w, _ = img.shape
                    n_box = boxes[0]

                    json_box = [float(c) for c in n_box]
                    self.send_overlay([{"type": "rect", "coords": json_box, "color": "yellow"}])
                    
                    x1, y1, x2, y2 = n_box
                    abs_tracker_box = (x1 * w, y1 * h, x2 * w, y2 * h)

                    if (x2 - x1) * w > 1 and (y2 - y1) * h > 1:
                        tracker_box_int = tuple(map(int, abs_tracker_box))
                        self.tracker.init(img, tracker_box_int)
                    else:
                        self.send_overlay([])
                else:
                    self.send_overlay([])
            else:
                box, _ = self.tracker.update(img)
                if box is None:
                    self.tracker.tracker = None
                    self.fc.set_axes(throttle=0, yaw=0, pitch=0, roll=0)
                    self.send_overlay([])
                    continue

                h, w, _ = img.shape
                x, y, w_box, h_box = box
                norm_box = [x/w, y/h, (x+w_box)/w, (y+h_box)/h]
                
                json_box = [float(c) for c in norm_box]
                self.send_overlay([{"type": "rect", "coords": json_box, "color": "lime"}])

                self.ctrl.update_target(box, img.shape[:2])
                yaw, pitch = self.ctrl.current_commands()

                self.fc.set_axes(throttle=0,
                                 yaw=yaw / 100.0,
                                 pitch=pitch / 100.0,
                                 roll=0)

    @staticmethod
    def _norm(b, f): h,w,_=f.shape; x1,y1,x2,y2=b; return (x1/w,y1/h,x2/w,y2/h)
    @staticmethod
    def _abs(b, f): h,w,_=f.shape; x1,y1,x2,y2=b; return (x1*w,y1*h,x2*w,y2*h)