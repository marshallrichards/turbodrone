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
                    abs_box = (n_box[0]*w, n_box[1]*h, n_box[2]*w, n_box[3]*h)
                    tracker_box = (abs_box[0], abs_box[1], abs_box[2]-abs_box[0], abs_box[3]-abs_box[1])
                    self.tracker.init(img, tracker_box)
            else:
                box, _ = self.tracker.update(img)
                if box is None:
                    self.tracker.tracker = None
                    self.fc.set_axes(throttle=0, yaw=0, pitch=0, roll=0)
                    continue

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