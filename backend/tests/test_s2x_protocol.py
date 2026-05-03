import unittest

from models.s2x_rc import S2xDroneModel
from protocols.s2x_rc_protocol_adapter import S2xRCProtocolAdapter


class S2xRcProtocolTests(unittest.TestCase):
    def _adapter(self):
        adapter = S2xRCProtocolAdapter.__new__(S2xRCProtocolAdapter)
        adapter.swap_yaw_roll = False
        adapter.speed_scale_by_index = {
            0: 0.7,
            1: 0.8,
            2: 1.0,
        }
        return adapter

    def test_default_packet_matches_macrochip_hy_layout(self):
        model = S2xDroneModel()
        model.roll = 128
        model.pitch = 129
        model.throttle = 130
        model.yaw = 131
        model.takeoff_flag = True
        adapter = self._adapter()

        packet = adapter.build_control_packet(model)

        self.assertEqual(len(packet), 20)
        self.assertEqual(packet[:8], bytes([0x66, 0x14, 128, 129, 131, 133, 0x01, 0x0A]))
        self.assertEqual(packet[18], 128 ^ 129 ^ 131 ^ 133 ^ 0x01 ^ 0x0A)
        self.assertEqual(packet[19], 0x99)
        self.assertFalse(model.takeoff_flag)

    def test_swap_yaw_roll_changes_transmitted_axes(self):
        model = S2xDroneModel()
        model.roll = 60
        model.pitch = 128
        model.throttle = 128
        model.yaw = 200
        adapter = self._adapter()
        adapter.swap_yaw_roll = True

        packet = adapter.build_control_packet(model)

        self.assertEqual(packet[2], 255)
        self.assertEqual(packet[5], 0)

    def test_speed_index_scales_roll_and_pitch_only(self):
        model = S2xDroneModel()
        model.roll = 200
        model.pitch = 60
        model.throttle = 200
        model.yaw = 60
        model.set_speed_index(0)
        adapter = self._adapter()

        packet = adapter.build_control_packet(model)

        self.assertEqual(packet[2], 216)
        self.assertEqual(packet[3], 38)
        self.assertEqual(packet[4], 255)
        self.assertEqual(packet[5], 0)


if __name__ == "__main__":
    unittest.main()
