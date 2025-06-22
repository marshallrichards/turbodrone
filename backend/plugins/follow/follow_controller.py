import time

class FollowController:
    """
    Calculates drone movements to keep a target centered and at a stable distance.
    """

    def __init__(self, fc,
                 p_gain_yaw=1.0,
                 p_gain_pitch=1.0,
                 target_box_width=0.25, # Desired width of the target as a fraction of frame width
                 yaw_deadzone=0.05,     # Horizontal deadzone as a fraction of frame width
                 pitch_deadzone=0.05):  # Size deadzone as a fraction of frame width
        self.fc = fc

        # --- Control gains ---
        self.p_gain_yaw = p_gain_yaw
        self.p_gain_pitch = p_gain_pitch
        
        # --- Target parameters (easily tunable) ---
        self.target_box_width = target_box_width
        
        # --- Deadzones to prevent oscillation ---
        self.yaw_deadzone = yaw_deadzone
        self.pitch_deadzone = pitch_deadzone

        # --- State updated by the tracker ---
        self.box_center_x = 0.5 # Normalized
        self.box_width = 0.0    # Normalized
        self.last_update = time.time()

    def update_target(self, box, frame_shape):
        """
        Update the target's position and size from the tracker.
        `box` is (x, y, w, h) in absolute pixel coordinates.
        `frame_shape` is (height, width).
        """
        frame_h, frame_w = frame_shape
        box_x, box_y, box_w, box_h = box

        # Normalize and store the center and width of the bounding box
        self.box_center_x = (box_x + box_w / 2) / frame_w
        self.box_width = box_w / frame_w
        
        self.last_update = time.time()

    def current_commands(self):
        """
        Returns (yaw, pitch) adjustments based on the target's state.
        - Yaw keeps the target horizontally centered.
        - Pitch keeps the target at a stable distance (by controlling box width).
        """
        
        # --- Yaw control (horizontal centering) ---
        yaw_adj = 0
        yaw_error = self.box_center_x - 0.5
        if abs(yaw_error) > self.yaw_deadzone:
            # If target is to the right (error > 0), yaw right.
            yaw_adj = self.p_gain_yaw * yaw_error * 100

        # --- Pitch control (distance management) ---
        pitch_adj = 0
        # This is the core logic for distance control.
        pitch_error = self.box_width - self.target_box_width
        if abs(pitch_error) > self.pitch_deadzone:
            # If the box is too big (error > 0), we need to move backward (negative pitch).
            # If the box is too small (error < 0), we need to move forward (positive pitch).
            pitch_adj = -self.p_gain_pitch * pitch_error * 100

        # Clamp values to the expected [-100, 100] range for the flight controller
        yaw_adj = max(-100, min(100, yaw_adj))
        pitch_adj = max(-100, min(100, pitch_adj))

        return yaw_adj, pitch_adj