import cv2, time

class KCFTracker:
    def __init__(self):
        self.tracker = None
        self.last_reinit = 0

    def init(self, frame, box):
        # box: (x1,y1,x2,y2) in absolute px
        x,y,w,h = self._to_xywh(box)
        self.tracker = cv2.TrackerKCF_create()
        self.tracker.init(frame, (x,y,w,h))
        self.last_reinit = time.time()

    def update(self, frame):
        if self.tracker is None:
            return None, 0.0
        ok, rect = self.tracker.update(frame)
        conf = 1.0                                  # OpenCV KCF has no score
        return (self._from_xywh(rect) if ok else None, conf)

    @staticmethod
    def _to_xywh(b): x1,y1,x2,y2=b; return x1,y1,x2-x1,y2-y1
    @staticmethod
    def _from_xywh(r): x,y,w,h=r; return (x, y, x+w, y+h)
