from __future__ import annotations

import json
from typing import Mapping


CTP_SIGNATURE = b"CTP:"
OP_PUT = "PUT"


def build_ctp_packet(
    topic: str,
    params: Mapping[str, str] | None = None,
    *,
    operation: str = OP_PUT,
) -> bytes:
    """
    Build the Jieli CTP envelope used by KY FPV's DeviceClient backend.

    Format:
      CTP: + le16(topic_length) + topic + le32(json_length) + json
    """
    payload: dict[str, object] = {"op": operation}
    if params:
        payload["param"] = dict(params)

    topic_bytes = topic.encode("utf-8")
    json_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    return (
        CTP_SIGNATURE
        + len(topic_bytes).to_bytes(2, "little", signed=False)
        + topic_bytes
        + len(json_bytes).to_bytes(4, "little", signed=False)
        + json_bytes
    )


def parse_ctp_packet(packet: bytes) -> tuple[str, dict]:
    """Parse a CTP packet. Intended for tests and diagnostics."""
    if not packet.startswith(CTP_SIGNATURE):
        raise ValueError("missing CTP signature")
    offset = len(CTP_SIGNATURE)
    if len(packet) < offset + 2:
        raise ValueError("missing topic length")
    topic_len = int.from_bytes(packet[offset : offset + 2], "little")
    offset += 2
    topic = packet[offset : offset + topic_len].decode("utf-8")
    offset += topic_len
    if len(packet) < offset + 4:
        raise ValueError("missing payload length")
    payload_len = int.from_bytes(packet[offset : offset + 4], "little")
    offset += 4
    payload = json.loads(packet[offset : offset + payload_len].decode("utf-8"))
    return topic, payload
