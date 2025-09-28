import asyncio
import threading
import queue
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState
import os
import dotenv

from services.flight_controller import FlightController
from control.strategies import DirectStrategy, IncrementalStrategy
from services.video_receiver import VideoReceiverService
from models.s2x_rc import S2xDroneModel as S2xRcModel
from models.debug_rc import DebugRcModel
from protocols.s2x_rc_protocol_adapter import S2xRCProtocolAdapter
from protocols.debug_rc_protocol_adapter import DebugRcProtocolAdapter
from protocols.s2x_video_protocol import S2xVideoProtocolAdapter
from protocols.debug_video_protocol import DebugVideoProtocolAdapter
from protocols.wifi_uav_rc_protocol_adapter import WifiUavRcProtocolAdapter
from protocols.wifi_uav_video_protocol import WifiUavVideoProtocolAdapter
from models.wifi_uav_rc import WifiUavRcModel
from plugins.manager import PluginManager
from utils.dropping_queue import DroppingQueue


class ConnectionManager:
    """
    Manages active WebSocket connections for broadcasting messages.
    """
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            if connection.client_state == WebSocketState.CONNECTED:
                await connection.send_text(message)

    async def broadcast_bytes(self, message: bytes):
        for connection in self.active_connections:
            if connection.client_state == WebSocketState.CONNECTED:
                await connection.send_bytes(message)

# Load environment variables
dotenv.load_dotenv()

# Managers for WebSocket connections
overlay_manager = ConnectionManager()
video_manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global flight_controller, receiver, plugin_manager, video_keepalive

    drone_type = os.getenv("DRONE_TYPE", "s2x").lower()
    
    print(f"[main] Using drone type: {drone_type}")

    if drone_type == "s2x":
        print("[main] Using S2X drone implementation.")
        # Allow overriding IP and ports via env to match prior behavior
        default_ip = "172.16.10.1"
        default_ctrl_port = 8080
        default_video_port = 8888

        drone_ip = os.getenv("DRONE_IP", default_ip)
        ctrl_port = int(os.getenv("CONTROL_PORT", default_ctrl_port))
        video_port = int(os.getenv("VIDEO_PORT", default_video_port))

        model = S2xRcModel()
        rc_proto = S2xRCProtocolAdapter(drone_ip, ctrl_port)
        video_adapter_cls = S2xVideoProtocolAdapter
        video_adapter_args = {
            "drone_ip": drone_ip,
            "control_port": ctrl_port,
            "video_port": video_port,
        }
    elif drone_type == "wifi_uav":
        print("[main] Using WiFi UAV drone implementation.")
        # Align with previous working setup: env-configurable IP and ports
        default_ip = "192.168.169.1"
        default_ctrl_port = 8800
        default_video_port = 8800

        drone_ip = os.getenv("DRONE_IP", default_ip)
        ctrl_port = int(os.getenv("CONTROL_PORT", default_ctrl_port))
        video_port = int(os.getenv("VIDEO_PORT", default_video_port))

        model = WifiUavRcModel()
        rc_proto = WifiUavRcProtocolAdapter(drone_ip, ctrl_port)
        video_adapter_cls = WifiUavVideoProtocolAdapter
        video_adapter_args = {
            "drone_ip": drone_ip,
            "control_port": ctrl_port,
            "video_port": video_port,
            "debug": False,
        }
    elif drone_type == "debug":
        print("[main] Using debug drone implementation.")
        model = DebugRcModel()
        rc_proto = DebugRcProtocolAdapter()
        video_adapter_cls = DebugVideoProtocolAdapter
        video_adapter_args = {"camera_index": 0, "debug": False}
    else:
        raise ValueError(f"Unknown drone type: {drone_type}")

    # 1. Video – let the service create / recycle the adapter
    video_service_args = {
        "protocol_adapter_class": video_adapter_cls,
        "protocol_adapter_args": video_adapter_args,
        "frame_queue": RAW_Q,
    }
    if drone_type == "wifi_uav":
        video_service_args["rc_adapter"] = rc_proto
    
    receiver = VideoReceiverService(**video_service_args)
    receiver.start()

    # Wait a moment for video to stabilize
    await asyncio.sleep(1)

    # 2. RC / flight
    flight_controller = FlightController(model, rc_proto)
    flight_controller.start()

    # 3. Plugin Manager
    PLUGIN_FRAME_Q = DroppingQueue(maxsize=100)
    PLUGIN_OVERLAY_Q = DroppingQueue(maxsize=100)
    plugin_manager = PluginManager(flight_controller, PLUGIN_FRAME_Q, PLUGIN_OVERLAY_Q)

    # 4. start bridge thread (daemon) for video pump
    _pump_stop = threading.Event()
    main_loop = asyncio.get_running_loop()
    _pump_thread = threading.Thread(
        target=_frame_pump_worker,
        args=(RAW_Q, PLUGIN_FRAME_Q, _pump_stop, main_loop),
        name="FramePump",
        daemon=True,
    )
    _pump_thread.start()

    # 5. Start overlay broadcaster
    overlay_broadcaster = OverlayBroadcaster(PLUGIN_OVERLAY_Q, main_loop)
    overlay_broadcaster.start()
    
    yield

    # Shutdown
    overlay_broadcaster.stop()
    if plugin_manager:
        plugin_manager.stop_all()
    if flight_controller:
        flight_controller.stop()
    if receiver:
        receiver.stop()
    if _pump_stop:
        _pump_stop.set()
    if _pump_thread:
        _pump_thread.join(timeout=1.0)

