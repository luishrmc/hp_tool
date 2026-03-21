"""Minimal Kermit packet encode/decode support."""

from __future__ import annotations

from dataclasses import dataclass

from utils.constants import CR, SOH
from utils.exceptions import PacketError


@dataclass(slots=True)
class KermitPacket:
    """Represents one minimal Kermit packet.

    This skeleton uses a simple 1-byte checksum and a compact framing model.
    It is intentionally conservative for early bring-up and logging.
    """

    seq: int
    pkt_type: bytes
    data: bytes = b""

    def encode(self) -> bytes:
        """Encode the packet to raw bytes."""
        if len(self.pkt_type) != 1:
            raise PacketError("Packet type must be exactly one byte")
        if not 0 <= self.seq <= 63:
            raise PacketError("Sequence number must be in range 0..63")

        length = len(self.data) + 3
        body = bytes([length + 32, self.seq + 32]) + self.pkt_type + self.data
        checksum = self._checksum(body)
        return bytes([SOH]) + body + bytes([checksum + 32, CR])

    @classmethod
    def decode(cls, raw: bytes) -> "KermitPacket":
        if len(raw) < 6:
            raise PacketError("Raw packet too short")
        if raw[0] != SOH:
            raise PacketError("Packet does not start with SOH")
        # EOL terminator is the last byte — validated by length, not value
        length = raw[1] - 32
        seq    = raw[2] - 32
        pkt_type = raw[3:4]
        data   = raw[4:-2]
        recv_checksum = raw[-2] - 32

        if length != len(data) + 3:
            raise PacketError("Length mismatch while decoding packet")

        body = raw[1:-2]
        calc_checksum = cls._checksum(body)
        if recv_checksum != calc_checksum:
            raise PacketError(
                f"Checksum mismatch: received={recv_checksum:02X} calculated={calc_checksum:02X}"
            )
        return cls(seq=seq, pkt_type=pkt_type, data=data)


    @staticmethod
    def _checksum(body: bytes) -> int:
        """Compute the classic 6-bit checksum for the packet body."""
        total = sum(body)
        return (total + ((total & 0xC0) >> 6)) & 0x3F

def kermit_encode(data: bytes, qctl: int = ord('#'), qbin: int | None = None) -> bytes:
    """Encode raw bytes for a Kermit D-packet data field.

    Control chars (0x00-0x1F, 0x7F) → QCTL + (char ^ 0x40)
    High bytes (0x80-0xFF)          → QBIN + encode(char & 0x7F)  [requires qbin]
    QCTL/QBIN literals in data      → quoted to avoid framing confusion
    """
    out = bytearray()
    for byte in data:
        high = byte & 0x80
        low  = byte & 0x7F

        if high and qbin is not None:
            out.append(qbin)
            # The 7-bit half may itself need quoting
            _encode_low(out, low, qctl, qbin)
        elif high:
            # 8-bit quoting not negotiated — protocol can't reliably transfer this byte
            raise ValueError(f"High byte 0x{byte:02X} in data but QBIN not negotiated")
        else:
            _encode_low(out, byte, qctl, qbin)
    return bytes(out)


def _encode_low(out: bytearray, c: int, qctl: int, qbin: int | None) -> None:
    """Encode a 7-bit value into the output buffer."""
    if c < 0x20 or c == 0x7F:          # control character
        out.append(qctl)
        out.append(c ^ 0x40)
    elif c == qctl:                     # literal QCTL in data
        out.append(qctl)
        out.append(qctl)
    elif qbin is not None and c == qbin:  # literal QBIN in data
        out.append(qctl)
        out.append(qbin)
    else:
        out.append(c)
