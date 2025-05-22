from abc import ABC, abstractmethod

class BaseRCModel(ABC):
    """Base abstract class for all RC model implementations"""
    
    @abstractmethod
    def update_axes(self, dt, throttle_dir, yaw_dir, pitch_dir, roll_dir):
        """Update control axes based on input directions"""
        pass
        
    @abstractmethod
    def takeoff(self):
        """Command the drone to take off"""
        pass
        
    @abstractmethod
    def land(self):
        """Command the drone to land"""
        pass
        
    @abstractmethod
    def toggle_record(self):
        """Toggle recording state"""
        pass
        
    @abstractmethod
    def get_control_state(self):
        """Get current control state values"""
        pass
        
    @abstractmethod
    def set_sensitivity(self, preset):
        """Set control sensitivity parameters"""
        pass
