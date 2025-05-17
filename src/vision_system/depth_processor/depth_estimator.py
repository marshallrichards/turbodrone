"""
Real-time depth estimation module using Depth Pro.
"""

import threading
from queue import Queue
from typing import Optional, Tuple, Dict

import numpy as np
import depth_pro
import cv2
import torch

class DepthEstimator:
    """Real-time depth estimation using Depth Pro."""
    
    def __init__(self, max_queue_size: int = 10):
        """
        Initialize the depth estimator.
        
        Args:
            max_queue_size: Maximum size of the frame queue for processing
        """
        # Initialize Depth Pro model
        self.model, self.transform = depth_pro.create_model_and_transforms()
        self.model.eval()  # Set to evaluation mode
        
        # Initialize queues for frame processing
        self.input_queue = Queue(maxsize=max_queue_size)
        self.output_queue = Queue(maxsize=max_queue_size)
        
        # Processing thread
        self.processing_thread = None
        self.is_running = False
        
        # Stats
        self.fps = 0
        self.processing_time = 0
        
    def start(self):
        """Start the depth estimation processing thread."""
        if not self.is_running:
            self.is_running = True
            self.processing_thread = threading.Thread(target=self._processing_loop)
            self.processing_thread.daemon = True
            self.processing_thread.start()
    
    def stop(self):
        """Stop the depth estimation processing thread."""
        self.is_running = False
        if self.processing_thread is not None:
            self.processing_thread.join()
            self.processing_thread = None
    
    def _processing_loop(self):
        """Main processing loop that runs in a separate thread."""
        import time
        
        while self.is_running:
            if not self.input_queue.empty():
                # Get frame from queue
                start_time = time.time()
                frame = self.input_queue.get()
                
                try:
                    # Process frame
                    depth_map = self.process_frame(frame)
                    
                    # Calculate processing stats
                    process_time = time.time() - start_time
                    self.processing_time = process_time
                    self.fps = 1.0 / process_time if process_time > 0 else 0
                    
                    # Put result in output queue
                    if not self.output_queue.full():
                        self.output_queue.put((depth_map, self.fps))
                        
                except Exception as e:
                    print(f"Error processing frame: {e}")
                
                self.input_queue.task_done()
            else:
                # Sleep briefly to prevent CPU spinning
                time.sleep(0.001)
    
    def process_frame(self, frame: np.ndarray) -> np.ndarray:
        """
        Process a single frame to generate a depth map.
        
        Args:
            frame: RGB frame as numpy array (H, W, 3)
            
        Returns:
            Depth map as numpy array (H, W)
        """
        # Convert BGR to RGB if needed
        if frame.shape[2] == 3:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Print input frame info
        print("Input frame shape:", frame.shape)
        print("Input frame type:", frame.dtype)
        
        # Let the transform handle the tensor conversion
        # The transform from depth_pro expects a numpy array
        image = self.transform(frame)
        
        # Add batch dimension if needed
        if len(image.shape) == 3:
            image = image.unsqueeze(0)  # Add batch dimension [1, C, H, W]
        
        # Print transformed image info
        print("Transformed image type:", type(image))
        print("Transformed image shape:", image.shape)
        
        # Estimate focal length based on image size
        # This is a rough approximation, you may want to calibrate this for your camera
        f_px = max(frame.shape[:2]) * 1.2
        print("Estimated focal length:", f_px)
        
        # Run inference with debug info
        with torch.no_grad():
            # Convert image to float32 for inference
            image = image.float()
            
            # Run inference
            prediction = self.model.infer(image, f_px=f_px)
            print("Prediction type:", type(prediction))
            print("Prediction value:", prediction)
            
            # Extract depth map
            if isinstance(prediction, dict) and "depth" in prediction:
                depth_map = prediction["depth"]
                if isinstance(depth_map, torch.Tensor):
                    depth_map = depth_map.squeeze().cpu().numpy()  # Remove batch dimension and convert to numpy
            else:
                raise ValueError(f"Unexpected prediction type: {type(prediction)}")
        
        return depth_map
    
    def add_frame(self, frame: np.ndarray) -> bool:
        """
        Add a frame to the processing queue.
        
        Args:
            frame: RGB frame as numpy array (H, W, 3)
            
        Returns:
            bool: True if frame was added, False if queue is full
        """
        if not self.input_queue.full():
            self.input_queue.put(frame)
            return True
        return False
    
    def get_latest_result(self) -> Optional[Tuple[np.ndarray, float]]:
        """
        Get the latest processed depth map and FPS.
        
        Returns:
            Tuple of (depth_map, fps) or None if no results available
        """
        if not self.output_queue.empty():
            return self.output_queue.get()
        return None
    
    def get_stats(self) -> Dict[str, float]:
        """
        Get current processing statistics.
        
        Returns:
            Dictionary containing FPS and processing time
        """
        return {
            "fps": self.fps,
            "processing_time": self.processing_time
        }
