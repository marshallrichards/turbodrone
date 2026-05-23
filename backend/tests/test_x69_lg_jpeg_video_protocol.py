import unittest

from protocols.x69_lg_jpeg_video_protocol import (
    JpegFrameAssembler,
    decrypt_packet,
    is_valid_jpeg,
)


def _build_packet(
    frame_num: int,
    is_end: int,
    package_num: int,
    payload: bytes,
    *,
    decrypt: bool = False,
) -> bytes:
    header = bytes([frame_num & 0xFF, is_end & 0xFF, package_num & 0xFF, 0, 0, 0, 0, 0, 0])
    pkt = header + payload
    if decrypt:
        idx = (((frame_num * package_num) + 10) * 6666) % (len(pkt) - 9)
        pos = 9 + idx
        buf = bytearray(pkt)
        buf[pos] ^= 0xFF
        return bytes(buf)
    return pkt


class TestX69LgJpegVideoProtocol(unittest.TestCase):
    def test_decrypt_roundtrip(self):
        payload = b"\xff\xd8" + b"abc" + b"\xff\xd9"
        enc = _build_packet(3, 1, 1, payload, decrypt=True)
        dec = decrypt_packet(enc)
        self.assertEqual(dec[9:], payload)

    def test_single_packet_frame(self):
        jpeg = b"\xff\xd8hello\xff\xd9"
        asm = JpegFrameAssembler(decrypt=False)
        out = asm.ingest(_build_packet(1, 1, 1, jpeg))
        self.assertEqual(out, jpeg)
        self.assertTrue(is_valid_jpeg(out))

    def test_multi_packet_frame(self):
        jpeg = b"\xff\xd8" + b"x" * 100 + b"\xff\xd9"
        asm = JpegFrameAssembler(decrypt=False)
        asm.ingest(_build_packet(5, 0, 1, jpeg[:40]))
        out = asm.ingest(_build_packet(5, 1, 2, jpeg[40:]))
        self.assertEqual(out, jpeg)

    def test_gap_drops_frame(self):
        jpeg = b"\xff\xd8zz\xff\xd9"
        asm = JpegFrameAssembler(decrypt=False)
        asm.ingest(_build_packet(7, 0, 1, jpeg[:4]))
        asm.ingest(_build_packet(7, 0, 3, jpeg[4:6]))
        out = asm.ingest(_build_packet(7, 1, 4, jpeg[6:]))
        self.assertIsNone(out)

    def test_encrypted_multi_packet(self):
        jpeg = b"\xff\xd8" + b"data" + b"\xff\xd9"
        asm = JpegFrameAssembler(decrypt=True)
        asm.ingest(_build_packet(2, 0, 1, jpeg[:5], decrypt=True))
        out = asm.ingest(_build_packet(2, 1, 2, jpeg[5:], decrypt=True))
        self.assertEqual(out, jpeg)


if __name__ == "__main__":
    unittest.main()
