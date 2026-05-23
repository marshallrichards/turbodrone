"""Normalize X69/LG video mode env values."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

H265_ALIASES = frozenset({"h265", "hevc", "udp"})
JPEG_ALIASES = frozenset({"jpeg", "udp_jpeg", "mjpeg"})
RTSP_ALIASES = frozenset({"rtsp"})


def normalize_x69_video_mode(raw: str | None, *, default: str = "rtsp") -> str:
    """
    Return canonical mode: ``jpeg`` | ``rtsp`` | ``h265``.

    Default is ``rtsp``. ``udp`` is a backward-compatible alias for ``h265``.
    """
    mode = (raw or default).lower().strip()
    if mode in H265_ALIASES:
        return "h265"
    if mode in JPEG_ALIASES:
        return "jpeg"
    if mode in RTSP_ALIASES:
        return "rtsp"
    logger.warning(
        "[x69-lg] Unknown X69_LG_VIDEO_MODE=%r, using %s", raw, default
    )
    return default
