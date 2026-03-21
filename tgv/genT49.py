"""
HP50g TGV Pipeline: T49 Binary Generator
========================================
This module handles the low-level construction of the .T49 binary format.
It performs the complex task of interleaving text strings with binary 
Graphics Objects (GROBs).

Binary Structure of a .T49:
1. Header: "HPHP49-C" identifying the file type.
2. Prefix: Specific Magic Bytes for the TGV viewer.
3. String Header: Encodes the total length of the text payload.
4. Text Payload: The actual content, including TGV formatting and image pointers.
5. GROB Objects: Binary pixel data for every image used.
6. Postamble: Closing metadata required by the HP48/49/50g OS.
"""

from pathlib import Path
import re
import logging
from PIL import Image
from utils.charmap import HP_HEX_MAP

# Standard HP49/50g file signature
HEADER = b"HPHP49-C"
# Specific library object entry points for the TGV viewer
PREFIX = b"\x9d\x2d\x40\xa7\x02"
# End-of-file metadata used by the calculator to verify object integrity
POSTAMBLE = b"\x2b\x31\x20\xe9\x02\x4d\x01\x00\x3b\xdc\xb3\x12\x03"

# Matches directives like \image{my_diagram.bmp} in the .txt source
IMAGE_DIRECTIVE_RE = re.compile(r"\\image\{([^}]+)\}")

def build_string_header(payload_len: int) -> bytes:
    """
    Calculates the internal HP-style length header for the text block.
    HP calculators use a 5-nibble (2.5 byte) little-endian size descriptor.
    """
    size_nibbles = 5 + (2 * payload_len)
    nibbles = [
        0xC, 0x2, 0xA, 0x2, 0x0, # Internal 'String Object' tags
        size_nibbles & 0xF, 
        (size_nibbles >> 4) & 0xF, 
        (size_nibbles >> 8) & 0xF, 
        (size_nibbles >> 12) & 0xF, 
        (size_nibbles >> 16) & 0xF
    ]
    header = bytearray()
    for i in range(0, len(nibbles), 2):
        header.append((nibbles[i+1] << 4) | nibbles[i])
    return bytes(header)

def apply_text_formatting_tags(text: str) -> str:
    """
    Translates human-readable placeholder tags into the specific 
    one-byte control codes used by the TGV viewer for font styles.
    """
    text = text.replace("\r", "")
    text = text.replace("[/B]", "\x01B").replace("[B]", "\x01B")     # Bold
    text = text.replace("[/INV]", "\x01V").replace("[INV]", "\x01V") # Inverted
    text = text.replace("[/I]", "\x01/").replace("[I]", "\x01/")     # Italic
    text = text.replace("[/U]", "\x01U").replace("[U]", "\x01U")     # Underline
    # Font size shifts (Subscript=4, Superscript=3, Normal=1)
    text = text.replace("[SUB]", "\x014").replace("[SUP]", "\x013").replace("[NORM]", "\x011")
    return text

