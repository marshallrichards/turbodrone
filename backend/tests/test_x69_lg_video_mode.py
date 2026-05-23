import unittest

from protocols.x69_lg_video_mode import normalize_x69_video_mode


class TestX69LgVideoMode(unittest.TestCase):
    def test_h265_aliases(self) -> None:
        for raw in ("h265", "H265", "udp", "hevc"):
            self.assertEqual(normalize_x69_video_mode(raw), "h265")

    def test_jpeg_aliases(self) -> None:
        for raw in ("jpeg", "udp_jpeg", "mjpeg"):
            self.assertEqual(normalize_x69_video_mode(raw), "jpeg")

    def test_rtsp(self) -> None:
        self.assertEqual(normalize_x69_video_mode("rtsp"), "rtsp")

    def test_unknown_defaults_rtsp(self) -> None:
        self.assertEqual(normalize_x69_video_mode("bogus"), "rtsp")

    def test_default_when_unset(self) -> None:
        self.assertEqual(normalize_x69_video_mode(None), "rtsp")


if __name__ == "__main__":
    unittest.main()
