"""Minimal Kermit packet encode/decode support."""

from __future__ import annotations

from dataclasses import dataclass

from utils.constants import CR, SOH
from utils.exceptions import PacketError


@dataclass(slots=True)
class KermitPacket:
    """Represent a single framed Kermit packet."""

    seq: int
    pkt_type: bytes
    data: bytes = b""

    def encode(self) -> bytes:
        """Encode the packet into raw wire bytes.

        Returns:
            bytes: Serialized packet including framing and checksum.

        Raises:
            PacketError: If the packet type or sequence number is invalid.
        """
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
        """Decode raw wire bytes into a packet object.

        Args:
            raw: Serialized packet bytes.

        Returns:
            KermitPacket: Decoded packet instance.

        Raises:
            PacketError: If the packet framing, length, or checksum is invalid.
        """
        if len(raw) < 6:
            raise PacketError("Raw packet too short")
        if raw[0] != SOH:
            raise PacketError("Packet does not start with SOH")

        length = raw[1] - 32
        seq = raw[2] - 32
        pkt_type = raw[3:4]
        data = raw[4:-2]
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
        """Compute the classic 6-bit checksum for a packet body.

        Args:
            body: Packet body excluding SOH, checksum, and EOL.

        Returns:
            int: Six-bit checksum value.
        """
        total = sum(body)
        return (total + ((total & 0xC0) >> 6)) & 0x3F


def kermit_encode_byte(byte: int, qctl: int = ord('#'), qbin: int | None = None) -> bytes:
    """Encode one raw byte for a Kermit D-packet payload."""
    out = bytearray()
    high = byte & 0x80
    low = byte & 0x7F

    if high and qbin is not None:
        out.append(qbin)
        _encode_low(out, low, qctl, qbin)
    elif high:
        raise ValueError(f"High byte 0x{byte:02X} in data but QBIN not negotiated")
    else:
        _encode_low(out, byte, qctl, qbin)
    return bytes(out)


def kermit_encode(data: bytes, qctl: int = ord('#'), qbin: int | None = None) -> bytes:
    """Encode file data for a Kermit D-packet payload.

    Args:
        data: Raw data bytes to encode.
        qctl: Control-quote character.
        qbin: Optional 8-bit quote character negotiated with the peer.

    Returns:
        bytes: Encoded payload safe for D-packet transmission.

    Raises:
        ValueError: If high-bit data is present without negotiated 8-bit quoting.
    """
    out = bytearray()
    for byte in data:
        out.extend(kermit_encode_byte(byte, qctl=qctl, qbin=qbin))
    return bytes(out)


def _encode_low(out: bytearray, c: int, qctl: int, qbin: int | None) -> None:
    """Append an encoded 7-bit byte to the output buffer."""
    if c < 0x20 or c == 0x7F:
        out.append(qctl)
        out.append(c ^ 0x40)
    elif c == qctl:
        out.append(qctl)
        out.append(qctl)
    elif qbin is not None and c == qbin:
        out.append(qctl)
        out.append(qbin)
    else:
        out.append(c)

def kermit_decode_data(data: bytes, qctl: int = ord('#'), qbin: int | None = None) -> bytes:
    """Decode a received D-packet payload back into raw bytes.

    Args:
        data: Encoded payload bytes.
        qctl: Control-quote character.
        qbin: Optional 8-bit quote character negotiated with the peer.

    Returns:
        bytes: Raw decoded payload.
    """
    out = bytearray()
    i = 0
    length = len(data)

    while i < length:
        byte = data[i]

        high_bit = 0x00

        # Check for 8-bit quote
        if qbin is not None and byte == qbin:
            i += 1
            if i >= length:
                break
            high_bit = 0x80
            byte = data[i]

        # Check for control quote
        if byte == qctl:
            i += 1
            if i >= length:
                break
            char = data[i]
            if char == qctl:
                out.append(char | high_bit)
            elif qbin is not None and char == qbin:
                out.append(char | high_bit)
            else:
                out.append((char ^ 0x40) | high_bit)
        else:
            out.append(byte | high_bit)

        i += 1

    return bytes(out)
