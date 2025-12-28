import sys
import unittest
from pathlib import Path


_EXPERIMENTAL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_EXPERIMENTAL_ROOT))

from turbodrone import Drone


class TestDroneWrapper(unittest.TestCase):
    def test_unsupported_protocol(self):
        with self.assertRaises(ValueError):
            Drone(protocol="NOT_A_DRONE")


if __name__ == "__main__":
    unittest.main()