def encode_text_chunk(text: str) -> bytes:
    """
    Encodes text into the HP charset. It checks the custom HP_HEX_MAP 
    first for math symbols, then falls back to standard Latin-1.
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
                output.extend(b"?") # Fallback for unsupported glyphs
    return bytes(output)

def build_image_object(image_ref: str, base_dir: Path, bmp_selected_dir: str) -> bytes:
    """
    Converts a BMP file into an HP GROB (Graphic Object).
    GROBs are stored as a stream of bits where 1 is black and 0 is white,
    padded to the nearest byte, with a specific nibble-based dimension header.
    """
    image_path = Path(image_ref)
    if not image_path.is_absolute():
        # Resolve relative to the project image selection folder
        image_path = (base_dir / bmp_selected_dir / image_path).resolve()

    if not image_path.exists():
        logging.error("Image not found: %s", image_path)
        return b""
        
    try:
        # Force 1-bit mode (monochrome)
        img = Image.open(image_path).convert('1', dither=Image.Dither.NONE)
    except Exception as e:
        logging.error("Failed to load image %s: %s", image_path, e)
        return b""

    width, height = img.size
    pixels = img.load() 
    grob_data = bytearray()
    
    # Binary serialization: bits are packed from left-to-right into bytes
    for y in range(height):
        row_byte = 0
        bit_idx = 0
        for x in range(width):
            pixel = pixels[x, y] # type: ignore
            if pixel == 0: # 0 is black in PIL mode '1'
                row_byte |= (1 << bit_idx) 
            bit_idx += 1
            if bit_idx == 8:
                grob_data.append(row_byte)
                row_byte = 0
                bit_idx = 0
        if bit_idx > 0:
            grob_data.append(row_byte)
    
    # Construct the GROB header (Type tag + Size + Height + Width)
    grob_len_nibbles = len(grob_data) * 2 + 10 + 5
    nibbles = [
        0xE, 0x1, 0xB, 0x2, 0x0, # GROB Object Tag
        grob_len_nibbles & 0xF, (grob_len_nibbles >> 4) & 0xF, (grob_len_nibbles >> 8) & 0xF, (grob_len_nibbles >> 12) & 0xF, (grob_len_nibbles >> 16) & 0xF,
        height & 0xF, (height >> 4) & 0xF, (height >> 8) & 0xF, (height >> 12) & 0xF, (height >> 16) & 0xF,
        width & 0xF, (width >> 4) & 0xF, (width >> 8) & 0xF, (width >> 12) & 0xF, (width >> 16) & 0xF
    ]
    
    header = bytearray()
    for i in range(0, len(nibbles), 2):
        header.append((nibbles[i+1] << 4) | nibbles[i])
        
    return bytes(header) + grob_data

def format_text(text: str, base_dir: Path | None = None, bmp_selected_dir: str = "img/bmp_images") -> bytes:
    """
    Parses the text and splits it into interleaved sections:
    'Text Chunk' -> 'Image Pointer' -> 'Text Chunk'
    The Image Pointer (0x02 + index) tells the TGV viewer which GROB to render.
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

        # Encode everything before the image
        text_chunk = text[last_end:start]
        master_string_data.extend(encode_text_chunk(text_chunk))
        
        # Generate the actual binary GROB
        grob_bytes = build_image_object(image_ref, base_dir, bmp_selected_dir)
        
        if grob_bytes:
            # Insert the binary pointer into the string
            master_string_data.extend(b"\x02" + bytes([image_index]))
            grobs_data.extend(grob_bytes)
            image_index += 1
            
        last_end = end

    # Encode remaining text after the last image
    if last_end < len(text):
        trailing = text[last_end:]
        if trailing:
            master_string_data.extend(encode_text_chunk(trailing))

    # Combine: Size Header + Text Payload + Binary Images
    output = bytearray()
    output.extend(build_string_header(len(master_string_data)))
    output.extend(master_string_data)
    output.extend(grobs_data)

    return bytes(output)

def generate_from_string(text: str, base_dir: Path | None = None, bmp_selected_dir: str = "../img/bmp_images") -> bytes:
    """Helper to create the full HPHP49-C structure from a string."""
    payload = format_text(text, base_dir=base_dir, bmp_selected_dir=bmp_selected_dir)
    return HEADER + PREFIX + payload + POSTAMBLE

def generate_t49(
    input_path: str,
    output_path: str,
    bmp_selected_dir: str = "../img/bmp_images"
) -> None:
    """Main entry point: Reads the final .txt and writes the binary .T49."""
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    t49_data = generate_from_string(content, base_dir=path.parent, bmp_selected_dir=bmp_selected_dir)

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "wb") as f:
        f.write(t49_data)

    logging.info("Successfully generated T49: %s (%d bytes)", out_path, len(t49_data))
