"""
Test script for the DepthEstimator class.
"""

import cv2
import numpy as np
from depth_estimator import DepthEstimator

def normalize_depth_map(depth_map: np.ndarray) -> np.ndarray:
    """Normalize depth map for visualization."""
    depth_min = depth_map.min()
    depth_max = depth_map.max()
    normalized = (depth_map - depth_min) / (depth_max - depth_min)
    return (normalized * 255).astype(np.uint8)

def main():
    # Initialize video capture (0 for default camera)
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: Could not open camera")
        return

    # Initialize depth estimator
    depth_estimator = DepthEstimator(max_queue_size=2)  # Small queue size for real-time
    depth_estimator.start()

    try:
        while True:
            # Read frame
            ret, frame = cap.read()
            if not ret:
                print("Error: Could not read frame")
                break

            # Add frame to processing queue
            if depth_estimator.add_frame(frame):
                # Get latest processed result
                result = depth_estimator.get_latest_result()
                if result is not None:
                    depth_map, fps = result
                    
                    # Normalize depth map for visualization
                    depth_vis = normalize_depth_map(depth_map)
                    
                    # Apply colormap for better visualization
                    depth_color = cv2.applyColorMap(depth_vis, cv2.COLORMAP_INFERNO)
                    
                    # Show stats
                    stats = depth_estimator.get_stats()
                    cv2.putText(depth_color, f"FPS: {stats['fps']:.1f}", (10, 30),
                              cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                    
                    # Display
                    cv2.imshow('RGB Frame', frame)
                    cv2.imshow('Depth Map', depth_color)

            # Check for exit
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    finally:
        # Cleanup
        depth_estimator.stop()
        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main() 