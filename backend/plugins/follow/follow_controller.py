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
                 pitch_deadzone=0.05,
                 min_box_width: float | None = None,
                 max_box_width: float | None = None,
                 invert_yaw: bool = False,
                 invert_pitch: bool = False,
                 max_yaw_rate: float = 80.0,    # max change per second in percentage points
                 max_pitch_rate: float = 60.0,
                 yaw_exp: float = 1.0,
                 pitch_exp: float = 1.0,
                 max_yaw_cmd: float = 100.0,
                 max_pitch_cmd: float = 100.0,
                 smoothing_alpha: float = 0.3): # max change per second in percentage points
        self.fc = fc

        # --- Control gains ---
        self.p_gain_yaw = p_gain_yaw
        self.p_gain_pitch = p_gain_pitch
        
        # --- Target parameters (easily tunable) ---
        self.target_box_width = target_box_width
        self.min_box_width = min_box_width
        self.max_box_width = max_box_width
        self.invert_yaw = invert_yaw
        self.invert_pitch = invert_pitch
        self.max_yaw_rate = max_yaw_rate
        self.max_pitch_rate = max_pitch_rate
        self.yaw_exp = max(0.5, float(yaw_exp))
        self.pitch_exp = max(0.5, float(pitch_exp))
        self.max_yaw_cmd = max(5.0, float(max_yaw_cmd))
        self.max_pitch_cmd = max(5.0, float(max_pitch_cmd))
        
        # --- Deadzones to prevent oscillation ---
        self.yaw_deadzone = yaw_deadzone
        self.pitch_deadzone = pitch_deadzone

        # --- Temporal smoothing (exponential moving average) ---
        # Alpha: 0.0 = no smoothing (instant), 1.0 = full smoothing (frozen)
        # 0.3 means new value gets 70% weight, old gets 30%
        self.smoothing_alpha = max(0.0, min(1.0, smoothing_alpha))
        self.smoothed_center_x = None  # Will be initialized on first update
        self.smoothed_width = None

        # --- State updated by the tracker ---
        self.box_center_x = 0.5 # Normalized (raw, unsmoothed)
        self.box_width = 0.0    # Normalized (raw, unsmoothed)
        self.last_update = time.time()
        self.last_cmd_time = time.time()

        # Smoothed command outputs (percentage points, -100..100)
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

        # Normalize the center and width of the bounding box
        raw_center_x = (box_x + box_w / 2) / frame_w
        raw_width = box_w / frame_w
        
        # Apply exponential moving average for temporal smoothing
        if self.smoothed_center_x is None:
            # First measurement - initialize with raw values
            self.smoothed_center_x = raw_center_x
            self.smoothed_width = raw_width
        else:
            # EMA: new_smooth = alpha * old_smooth + (1 - alpha) * new_raw
            self.smoothed_center_x = (self.smoothing_alpha * self.smoothed_center_x + 
                                     (1.0 - self.smoothing_alpha) * raw_center_x)
            self.smoothed_width = (self.smoothing_alpha * self.smoothed_width + 
                                  (1.0 - self.smoothing_alpha) * raw_width)
        
        # Store both raw and smoothed values
        self.box_center_x = raw_center_x
        self.box_width = raw_width
        
        self.last_update = time.time()

    def current_commands(self):
        """
        Returns (yaw, pitch) adjustments based on the target's state.
        - Yaw keeps the target horizontally centered.
        - Pitch keeps the target at a stable distance (by controlling box width).
        """
        
        # Use smoothed values for control (if available)
        center_x = self.smoothed_center_x if self.smoothed_center_x is not None else self.box_center_x
        width = self.smoothed_width if self.smoothed_width is not None else self.box_width
        
        # --- Yaw control (horizontal centering) ---
        yaw_target = 0.0
        yaw_error = center_x - 0.5
        if abs(yaw_error) > self.yaw_deadzone:
            # Default: positive error (right of centre) → yaw right (positive)
            # If invert_yaw is True, flip the sign.
            sign = -1 if self.invert_yaw else 1
            # Non-linear scaling to reduce overshoot near centre (exp > 1.0 reduces small errors)
            yaw_error_adj = (abs(yaw_error) ** self.yaw_exp) * (1 if yaw_error >= 0 else -1)
            yaw_target = sign * self.p_gain_yaw * yaw_error_adj * 100

        # --- Pitch control (distance management) ---
        pitch_target = 0.0
        # Band control: if min/max provided, steer to bring width back into the band
        if self.min_box_width is not None and self.max_box_width is not None:
            if width < self.min_box_width:
                # Too far: move forward (positive pitch by default)
                # error is distance to min bound
                pitch_error = self.min_box_width - width
                if pitch_error > self.pitch_deadzone:
                    # Non-linear scaling to soften corrections near threshold
                    pitch_direction = +1 if not self.invert_pitch else -1
                    pitch_target = pitch_direction * self.p_gain_pitch * (pitch_error ** self.pitch_exp) * 100
            elif width > self.max_box_width:
                # Too close: move backward (negative pitch by default)
                pitch_error = width - self.max_box_width
                if pitch_error > self.pitch_deadzone:
                    pitch_direction = -1 if not self.invert_pitch else +1
                    pitch_target = pitch_direction * self.p_gain_pitch * (pitch_error ** self.pitch_exp) * 100
            else:
                pitch_target = 0
        else:
            # Single target width control
            pitch_error = width - self.target_box_width
            if abs(pitch_error) > self.pitch_deadzone:
                # If the box is too big (error > 0), we need to move backward (negative pitch).
                # If the box is too small (error < 0), we need to move forward (positive pitch).
                pitch_sign = -1 if pitch_error > 0 else +1
                if self.invert_pitch:
                    pitch_sign *= -1
                pitch_target = pitch_sign * self.p_gain_pitch * (abs(pitch_error) ** self.pitch_exp) * 100
        # Clamp targets to global and per-axis maxima
        yaw_target = max(-self.max_yaw_cmd, min(self.max_yaw_cmd, yaw_target))
        pitch_target = max(-self.max_pitch_cmd, min(self.max_pitch_cmd, pitch_target))

        # Slew-rate limiting toward targets
        now = time.time()
        dt = max(0.0, now - self.last_cmd_time)
        self.last_cmd_time = now

        def approach(current: float, target: float, max_rate: float, dt_sec: float) -> float:
            max_delta = max_rate * dt_sec
            if target > current:
                return min(target, current + max_delta)
            else:
                return max(target, current - max_delta)

        self.current_yaw_cmd = approach(self.current_yaw_cmd, yaw_target, self.max_yaw_rate, dt)
        self.current_pitch_cmd = approach(self.current_pitch_cmd, pitch_target, self.max_pitch_rate, dt)

        # Final clamp and return
        self.current_yaw_cmd = max(-100, min(100, self.current_yaw_cmd))
        self.current_pitch_cmd = max(-100, min(100, self.current_pitch_cmd))

        return self.current_yaw_cmd, self.current_pitch_cmd