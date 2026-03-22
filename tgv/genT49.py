"""T49 binary generation for HP50g TGV documents."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from PIL import Image

from utils.charmap import HP_HEX_MAP

HEADER = b"HPHP49-C"
PREFIX = b"\x9d\x2d\x40\xa7\x02"
POSTAMBLE = b"\x2b\x31\x20\xe9\x02\x4d\x01\x00\x3b\xdc\xb3\x12\x03"
IMAGE_DIRECTIVE_RE = re.compile(r"\\image\{([^}]+)\}")


def build_string_header(payload_len: int) -> bytes:
    """Build the HP string-object header for a payload.

    Args:
        payload_len: Length of the encoded text payload in bytes.

    Returns:
        bytes: Packed nibble header for the HP string object.
    """
    size_nibbles = 5 + (2 * payload_len)
    nibbles = [
        0xC, 0x2, 0xA, 0x2, 0x0,
        size_nibbles & 0xF,
        (size_nibbles >> 4) & 0xF,
        (size_nibbles >> 8) & 0xF,
        (size_nibbles >> 12) & 0xF,
        (size_nibbles >> 16) & 0xF,
    ]
    header = bytearray()
    for index in range(0, len(nibbles), 2):
        header.append((nibbles[index + 1] << 4) | nibbles[index])
    return bytes(header)


def apply_text_formatting_tags(text: str) -> str:
    """Translate textual formatting markers into TGV control codes.

    Args:
        text: Plain-text content containing placeholder formatting tags.

    Returns:
        str: Text containing TGV control characters.
    """
    text = text.replace("\r", "")
    text = text.replace("[/B]", "\x01B").replace("[B]", "\x01B")
    text = text.replace("[/INV]", "\x01V").replace("[INV]", "\x01V")
    text = text.replace("[/I]", "\x01/").replace("[I]", "\x01/")
    text = text.replace("[/U]", "\x01U").replace("[U]", "\x01U")
    text = text.replace("[SUB]", "\x014").replace("[SUP]", "\x013").replace("[NORM]", "\x011")
    return text


def encode_text_chunk(text: str) -> bytes:
    """Encode text using the project-specific HP glyph map.

    Args:
        text: Text chunk to encode.

    Returns:
        bytes: Encoded chunk ready for inclusion in a T49 payload.
    """
    text = apply_text_formatting_tags(text)
    output = bytearray()
    for char in text:
        if char in HP_HEX_MAP:
            output.extend(HP_HEX_MAP[char])
        else:
            try:
                output.extend(char.encode("latin-1"))
            except UnicodeEncodeError:
                output.extend(b"?")
    return bytes(output)


def build_image_object(image_ref: str, base_dir: Path, bmp_selected_dir: str) -> bytes:
    """Convert a BMP image into an HP GROB object.

    Args:
        image_ref: Image file name or path from a ``\\image{...}`` directive.
        base_dir: Base directory relative to which images are resolved.
        bmp_selected_dir: Relative directory that holds selected BMP assets.

    Returns:
        bytes: Encoded GROB object bytes, or ``b''`` if the image cannot be loaded.
    """
    image_path = Path(image_ref)
    if not image_path.is_absolute():
        image_path = (base_dir / bmp_selected_dir / image_path).resolve()

    if not image_path.exists():
        logging.error("Image not found: %s", image_path)
        return b""

    try:
        img = Image.open(image_path).convert('1', dither=Image.Dither.NONE)
    except Exception as exc:  # noqa: BLE001
        logging.error("Failed to load image %s: %s", image_path, exc)
        return b""

    width, height = img.size
    pixels = img.load()
    grob_data = bytearray()

    for y_pos in range(height):
        row_byte = 0
        bit_idx = 0
        for x_pos in range(width):
            pixel = pixels[x_pos, y_pos]  # type: ignore[index]
            if pixel == 0:
                row_byte |= 1 << bit_idx
            bit_idx += 1
            if bit_idx == 8:
                grob_data.append(row_byte)
                row_byte = 0
                bit_idx = 0
        if bit_idx > 0:
            grob_data.append(row_byte)

    grob_len_nibbles = len(grob_data) * 2 + 10 + 5
    nibbles = [
        0xE, 0x1, 0xB, 0x2, 0x0,
        grob_len_nibbles & 0xF,
        (grob_len_nibbles >> 4) & 0xF,
        (grob_len_nibbles >> 8) & 0xF,
        (grob_len_nibbles >> 12) & 0xF,
        (grob_len_nibbles >> 16) & 0xF,
        height & 0xF,
        (height >> 4) & 0xF,
        (height >> 8) & 0xF,
        (height >> 12) & 0xF,
        (height >> 16) & 0xF,
        width & 0xF,
        (width >> 4) & 0xF,
        (width >> 8) & 0xF,
        (width >> 12) & 0xF,
        (width >> 16) & 0xF,
    ]

    header = bytearray()
    for index in range(0, len(nibbles), 2):
        header.append((nibbles[index + 1] << 4) | nibbles[index])

    return bytes(header) + grob_data


def format_text(
    text: str,
    base_dir: Path | None = None,
    bmp_selected_dir: str = "img/bmp_images",
) -> bytes:
    """Interleave encoded text with image references for T49 output.

    Args:
        text: Source text containing optional ``\\image{...}`` directives.
        base_dir: Base directory for relative image resolution.
        bmp_selected_dir: Relative directory containing selected BMP assets.

    Returns:
        bytes: String-object payload plus appended GROB objects.
    """
    if base_dir is None:
        base_dir = Path.cwd()

    text = text.strip()
    master_string_data = bytearray()
    grobs_data = bytearray()
    last_end = 0
    image_index = 1

    for match in IMAGE_DIRECTIVE_RE.finditer(text):
        start, end = match.span()
        image_ref = match.group(1).strip()

        text_chunk = text[last_end:start]
        master_string_data.extend(encode_text_chunk(text_chunk))

        grob_bytes = build_image_object(image_ref, base_dir, bmp_selected_dir)
        if grob_bytes:
            master_string_data.extend(b"\x02" + bytes([image_index]))
            grobs_data.extend(grob_bytes)
            image_index += 1

        last_end = end

    if last_end < len(text):
        trailing = text[last_end:]
        if trailing:
            master_string_data.extend(encode_text_chunk(trailing))

    output = bytearray()
    output.extend(build_string_header(len(master_string_data)))
    output.extend(master_string_data)
    output.extend(grobs_data)
    return bytes(output)


def generate_from_string(
    text: str,
    base_dir: Path | None = None,
    bmp_selected_dir: str = "../img/bmp_images",
) -> bytes:
    """Build a complete ``HPHP49-C`` object from source text.

    Args:
        text: Source content ready for T49 encoding.
        base_dir: Base directory for image resolution.
        bmp_selected_dir: Relative directory containing selected BMP assets.

    Returns:
        bytes: Complete T49 object bytes including header and postamble.
    """
    payload = format_text(text, base_dir=base_dir, bmp_selected_dir=bmp_selected_dir)
    return HEADER + PREFIX + payload + POSTAMBLE


def generate_t49(
    input_path: str,
    output_path: str,
    bmp_selected_dir: str = "../img/bmp_images",
) -> None:
    """Generate a T49 file from a prepared text file.

    Args:
        input_path: Path to the source text file.
        output_path: Destination path for the generated ``.T49`` file.
        bmp_selected_dir: Relative directory containing selected BMP assets.

    Raises:
        FileNotFoundError: If the source text file does not exist.
    """
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    content = path.read_text(encoding="utf-8")
    t49_data = generate_from_string(content, base_dir=path.parent, bmp_selected_dir=bmp_selected_dir)

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(t49_data)

    logging.info("Successfully generated T49: %s (%d bytes)", out_path, len(t49_data))
