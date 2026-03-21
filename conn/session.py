"""Minimal send-session orchestration."""

from __future__ import annotations

import logging
from pathlib import Path

from conn.packet import KermitPacket
from conn.packet import kermit_encode
from conn.transport import SerialTransport
from utils.constants import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_PACKET_DATA_SIZE,
    PKT_ACK,
    PKT_BREAK,
    PKT_DATA,
    PKT_EOF,
    PKT_FILE_HEADER,
    PKT_NAK,
    PKT_SEND_INIT,
)

from utils.exceptions import PacketError, SessionError

QBIN_CHAR = ord('&')  # 8-bit prefix character we propose

class KermitSession:
    """Very small session driver for file sending.

    The implementation is intentionally incomplete but structured so you can
    evolve it incrementally while preserving the core architecture.
    """

    def __init__(
        self,
        transport: SerialTransport,
        packet_size: int = DEFAULT_PACKET_DATA_SIZE,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        self.transport = transport
        self.packet_size = packet_size
        self.max_retries = max_retries
        self.seq = 0

    def send_init(self) -> KermitPacket:
        payload = bytes([
            self.packet_size + 32,  # MAXL
            0x20,                   # TIME = 0
            0x20,                   # NPAD = 0
            ord('#'),               # PADC
            0x0D + 32,              # EOL  = CR  ('-')
            ord('#'),               # QCTL = '#'
            QBIN_CHAR,              # QBIN = '&'  ← NEW: propose 8-bit quoting
        ])
        reply = self._send_and_expect(KermitPacket(self.seq, PKT_SEND_INIT, payload), PKT_ACK)
        self._parse_init_params(reply)   # ← extract negotiated values
        return reply

    def _parse_init_params(self, y_packet: KermitPacket) -> None:
        """Read MAXL and QBIN from the calculator's Y response."""
        d = y_packet.data
        # Field 1: MAXL — max packet size the calculator accepts
        if len(d) >= 1:
            remote_maxl = d[0] - 32
            # Max encoded data = remote_maxl - 6 (SOH+LEN+SEQ+TYPE+CHKSUM+EOL overhead)
            self.max_encoded_data = remote_maxl - 6
        # Field 7: QBIN — calculator mirrors our proposed char if it agrees
        if len(d) >= 7 and d[6] not in (0x20, ord('N')):
            self.qbin = d[6]   # agreed 8-bit prefix byte
            logging.debug("8-bit quoting negotiated: QBIN=0x%02X ('%s')", self.qbin, chr(self.qbin))
        else:
            self.qbin = None
            logging.warning("8-bit quoting NOT agreed — high bytes will fail")


    def send_file(self, file_path: str | Path) -> None:
        path = Path(file_path)
        data = path.read_bytes()

        logging.info("Starting file send: %s (%d bytes)", path.name, len(data))
        self.send_init()
        self._next_seq()

        self._send_and_expect(
            KermitPacket(self.seq, PKT_FILE_HEADER, path.name.encode('ascii', errors='replace')),
            PKT_ACK,
        )
        self._next_seq()

        offset = 0
        while offset < len(data):
            # Build encoded chunk that fits within max_encoded_data
            chunk = self._build_chunk(data, offset)
            logging.debug("Sending data chunk offset=%d raw_size=%d encoded_size=%d",
                          offset, len(chunk['raw']), len(chunk['encoded']))
            self._send_and_expect(KermitPacket(self.seq, PKT_DATA, chunk['encoded']), PKT_ACK)
            offset += len(chunk['raw'])
            self._next_seq()

        self._send_and_expect(KermitPacket(self.seq, PKT_EOF,   b''), PKT_ACK)
        self._next_seq()
        self._send_and_expect(KermitPacket(self.seq, PKT_BREAK, b''), PKT_ACK)
        logging.info("File send finished")

    def _build_chunk(self, data: bytes, offset: int) -> dict:
        """Greedily consume raw bytes until the encoded size would exceed max_encoded_data."""
        raw = bytearray()
        for byte in data[offset:]:
            trial = bytes(raw) + bytes([byte])
            encoded = kermit_encode(trial, qctl=ord('#'), qbin=self.qbin)
            if len(encoded) > self.max_encoded_data:
                break
            raw.append(byte)
            if not raw:  # single byte expands too large — shouldn't happen with MAXL≥16
                raise SessionError("Single byte encoded size exceeds MAXL")
        encoded = kermit_encode(bytes(raw), qctl=ord('#'), qbin=self.qbin)
        return {'raw': bytes(raw), 'encoded': encoded}


    def _send_and_expect(self, packet: KermitPacket, expected_type: bytes) -> KermitPacket:
        """Send one packet and wait for the expected response type."""
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            logging.debug(
                "TX packet: seq=%d type=%s data_len=%d attempt=%d",
                packet.seq,
                packet.pkt_type.decode("latin-1"),
                len(packet.data),
                attempt,
            )
            self.transport.write(packet.encode())
            raw = self.transport.read_packet()

            if not raw:
                last_error = SessionError("Timed out waiting for reply")
                continue

            try:
                reply = KermitPacket.decode(raw)
            except PacketError as exc:
                last_error = exc
                continue

            logging.debug(
                "RX packet: seq=%d type=%s data_len=%d",
                reply.seq,
                reply.pkt_type.decode("latin-1"),
                len(reply.data),
            )

            if reply.pkt_type == expected_type:
                return reply
            if reply.pkt_type == PKT_NAK:
                last_error = SessionError(f"Received NAK for seq {packet.seq}")
                continue

            last_error = SessionError(
                f"Unexpected reply type {reply.pkt_type!r}, expected {expected_type!r}"
            )

        raise SessionError(f"Packet exchange failed after retries: {last_error}")

    def _next_seq(self) -> None:
        """Advance the 6-bit packet sequence number."""
        self.seq = (self.seq + 1) % 64
