"""Protocol and transport constants."""

from __future__ import annotations

# Classic Kermit framing bytes
SOH = 0x01
CR = 0x0D

# Conservative defaults for early debugging
DEFAULT_BAUDRATE = 115200
DEFAULT_TIMEOUT = 5.0
DEFAULT_PACKET_DATA_SIZE = 80
DEFAULT_MAX_RETRIES = 5

# Packet types used by a basic send flow
PKT_SEND_INIT = b"S"
PKT_FILE_HEADER = b"F"
PKT_DATA = b"D"
PKT_EOF = b"Z"
PKT_BREAK = b"B"
PKT_ACK = b"Y"
PKT_NAK = b"N"
PKT_ERROR = b"E"
