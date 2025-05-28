from typing import List

# Start Of Image
SOI = bytearray(b"\xff\xd8")
# End Of Image
EOI = bytearray(b"\xff\xd9")

# fmt: off
# Standard luminance quantization table
std_luminance_qt = [
     16, 11, 10, 16, 24,  40,  51,  61,
     12, 12, 14, 19, 26,  58,  60,  55,
     14, 13, 16, 24, 40,  57,  69,  56,
     14, 17, 22, 29, 51,  87,  80,  62,
     18, 22, 37, 56, 68, 109, 103,  77,
     24, 35, 55, 64, 81, 104, 113,  92,
     49, 64, 78, 87,103, 121, 120, 101,
     72, 92, 95, 98,112, 100, 103,  99
]

# Standard chrominance quantization table
std_chrominance_qt = [
    17, 18, 24, 47, 99,  99,  99,  99,
    18, 21, 26, 66, 99,  99,  99,  99,
    24, 26, 56, 99, 99,  99,  99,  99,
    47, 66, 99, 99, 99,  99,  99,  99,
    99, 99, 99, 99, 99,  99,  99,  99,
    99, 99, 99, 99, 99,  99,  99,  99,
    99, 99, 99, 99, 99,  99,  99,  99,
    99, 99, 99, 99, 99,  99,  99,  99
]
# fmt: on


def generate_dqt_segment(id: int, table: List[int], precision: int = 0) -> bytes:
    """
    Generates the DQT (Define Quantization Table) segment.

    Args:
        id (int): Table ID (0–3)
        table (list of 64 ints): Quantization values in zigzag order
        precision (int): 0 for 8-bit, 1 for 16-bit. Defaults to 0.

    Returns:
        bytes: The full DQT segment.
    """

    if len(table) != 64:
        raise ValueError(f"Quantization table must have 64 values.")
    if precision not in (0, 1):
        raise ValueError("Precision must be 0 (8-bit) or 1 (16-bit).")

    segment = bytearray(b"\xff\xdb")  # Marker
    payload = bytearray()

    # Info byte: (precision << 4) | table_id
    payload.append((precision << 4) | id)

    # Add table data
    if precision == 0:
        payload.extend(table)
    else:
        for val in table:
            payload.extend(val.to_bytes(2, "big"))

    # Length = 2 (for length field itself) + payload size
    length = len(payload) + 2
    segment.extend(length.to_bytes(2, "big"))
    segment.extend(payload)

    return bytes(segment)


def generate_sof0_segment(width: int, height: int, num_components: int = 3) -> bytes:
    """
    Generates a SOF0 (Start of Frame, Baseline DCT) segment for a JPEG image.
    Uses 4:4:4 subsampling.

    Args:
        width (int): Image width in pixels.
        height (int): Image height in pixels.
        num_components (int): Number of components (e.g., 1 for grayscale, 3 for YCbCr).
            Defaults to 3.
        component_info (list of dict, optional): List of dicts with keys:
            - 'id' (int): Component ID
            - 'sampling' (tuple): (H, V) sampling factors
            - 'qt_id' (int): Quantization table ID
            If not provided, defaults to common layout.

    Returns:
        bytes: Complete SOF0 segment (including marker).
    """
    if not (1 <= width <= 65535 and 1 <= height <= 65535):
        raise ValueError("Width and height must be between 1 and 65535.")
    if num_components not in (1, 3):
        raise ValueError("Number of components must be 1 or 3.")

    marker = b"\xff\xc0"  # SOF0 marker
    precision = b"\x08"  # 8-bit sample precision
    height_bytes = height.to_bytes(2, "big")
    width_bytes = width.to_bytes(2, "big")
    num_components_byte = num_components.to_bytes(1, "big")

    # Default component layout
    if num_components == 1:
        component_info = [{"id": 1, "sampling": (1, 1), "qt_id": 0}]
    elif num_components == 3:
        component_info = [
            {"id": 1, "sampling": (1, 1), "qt_id": 0},  # Y
            {"id": 2, "sampling": (1, 1), "qt_id": 1},  # Cb
            {"id": 3, "sampling": (1, 1), "qt_id": 1},  # Cr
        ]
    else:
        raise ValueError("Invalid num_components")

    # Build component specs
    component_specs = b""
    for comp in component_info:
        comp_id = comp["id"].to_bytes(1, "big")
        H, V = comp["sampling"]
        sampling_byte = ((H << 4) | V).to_bytes(1, "big")
        qt_id = comp["qt_id"].to_bytes(1, "big")
        component_specs += comp_id + sampling_byte + qt_id

    # Total length = 8 (header) + 3 bytes per component
    length = (8 + 3 * num_components).to_bytes(2, "big")

    return (
        marker
        + length
        + precision
        + height_bytes
        + width_bytes
        + num_components_byte
        + component_specs
    )


def generate_sos_segment(
    num_components: int, Ss: int = 0, Se: int = 63, AhAl: int = 0
) -> bytes:
    """
    Generates the SOS (Start of Scan) segment for a JPEG file.

    Args:
        num_components (int): Number of components (1 for grayscale, 3 for YCbCr).
        Ss (int): Start of spectral selection. Defaults to 0.
        Se (int): End of spectral selection. Defaults to 63
        AhAl (int): Approximation bit position. Defaults to 0.

    Returns:
        bytes: Complete SOS segment (including marker).
    """
    if num_components == 1:
        component_selectors = [{"id": 1, "dc": 0, "ac": 0}]
    elif num_components == 3:
        component_selectors = [
            {"id": 1, "dc": 0, "ac": 0},  # Y
            {"id": 2, "dc": 1, "ac": 1},  # Cb
            {"id": 3, "dc": 1, "ac": 1},  # Cr
        ]
    else:
        raise ValueError("Component count must be 1 or 3.")

    marker = b"\xff\xda"
    length = 6 + 2 * num_components
    segment = bytearray(marker)
    segment += length.to_bytes(2, "big")
    segment.append(num_components)

    for comp in component_selectors:
        table_selector = (comp["dc"] << 4) | comp["ac"]
        segment.append(comp["id"])
        segment.append(table_selector)

    segment.append(Ss)
    segment.append(Se)
    segment.append(AhAl)

    return bytes(segment)


def generate_jpeg_headers(width: int, height: int, num_components: int = 3) -> bytes:
    """
    Generates a minimal JPEG header without Huffman tables and default quantization tables.

    Args:
        width (int): Image width in pixels.
        height (int): Image height in pixels.
        num_components (int): Number of components (1 for grayscale, 3 for YCbCr).

    Returns:
        bytes: JPEG header bytes (SOI, DQT, SOF0, SOS).
    """
    # Generate segments
    luminance_dqt = generate_dqt_segment(id=0, table=std_luminance_qt)
    chrominance_dqt = generate_dqt_segment(id=1, table=std_chrominance_qt)
    sof = generate_sof0_segment(
        width=width, height=height, num_components=num_components
    )
    sos = generate_sos_segment(num_components=num_components)

    # Build the header
    header = bytearray()
    header += SOI
    header += luminance_dqt
    if num_components == 3:
        header += chrominance_dqt
    header += sof
    header += sos
    return bytes(header)
