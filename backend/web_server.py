import asyncio
import threading
import queue
import time
from contextlib import asynccontextmanager
from typing import Any, Optional
import logging

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
        # Copy to avoid mutation during iteration
        for connection in list(self.active_connections):
            if connection.client_state == WebSocketState.CONNECTED:
                try:
                    await connection.send_text(message)
                except Exception:
                    self.disconnect(connection)

    async def broadcast_bytes(self, message: bytes):
        # Copy to avoid mutation during iteration
        for connection in list(self.active_connections):
            if connection.client_state == WebSocketState.CONNECTED:
                try:
                    await connection.send_bytes(message)
                except Exception:
                    self.disconnect(connection)

    async def broadcast_json(self, obj: Any):
        # Copy to avoid mutation during iteration
        for connection in list(self.active_connections):
            if connection.client_state == WebSocketState.CONNECTED:
                try:
                    await connection.send_json(obj)
                except Exception:
                    self.disconnect(connection)

# Load environment variables
dotenv.load_dotenv()

# Feature flags
PLUGINS_ENABLED = os.getenv("PLUGINS_ENABLED", "false").lower() in ("1", "true", "yes", "on")

# Basic logging configuration (industry-standard: Python stdlib logging).
# Set LOG_LEVEL=DEBUG to see verbose control-loop logs.
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Managers for WebSocket connections
overlay_manager = ConnectionManager()
video_manager = ConnectionManager()

