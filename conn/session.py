"""Minimal send-session orchestration."""

from __future__ import annotations

import logging
from pathlib import Path

from conn.packet import KermitPacket, kermit_encode_byte
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
    PKT_HOST_CMD,
)
from utils.exceptions import PacketError, SessionError

QBIN_CHAR = ord('&')


class KermitSession:
    """Drive a minimal Kermit send session for one or more files."""

    def __init__(
        self,
        transport: SerialTransport,
        packet_size: int = DEFAULT_PACKET_DATA_SIZE,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        """Initialize the session state.

        Args:
            transport: Serial transport used for raw packet I/O.
            packet_size: Requested payload size for send-init negotiation.
            max_retries: Maximum retries for each packet exchange.
        """
        self.transport = transport
        self.packet_size = packet_size
        self.max_retries = max_retries
        self.seq = 0
        self.max_encoded_data = packet_size
        self.qbin: int | None = None

    def send_init(self) -> KermitPacket:
        """Send the initial Kermit negotiation packet.

        Returns:
            KermitPacket: ACK packet returned by the remote peer.

        Raises:
            SessionError: If the exchange fails after the retry budget.
        """
        payload = bytes([
            self.packet_size + 32,
            0x20,
            0x20,
            ord('#'),
            0x0D + 32,
            ord('#'),
            QBIN_CHAR,
        ])
        reply = self._send_and_expect(KermitPacket(self.seq, PKT_SEND_INIT, payload), PKT_ACK)
        self._parse_init_params(reply)
        return reply

    def _parse_init_params(self, y_packet: KermitPacket) -> None:
        """Apply negotiated parameters from a send-init ACK.

        Args:
            y_packet: ACK packet returned by the remote peer.
        """
        data = y_packet.data
        if len(data) >= 1:
            remote_maxl = data[0] - 32
            self.max_encoded_data = remote_maxl - 6
        if len(data) >= 7 and data[6] not in (0x20, ord('N')):
            self.qbin = data[6]
            logging.debug("8-bit quoting negotiated: QBIN=0x%02X ('%s')", self.qbin, chr(self.qbin))
        else:
            self.qbin = None
            logging.warning("8-bit quoting NOT agreed — high bytes will fail")

    def send_file(self, file_path: str | Path) -> None:
        """Send a single file across the active Kermit session.

        Args:
            file_path: Path to the file to send.

        Raises:
            SessionError: If packet negotiation or transfer fails.
        """
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
            chunk = self._build_chunk(data, offset)
            logging.debug(
                "Sending data chunk offset=%d raw_size=%d encoded_size=%d",
                offset,
                len(chunk["raw"]),
                len(chunk["encoded"]),
            )
            self._send_and_expect(KermitPacket(self.seq, PKT_DATA, chunk["encoded"]), PKT_ACK)
            offset += len(chunk["raw"])
            self._next_seq()

        self._send_and_expect(KermitPacket(self.seq, PKT_EOF, b''), PKT_ACK)
        self._next_seq()
        self._send_and_expect(KermitPacket(self.seq, PKT_BREAK, b''), PKT_ACK)
        logging.info("File send finished")

    def _build_chunk(self, data: bytes, offset: int) -> dict[str, bytes]:
        """Build the next encoded payload chunk that fits the negotiated size.

        Args:
            data: Full file contents.
            offset: Starting byte offset for the next chunk.

        Returns:
            dict[str, bytes]: Raw and encoded payload slices for the next packet.

        Raises:
            SessionError: If even a single byte cannot fit in the negotiated size.
        """
        raw = bytearray()
        encoded = bytearray()
        for byte in data[offset:]:
            encoded_byte = kermit_encode_byte(byte, qctl=ord('#'), qbin=self.qbin)
            if len(encoded) + len(encoded_byte) > self.max_encoded_data:
                break
            raw.append(byte)
            encoded.extend(encoded_byte)

        if not raw:
            raise SessionError("Single byte encoded size exceeds negotiated MAXL")

        return {"raw": bytes(raw), "encoded": bytes(encoded)}

    def _send_and_expect(self, packet: KermitPacket, expected_type: bytes) -> KermitPacket:
        """Send a packet and wait for the expected response type.

        Args:
            packet: Packet to transmit.
            expected_type: Packet type expected in the reply.

        Returns:
            KermitPacket: Decoded reply packet.

        Raises:
            SessionError: If retries are exhausted without the expected reply.
        """
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

    def send_host_command(self, command: str) -> KermitPacket:
        """Send a Kermit host-command packet (experimental fallback)."""
        payload = command.encode("ascii", errors="replace")
        reply = self._send_and_expect(KermitPacket(self.seq, PKT_HOST_CMD, payload), PKT_ACK)
        self._next_seq()
        logging.debug("Host command executed: %s", command)
        return reply
