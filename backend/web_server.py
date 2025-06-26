"""web_server.py – FastAPI bridge
----------------------------------------------------------------
* Streams MJPEG at `/mjpeg`
* Accepts joystick/game-pad JSON over `/ws`
----------------------------------------------------------------
"""

from __future__ import annotations

import asyncio
import os
import queue
from typing import Optional
import threading
from contextlib import asynccontextmanager

import cv2
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from starlette.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

# ───────────────────────────────────────────────────────────────
# Domain-specific imports
# ───────────────────────────────────────────────────────────────
from models.s2x_rc import S2xDroneModel
from protocols.s2x_rc_protocol_adapter import S2xRCProtocolAdapter
from protocols.s2x_video_protocol import S2xVideoProtocolAdapter
from models.wifi_uav_rc import WifiUavRcModel
from protocols.wifi_uav_rc_protocol_adapter import WifiUavRcProtocolAdapter
from protocols.wifi_uav_video_protocol import WifiUavVideoProtocolAdapter
from models.debug_rc import DebugRcModel
from protocols.debug_rc_protocol_adapter import DebugRcProtocolAdapter
from protocols.debug_video_protocol import DebugVideoProtocolAdapter
from services.flight_controller import FlightController
from services.video_receiver import VideoReceiverService
from control.strategies import DirectStrategy, IncrementalStrategy
from plugins.manager import PluginManager

# ───────────────────────────────────────────────────────────────
# Globals to track the pump
# ───────────────────────────────────────────────────────────────
_pump_stop: threading.Event | None = None
_pump_thread: threading.Thread | None = None

# List of active WebSocket connections for overlays
overlay_websockets: list[WebSocket] = []