class FrameHub:
    """
    Fan-out hub for MJPEG frames.

    Each /mjpeg client gets its own asyncio.Queue, so multiple clients don't
    steal frames from each other.
    """
    def __init__(self, per_client_queue_size: int = 2):
        self._per_client_queue_size = per_client_queue_size
        self._clients: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def register(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(self._per_client_queue_size)
        async with self._lock:
            self._clients.add(q)
        return q

    async def unregister(self, q: asyncio.Queue) -> None:
        async with self._lock:
            self._clients.discard(q)

    async def publish(self, frame: Optional[bytes]) -> None:
        # Snapshot under lock; we only do non-blocking puts.
        async with self._lock:
            clients = list(self._clients)

        for q in clients:
            try:
                q.put_nowait(frame)
            except asyncio.QueueFull:
                # Drop oldest then try again.
                try:
                    _ = q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    q.put_nowait(frame)
                except Exception:
                    # Give up on this client queue; it's likely stalled.
                    await self.unregister(q)

FRAME_HUB = FrameHub(per_client_queue_size=2)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global flight_controller, receiver, plugin_manager

    drone_type = os.getenv("DRONE_TYPE", "s2x").lower()
    
    logger.info("[main] Using drone type: %s", drone_type)

    if drone_type == "s2x":
        logger.info("[main] Using S2X drone implementation.")
        # Allow overriding IP and ports via env to match prior behavior
        default_ip = "172.16.10.1"
        default_ctrl_port = 8080
        default_video_port = 8888

        drone_ip = os.getenv("DRONE_IP", default_ip)
        ctrl_port = int(os.getenv("CONTROL_PORT", default_ctrl_port))
        video_port = int(os.getenv("VIDEO_PORT", default_video_port))

        model = S2xRcModel()
        rc_proto = S2xRCProtocolAdapter(drone_ip, ctrl_port)
        # Optional remap via env: some S2x variants swap yaw and roll
        try:
            rc_proto.swap_yaw_roll = os.getenv("S2X_SWAP_YAW_ROLL", "false").lower() in ("1", "true", "yes", "on")
            if rc_proto.swap_yaw_roll:
                logger.info("[main] S2X swap_yaw_roll enabled")
        except Exception:
            pass
        video_adapter_cls = S2xVideoProtocolAdapter
        video_adapter_args = {
            "drone_ip": drone_ip,
            "control_port": ctrl_port,
            "video_port": video_port,
        }
    elif drone_type == "wifi_uav":
        logger.info("[main] Using WiFi UAV drone implementation.")
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
        logger.info("[main] Using debug drone implementation.")
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
    # Optional: enable low-level RC packet debug via env
    try:
        if os.getenv("RC_DEBUG_PACKETS", "false").lower() in ("1", "true", "yes", "on"):
            try:
                rc_proto.toggle_debug()
                logger.info("[main] RC packet debug: ON")
            except Exception:
                pass
    except Exception:
        pass

    flight_controller = FlightController(model, rc_proto)
    flight_controller.start()

    # 3. Plugins (optional)
    plugin_frame_q: Optional[queue.Queue] = None
    overlay_broadcaster: Optional["OverlayBroadcaster"] = None
    if PLUGINS_ENABLED:
        PLUGIN_FRAME_Q = DroppingQueue(maxsize=100)
        PLUGIN_OVERLAY_Q = DroppingQueue(maxsize=100)
        plugin_manager = PluginManager(flight_controller, PLUGIN_FRAME_Q, PLUGIN_OVERLAY_Q)
        plugin_frame_q = PLUGIN_FRAME_Q

        # Start overlay broadcaster only when plugins are enabled
        overlay_broadcaster = OverlayBroadcaster(PLUGIN_OVERLAY_Q, asyncio.get_running_loop())
        overlay_broadcaster.start()
        logger.info("[plugins] Plugins enabled")
    else:
        plugin_manager = None
        logger.info("[plugins] Plugins disabled (set PLUGINS_ENABLED=true to enable)")

    # 4. start bridge thread (daemon) for video pump (always, for MJPEG)
    _pump_stop = threading.Event()
    main_loop = asyncio.get_running_loop()
    _pump_thread = threading.Thread(
        target=_frame_pump_worker,
        args=(RAW_Q, plugin_frame_q, FRAME_HUB, _pump_stop, main_loop),
        name="FramePump",
        daemon=True,
    )
    _pump_thread.start()

    yield

    # Shutdown
    if overlay_broadcaster:
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

flight_controller: Optional[FlightController] = None
receiver: Optional[VideoReceiverService] = None
plugin_manager: Optional[PluginManager] = None

video_keepalive = None  # legacy; no longer used

# ───────────────────────────────────────────────────────────────
# Plugin Management
# ───────────────────────────────────────────────────────────────
@app.get("/plugins")
async def get_plugins():
    if not PLUGINS_ENABLED:
        raise HTTPException(status_code=404, detail="Plugins disabled")
    if not plugin_manager:
        raise HTTPException(status_code=503, detail="PluginManager not available")
    return {
        "available": plugin_manager.available(),
        "running": plugin_manager.running(),
    }

@app.post("/plugins/{name}/start")
async def start_plugin(name: str):
    if not PLUGINS_ENABLED:
        raise HTTPException(status_code=404, detail="Plugins disabled")
    if not plugin_manager:
        raise HTTPException(status_code=503, detail="PluginManager not available")
    try:
        # Current architecture can technically run multiple plugins, but they
        # will compete for frames from the shared plugin frame queue. For now
        # we enforce a single running plugin for predictable behavior.
        running = plugin_manager.running()
        if running and name not in running:
            raise HTTPException(
                status_code=409,
                detail=f"Another plugin is already running: {running}. Stop it first.",
            )
        started = plugin_manager.start(name)
        if not started:
            raise HTTPException(status_code=409, detail="Plugin already running")
        return {"status": "started", "name": name}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/plugins/{name}/stop")
async def stop_plugin(name: str):
    if not PLUGINS_ENABLED:
        raise HTTPException(status_code=404, detail="Plugins disabled")
    if not plugin_manager:
        raise HTTPException(status_code=503, detail="PluginManager not available")
    try:
        stopped = plugin_manager.stop(name)
        if not stopped:
            raise HTTPException(status_code=409, detail="Plugin not running")
        return {"status": "stopped", "name": name}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
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
    except Exception:
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

                # If any plugin is running, completely ignore frontend control commands
                # Frontend should already be suppressing these, but this is a safety check
                plugin_running = bool(plugin_manager and plugin_manager.running())

                if plugin_running:
                    # Plugin has full control - don't process frontend axes at all
                    pass
                else:
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
                    
                    flight_controller.set_axes_from("frontend", throttle, yaw, pitch, roll)
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
        logger.info("[WebSocket] Client disconnected")
    except Exception as e:
        logger.exception("[WebSocket] Error: %s", e)

# ───────────────────────────────────────────────────────────────
# Video streaming
# ───────────────────────────────────────────────────────────────

def _frame_pump_worker(
    raw_q: queue.Queue,
    plugin_q: Optional[queue.Queue],
    frame_hub: FrameHub,
    stop_event: threading.Event,
    loop: asyncio.AbstractEventLoop,
):
    """
    This worker runs in a separate thread and pumps frames from the
    thread-safe queue to the asyncio queues.
    """
    # Wait for the very first frame before starting keepalive, to avoid
    # prematurely closing the MJPEG stream during initial connection.
    first_frame_seen = False
    last_frame_time = time.monotonic()
    timed_out = False
    while not stop_event.is_set() and not first_frame_seen:
        try:
            frame = raw_q.get(timeout=5.0)
            if frame:
                first_frame_seen = True
                last_frame_time = time.monotonic()
                # Send to MJPEG/overlay pipelines immediately
                asyncio.run_coroutine_threadsafe(frame_hub.publish(frame.data), loop)
                if plugin_q is not None:
                    try:
                        plugin_q.put_nowait(frame)
                    except queue.Full:
                        pass
                break
        except queue.Empty:
            # keep waiting for initial frame without killing the stream
            continue

    # After frames start flowing, if the stream stalls for too long we close
    # existing MJPEG clients by publishing None. (Pump continues regardless.)
    stream_timeout_s = 3.0
    while not stop_event.is_set():
        try:
            frame = raw_q.get(timeout=1.0)
            if frame:
                last_frame_time = time.monotonic()
                timed_out = False
                try:
                    asyncio.run_coroutine_threadsafe(frame_hub.publish(frame.data), loop)
                except Exception:
                    pass
                if plugin_q is not None:
                    try:
                        plugin_q.put_nowait(frame)
                    except queue.Full:
                        pass
        except queue.Empty:
            if first_frame_seen and not timed_out and (time.monotonic() - last_frame_time) > stream_timeout_s:
                timed_out = True
                try:
                    asyncio.run_coroutine_threadsafe(frame_hub.publish(None), loop)
                except Exception:
                    pass
            continue

@app.get("/mjpeg")
async def mjpeg_stream():
    """
    Streams JPEG frames over HTTP multipart/x-mixed-replace.
    """
    from fastapi.responses import StreamingResponse
    
    async def frame_generator():
        q = await FRAME_HUB.register()
        try:
            while True:
                frame = await q.get()
                if frame is None:
                    break
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                )
        finally:
            await FRAME_HUB.unregister(q)

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
                # IMPORTANT: empty overlays are sent as [] and must still be broadcast,
                # otherwise the frontend will keep rendering the last overlay forever.
                if data is None:
                    continue

                # Plugins typically put python objects (lists/dicts) into this queue.
                # The frontend expects JSON. IMPORTANT: decide which coroutine to create
                # BEFORE constructing it, otherwise an un-awaited coroutine may be
                # garbage-collected (RuntimeWarning: coroutine was never awaited).
                if isinstance(data, (str, bytes)):
                    msg = data if isinstance(data, str) else data.decode("utf-8", errors="ignore")
                    coro = overlay_manager.broadcast(msg)
                else:
                    coro = overlay_manager.broadcast_json(data)

                future = asyncio.run_coroutine_threadsafe(coro, self.loop)
                future.result(timeout=1.0)
            except queue.Empty:
                continue
            except Exception as e:
                logger.exception("[OverlayBroadcaster] Error: %s", e)
