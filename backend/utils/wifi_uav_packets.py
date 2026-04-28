# Start Video Feed
START_STREAM = b"\xef\x00\x04\x00"

# Unknown
UNK_FRAME = b"\xef\x20\x06\x00\x01\x65"

# Drone Info I think
SSID2 = (
    b"\xef\x20\x19\x00\x01\x67"
    b"\x3c\x69\x3d\x32\x5e\x62\x66\x5f\x73\x73\x69\x64\x3d\x63\x6d\x64"
    b"\x3d\x32\x3e"
)
SSID3 = (
    b"\xef\x20\x19\x00\x01\x67"
    b"\x3c\x69\x3d\x32\x5e\x62\x66\x5f\x73\x73\x69\x64\x3d\x63\x6d\x64"
    b"\x3d\x33\x3e"
)

# Both of these are sent for each frame. Native `build_send_ack()` builds this
# same outer packet shape:
#
#   ef 02 <len:u16> 02 02 00 01 <ack-count> ...
#
# The packet also embeds the latest user command at offset 18. The current
# constants carry a neutral extended command (`66 14 80 80 80 80 ... 99`) so
# video can advance even when no RC input has changed.
REQUEST_A = (
    b"\xef\x02\x58\x00\x02\x02"
    b"\x00\x01\x00\x00\x00\x00\x05\x00\x00\x00\x14\x00\x66\x14\x80\x80"
    b"\x80\x80\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x99"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x32\x4b\x14\x2d"
    b"\x00\x00"
)

# See previous comment
REQUEST_B = (
    b"\xef\x02\x7c\x00\x02\x02"
    b"\x00\x01\x02\x00\x00\x00\x09\x00\x00\x00\x14\x00\x66\x14\x80\x80"
    b"\x80\x80\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x99"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x32\x4b\x14\x2d"
    b"\x00\x00\x08\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x14\x00"
    b"\x00\x00\xff\xff\xff\xff\x09\x00\x00\x00\x00\x00\x00\x00\x03\x00"
    b"\x00\x00\x10\x00\x00\x00"
)

# Native ACK packet sequence fields. These are little-endian integer fields, not
# arbitrary byte offsets:
# - 12: queued user-command sequence
# - 88: first ACK slot sequence
# - 108: second ACK slot sequence
REQUEST_A_COMMAND_SEQ_OFFSET = 12
REQUEST_B_COMMAND_SEQ_OFFSET = 12
REQUEST_B_ACK_SEQ_OFFSETS = (88, 108)

NEUTRAL_EXTENDED_COMMAND = (
    b"\x66\x14\x80\x80\x80\x80\x00\x02"
    b"\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x00\x00\x02\x99"
)

DEFAULT_QUALITY_PARAMS = b"\x32\x4b\x14\x2d\x00"


def build_fragment_ack_bitmap(fragment_total: int, received_fragments: set[int]) -> bytes:
    """Build the native little-endian fragment ACK bitmap."""
    if fragment_total <= 0:
        return b""

    word_count = (fragment_total + 31) // 32
    words = [0] * word_count
    for fragment_id in received_fragments:
        if 0 <= fragment_id < fragment_total:
            words[fragment_id // 32] |= 1 << (fragment_id & 31)

    return b"".join(word.to_bytes(4, "little") for word in words)


def build_ack_slot(seq: int, status: int, bitmap: bytes = b"") -> bytes:
    """Build one native ACK slot record."""
    record_len = 16 + len(bitmap)
    return (
        (seq & 0xFFFFFFFFFFFFFFFF).to_bytes(8, "little")
        + (status & 0xFFFFFFFF).to_bytes(4, "little")
        + record_len.to_bytes(4, "little")
        + bitmap
    )


def build_native_ack_packet(
    command_seq: int,
    ack_slots: list[bytes],
    command: bytes = NEUTRAL_EXTENDED_COMMAND,
    quality_params: bytes = DEFAULT_QUALITY_PARAMS,
) -> bytes:
    """
    Build a native-shaped WiFi-UAV ACK/request packet.

    This mirrors the header layout emitted by `build_send_ack()` /
    `build_send_ack_bl618()` in `libuav_lib.so`.
    """
    if len(command) > 64:
        raise ValueError("WiFi-UAV command payload must be <= 64 bytes")
    if len(quality_params) != 5:
        raise ValueError("WiFi-UAV quality params must be exactly 5 bytes")

    packet = bytearray()
    packet += b"\xef\x02\x00\x00"
    packet += b"\x02\x02\x00\x01"
    packet += bytes([len(ack_slots) & 0xFF])
    packet += b"\x00\x00\x00"
    packet += (command_seq & 0xFFFFFFFF).to_bytes(4, "little")
    packet += len(command).to_bytes(2, "little")
    packet += command.ljust(64, b"\x00")
    packet += quality_params
    packet += b"\x00"
    for slot in ack_slots:
        packet += slot
    packet[2:4] = len(packet).to_bytes(2, "little")
    return bytes(packet)
