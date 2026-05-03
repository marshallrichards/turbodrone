import unittest

from models.wifi_cam_rc import WifiCamRcModel
from protocols.wifi_cam_rc_protocol_adapter import WifiCamRcProtocolAdapter
from protocols.wifi_cam_video_protocol import WifiCamVideoProtocolAdapter


class WifiCamRcProtocolTests(unittest.TestCase):
    def _adapter(self, mode="short"):
        adapter = WifiCamRcProtocolAdapter.__new__(WifiCamRcProtocolAdapter)
        adapter.command_mode = mode
        adapter.camera_type = 0
        return adapter

    def test_short_packet_matches_base_cmd_layout(self):
        model = WifiCamRcModel()
        model.roll = 128
        model.pitch = 129
        model.throttle = 130
        model.yaw = 131
        model.takeoff_flag = True
        adapter = self._adapter("short")

        packet = adapter.build_control_packet(model)

        expected_checksum = 128 ^ 129 ^ 130 ^ 131 ^ 0x01
        self.assertEqual(packet, bytes([0x66, 128, 129, 130, 131, 0x01, expected_checksum, 0x99]))
        self.assertFalse(model.takeoff_flag)

    def test_short_packet_escapes_marker_checksum(self):
        model = WifiCamRcModel()
        model.roll = 128
        model.pitch = 128
        model.throttle = 128
        model.yaw = 230
        adapter = self._adapter("short")

        packet = adapter.build_control_packet(model)

        self.assertEqual(packet[6], 0x67)

    def test_extended_packet_uses_camera_type_two_in_auto_mode(self):
        model = WifiCamRcModel()
        model.roll = 128
        model.pitch = 129
        model.throttle = 130
        model.yaw = 131
        model.land_flag = True
        model.stop_flag = True
        model.headless_flag = True
        adapter = self._adapter("auto")
        adapter.set_camera_type(2)

        packet = adapter.build_control_packet(model)

        self.assertEqual(len(packet), 20)
        self.assertEqual(packet[:8], bytes([0x66, 0x14, 128, 129, 130, 131, 0x03, 0x01]))
        self.assertEqual(packet[18], 128 ^ 129 ^ 130 ^ 131 ^ 0x03 ^ 0x01)
        self.assertEqual(packet[19], 0x99)
        self.assertFalse(model.land_flag)
        self.assertFalse(model.stop_flag)


class FakeRcAdapter:
    def __init__(self):
        self.camera_type = None

    def set_camera_type(self, camera_type):
        self.camera_type = camera_type


class WifiCamVideoProtocolTests(unittest.TestCase):
    def test_camera_type_probe_updates_rc_adapter(self):
        adapter = WifiCamVideoProtocolAdapter()
        rc_adapter = FakeRcAdapter()
        adapter.set_rc_adapter(rc_adapter)

        frame = adapter.handle_payload(b"\x55\x00\x02\x00\x00\x00\x02\x99")

        self.assertIsNone(frame)
        self.assertEqual(adapter.camera_type, 2)
        self.assertEqual(rc_adapter.camera_type, 2)

    def test_single_chunk_jpeg_frame(self):
        adapter = WifiCamVideoProtocolAdapter()
        jpeg = b"\xff\xd8hello\xff\xd9"
        packet = bytes([1, 1, 1, 8, 0, 0, 0, 0]) + jpeg

        frame = adapter.handle_payload(packet)

        self.assertIsNotNone(frame)
        self.assertEqual(frame.data, jpeg)
        self.assertEqual(frame.format, "jpeg")
        self.assertEqual(frame.resolution, 8)
        self.assertEqual(frame.retain, 0)

    def test_multi_chunk_jpeg_frame_uses_native_final_marker(self):
        adapter = WifiCamVideoProtocolAdapter()
        first_chunk = b"\xff\xd8" + (b"a" * (adapter.CHUNK_SIZE - 2))
        second_chunk = b"tail\xff\xd9"
        packet1 = bytes([7, 0, 2, 8, 0, 0, 0, 1]) + first_chunk
        packet2 = bytes([7, 1, 2, 8, 0, 0, 0, 1]) + second_chunk

        self.assertIsNone(adapter.handle_payload(packet1))
        frame = adapter.handle_payload(packet2)

        self.assertIsNotNone(frame)
        self.assertEqual(frame.data, first_chunk + second_chunk)
        self.assertEqual(frame.retain, 1)

    def test_rejects_final_chunk_without_jpeg_tail(self):
        adapter = WifiCamVideoProtocolAdapter()
        packet = bytes([1, 1, 1, 8, 0, 0, 0, 0]) + b"\xff\xd8missing-tail"

        frame = adapter.handle_payload(packet)

        self.assertIsNone(frame)


if __name__ == "__main__":
    unittest.main()