# ───────────────────────────────────────────────────────────────
# FastAPI app + permissive CORS (tighten in production!)
# ───────────────────────────────────────────────────────────────
app = FastAPI(title="Drone web adapter", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict in prod
    allow_methods=["*"],
    allow_headers=["*"],
)

# ───────────────────────────────────────────────────────────────
# Global objects (single-drone)
# ───────────────────────────────────────────────────────────────
RAW_Q: queue.Queue = DroppingQueue(maxsize=2)          # thread-safe → pump
FRAME_Q: asyncio.Queue[bytes] = asyncio.Queue(2)     # asyncio → /mjpeg

flight_controller: Optional[FlightController] = None
receiver: Optional[VideoReceiverService] = None
plugin_manager: Optional[PluginManager] = None

video_keepalive: "VideoKeepAlive | None" = None

# ───────────────────────────────────────────────────────────────
# Plugin Management
# ───────────────────────────────────────────────────────────────
@app.get("/plugins")
async def get_plugins():
    if not plugin_manager:
        raise HTTPException(status_code=503, detail="PluginManager not available")
    return {
        "available": plugin_manager.available(),
        "running": plugin_manager.running(),
    }

@app.post("/plugins/{name}/start")
async def start_plugin(name: str):
    if not plugin_manager:
        raise HTTPException(status_code=503, detail="PluginManager not available")
    try:
        plugin_manager.start(name)
        return {"status": "started"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/plugins/{name}/stop")
async def stop_plugin(name: str):
    if not plugin_manager:
        raise HTTPException(status_code=503, detail="PluginManager not available")
    try:
        plugin_manager.stop(name)
        return {"status": "stopped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ───────────────────────────────────────────────────────────────
# Websocket handlers
# ───────────────────────────────────────────────────────────────
@app.websocket("/ws/overlays")
async def websocket_overlay_endpoint(websocket: WebSocket):
    await overlay_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text() # Keep connection open
    except WebSocketDisconnect:
        overlay_manager.disconnect(websocket)

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            if not flight_controller:
                continue

            msg_type = data.get("type")
            if msg_type == "axes":
                mode = data.get("mode", "abs")
                # Switch strategy based on mode (treat "mouse" as absolute)
                try:
                    if mode in ("abs", "mouse"):
                        if not isinstance(flight_controller.model.strategy, DirectStrategy):
                            flight_controller.model.set_strategy(DirectStrategy())
                    else:
                        if not isinstance(flight_controller.model.strategy, IncrementalStrategy):
                            flight_controller.model.set_strategy(IncrementalStrategy())
                except Exception:
                    pass

                throttle = float(data.get("throttle", 0))
                yaw      = float(data.get("yaw", 0))
                pitch    = float(data.get("pitch", 0))
                roll     = float(data.get("roll", 0))
                flight_controller.set_axes(throttle, yaw, pitch, roll)
            elif msg_type == "set_profile":
                try:
                    flight_controller.model.set_profile(data.get("name", "normal"))
                except Exception:
                    pass
            elif msg_type == "takeoff":
                try:
                    flight_controller.model.takeoff()
                except Exception:
                    pass
            elif msg_type == "land":
                try:
                    flight_controller.model.land()
                except Exception:
                    pass
    except WebSocketDisconnect:
        print("[WebSocket] Client disconnected")
    except Exception as e:
        print(f"[WebSocket] Error: {e}")

# ───────────────────────────────────────────────────────────────
# Video streaming
# ───────────────────────────────────────────────────────────────

class VideoKeepAlive(threading.Thread):
    def __init__(self, q: queue.Queue, timeout: int = 1):
        super().__init__(daemon=True)
        self._q = q
        self._timeout = timeout
        self._stop = threading.Event()

    def run(self):
        while not self._stop.is_set():
            try:
                self._q.get(timeout=self._timeout)
            except queue.Empty:
                print("[MJPEG] Keep-alive failed. Stopping video stream.")
                break
        
        # This will terminate the /mjpeg endpoint stream
        try:
            FRAME_Q.put_nowait(None)
        except asyncio.QueueFull:
            pass # Loop may already be closing

    def stop(self):
        self._stop.set()

def _frame_pump_worker(
    raw_q: queue.Queue,
    plugin_q: queue.Queue,
    stop_event: threading.Event,
    loop: asyncio.AbstractEventLoop,
):
    """
    This worker runs in a separate thread and pumps frames from the
    thread-safe queue to the asyncio queues.
    """
    global video_keepalive
    if video_keepalive:
        video_keepalive.stop()
    
    video_keepalive = VideoKeepAlive(raw_q)
    video_keepalive.start()

    while not stop_event.is_set():
        try:
            frame = raw_q.get(timeout=1.0)
            if frame:
                # Put to MJPEG stream
                try:
                    # Non-blocking put, or drop if the queue is full
                    FRAME_Q.put_nowait(frame.data)
                except asyncio.QueueFull:
                    # This is okay, it means the client is not consuming frames fast enough
                    pass
                
                # Put to plugin manager
                try:
                    plugin_q.put_nowait(frame)
                except queue.Full:
                    pass

        except queue.Empty:
            continue

    if video_keepalive:
        video_keepalive.stop()

@app.get("/mjpeg")
async def mjpeg_stream():
    """
    Streams JPEG frames over HTTP multipart/x-mixed-replace.
    """
    from fastapi.responses import StreamingResponse
    
    async def frame_generator():
        while True:
            frame = await FRAME_Q.get()
            if frame is None:
                break
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            )

    return StreamingResponse(
        frame_generator(), media_type="multipart/x-mixed-replace; boundary=frame"
    )

class OverlayBroadcaster:
    def __init__(self, q: queue.Queue, loop: asyncio.AbstractEventLoop):
        self.q = q
        self.loop = loop
        self.thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=1.0)

    def _run(self):
        while not self.stop_event.is_set():
            try:
                data = self.q.get(timeout=0.1)
                if data:
                    future = asyncio.run_coroutine_threadsafe(
                        overlay_manager.broadcast(data), self.loop
                    )
                    future.result(timeout=1.0)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[OverlayBroadcaster] Error: {e}")
