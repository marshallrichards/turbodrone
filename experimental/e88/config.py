from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class E88Config:
    rtsp_url: str = "rtsp://192.168.1.1:7070/webcam"
    drone_ip: str = "192.168.1.1"
    drone_port: int = 7099
    source_port: int = 7099
    control_interval_sec: float = 0.03
    video_reopen_delay_sec: float = 2.0
