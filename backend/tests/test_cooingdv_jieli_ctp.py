import unittest

from utils.cooingdv_jieli_ctp import build_ctp_packet, parse_ctp_packet
from protocols.cooingdv_jieli_rc_protocol_adapter import CooingdvJieliRcProtocolAdapter
from models.cooingdv_rc import CooingdvRcModel


class CooingdvJieliCtpTests(unittest.TestCase):
    def test_builds_little_endian_ctp_packet(self):
        packet = build_ctp_packet("CONTROL_MODE", {"state": "1"})

        self.assertTrue(packet.startswith(b"CTP:"))
        topic_len = int.from_bytes(packet[4:6], "little")
        self.assertEqual(topic_len, len("CONTROL_MODE"))
        self.assertEqual(packet[6 : 6 + topic_len], b"CONTROL_MODE")

        topic, payload = parse_ctp_packet(packet)
        self.assertEqual(topic, "CONTROL_MODE")
        self.assertEqual(payload, {"op": "PUT", "param": {"state": "1"}})

    def test_flying_control_payload_preserves_tc_bytes(self):
        model = CooingdvRcModel()
        model.roll = 128
        model.pitch = 129
        model.throttle = 130
        model.yaw = 131
        model.stop_flag = True

        adapter = CooingdvJieliRcProtocolAdapter.__new__(CooingdvJieliRcProtocolAdapter)
        payload = adapter._build_flying_payload(model)

        expected_checksum = 128 ^ 129 ^ 130 ^ 131 ^ 0x04
        self.assertEqual(payload, [102, 128, 129, 130, 131, 4, expected_checksum, 153])

        packet = build_ctp_packet("FLYING_CTRL", {f"BYTE{i}": str(v) for i, v in enumerate(payload)})
        topic, body = parse_ctp_packet(packet)
        self.assertEqual(topic, "FLYING_CTRL")
        self.assertEqual(body["op"], "PUT")
        self.assertEqual(body["param"]["BYTE0"], "102")
        self.assertEqual(body["param"]["BYTE7"], "153")


if __name__ == "__main__":
    unittest.main()
