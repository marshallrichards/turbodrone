import unittest

from models.s2x_video_model import S2xVideoModel
from protocols.s2x_video_protocol import S2xVideoProtocolAdapter


class S2xVideoProtocolTests(unittest.TestCase):
    def _adapter(self):
        adapter = S2xVideoProtocolAdapter.__new__(S2xVideoProtocolAdapter)
        adapter.model = S2xVideoModel()
        return adapter

    def _packet(self, frame_id: int, total_chunks: int, chunk_id: int, body: bytes) -> bytes:
        payload = (
            b"\x40\x40"
            + frame_id.to_bytes(2, "little")
            + bytes([total_chunks, chunk_id])
        )
        packet_len = 8 + len(body) + 2
        return payload + packet_len.to_bytes(2, "little") + body + b"##"

    def test_emits_frame_when_all_declared_chunks_arrive(self):
        adapter = self._adapter()
        first = self._packet(0x1234, 2, 0, b"\xff\xd8hello")
        second = self._packet(0x1234, 2, 1, b" world\xff\xd9")

        self.assertIsNone(adapter.handle_payload(first))
        frame = adapter.handle_payload(second)

        self.assertIsNotNone(frame)
        self.assertEqual(frame.frame_id, 0x1234)
        self.assertEqual(frame.data, b"\xff\xd8hello world\xff\xd9")
        self.assertEqual(frame.format, "jpeg")

    def test_accepts_out_of_order_chunks(self):
        adapter = self._adapter()
        second = self._packet(7, 2, 1, b" tail\xff\xd9")
        first = self._packet(7, 2, 0, b"\xff\xd8head")

        self.assertIsNone(adapter.handle_payload(second))
        frame = adapter.handle_payload(first)

        self.assertIsNotNone(frame)
        self.assertEqual(frame.data, b"\xff\xd8head tail\xff\xd9")

    def test_rejects_mismatched_declared_length(self):
        adapter = self._adapter()
        packet = bytearray(self._packet(1, 1, 0, b"\xff\xd8x\xff\xd9"))
        packet[6:8] = (len(packet) + 1).to_bytes(2, "little")

        self.assertIsNone(adapter.handle_payload(bytes(packet)))


if __name__ == "__main__":
    unittest.main()
