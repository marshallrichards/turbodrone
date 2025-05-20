import threading
import time

class FlightController:
    """Core service that manages drone flight operations"""
    
    def __init__(self, drone_model, protocol_adapter, update_rate=20.0):
        self.model = drone_model
        self.protocol = protocol_adapter
        self.update_interval = 1.0 / update_rate
        self.running = True
        
        # Input state
        self.throttle_dir = 0
        self.yaw_dir = 0
        self.pitch_dir = 0
        self.roll_dir = 0
        
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
            
    def _control_loop(self):
        """Background thread for sending control updates"""
        prev_time = time.time()
        
        while self.running:
            now = time.time()
            dt = now - prev_time
            prev_time = now
            
            # Update drone controls based on input directions
            self.model.update_axes(
                dt,
                self.throttle_dir,
                self.yaw_dir,
                self.pitch_dir,
                self.roll_dir
            )
            
            # Build and send packet
            packet = self.protocol.build_control_packet(self.model)
            self.protocol.send_control_packet(packet)
            
            # Sleep to maintain update rate
            time.sleep(self.update_interval)