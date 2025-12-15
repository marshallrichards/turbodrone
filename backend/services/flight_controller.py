import threading
import time
import os
import logging

logger = logging.getLogger(__name__)

class FlightController:
    """Core service that manages drone flight operations"""
    
    def __init__(self, drone_model, protocol_adapter, update_rate=80.0):
        self.model = drone_model
        self.protocol = protocol_adapter
        self.update_interval = 1.0 / update_rate
        self.running = True
        
        # Input state
        self.throttle_dir = 0
        self.yaw_dir = 0
        self.pitch_dir = 0
        self.roll_dir = 0

        # Logging / diagnostics
        self.last_control_source = "init"
        self._last_log_time = 0.0
        # When enabled, logs control state at DEBUG level (so it is still quiet
        # unless LOG_LEVEL=DEBUG).
        self.log_controls = os.getenv("FLIGHT_LOG_CONTROLS", "true").lower() in ("1", "true", "yes", "on")
        
    def start(self):
        """Start the control thread"""
        self.control_thread = threading.Thread(target=self._control_loop)
        self.control_thread.daemon = True
        self.control_thread.start()
        
    def stop(self):
        """Stop the control thread"""
        self.running = False
        if hasattr(self, 'control_thread'):
            self.control_thread.join(timeout=1.0)
        
        if hasattr(self.protocol, 'stop'):
            self.protocol.stop()
            
    def set_control_direction(self, control, direction):
        """Set control direction (-1, 0, 1)"""
        if control == 'throttle':
            self.throttle_dir = direction
        elif control == 'yaw':
            self.yaw_dir = direction
        elif control == 'pitch':
            self.pitch_dir = direction  
        elif control == 'roll':
            self.roll_dir = direction
            
    def set_axes(self, throttle: float, yaw: float, pitch: float, roll: float) -> None:
        """
        Atomically update all four stick directions.
        Each value is expected in the range [-1.0 … +1.0].
        """
        self.set_axes_from("unknown", throttle, yaw, pitch, roll)

    def set_axes_from(self, source: str, throttle: float, yaw: float, pitch: float, roll: float) -> None:
        """Same as set_axes, but records the control source and logs."""
        self.throttle_dir = max(-1.0, min(1.0, throttle))
        self.yaw_dir      = max(-1.0, min(1.0, yaw))
        self.pitch_dir    = max(-1.0, min(1.0, pitch))
        self.roll_dir     = max(-1.0, min(1.0, roll))
        self.last_control_source = source

        # Optional immediate debug of inbound commands
        try:
            if getattr(self, "debug_set_axes", False) or self.log_controls:
                state = {}
                try:
                    state = self.model.get_control_state()
                except Exception:
                    pass
                logger.debug(
                    "[RC-In] src=%-8s norm T:%+.2f Y:%+.2f P:%+.2f R:%+.2f | raw T:%s Y:%s P:%s R:%s",
                    source,
                    self.throttle_dir,
                    self.yaw_dir,
                    self.pitch_dir,
                    self.roll_dir,
                    state.get("throttle"),
                    state.get("yaw"),
                    state.get("pitch"),
                    state.get("roll"),
                )
        except Exception:
            pass
            
    def _control_loop(self):
        """Background thread for sending control updates"""
        prev_time = time.time()
        
        while self.running:
            now = time.time()
            dt = now - prev_time
            prev_time = now
            
            # Update drone controls based on input directions
            self.model.update(dt, {
                "throttle": self.throttle_dir,   # still -1…+1
                "yaw":      self.yaw_dir,
                "pitch":    self.pitch_dir,
                "roll":     self.roll_dir,
            })
            
            # Build and send packet
            try:
                packet = self.protocol.build_control_packet(self.model)
                self.protocol.send_control_packet(packet)
            except Exception:
                # The RC socket may be momentarily unavailable while the
                # video layer is recreating its socket. Ignore and keep
                # looping – a fresh socket will be injected shortly.
                pass
            
            # Sleep to maintain update rate
            time.sleep(self.update_interval)

            # Periodic state log (shows current model raw sticks after update)
            if self.log_controls:
                if now - self._last_log_time >= 0.5:
                    try:
                        state = self.model.get_control_state()
                        strategy = getattr(self.model, "strategy", None)
                        strat_name = strategy.__class__.__name__ if strategy else "(none)"
                        logger.debug(
                            "[RC-Loop] src=%-8s norm T:%+.2f Y:%+.2f P:%+.2f R:%+.2f | raw T:%s Y:%s P:%s R:%s | strat=%s",
                            self.last_control_source,
                            self.throttle_dir,
                            self.yaw_dir,
                            self.pitch_dir,
                            self.roll_dir,
                            state.get("throttle"),
                            state.get("yaw"),
                            state.get("pitch"),
                            state.get("roll"),
                            strat_name,
                        )
                    except Exception:
                        pass
                    self._last_log_time = now