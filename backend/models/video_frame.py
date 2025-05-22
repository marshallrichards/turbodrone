import time

class VideoFrame:
    """Model representing a video frame from the drone"""
    
    def __init__(self, frame_id, data, format_type="jpeg", timestamp=None):
        self.frame_id = frame_id
        self.data = data
        self.format = format_type  # jpeg, h264, h265, yuv, etc.
        self.timestamp = timestamp or time.time()
        self.width = None
        self.height = None
        self.size = len(data) if data else 0
        
    def __repr__(self):
        return f"VideoFrame(id={self.frame_id}, format={self.format}, size={self.size})" 