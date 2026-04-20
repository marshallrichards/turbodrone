import sys
import unittest
from pathlib import Path


_EXPERIMENTAL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_EXPERIMENTAL_ROOT))

from e88.rc import E88RcPacketBuilder, E88RcState


class TestE88RcPacketBuilder(unittest.TestCase):
    def test_packet_format_and_checksum(self):
        builder = E88RcPacketBuilder()
        state = E88RcState(roll=10, pitch=20, throttle=30, yaw=40, flags=0x08)

        pkt = builder.build_packet(state)

        self.assertEqual(len(pkt), 9)
        self.assertEqual(pkt[0], 0x03)
        self.assertEqual(pkt[1], 0x66)
        self.assertEqual(pkt[2], 10)
        self.assertEqual(pkt[3], 20)
        self.assertEqual(pkt[4], 30)
        self.assertEqual(pkt[5], 40)
        self.assertEqual(pkt[6], 0x08)
        self.assertEqual(pkt[8], 0x99)

        expected_checksum = 10 ^ 20 ^ 30 ^ 40 ^ 0x08
        self.assertEqual(pkt[7], expected_checksum)


if __name__ == "__main__":
    unittest.main()
