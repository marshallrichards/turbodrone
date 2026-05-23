import os
import unittest

from protocols.x69_lg_rtsp_video_protocol import (
    X69LgRtspVideoProtocolAdapter,
    build_x69_rtsp_url,
)


class TestX69LgRtspVideoProtocol(unittest.TestCase):
    def test_build_url_default_port(self):
        url = build_x69_rtsp_url(
            drone_ip="172.16.11.1",
            video_port=554,
            rtsp_path="/live/ch00_1",
            rtsp_url=None,
        )
        self.assertEqual(url, "rtsp://172.16.11.1/live/ch00_1")

    def test_build_url_custom_port(self):
        url = build_x69_rtsp_url(
            drone_ip="172.16.11.1",
            video_port=8554,
            rtsp_path="/live/ch00_1",
            rtsp_url=None,
        )
        self.assertEqual(url, "rtsp://172.16.11.1:8554/live/ch00_1")

    def test_build_url_override(self):
        url = build_x69_rtsp_url(
            drone_ip="ignored",
            video_port=1,
            rtsp_path="/ignored",
            rtsp_url="rtsp://10.0.0.5/custom",
        )
        self.assertEqual(url, "rtsp://10.0.0.5/custom")

    def test_adapter_uses_env_url(self):
        os.environ["X69_LG_RTSP_URL"] = "rtsp://172.16.11.1/live/ch00_1"
        adapter = X69LgRtspVideoProtocolAdapter(debug=False)
        self.assertEqual(adapter.rtsp_url, "rtsp://172.16.11.1/live/ch00_1")
        del os.environ["X69_LG_RTSP_URL"]


if __name__ == "__main__":
    unittest.main()
