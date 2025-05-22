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
        self._stop_evt = threading.Event()
        self.keepalive_thread = threading.Thread(
            target=self._keepalive_loop,
            args=(interval,),
            daemon=True
        )
        self.keepalive_thread.start()
    
    def stop_keepalive(self):
        """Stop the keepalive thread"""
        if hasattr(self, "_stop_evt"):
            self._stop_evt.set()        # wake the waiter
        if self.keepalive_thread:
            self.keepalive_thread.join()
    
    def _keepalive_loop(self, interval):
        """Periodically send start command to maintain video stream"""
        while not self._stop_evt.is_set():
            self.send_start_command()
            # wait() returns early when _stop_evt is set
            self._stop_evt.wait(interval)