import sys
import unittest
from pathlib import Path


_EXPERIMENTAL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_EXPERIMENTAL_ROOT))

from e88.drone import E88Drone


class TestE88Mapping(unittest.TestCase):
    def test_axis_to_byte_clamps(self):
        self.assertEqual(E88Drone._axis_to_byte(-1.0), 1)
        self.assertEqual(E88Drone._axis_to_byte(0.0), 128)
        self.assertEqual(E88Drone._axis_to_byte(1.0), 255)

        self.assertEqual(E88Drone._axis_to_byte(-2.0), 1)
        self.assertEqual(E88Drone._axis_to_byte(2.0), 255)

    def test_throttle_to_byte_clamps(self):
        self.assertEqual(E88Drone._throttle_to_byte(0.0), 0)
        self.assertEqual(E88Drone._throttle_to_byte(50.0), 128)
        self.assertEqual(E88Drone._throttle_to_byte(100.0), 255)

        self.assertEqual(E88Drone._throttle_to_byte(-10.0), 0)
        self.assertEqual(E88Drone._throttle_to_byte(200.0), 255)


if __name__ == "__main__":
    unittest.main()
