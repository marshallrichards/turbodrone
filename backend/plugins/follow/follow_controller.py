 

class FollowController:
    """
    Calculates drone movements to keep a target centered and at a stable distance.
    """

    def __init__(self, fc,
                 yaw_deadzone=0.15,
                 pitch_deadzone=0.02,
                 min_box_width: float | None = None,
                 max_box_width: float | None = None,
                 invert_yaw: bool = False,
                 invert_pitch: bool = False,
                 const_yaw_cmd: float = 20.0,
                 const_pitch_cmd: float = 20.0):
        self.fc = fc

        # --- Deadzones and band ---
        self.yaw_deadzone = yaw_deadzone
        self.pitch_deadzone = pitch_deadzone
        self.min_box_width = min_box_width
        self.max_box_width = max_box_width
        self.invert_yaw = invert_yaw
        self.invert_pitch = invert_pitch

        # --- Constant-rate magnitudes (percentage points, 0..100) ---
        self.const_yaw_cmd = max(0.0, min(100.0, float(const_yaw_cmd)))
        self.const_pitch_cmd = max(0.0, min(100.0, float(const_pitch_cmd)))

        # --- State ---
        self.box_center_x = 0.5  # normalized
        self.box_width = 0.0     # normalized
        self.current_yaw_cmd = 0.0
        self.current_pitch_cmd = 0.0

    def update_target(self, box, frame_shape):
        """
        Update the target's position and size from the tracker.
        `box` is (x, y, w, h) in absolute pixel coordinates.
        `frame_shape` is (height, width).
        """
        frame_h, frame_w = frame_shape
        box_x, box_y, box_w, box_h = box

        # Normalize and store raw values
        self.box_center_x = (box_x + box_w / 2) / frame_w
        self.box_width = box_w / frame_w

    def current_commands(self):
        """
        Returns constant-rate (yaw, pitch) corrections based on target offset and size.
        """
        center_x = self.box_center_x
        width = self.box_width

        # Yaw: fixed-magnitude correction outside horizontal deadzone
        yaw_cmd = 0.0
        yaw_error = center_x - 0.5
        if abs(yaw_error) > self.yaw_deadzone:
            base = self.const_yaw_cmd
            yaw_cmd = (base if yaw_error > 0 else -base)
            if self.invert_yaw:
                yaw_cmd = -yaw_cmd

        # Pitch: fixed-magnitude correction to keep width within band (if provided)
        pitch_cmd = 0.0
        if self.min_box_width is not None and self.max_box_width is not None:
            if width < (self.min_box_width - self.pitch_deadzone):
                pitch_cmd = self.const_pitch_cmd
            elif width > (self.max_box_width + self.pitch_deadzone):
                pitch_cmd = -self.const_pitch_cmd
            else:
                pitch_cmd = 0.0

        if self.invert_pitch:
            pitch_cmd = -pitch_cmd

        self.current_yaw_cmd = max(-100.0, min(100.0, yaw_cmd))
        self.current_pitch_cmd = max(-100.0, min(100.0, pitch_cmd))
        return self.current_yaw_cmd, self.current_pitch_cmd