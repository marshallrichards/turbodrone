import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


_EXPERIMENTAL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_EXPERIMENTAL_ROOT))

from e88.config import E88Config
from e88.drone import E88Drone


class TestE88SocketSend(unittest.TestCase):
    def test_connect_sends_handshake_packet(self):
        mock_sock = MagicMock()

        with patch("e88.drone.socket.socket", return_value=mock_sock):
            cfg = E88Config(
                rtsp_url="rtsp://127.0.0.1:1/unused",
                drone_ip="192.168.1.1",
                drone_port=7099,
                source_port=7099,
            )
            drone = E88Drone(cfg)

            drone.connect(start_video=False, start_control=False)

        mock_sock.bind.assert_called_once_with(("", 7099))
        mock_sock.sendto.assert_any_call(b"\x08\x01", ("192.168.1.1", 7099))


if __name__ == "__main__":
    unittest.main()
