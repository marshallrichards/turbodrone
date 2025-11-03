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
    FRAME_RATE = 20  # default frames per second; can be overridden via env

    def _on_start(self):
        # ---- Thread caps for better CPU behavior on low-end hardware----
        try:
            # Torch thread caps (lazy import so we don't require torch globally if backend changes)
            import torch  # noqa: WPS433 (local import by design)
            # Respect user-provided env overrides if set; otherwise use conservative defaults
            torch_threads = int(os.getenv("TORCH_NUM_THREADS", "2"))
            torch.set_num_threads(max(1, torch_threads))
            torch.set_num_interop_threads(1)
        except Exception:
            pass

        try:
            # OpenCV thread cap
            cv2.setNumThreads(1)
        except Exception:
            pass

        # Helpful BLAS/OpenMP caps (only set if user didn't already)
        os.environ.setdefault("OMP_NUM_THREADS", "2")
        os.environ.setdefault("MKL_NUM_THREADS", "2")

        # ---- Runtime configuration via environment variables ----
        # FPS (frames processed per second)
        self.FRAME_RATE = int(os.getenv("FOLLOW_FPS", str(self.FRAME_RATE)))
        # YOLO image size (short side). Typical values: 256, 320, 384
        self.IMG_SIZE = int(os.getenv("YOLO_IMG_SIZE", "320"))
        # Optional: override confidence threshold
        self.CONFIDENCE_THRESHOLD = float(os.getenv(
            "YOLO_CONFIDENCE", str(self.CONFIDENCE_THRESHOLD)
        ))

        # Hybrid detect-then-track toggle and cadence
        self.HYBRID_DETECT = os.getenv("HYBRID_DETECT", "false").lower() in ("1", "true", "yes", "on")
        self.DETECT_EVERY = max(1, int(os.getenv("FOLLOW_DETECT_EVERY", "5")))

        # Debug overlay toggle: draw full-frame border to verify alignment
        self.DEBUG_OVERLAY = os.getenv("FOLLOW_DEBUG_OVERLAY", "false").lower() in ("1", "true", "yes", "on")
        self.DEBUG_BORDER_COLOR = os.getenv("FOLLOW_DEBUG_BORDER_COLOR", "yellow")

        # Logging toggle for centering diagnostics
        self.LOG_ENABLED = os.getenv("FOLLOW_LOG_ENABLED", "true").lower() in ("1", "true", "yes", "on")
        self.LOG_INTERVAL = float(os.getenv("FOLLOW_LOG_INTERVAL", "2.0"))
        
        # Command persistence: continue last command for N frames after losing tracking
        self.PERSIST_FRAMES = int(os.getenv("FOLLOW_PERSIST_FRAMES", "5"))  # ~0.5s at 20fps
        self._frames_since_detection = 0
        self._last_yaw_cmd = 0.0
        self._last_pitch_cmd = 0.0

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

        # Centering tolerance and distance band
        center_deadzone = float(os.getenv("FOLLOW_CENTER_DEADZONE", "0.15"))
        pitch_deadzone = float(os.getenv("FOLLOW_PITCH_DEADZONE", "0.02"))
        min_box_width = float(os.getenv("FOLLOW_MIN_BOX_WIDTH", "0.30"))
        max_box_width = float(os.getenv("FOLLOW_MAX_BOX_WIDTH", "0.80"))

        invert_yaw = os.getenv("FOLLOW_INVERT_YAW", "false").lower() in ("1", "true", "yes", "on")
        invert_pitch = os.getenv("FOLLOW_INVERT_PITCH", "false").lower() in ("1", "true", "yes", "on")

        # Constant-rate command magnitudes (percentage points)
        const_yaw_cmd = float(os.getenv("FOLLOW_CONST_YAW_CMD", "20.0"))
        const_pitch_cmd = float(os.getenv("FOLLOW_CONST_PITCH_CMD", "20.0"))

        self.ctrl = FollowController(
            self.fc,
            yaw_deadzone=center_deadzone,
            pitch_deadzone=pitch_deadzone,
            min_box_width=min_box_width,
            max_box_width=max_box_width,
            invert_yaw=invert_yaw,
            invert_pitch=invert_pitch,
            const_yaw_cmd=const_yaw_cmd,
            const_pitch_cmd=const_pitch_cmd,
        )

        # Tracker state (for hybrid mode)
        self._tracker = None
        self._tracked_box = None  # (x, y, w, h)

        # Set DirectStrategy for follow control
        # Maps commands directly to stick positions (works well with S2X and WiFi UAV)
        self._prev_strategy = getattr(self.fc.model, "strategy", None)
        self._prev_expo = getattr(self.fc.model, "expo_factor", None)
        
        try:
            self.fc.model.set_strategy(DirectStrategy())
            # Disable expo so tiny commands aren't squashed by v^(1+expo)
            try:
                self.fc.model.expo_factor = 0.0
                print(f"[FollowService] Using DirectStrategy with expo=0.0")
            except Exception:
                pass
        except Exception as e:
            print(f"[FollowService] Warning: Failed to set strategy: {e}")

        self.loop_thread = threading.Thread(target=self._loop, daemon=True)
        self.loop_thread.start()

    def _on_stop(self):
        # Restore previous strategy if we changed it
        try:
            if hasattr(self, "_prev_strategy") and self._prev_strategy is not None:
                self.fc.model.set_strategy(self._prev_strategy)
            if hasattr(self, "_prev_expo") and self._prev_expo is not None:
                self.fc.model.expo_factor = self._prev_expo
        except Exception:
            pass

        if self.loop_thread:
            self.loop_thread.join(timeout=1.0)

    def _loop(self):
        print("[FollowService] Loop started. Waiting for frames...")
        last_frame_time = 0
        frame_interval = 1.0 / self.FRAME_RATE
        frame_idx = 0
        last_log_time = 0.0

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
            frame_idx += 1

            def run_detection_on_image(image):
                persons_local = []
                try:
                    results_local = self.model(
                        image,
                        stream=True,
                        verbose=False,
                        classes=[0],                # only 'person'
                        imgsz=self.IMG_SIZE,
                        conf=self.CONFIDENCE_THRESHOLD,
                    )
                except Exception:
                    results_local = []
                for r_ in results_local:
                    for box in getattr(r_, "boxes", []) or []:
                        try:
                            cls_id = int(box.cls[0].item())
                            conf = float(box.conf[0].item())
                            if cls_id == 0 and conf > self.CONFIDENCE_THRESHOLD:
                                xyxy = box.xyxy[0].tolist()
                                persons_local.append(xyxy)
                        except Exception:
                            continue
                return persons_local

            def init_tracker_from_xyxy(x1, y1, x2, y2):
                # Convert to (x, y, w, h)
                bbox = (float(x1), float(y1), float(x2 - x1), float(y2 - y1))
                tracker = None
                # MOSSE is very fast; fallback to CSRT if MOSSE unavailable
                try:
                    tracker = cv2.legacy.TrackerMOSSE_create()
                except Exception:
                    try:
                        tracker = cv2.TrackerMOSSE_create()
                    except Exception:
                        try:
                            tracker = cv2.legacy.TrackerCSRT_create()
                        except Exception:
                            try:
                                tracker = cv2.TrackerCSRT_create()
                            except Exception:
                                tracker = None
                if tracker is not None:
                    try:
                        tracker.init(img, bbox)
                        return tracker, bbox
                    except Exception:
                        return None, None
                return None, None

            box_for_control = None  # (x, y, w, h)

            if self.HYBRID_DETECT:
                should_detect = (self._tracker is None) or (frame_idx % self.DETECT_EVERY == 0)
                if should_detect:
                    persons = run_detection_on_image(img)
                    if persons:
                        largest = max(persons, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
                        x1, y1, x2, y2 = largest
                        self._tracker, self._tracked_box = init_tracker_from_xyxy(x1, y1, x2, y2)
                        if self._tracked_box is not None:
                            box_for_control = self._tracked_box
                        else:
                            box_for_control = (x1, y1, x2 - x1, y2 - y1)
                    else:
                        self._tracker = None
                        self._tracked_box = None
                else:
                    if self._tracker is not None:
                        try:
                            ok, bbox = self._tracker.update(img)
                        except Exception:
                            ok, bbox = False, None
                        if ok and bbox is not None:
                            self._tracked_box = bbox
                            box_for_control = bbox
                        else:
                            self._tracker = None
                            self._tracked_box = None

            else:
                # Pure detection every processed frame (with class filter and smaller imgsz)
                persons = run_detection_on_image(img)
                if persons:
                    largest = max(persons, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
                    x1, y1, x2, y2 = largest
                    box_for_control = (x1, y1, (x2 - x1), (y2 - y1))

            if box_for_control is not None:
                # Fresh detection - reset persistence counter
                self._frames_since_detection = 0
                
                x, y, w_box, h_box = box_for_control
                x1_draw, y1_draw, x2_draw, y2_draw = x, y, x + w_box, y + h_box

                # Send overlay
                h, w, _ = img.shape
                norm_box = [
                    float(x1_draw / w),
                    float(y1_draw / h),
                    float(x2_draw / w),
                    float(y2_draw / h),
                ]
                overlay_data = [{"type": "rect", "coords": norm_box, "color": "lime"}]
                if self.DEBUG_OVERLAY:
                    overlay_data.insert(0, {"type": "rect", "coords": [0.0, 0.0, 1.0, 1.0], "color": self.DEBUG_BORDER_COLOR})
                self.send_overlay(json.dumps(overlay_data))

                # Update controller
                self.ctrl.update_target((x, y, w_box, h_box), img.shape[:2])
                yaw, pitch = self.ctrl.current_commands()
                
                # Store last valid commands
                self._last_yaw_cmd = yaw / 100.0
                self._last_pitch_cmd = pitch / 100.0
                
                self.fc.set_axes_from("follow", throttle=0, yaw=self._last_yaw_cmd, pitch=self._last_pitch_cmd, roll=0)

                # Optional per-frame debug of commands issued
                if os.getenv("FOLLOW_DEBUG_AXES", "false").lower() in ("1", "true", "yes", "on"):
                    try:
                        state = self.fc.model.get_control_state()
                        print(
                            f"[FollowService] cmd yaw={yaw:5.1f} pitch={pitch:5.1f} -> norm Y:{yaw/100.0:+.2f} P:{pitch/100.0:+.2f} | "
                            f"raw Y:{state.get('yaw')} P:{state.get('pitch')}"
                        )
                    except Exception:
                        pass

                # Periodic centering diagnostics
                now = time.time()
                if self.LOG_ENABLED and now - last_log_time >= self.LOG_INTERVAL:
                    box_center_x = (x + w_box / 2.0) / float(w)
                    center_error = box_center_x - 0.5
                    center_pct = center_error * 100.0
                    side = "right" if center_pct > 0 else ("left" if center_pct < 0 else "center")
                    print(
                        f"[FollowService] center_offset: {center_pct:+5.1f}% ({side}), "
                        f"box_width: {w_box/float(w)*100:4.1f}% of frame, yaw={yaw:5.1f}, pitch={pitch:5.1f}"
                    )
                    last_log_time = now
            else:
                # No detection this frame - use command persistence
                self._frames_since_detection += 1
                
                if self._frames_since_detection <= self.PERSIST_FRAMES:
                    # Continue with last known commands (gradually decay to zero)
                    decay_factor = 1.0 - (self._frames_since_detection / float(self.PERSIST_FRAMES))
                    yaw_persist = self._last_yaw_cmd * decay_factor
                    pitch_persist = self._last_pitch_cmd * decay_factor
                    
                    self.fc.set_axes_from("follow", throttle=0, yaw=yaw_persist, pitch=pitch_persist, roll=0)
                    
                    if os.getenv("FOLLOW_DEBUG_PERSIST", "false").lower() in ("1", "true", "yes", "on"):
                        print(f"[FollowService] PERSIST frame {self._frames_since_detection}/{self.PERSIST_FRAMES}: "
                              f"yaw={yaw_persist:+.2f}, pitch={pitch_persist:+.2f} (decay={decay_factor:.2f})")
                else:
                    # Exceeded persistence limit - send zeros
                    self.fc.set_axes(throttle=0, yaw=0, pitch=0, roll=0)
                    if os.getenv("FOLLOW_DEBUG_PERSIST", "false").lower() in ("1", "true", "yes", "on"):
                        print(f"[FollowService] Lost tracking for {self._frames_since_detection} frames - sending zeros")
                
                if self.DEBUG_OVERLAY:
                    debug_overlay = [{"type": "rect", "coords": [0.0, 0.0, 1.0, 1.0], "color": self.DEBUG_BORDER_COLOR}]
                    self.send_overlay(json.dumps(debug_overlay))
                else:
                    self.send_overlay(json.dumps([]))
