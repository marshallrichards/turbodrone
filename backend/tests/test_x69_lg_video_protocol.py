import os
import unittest

from protocols.x69_lg_video_protocol import X69LgVideoProtocolAdapter


class FakeDecoder:
    def __init__(self):
        self.frames = []
        self.stopped = False

    def feed(self, frame: bytes) -> None:
        self.frames.append(frame)

    def get_frame(self, timeout: float = 0.0):
        if self.frames:
            return b"\xff\xd8jpeg" + self.frames.pop(0) + b"\xff\xd9"
        return None

    def stop(self) -> None:
        self.stopped = True


class X69LgVideoProtocolTests(unittest.TestCase):
    def setUp(self):
        os.environ["X69_LG_DUMP_H265"] = "false"

    def _adapter(self) -> X69LgVideoProtocolAdapter:
        return X69LgVideoProtocolAdapter(decoder=FakeDecoder())

    def _packet(
        self,
        *,
        frame_len: int,
        frame_id: int,
        frame_type: int,
        total_chunks: int,
        chunk_index: int,
        offset: int,
        payload: bytes,
    ) -> bytes:
        header = bytearray(32)
        header[0:4] = X69LgVideoProtocolAdapter.STREAM_MAGIC
        header[4:8] = frame_len.to_bytes(4, "little")
        header[8:12] = frame_id.to_bytes(4, "little")
        header[17] = frame_type
        header[20:22] = total_chunks.to_bytes(2, "little")
        header[22:24] = chunk_index.to_bytes(2, "little")
        header[24:28] = offset.to_bytes(4, "little")
        header[28:32] = len(payload).to_bytes(4, "little")
        return bytes(header) + payload

    def test_native_video_command_bytes(self):
        self.assertEqual(
            X69LgVideoProtocolAdapter.OPEN_STREAM,
            bytes.fromhex("a8 8a 20 00 08 00 00 00 01 00 02 00 00 00 d2 04"),
        )
        self.assertEqual(
            X69LgVideoProtocolAdapter.CLOSE_STREAM,
            bytes.fromhex("a8 8a 21 00 06 00 00 00 01 00 00 00 00 00"),
        )
        self.assertEqual(
            X69LgVideoProtocolAdapter.IFRAME_REQUEST,
            bytes.fromhex("a8 8a 24 00 02 00 00 00 01 00"),
        )

    def test_reassembles_single_packet_h265_frame(self):
        adapter = self._adapter()
        payload = b"\x00\x00\x00\x01\x40\x01vps"
        packet = self._packet(
            frame_len=len(payload),
            frame_id=7,
            frame_type=1,
            total_chunks=1,
            chunk_index=0,
            offset=0,
            payload=payload,
        )

        frame = adapter.handle_payload(packet)

        self.assertIsNotNone(frame)
        self.assertEqual(frame.format, "jpeg")
        self.assertIn(payload, frame.data)

    def test_reassembles_multi_packet_frame_by_offsets(self):
        adapter = self._adapter()
        first = b"\x00\x00\x00\x01"
        second = b"\x40\x01vps"
        packet_a = self._packet(
            frame_len=len(first) + len(second),
            frame_id=9,
            frame_type=1,
            total_chunks=2,
            chunk_index=0,
            offset=0,
            payload=first,
        )
        packet_b = self._packet(
            frame_len=len(first) + len(second),
            frame_id=9,
            frame_type=1,
            total_chunks=2,
            chunk_index=1,
            offset=len(first),
            payload=second,
        )

        self.assertIsNone(adapter.handle_payload(packet_a))
        frame = adapter.handle_payload(packet_b)

        self.assertIsNotNone(frame)
        self.assertIn(first + second, frame.data)

    def test_rejects_bad_magic(self):
        adapter = self._adapter()
        self.assertIsNone(adapter.handle_payload(b"bad"))

    def test_waits_for_h265_parameter_set_before_feeding_decoder(self):
        adapter = self._adapter()
        payload = b"\x00\x00\x00\x01\x02\x01pframe"
        packet = self._packet(
            frame_len=len(payload),
            frame_id=11,
            frame_type=0,
            total_chunks=1,
            chunk_index=0,
            offset=0,
            payload=payload,
        )

        self.assertIsNone(adapter.handle_payload(packet))
        self.assertEqual(adapter._decoder.frames, [])

    def test_h265_nal_type_parser_finds_parameter_sets(self):
        adapter = self._adapter()
        self.assertFalse(adapter._has_parameter_set(b"\x00\x00\x00\x01\x02\x01"))
        self.assertTrue(adapter._has_parameter_set(b"\x00\x00\x00\x01\x40\x01"))
        self.assertTrue(adapter._has_parameter_set(b"\x00\x00\x01\x42\x01"))


if __name__ == "__main__":
    unittest.main()
