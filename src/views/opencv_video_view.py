import cv2
import numpy as np
import queue
import time
import sys
import ctypes
from views.base_video_view import BaseVideoView

class OpenCVVideoView(BaseVideoView):
    """OpenCV-based video display view"""
    
    def __init__(self, frame_queue, window_name="Drone Video"):
        super().__init__(frame_queue)
        self.window_name = window_name
        
    # ------------------------------------------------------------------ #
    # private helper – poke HighGUI so waitKey() returns immediately
    # ------------------------------------------------------------------ #
    def _wakeup_highgui(self):
        if sys.platform.startswith("win"):
            hwnd = ctypes.windll.user32.FindWindowW(None, self.window_name)
            if hwnd:
                ctypes.windll.user32.PostMessageW(hwnd, 0, 0, 0)
        else:
            # On X11 / Cocoa / Qt nothing special is needed – an extra waitKey
            # call will do.
            cv2.waitKey(1)

    def run(self):
        """Start the OpenCV display loop"""
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        
        # Build a placeholder image (black + red warning text)
        placeholder_h, placeholder_w = 480, 640
        placeholder = np.zeros((placeholder_h, placeholder_w, 3), np.uint8)
        txt = "No video frames received yet"
        font, scale, th = cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2
        (tw, th_), _ = cv2.getTextSize(txt, font, scale, th)
        x = (placeholder_w - tw) // 2
        y = (placeholder_h + th_) // 2
        cv2.putText(placeholder, txt, (x, y), font, scale, (0, 0, 255), th)
        
        fps_timer = time.time()
        frame_count = 0
        
        while self.running:
            frame = None
            try:
                frame = self.frame_queue.get(timeout=1.0)
            except queue.Empty:
                pass
            
            if frame is None:
                img = placeholder
                is_real = False
            else:
                # Handle different frame formats
                if frame.format == "jpeg":
                    arr = np.frombuffer(frame.data, dtype=np.uint8)
                    decoded = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    if decoded is None:
                        print(f"[display] ⚠ imdecode failed ({len(arr)} bytes)")
                        img, is_real = placeholder, False
                    else:
                        img, is_real = decoded, True
                        # Store dimensions in frame for future reference
                        frame.width, frame.height = img.shape[1], img.shape[0]
                else:
                    # For future formats like h264, h265, etc.
                    print(f"[display] Unsupported format: {frame.format}")
                    img, is_real = placeholder, False
            
            cv2.imshow(self.window_name, img)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                self.running = False
                break
            
            # Only count toward FPS when we had a real frame
            if is_real:
                frame_count += 1
                if frame_count % 60 == 0:
                    now = time.time()
                    print(f"[display] ~{frame_count/(now-fps_timer):4.1f} fps")
                    fps_timer, frame_count = now, 0
        
        cv2.destroyAllWindows()

    def stop(self):
        """Stop the display loop"""
        self.running = False
        self._wakeup_highgui()            # make waitKey return 