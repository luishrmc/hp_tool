"""Unit tests for host-command result capture in the session layer."""

from __future__ import annotations

import unittest

from conn.packet import KermitPacket, kermit_encode
from conn.session import KermitSession
from utils.constants import PKT_BREAK, PKT_DATA, PKT_EOF, PKT_FILE_HEADER, PKT_SEND_INIT


class FakeTransport:
    """Simple transport double returning pre-encoded packets in order."""

    def __init__(self, packets: list[bytes]) -> None:
        self._packets = list(packets)
        self.writes: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    def read_packet(self, max_bytes: int = 1024) -> bytes:
        del max_bytes
        if not self._packets:
            return b""
        return self._packets.pop(0)


class HostCommandSessionTests(unittest.TestCase):
    """Verify that host-command output is captured as structured results."""

    def test_send_host_command_returns_ack_result_without_transfer(self) -> None:
        transport = FakeTransport([KermitPacket(0, b"Y", b"").encode()])
        session = KermitSession(transport)

        result = session.send_host_command("1 1 +")

        self.assertEqual(result.command, "1 1 +")
        self.assertEqual(result.output_text, "")
        self.assertIsNone(result.transfer)

    def test_send_host_command_captures_returned_transfer_text(self) -> None:
        send_init = KermitPacket(
            0,
            PKT_SEND_INIT,
            bytes([80 + 32, 0x20, 0x20, ord('#'), 0x0D + 32, ord('#'), ord('N')]),
        ).encode()
        file_header = KermitPacket(1, PKT_FILE_HEADER, b"VARS.TXT").encode()
        data = KermitPacket(2, PKT_DATA, kermit_encode(b"A\nB\n")).encode()
        eof = KermitPacket(3, PKT_EOF, b"").encode()
        brk = KermitPacket(4, PKT_BREAK, b"").encode()
        transport = FakeTransport([send_init, file_header, data, eof, brk])
        session = KermitSession(transport)

        result = session.send_host_command("VARS")

        self.assertEqual(result.command, "VARS")
        self.assertEqual(result.transfer.file_name, "VARS.TXT")
        self.assertEqual(result.output_text, "A\nB\n")
        self.assertGreaterEqual(len(transport.writes), 5)


if __name__ == "__main__":
    unittest.main()
