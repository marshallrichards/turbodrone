"""
Video Protocol Adapter for Cooingdv drones.

Uses RTSP streaming instead of custom UDP protocol - much simpler than 
the S2x and WiFi UAV implementations.

The drone broadcasts video at: rtsp://192.168.1.1:7070/webcam

This adapter uses OpenCV's VideoCapture to connect to the RTSP stream
and provides frames through the standard turbodrone interface.
"""

import cv2
import queue
import threading
import time
from typing import Final, Optional, List

from models.video_frame import VideoFrame
from protocols.base_video_protocol import BaseVideoProtocolAdapter


class CooingdvVideoProtocolAdapter(BaseVideoProtocolAdapter):
    """
    Video protocol adapter for cooingdv drones using RTSP streaming.
    
    Unlike the UDP-based adapters for S2x and WiFi UAV drones, this adapter
    connects to a standard RTSP stream, making it much simpler and more
    reliable.
    
    Features:
    - Automatic reconnection on stream failure
    - Frame rate limiting to prevent buffer overflow
    - Thread-safe frame queue
    """

    DEFAULT_DRONE_IP: Final = "192.168.1.1"
    DEFAULT_RTSP_PORT: Final = 7070
    DEFAULT_CONTROL_PORT: Final = 7099
    
    RTSP_PATH: Final = "/webcam"
    
    # Reconnection settings
    RECONNECT_DELAY: Final = 2.0  # seconds
    MAX_RECONNECT_ATTEMPTS: Final = 10
    
    # Frame capture settings
    FRAME_TIMEOUT: Final = 5.0  # seconds without frame triggers reconnect

    def __init__(
        self,
        drone_ip: str = DEFAULT_DRONE_IP,
        control_port: int = DEFAULT_CONTROL_PORT,
        video_port: int = DEFAULT_RTSP_PORT,
        *,
        debug: bool = False,
    ):
        super().__init__(drone_ip, control_port, video_port)
        
        self.debug = debug
        self._dbg = (lambda *a, **k: print(*a, **k)) if debug else (lambda *a, **k: None)
        
        # Build RTSP URL
        self.rtsp_url = f"rtsp://{drone_ip}:{video_port}{self.RTSP_PATH}"
        self._dbg(f"[cooingdv-video] RTSP URL: {self.rtsp_url}")
        
        # OpenCV capture object
        self._cap: Optional[cv2.VideoCapture] = None
        self._cap_lock = threading.Lock()
        
        # Threading
        self._running = False
        self._rx_thread: Optional[threading.Thread] = None
        self._frame_q: "queue.Queue[VideoFrame]" = queue.Queue(maxsize=2)
        
        # Packet buffer for compatibility with existing interface
        self._pkt_lock = threading.Lock()
        self._pkt_buffer: List[bytes] = []
        
        # Statistics
        self.frames_ok = 0
        self.frames_dropped = 0
        self.reconnect_count = 0
        self._frame_id = 0
        self._last_frame_time = time.time()

    # ------------------------------------------------------------------ #
    # RTSP Connection Management
    # ------------------------------------------------------------------ #
    def _open_stream(self) -> bool:
        """
        Open the RTSP stream. Returns True on success.
        
        Uses specific OpenCV settings optimized for RTSP:
        - CAP_FFMPEG backend for better RTSP support
        - Low buffer size to reduce latency
        """
        with self._cap_lock:
            if self._cap is not None:
                self._cap.release()
            
            self._dbg(f"[cooingdv-video] Opening RTSP stream: {self.rtsp_url}")
            
            # Create capture with FFMPEG backend for better RTSP handling
            self._cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
            
            # Configure for low latency
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            if self._cap.isOpened():
                self._dbg("[cooingdv-video] Stream opened successfully")
                self._last_frame_time = time.time()
                return True
            else:
                self._dbg("[cooingdv-video] Failed to open stream")
                self._cap = None
                return False

    def _close_stream(self) -> None:
        """Close the RTSP stream."""
        with self._cap_lock:
            if self._cap is not None:
                self._cap.release()
                self._cap = None
                self._dbg("[cooingdv-video] Stream closed")

    def _reconnect(self) -> bool:
        """Attempt to reconnect to the stream."""
        self.reconnect_count += 1
        self._dbg(f"[cooingdv-video] Reconnection attempt #{self.reconnect_count}")
        
        self._close_stream()
        time.sleep(self.RECONNECT_DELAY)
        
        for attempt in range(self.MAX_RECONNECT_ATTEMPTS):
            if not self._running:
                return False
            
            if self._open_stream():
                return True
            
            self._dbg(f"[cooingdv-video] Reconnect attempt {attempt + 1}/{self.MAX_RECONNECT_ATTEMPTS} failed")
            time.sleep(self.RECONNECT_DELAY)
        
        return False

    # ------------------------------------------------------------------ #
    # BaseVideoProtocolAdapter interface
    # ------------------------------------------------------------------ #
    def send_start_command(self) -> None:
        """
        For RTSP, we don't need to send a start command.
        The stream starts when we connect.
        """
        pass

    def create_receiver_socket(self):
        """
        Not used for RTSP - OpenCV handles the connection.
        Returns None for compatibility.
        """
        return None

    def handle_payload(self, payload: bytes) -> Optional[VideoFrame]:
        """
        Not used for RTSP - frames come from OpenCV directly.
        """
        return None

    # ------------------------------------------------------------------ #
    # Receiver Thread API (matches existing interface)
    # ------------------------------------------------------------------ #
    def start(self) -> None:
        """Start the video receiver thread."""
        if self._rx_thread and self._rx_thread.is_alive():
            return
        
        self._running = True
        self._frame_q = queue.Queue(maxsize=2)
        
        # Open initial connection
        if not self._open_stream():
            self._dbg("[cooingdv-video] Warning: Could not open stream on start")
        
        # Start receiver thread
        self._rx_thread = threading.Thread(
            target=self._rx_loop,
            daemon=True,
            name="CooingdvVideoRx",
        )
        self._rx_thread.start()
        self._dbg("[cooingdv-video] Receiver thread started")

    def _rx_loop(self) -> None:
        """
        Main receiver loop - reads frames from RTSP stream.
        """
        while self._running:
            # Check if we have a valid capture
            with self._cap_lock:
                cap = self._cap
            
            if cap is None or not cap.isOpened():
                if not self._reconnect():
                    self._dbg("[cooingdv-video] Failed to reconnect, retrying...")
                    time.sleep(self.RECONNECT_DELAY)
                continue
            
            # Try to read a frame
            try:
                ret, frame = cap.read()
                
                if not ret or frame is None:
                    # Check for timeout
                    if time.time() - self._last_frame_time > self.FRAME_TIMEOUT:
                        self._dbg("[cooingdv-video] Frame timeout, reconnecting...")
                        self._reconnect()
                    continue
                
                self._last_frame_time = time.time()
                self._frame_id += 1
                self.frames_ok += 1
                
                # Encode as JPEG (OpenCV handles BGR→YCbCr conversion internally)
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 85]
                _, jpeg_data = cv2.imencode('.jpg', frame, encode_param)
                
                # Create VideoFrame
                video_frame = VideoFrame(
                    frame_id=self._frame_id,
                    data=jpeg_data.tobytes(),
                )
                
                # Add to queue (drop if full)
                try:
                    self._frame_q.put(video_frame, timeout=0.1)
                except queue.Full:
                    self.frames_dropped += 1
                    # Drop oldest frame and add new one
                    try:
                        self._frame_q.get_nowait()
                        self._frame_q.put(video_frame, timeout=0.1)
                    except (queue.Empty, queue.Full):
                        pass
                
            except cv2.error as e:
                self._dbg(f"[cooingdv-video] OpenCV error: {e}")
                self._reconnect()
            except Exception as e:
                self._dbg(f"[cooingdv-video] Unexpected error: {e}")
                time.sleep(0.1)

    def stop(self) -> None:
        """Stop the video receiver and clean up."""
        self._dbg("[cooingdv-video] Stopping...")
        self._running = False
        
        # Wait for thread to finish
        if self._rx_thread and self._rx_thread.is_alive():
            self._rx_thread.join(timeout=2.0)
        
        # Close stream
        self._close_stream()
        
        self._dbg(
            f"[cooingdv-video] Stopped. Stats: "
            f"frames_ok={self.frames_ok}, "
            f"frames_dropped={self.frames_dropped}, "
            f"reconnects={self.reconnect_count}"
        )

    def is_running(self) -> bool:
        """Check if the receiver is running."""
        return self._running and self._rx_thread is not None and self._rx_thread.is_alive()

    def get_frame(self, timeout: float = 1.0) -> Optional[VideoFrame]:
        """Get the next available frame from the queue."""
        try:
            return self._frame_q.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_packets(self) -> List[bytes]:
        """
        Get raw packets - not really applicable for RTSP.
        Returns empty list for compatibility.
        """
        return []

    # ------------------------------------------------------------------ #
    # Keep-alive (not needed for RTSP, but required by base class)
    # ------------------------------------------------------------------ #
    def start_keepalive(self, interval: float = 1.0) -> None:
        """RTSP doesn't need keep-alive packets."""
        pass

    def stop_keepalive(self) -> None:
        """RTSP doesn't need keep-alive packets."""
        pass

