from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Final


WIFI_UAV_DRONE_TYPES: Final[frozenset[str]] = frozenset({
    "wifi_uav",
    "wifi_uav_fld",
    "wifi_uav_uav",
})

_UAV_PREFIXES: Final[tuple[str, ...]] = ("flow_", "flow-", "flow")
_FLD_PREFIXES: Final[tuple[str, ...]] = ("wifi_", "gd89pro_", "wtech-", "wtech_", "drone_")


@dataclass(frozen=True)
class WifiUavCapabilities:
    variant: str
    transport: str
    supports_camera_tilt: bool
    supports_camera_switch: bool
    video_ports: tuple[int, ...]
    rc_command_shape: str


_VARIANT_CAPABILITIES: Final[dict[str, WifiUavCapabilities]] = {
    "fld": WifiUavCapabilities(
        variant="fld",
        transport="fld_compat",
        supports_camera_tilt=True,
        supports_camera_switch=False,
        video_ports=(8800,),
        rc_command_shape="native_ack_embedded",
    ),
    "uav": WifiUavCapabilities(
        variant="uav",
        transport="uav_dual_port",
        supports_camera_tilt=True,
        supports_camera_switch=True,
        video_ports=(8800, 8801),
        rc_command_shape="native_ack_embedded",
    ),
}


def wifi_uav_variant_from_drone_type(drone_type: str) -> str:
    """Map the user-facing DRONE_TYPE onto the internal wifi_uav variant name."""
    normalised = (drone_type or "").strip().lower()
    if normalised == "wifi_uav_fld":
        return "fld"
    if normalised == "wifi_uav_uav":
        return "uav"
    return "auto"


def resolve_wifi_uav_variant(drone_type: str) -> str:
    """
    Resolve the effective wifi_uav transport variant.

    Explicit DRONE_TYPE aliases win. The umbrella `wifi_uav` type stays on the
    legacy/default FLD-compatible path because both K417 and D16/FLOW hardware
    have worked there, while the native UAVSDK-shaped split remains available as
    `DRONE_TYPE=wifi_uav_uav` for experiments.
    """
    explicit = wifi_uav_variant_from_drone_type(drone_type)
    if explicit != "auto":
        return explicit

    ssid = detect_active_wifi_ssid()
    mapped = map_wifi_uav_variant_from_ssid(ssid)
    if mapped:
        return mapped

    return "fld"


def get_wifi_uav_capabilities(variant: str) -> WifiUavCapabilities:
    """Return the internal capability profile for a resolved WiFi-UAV variant."""
    return _VARIANT_CAPABILITIES.get((variant or "").strip().lower(), _VARIANT_CAPABILITIES["fld"])


def resolve_wifi_uav_capabilities(drone_type: str) -> WifiUavCapabilities:
    """Resolve a user-facing DRONE_TYPE to its internal capability profile."""
    return get_wifi_uav_capabilities(resolve_wifi_uav_variant(drone_type))


def map_wifi_uav_variant_from_ssid(ssid: str | None) -> str | None:
    """Map a Wi-Fi SSID prefix onto the app's Uav/Fld backend choice."""
    if not ssid:
        return None

    normalised = ssid.strip().lower()
    if any(normalised.startswith(prefix) for prefix in _UAV_PREFIXES):
        return "fld"
    if any(normalised.startswith(prefix) for prefix in _FLD_PREFIXES):
        return "fld"
    return None


def detect_active_wifi_ssid() -> str | None:
    """
    Best-effort detection of the currently connected Wi-Fi SSID.

    This is intentionally conservative: if platform-specific commands are not
    available or parsing fails, return None and let the caller fall back.
    """
    for env_name in ("WIFI_UAV_SSID", "DRONE_SSID", "WIFI_SSID"):
        value = os.getenv(env_name, "").strip()
        if value:
            return value

    try:
        if sys.platform.startswith("win"):
            return _detect_ssid_windows()
        if sys.platform == "darwin":
            return _detect_ssid_macos()
        return _detect_ssid_linux()
    except Exception:
        return None


def _detect_ssid_windows() -> str | None:
    result = subprocess.run(
        ["netsh", "wlan", "show", "interfaces"],
        capture_output=True,
        text=True,
        timeout=2.0,
        check=False,
    )
    if result.returncode != 0:
        return None

    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped.lower().startswith("ssid") or stripped.lower().startswith("bssid"):
            continue
        _, _, value = stripped.partition(":")
        ssid = value.strip()
        if ssid:
            return ssid
    return None


def _detect_ssid_macos() -> str | None:
    airport = "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport"
    result = subprocess.run(
        [airport, "-I"],
        capture_output=True,
        text=True,
        timeout=2.0,
        check=False,
    )
    if result.returncode != 0:
        return None

    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped.startswith("SSID:"):
            continue
        _, _, value = stripped.partition(":")
        ssid = value.strip()
        if ssid:
            return ssid
    return None


def _detect_ssid_linux() -> str | None:
    for command in (["iwgetid", "-r"], ["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"]):
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
        if result.returncode != 0:
            continue

        output = result.stdout.strip()
        if not output:
            continue

        if command[0] == "nmcli":
            for line in output.splitlines():
                if not line.startswith("yes:"):
                    continue
                ssid = line.split(":", 1)[1].strip()
                if ssid:
                    return ssid
        else:
            return output

    return None
