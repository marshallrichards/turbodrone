import unittest

from models.wifi_uav_rc import WifiUavRcModel
from protocols.wifi_uav_rc_protocol_adapter import WifiUavRcProtocolAdapter
from utils.wifi_uav_variants import get_wifi_uav_capabilities, map_wifi_uav_variant_from_ssid


class WifiUavRcProtocolTests(unittest.TestCase):
    def _adapter(self, variant="fld"):
        adapter = WifiUavRcProtocolAdapter.__new__(WifiUavRcProtocolAdapter)
        adapter._ctr1 = 0
        adapter._ctr2 = 1
        adapter._ctr3 = 2
        adapter.capabilities = get_wifi_uav_capabilities(variant)
        return adapter

    def test_camera_tilt_is_packed_into_extended_command_bits(self):
        model = WifiUavRcModel()
        model.set_camera_tilt_state(1)
        adapter = self._adapter()

        packet = adapter.build_control_packet(model)

        self.assertEqual(packet[24] & 0xC0, 0x40)
        self.assertEqual(packet[36], packet[20] ^ packet[21] ^ packet[22] ^ packet[23] ^ packet[24] ^ packet[25])
        self.assertEqual(model.camera_tilt_state, 0)

    def test_camera_tilt_up_uses_second_ptz_state(self):
        model = WifiUavRcModel()
        model.set_camera_tilt_state(2)
        adapter = self._adapter()

        packet = adapter.build_control_packet(model)

        self.assertEqual(packet[24] & 0xC0, 0x80)

    def test_fld_high_speed_uses_k417_axis_order(self):
        model = WifiUavRcModel()
        model.set_speed_index(2)
        model.yaw = 10
        model.pitch = 255
        model.throttle = 255
        model.roll = 240
        adapter = self._adapter()

        packet = adapter.build_control_packet(model)

        self.assertEqual(packet[20:24], bytes([240, 255, 255, 10]))

    def test_uav_high_speed_uses_app_axis_order(self):
        model = WifiUavRcModel()
        model.set_speed_index(2)
        model.yaw = 10
        model.pitch = 255
        model.throttle = 255
        model.roll = 240
        adapter = self._adapter("uav")

        packet = adapter.build_control_packet(model)

        self.assertEqual(packet[20:24], bytes([10, 255, 255, 240]))

    def test_low_speed_scales_yaw_pitch_roll_but_not_throttle(self):
        model = WifiUavRcModel()
        model.set_speed_index(0)
        model.yaw = 255
        model.pitch = 255
        model.throttle = 255
        model.roll = 255
        adapter = self._adapter()

        packet = adapter.build_control_packet(model)

        self.assertEqual(packet[20:24], bytes([166, 166, 255, 166]))

    def test_flow_ssids_use_legacy_compatible_default_variant(self):
        self.assertEqual(map_wifi_uav_variant_from_ssid("FLOW_123456"), "fld")
        self.assertEqual(map_wifi_uav_variant_from_ssid("FlOW_123456"), "fld")


if __name__ == "__main__":
    unittest.main()
