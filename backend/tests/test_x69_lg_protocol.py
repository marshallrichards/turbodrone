import unittest

from models.x69_lg_rc import X69LgRcModel
from protocols.x69_lg_rc_protocol_adapter import X69LgRcProtocolAdapter


class X69LgProtocolTests(unittest.TestCase):
    def _adapter(self) -> X69LgRcProtocolAdapter:
        adapter = X69LgRcProtocolAdapter.__new__(X69LgRcProtocolAdapter)
        adapter.speed_scale_by_index = {0: 0.55, 1: 0.75, 2: 1.0}
        return adapter

    def test_idle_packet_matches_lg_optical_flow_shape(self):
        model = X69LgRcModel()
        model.speed_index = 2
        packet = self._adapter().build_control_payload(model)

        self.assertEqual(len(packet), 20)
        self.assertEqual(packet[0], 0x66)
        self.assertEqual(packet[1], 0x14)
        self.assertEqual(packet[2:6], bytes([128, 128, 128, 128]))
        self.assertEqual(packet[6], 0)
        self.assertEqual(packet[7], 0)
        self.assertEqual(packet[8:18], bytes(10))
        self.assertEqual(packet[18], 0)
        self.assertEqual(packet[19], 0x99)

    def test_one_shot_flags_and_checksum(self):
        model = X69LgRcModel()
        model.speed_index = 2
        model.takeoff()
        model.land()
        model.emergency_stop()
        model.calibrate_gyro()
        model.flip()

        packet = self._adapter().build_control_payload(model)

        self.assertEqual(packet[6], 0x8F)
        expected_checksum = 0
        for value in packet[2:18]:
            expected_checksum ^= value
        self.assertEqual(packet[18], expected_checksum)

        # One-shot commands clear after one packet.
        self.assertFalse(model.takeoff_flag)
        self.assertFalse(model.land_flag)
        self.assertFalse(model.stop_flag)
        self.assertFalse(model.calibration_flag)
        self.assertFalse(model.flip_flag)

    def test_camera_tilt_up_down_bits_are_momentary_state(self):
        model = X69LgRcModel()
        adapter = self._adapter()

        model.set_camera_tilt_state(2)
        packet = adapter.build_control_payload(model)
        self.assertEqual(packet[7], 0x08)

        model.set_camera_tilt_state(1)
        packet = adapter.build_control_payload(model)
        self.assertEqual(packet[7], 0x10)

        model.set_camera_tilt_state(0)
        packet = adapter.build_control_payload(model)
        self.assertEqual(packet[7], 0x00)

    def test_speed_scale_affects_roll_and_pitch_only(self):
        model = X69LgRcModel()
        model.roll = 228
        model.pitch = 28
        model.throttle = 228
        model.yaw = 28
        model.speed_index = 1

        packet = self._adapter().build_control_payload(model)

        self.assertEqual(packet[2], 203)
        self.assertEqual(packet[3], 53)
        self.assertEqual(packet[4], 228)
        self.assertEqual(packet[5], 28)

    def test_wire_packet_wraps_control_payload_like_native_socket(self):
        model = X69LgRcModel()
        adapter = self._adapter()

        wire_packet = adapter.build_control_packet(model)

        self.assertEqual(wire_packet[:4], b"\xca\x47\xd5\x00")
        self.assertEqual(int.from_bytes(wire_packet[4:8], "little"), 20)
        self.assertEqual(len(wire_packet), 28)
        self.assertEqual(wire_packet[8:10], b"\x66\x14")
        self.assertEqual(wire_packet[-1], 0x99)

    def test_d1_keepalive_matches_native_socket(self):
        self.assertEqual(
            X69LgRcProtocolAdapter.D1_KEEPALIVE,
            b"\xca\x47\xd1\x00\x00\x00\x00\x00",
        )


if __name__ == "__main__":
    unittest.main()
