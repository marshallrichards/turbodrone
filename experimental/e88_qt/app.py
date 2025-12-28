import sys

import cv2
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget

from turbodrone import Drone


class E88QtControllerWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("E88 Pro Controller")
        self.setGeometry(100, 100, 800, 700)

        self._drone = Drone(protocol="E88")
        self._drone.connect()

        self._accel = 50
        self._decel = 5

        self._roll = 128
        self._pitch = 128
        self._throttle = 128
        self._yaw = 128

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        self.image_label = QLabel(self)
        self.image_label.setFixedSize(640, 480)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: black; border: 1px solid gray;")
        self.image_label.setText("Loading RTSP stream...")
        self.layout.addWidget(self.image_label, alignment=Qt.AlignCenter)

        self.cam1_button = QPushButton("Cam 1")
        self.cam1_button.setFixedSize(100, 40)
        self.cam1_button.clicked.connect(lambda: self._drone.switch_camera(1))
        self.layout.addWidget(self.cam1_button, alignment=Qt.AlignCenter)

        self.cam2_button = QPushButton("Cam 2")
        self.cam2_button.setFixedSize(100, 40)
        self.cam2_button.clicked.connect(lambda: self._drone.switch_camera(2))
        self.layout.addWidget(self.cam2_button, alignment=Qt.AlignCenter)

        self.setFocusPolicy(Qt.StrongFocus)

        self._video_timer = QTimer(self)
        self._video_timer.timeout.connect(self._tick_video)
        self._video_timer.start(33)

        self._control_timer = QTimer(self)
        self._control_timer.timeout.connect(self._tick_controls)
        self._control_timer.start(30)

    def closeEvent(self, event):
        try:
            self._drone.close()
        except Exception:
            pass
        event.accept()

    def keyPressEvent(self, event):
        key = event.key()

        if key == Qt.Key_Up:
            self._pitch = min(200, self._pitch + self._accel)
            event.accept()
            return
        if key == Qt.Key_Down:
            self._pitch = max(50, self._pitch - self._accel)
            event.accept()
            return
        if key == Qt.Key_Left:
            self._roll = max(50, self._roll - self._accel)
            event.accept()
            return
        if key == Qt.Key_Right:
            self._roll = min(200, self._roll + self._accel)
            event.accept()
            return

        if key == Qt.Key_W:
            self._throttle = min(200, self._throttle + self._accel)
            event.accept()
            return
        if key == Qt.Key_S:
            self._throttle = max(50, self._throttle - self._accel)
            event.accept()
            return
        if key == Qt.Key_D:
            self._yaw = min(200, self._yaw + self._accel)
            event.accept()
            return
        if key == Qt.Key_A:
            self._yaw = max(50, self._yaw - self._accel)
            event.accept()
            return

        if key == Qt.Key_Z:
            self._drone.takeoff()
            event.accept()
            return
        if key == Qt.Key_X:
            self._drone.land()
            event.accept()
            return
        if key == Qt.Key_C:
            self._drone.calibrate()
            event.accept()
            return
        if key == Qt.Key_F:
            self._drone.flip()
            event.accept()
            return
        if key == Qt.Key_H:
            self._drone.toggle_headless()
            event.accept()
            return

        if key == Qt.Key_1:
            self._drone.switch_camera(1)
            event.accept()
            return
        if key == Qt.Key_2:
            self._drone.switch_camera(2)
            event.accept()
            return

        super().keyPressEvent(event)

    def _tick_controls(self) -> None:
        self._drone.set_sticks_raw(
            roll=self._roll,
            pitch=self._pitch,
            throttle=self._throttle,
            yaw=self._yaw,
        )

        self._roll = self._decay_to_center(self._roll)
        self._pitch = self._decay_to_center(self._pitch)
        self._throttle = self._decay_to_center(self._throttle)
        self._yaw = self._decay_to_center(self._yaw)

    def _tick_video(self) -> None:
        frame = self._drone.get_frame(timeout=0)
        if frame is None:
            return

        rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb_image = cv2.rotate(rgb_image, cv2.ROTATE_90_CLOCKWISE)

        h, w, ch = rgb_image.shape
        bytes_per_line = rgb_image.strides[0]
        q_img = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888).copy()

        p = q_img.scaled(640, 480, Qt.KeepAspectRatio)
        self.image_label.setPixmap(QPixmap.fromImage(p))
        self.image_label.setText("")
        self.image_label.setStyleSheet("background-color: black; border: 1px solid gray;")

    def _decay_to_center(self, v: int) -> int:
        if v > 128:
            return max(128, v - self._decel)
        if v < 128:
            return min(128, v + self._decel)
        return v


def main() -> None:
    app = QApplication(sys.argv)
    window = E88QtControllerWindow()
    window.show()
    sys.exit(app.exec_())
