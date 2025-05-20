from abc import ABC, abstractmethod
import socket
import threading
import time

class BaseVideoProtocolAdapter(ABC):
    """Base abstract class for drone video protocol adapters"""
    
    def __init__(self, drone_ip, control_port, video_port):
        self.drone_ip = drone_ip
        self.control_port = control_port
        self.video_port = video_port
        self.keepalive_thread = None
        self.running = False
    
    @abstractmethod
    def send_start_command(self):
        """Send command to start video streaming"""
        pass
    
    @abstractmethod
    def create_receiver_socket(self):
        """Create and configure socket for receiving video data"""
        pass
    
    @abstractmethod
    def parse_packet(self, packet):
        """Parse a received packet and extract frame data"""
        pass
    
    @abstractmethod
    def is_valid_packet(self, packet):
        """Check if a packet is valid for this protocol"""
        pass
    
    def start_keepalive(self, interval=1.0):
        """Start keepalive thread to maintain video stream"""
        if self.keepalive_thread and self.keepalive_thread.is_alive():
            return
            
        self.running = True
        self.keepalive_thread = threading.Thread(
            target=self._keepalive_loop,
            args=(interval,),
            daemon=True
        )
        self.keepalive_thread.start()
    
    def stop_keepalive(self):
        """Stop the keepalive thread"""
        # Set flag to stop the thread
        self.running = False
        
        if self.keepalive_thread:
            try:
                # Give the thread a chance to exit gracefully
                self.keepalive_thread.join(timeout=1.0)
                
                # If thread is still alive, we need more aggressive measures
                if self.keepalive_thread.is_alive():
                    print("[video] Warning: Keepalive thread did not terminate gracefully")
                    # We can't forcibly kill threads in Python, but we've set the flag
                    # which should prevent further commands from being sent
            except RuntimeError:
                # Thread may already be dead
                pass
            
            self.keepalive_thread = None
    
    def _keepalive_loop(self, interval):
        """Periodically send start command to maintain video stream"""
        while self.running:
            self.send_start_command()
            time.sleep(interval)