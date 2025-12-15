import logging

log = logging.getLogger(__name__)

class DebugRcProtocolAdapter:
    """Dummy RC protocol adapter for debugging."""

    def __init__(self):
        log.info("Debug RC protocol adapter initialized.")

    def send_control_data(self, data: bytes):
        log.debug(f"Debug: send_control_data({data.hex() if isinstance(data, bytes) else data})") 