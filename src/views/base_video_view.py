from abc import ABC, abstractmethod

class BaseVideoView(ABC):
    """Base abstract class for video display views"""
    
    def __init__(self, frame_queue):
        self.frame_queue = frame_queue
        self.running = True
    
    @abstractmethod
    def run(self):
        """Start the view's main loop"""
        pass
    
    @abstractmethod
    def stop(self):
        """Stop the view"""
        pass 