import cv2, numpy as np

class PersonDetector:
    def __init__(self, proto, weights, conf_th=0.72):
        self.net = cv2.dnn.readNetFromCaffe(proto, weights)
        self.conf_th = conf_th

    def detect(self, frame_bgr):
        blob = cv2.dnn.blobFromImage(frame_bgr, 1/255.0, (300, 300),
                                     (104, 117, 123), swapRB=True)
        self.net.setInput(blob)
        out = self.net.forward()[0,0]                  # (N,7)
        # columns: [batch, cls-id, score, x1, y1, x2, y2]
        boxes = []
        for _, _, score, x1, y1, x2, y2 in out:
            if score < self.conf_th:                   # filter low conf
                continue
            boxes.append((x1, y1, x2, y2))
        return boxes                                   # floats 0–1
