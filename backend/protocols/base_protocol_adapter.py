from abc import ABC, abstractmethod

class BaseProtocolAdapter(ABC):
    """Base abstract class for drone protocol adapters"""
    
    @abstractmethod
    def build_control_packet(self, drone_model):
        """Build a control packet for the specific drone protocol"""
        pass
        
    @abstractmethod
    def send_control_packet(self, packet):
        """Send the control packet to the drone"""
        pass
        
    @abstractmethod
    def toggle_debug(self):
        """Toggle debug packet logging"""
        pass