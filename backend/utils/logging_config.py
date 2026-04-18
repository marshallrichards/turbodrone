from __future__ import annotations

import logging
import os

import dotenv


_BOOTSTRAPPED = False
_CONFIGURED = False
_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def _normalise_level(raw: str | None) -> str:
    value = (raw or "INFO").strip().upper()
    if value == "WARN":
        return "WARNING"
    if value not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}:
        return "INFO"
    return value


def bootstrap_runtime() -> None:
    """
    Load `.env` and set sane defaults for noisy native libraries before modules
    that import `cv2` are loaded.
    """
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return

    dotenv.load_dotenv()

    level_name = _normalise_level(os.getenv("LOG_LEVEL"))
    debug_native = level_name == "DEBUG"

    # Keep OpenCV / FFmpeg mostly quiet by default. These can still be
    # overridden explicitly by environment variables if needed.
    os.environ.setdefault("OPENCV_LOG_LEVEL", "INFO" if debug_native else "ERROR")
    os.environ.setdefault("OPENCV_FFMPEG_LOGLEVEL", "32" if debug_native else "16")
    os.environ.setdefault("OPENCV_VIDEOIO_DEBUG", "1" if debug_native else "0")
    os.environ.setdefault("OPENCV_FFMPEG_DEBUG", "1" if debug_native else "0")

    _BOOTSTRAPPED = True


def configure_logging(level: str | None = None) -> str:
    """
    Configure stdlib logging for backend entrypoints.

    Returns the resolved log level name.
    """
    global _CONFIGURED

    bootstrap_runtime()

    level_name = _normalise_level(level or os.getenv("LOG_LEVEL"))
    level_value = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=level_value, format=_LOG_FORMAT)
    else:
        root.setLevel(level_value)
        for handler in root.handlers:
            if handler.formatter is None:
                handler.setFormatter(logging.Formatter(_LOG_FORMAT))

    _CONFIGURED = True
    return level_name
