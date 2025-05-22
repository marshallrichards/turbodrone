import asyncio
import io
import os
from typing import Optional

import cv2
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, FileResponse
from starlette.middleware.cors import CORSMiddleware

from models.s2x_rc import S2xDroneModel
from protocols.s2x_rc_protocol_adapter import S2xRCProtocolAdapter
from protocols.s2x_video_protocol import S2xVideoProtocolAdapter
from services.flight_controller import FlightController
from services.video_receiver import VideoReceiverService

# ---------------------------------------------------------------------
# App & CORS
# ---------------------------------------------------------------------
app = FastAPI(title="Drone web adapter")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dev only – lock down in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------
# Global single-drone objects
# ---------------------------------------------------------------------
FRAME_Q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)
flight_controller: Optional[FlightController] = None


# ---------------------------------------------------------------------
# Start drone services once, when the web server boots
# ---------------------------------------------------------------------
@app.on_event("startup")
async def _startup() -> None:
    global flight_controller

    drone_ip = os.environ.get("DRONE_IP", "172.16.10.1")
    control_port = int(os.environ.get("CONTROL_PORT", 8080))
    video_port   = int(os.environ.get("VIDEO_PORT", 8888))

    # 1. flight
    model = S2xDroneModel()
    rc_proto = S2xRCProtocolAdapter(drone_ip, control_port)
    flight_controller = FlightController(model, rc_proto)
    flight_controller.start()

    # 2. video
    video_proto = S2xVideoProtocolAdapter(drone_ip, control_port, video_port)
    receiver = VideoReceiverService(video_proto, FRAME_Q)
    video_proto.send_start_command()
    receiver.start()

    # 3. background JPEG encoder
    asyncio.create_task(_frame_pump())

async def _frame_pump() -> None:
    """
    Pull raw VideoFrame objects from receiver.frame_queue (running in its own
    thread), JPEG-encode them and push into the asyncio queue that the MJPEG
    endpoint consumes.
    """
    import threading
    recv_q = FRAME_Q  # alias for speed

    def _worker() -> None:
        while True:
            frame = receiver_frame_q.get()         # type: ignore
            ok, jpg = cv2.imencode(".jpg", frame.data)
            if ok:
                try:
                    recv_q.put_nowait(jpg.tobytes())
                except asyncio.QueueFull:
                    pass  # drop if browser is too slow

    # locate the queue inside the VideoReceiverService object
    receiver_frame_q = None
    for t in threading.enumerate():
        if hasattr(t, "name") and t.name.startswith("VideoReceiver"):
            # meh: rely on private attribute – fine for now
            receiver_frame_q = t._target.__self__.frame_queue  # type: ignore
            break

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _worker)


# ---------------------------------------------------------------------
# MJPEG endpoint
# ---------------------------------------------------------------------
@app.get("/mjpeg")
async def mjpeg() -> StreamingResponse:
    boundary = b"--frame"

    async def _gen():
        while True:
            jpg = await FRAME_Q.get()
            yield boundary + b"\r\n"
            yield b"Content-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"

    headers = {"Cache-Control": "no-cache"}
    media_type = "multipart/x-mixed-replace; boundary=frame"
    return StreamingResponse(_gen(), media_type=media_type, headers=headers)


# ---------------------------------------------------------------------
# WebSocket → flight controller
# ---------------------------------------------------------------------
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            data = await ws.receive_json()
            if data.get("type") == "axes":
                fc = flight_controller
                if fc:
                    fc.set_axes(
                        data.get("throttle", 0.0),
                        data.get("yaw", 0.0),
                        data.get("pitch", 0.0),
                        data.get("roll", 0.0),
                    )
    except WebSocketDisconnect:
        pass
