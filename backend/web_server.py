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

import cv2
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from starlette.middleware.cors import CORSMiddleware

# ───────────────────────────────────────────────────────────────
# Domain-specific imports
# ───────────────────────────────────────────────────────────────
from models.s2x_rc import S2xDroneModel
from protocols.s2x_rc_protocol_adapter import S2xRCProtocolAdapter
from protocols.s2x_video_protocol import S2xVideoProtocolAdapter
from services.flight_controller import FlightController
from services.video_receiver import VideoReceiverService

# ───────────────────────────────────────────────────────────────
# FastAPI app + permissive CORS (tighten in production!)
# ───────────────────────────────────────────────────────────────
app = FastAPI(title="Drone web adapter")

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


# ───────────────────────────────────────────────────────────────
# Boot drone services at web-server startup
# ───────────────────────────────────────────────────────────────
@app.on_event("startup")
async def _startup() -> None:
    global flight_controller, receiver

    drone_ip = os.getenv("DRONE_IP", "172.16.10.1")
    ctrl_port = int(os.getenv("CONTROL_PORT", 8080))
    video_port = int(os.getenv("VIDEO_PORT", 8888))

    # 1. RC / flight
    model = S2xDroneModel()
    rc_proto = S2xRCProtocolAdapter(drone_ip, ctrl_port)
    flight_controller = FlightController(model, rc_proto)
    flight_controller.start()

    # 2. video
    video_proto = S2xVideoProtocolAdapter(drone_ip, ctrl_port, video_port)
    receiver = VideoReceiverService(video_proto, RAW_Q)
    video_proto.send_start_command()
    receiver.start()

    # 3️. bridge thread-queue → asyncio-queue
    asyncio.create_task(_frame_pump(RAW_Q))


@app.on_event("shutdown")
async def _shutdown() -> None:
    # graceful teardown (optional)
    if flight_controller:
        flight_controller.stop()

    if receiver:
        receiver.stop()


# ───────────────────────────────────────────────────────────────
# Thread → asyncio bridge
# ───────────────────────────────────────────────────────────────
async def _frame_pump(src_q: queue.Queue) -> None:
    """Convert frames to JPEG (if needed) and push into FRAME_Q."""
    loop = asyncio.get_running_loop()

    def worker() -> None:
        while True:
            frame = src_q.get()  # blocks in thread
            if frame is None:
                continue

            # Already JPEG?
            if getattr(frame, "format", "jpeg") == "jpeg":
                jpg_bytes: bytes = frame.data
            else:
                ok, jpg = cv2.imencode(".jpg", frame.data)
                if not ok:
                    continue
                jpg_bytes = jpg.tobytes()

            # hand off to event loop safely
            try:
                loop.call_soon_threadsafe(FRAME_Q.put_nowait, jpg_bytes)
            except asyncio.QueueFull:
                # consumer (browser) too slow – drop frame
                pass

    # run worker in default ThreadPoolExecutor
    await asyncio.to_thread(worker)


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
# WebSocket -> flight controller
# ───────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            data = await ws.receive_json()
            if data.get("type") == "axes" and flight_controller:
                flight_controller.set_axes(
                    data.get("throttle", 0.0),
                    data.get("yaw", 0.0),
                    data.get("pitch", 0.0),
                    data.get("roll", 0.0),
                )
    except WebSocketDisconnect:
        pass