class OverlayBroadcaster:
    def __init__(self, overlay_q: queue.Queue, loop: asyncio.AbstractEventLoop):
        self._q = overlay_q
        self._loop = loop
        self._stop_evt = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop_evt.set()
        self._thread.join(timeout=1)

    def _run(self):
        while not self._stop_evt.is_set():
            try:
                overlay_data = self._q.get(timeout=1)
                future = asyncio.run_coroutine_threadsafe(
                    self.broadcast(overlay_data), self._loop
                )
                future.result()
            except queue.Empty:
                continue

    async def broadcast(self, data: list):
        for ws in list(overlay_websockets):
            try:
                await ws.send_json(data)
            except WebSocketDisconnect:
                overlay_websockets.remove(ws)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global flight_controller, receiver, video_keepalive, _pump_stop, _pump_thread, plugin_manager
    drone_type = os.getenv("DRONE_TYPE", "s2x")

    if drone_type == "s2x":
        print("[main] Using S2X drone implementation.")
        default_ip = "172.16.10.1"
        default_ctrl_port = 8080
        default_video_port = 8888
        
        drone_ip = os.getenv("DRONE_IP", default_ip)
        ctrl_port = int(os.getenv("CONTROL_PORT", default_ctrl_port))
        video_port = int(os.getenv("VIDEO_PORT", default_video_port))

        model = S2xDroneModel()
        rc_proto = S2xRCProtocolAdapter(drone_ip, ctrl_port)
        video_adapter_cls  = S2xVideoProtocolAdapter
        video_adapter_args = {
            "drone_ip":   drone_ip,
            "control_port": ctrl_port,
            "video_port": video_port,
            "debug":      False,
        }

    elif drone_type == "wifi_uav":
        print("[main] Using WiFi UAV drone implementation.")
        default_ip = "192.168.169.1"
        default_ctrl_port = 8800
        default_video_port = 8800

        drone_ip = os.getenv("DRONE_IP", default_ip)
        ctrl_port = int(os.getenv("CONTROL_PORT", default_ctrl_port))
        video_port = int(os.getenv("VIDEO_PORT", default_video_port))

        model = WifiUavRcModel()
        rc_proto = WifiUavRcProtocolAdapter(drone_ip, ctrl_port)
        video_adapter_cls  = WifiUavVideoProtocolAdapter
        video_adapter_args = {
            "drone_ip":   drone_ip,
            "control_port": ctrl_port,
            "video_port": video_port,
            "debug":      False,   # keep verbose output
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
    PLUGIN_FRAME_Q = queue.Queue(maxsize=100)
    PLUGIN_OVERLAY_Q = queue.Queue(maxsize=100)
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
RAW_Q: queue.Queue = queue.Queue(maxsize=200)          # thread-safe → pump
FRAME_Q: asyncio.Queue[bytes] = asyncio.Queue(100)     # asyncio → /mjpeg

flight_controller: Optional[FlightController] = None
receiver: Optional[VideoReceiverService] = None
plugin_manager: Optional[PluginManager] = None

video_keepalive: "VideoKeepAlive | None" = None

# ───────────────────────────────────────────────────────────────
# Frame-pump implementation
# ───────────────────────────────────────────────────────────────
def _frame_pump_worker(
    src_q: queue.Queue,
    plugin_q: queue.Queue,
    stop_evt: threading.Event,
    loop: asyncio.AbstractEventLoop,       # <-- receive main loop
) -> None:
    """
    Convert incoming frames to JPEG (if needed) and pass them into the
    asyncio queue.  Runs in its own *daemon* thread.
    """

    while not stop_evt.is_set():
        try:
            frame = src_q.get(timeout=0.5)
        except queue.Empty:
            continue
        if frame is None:                     # sentinel
            break

        # --- Feed plugins ------------------------------------------------
        # Plugins get the raw VideoFrame object
        try:
            plugin_q.put_nowait(frame)
        except queue.Full:
            pass # Plugins will just miss a frame

        # --- JPEG encode -------------------------------------------------
        if getattr(frame, "format", "jpeg") == "jpeg":
            jpg_bytes: bytes = frame.data
        else:
            ok, jpg = cv2.imencode(".jpg", frame.data)
            if not ok:
                continue
            jpg_bytes = jpg.tobytes()
        # -----------------------------------------------------------------

        try:
            loop.call_soon_threadsafe(FRAME_Q.put_nowait, jpg_bytes)
        except asyncio.QueueFull:
            pass


# ───────────────────────────────────────────────────────────────
# MJPEG HTTP endpoint
# ───────────────────────────────────────────────────────────────
@app.get("/mjpeg")
async def mjpeg() -> StreamingResponse:
    boundary = b"--frame"

    async def generator():
        while True:
            jpg = await FRAME_Q.get()
            yield (
                boundary + b"\r\n"
                + f"Content-Length: {len(jpg)}\r\n".encode()
                + b"Content-Type: image/jpeg\r\n\r\n"
                + jpg + b"\r\n"
            )

    return StreamingResponse(
        generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache"},
    )


# ───────────────────────────────────────────────────────────────
# Plugin HTTP endpoints
# ───────────────────────────────────────────────────────────────
@app.get("/plugins")
async def list_plugins():
    if not plugin_manager:
        return {"error": "Plugin manager not available"}
    return {
        "available": plugin_manager.available(),
        "running": plugin_manager.running(),
    }

@app.post("/plugins/{name}/start")
async def start_plugin(name: str):
    if not plugin_manager:
        return {"error": "Plugin manager not available"}
    plugin_manager.start(name)
    return {"running": plugin_manager.running()}

@app.post("/plugins/{name}/stop")
async def stop_plugin(name: str):
    if not plugin_manager:
        return {"error": "Plugin manager not available"}
    plugin_manager.stop(name)
    return {"running": plugin_manager.running()}


# ───────────────────────────────────────────────────────────────
# WebSocket -> flight controller
# ───────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            data = await ws.receive_json()
            if data["type"] == "axes":
                mode = data.get("mode", "abs")
                if mode == "abs":
                    if not isinstance(flight_controller.model.strategy, DirectStrategy):
                        flight_controller.model.set_strategy(DirectStrategy())
                else:   # "inc"
                    if not isinstance(flight_controller.model.strategy, IncrementalStrategy):
                        flight_controller.model.set_strategy(IncrementalStrategy())

                flight_controller.set_axes(
                    data["throttle"], data["yaw"], data["pitch"], data["roll"]
                )
            elif data["type"] == "set_profile":
                flight_controller.model.set_profile(data["name"])
            elif data["type"] == "takeoff":
                if flight_controller and hasattr(flight_controller.model, 'takeoff'):
                    flight_controller.model.takeoff()
                    print("[WebSocket] Takeoff command received")
            elif data["type"] == "land":
                if flight_controller and hasattr(flight_controller.model, 'land'):
                    flight_controller.model.land()
                    print("[WebSocket] Land command received")
    except WebSocketDisconnect:
        print("[WebSocket] Client disconnected")
        # Optionally, reset controls or land the drone if appropriate
        # if flight_controller and hasattr(flight_controller.model, 'land'):
        #     flight_controller.model.land() # Example: auto-land on disconnect
    except Exception as e:
        print(f"[WebSocket] Error: {e}")


class VideoKeepAlive:
    """Periodically sends a start-stream command to the drone until stopped."""

    def __init__(self, send_start_cmd, interval: float = 2.0):
        self._send_start_cmd = send_start_cmd
        self._interval       = interval
        self._stop           = threading.Event()
        self._thread         = threading.Thread(
            target=self._loop,
            name="VideoKeepAlive",
            daemon=True
        )

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=1.0)

    def _loop(self):
        while not self._stop.is_set():
            self._send_start_cmd()
            # wait() lets us wake up immediately on stop()
            self._stop.wait(self._interval)

@app.websocket("/ws/overlays")
async def overlays_endpoint(ws: WebSocket):
    await ws.accept()
    overlay_websockets.append(ws)
    try:
        while True:
            await ws.receive_text() # Keep connection open
    except WebSocketDisconnect:
        print("[Overlays] Client disconnected")
        overlay_websockets.remove(ws)
