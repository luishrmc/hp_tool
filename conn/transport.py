"""Serial transport wrapper."""

from __future__ import annotations

import logging

import serial

from utils.constants import DEFAULT_BAUDRATE, DEFAULT_TIMEOUT, SOH
from utils.exceptions import TransportError

class SerialTransport:
    """Small serial abstraction for send/receive and raw logging."""

    def __init__(self, port: str, baudrate: int = DEFAULT_BAUDRATE, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial: serial.Serial | None = None

    def open(self) -> None:
        """Open the configured serial port."""
        try:
            self._serial = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            logging.debug("Opened serial port %s @ %d", self.port, self.baudrate)
        except serial.SerialException as exc:
            raise TransportError(f"Failed to open serial port {self.port}: {exc}") from exc

    def close(self) -> None:
        """Close the serial port if open."""
        if self._serial and self._serial.is_open:
            self._serial.close()
            logging.debug("Closed serial port %s", self.port)

    def flush_input(self) -> None:
        """Flush unread bytes from the input buffer."""
        if not self._serial:
            raise TransportError("Serial port is not open")
        self._serial.reset_input_buffer()
        logging.debug("Input buffer flushed")

    @staticmethod
    def _hex_bytes(data: bytes) -> str:
        """Return uppercase hex bytes separated by spaces."""
        return " ".join(f"{byte:02X}" for byte in data)

    def write(self, data: bytes) -> None:
        """Write raw bytes to the serial port."""
        if not self._serial:
            raise TransportError("Serial port is not open")
        self._serial.write(data)
        logging.debug("TX raw: %s", self._hex_bytes(data))

    def read_packet(self, max_bytes: int = 1024) -> bytes:
        """Read one complete Kermit packet using the LEN field to know when to stop."""
        if not self._serial:
            raise TransportError("Serial port is not open")

        soh = self._serial.read(1)
        if not soh:
            logging.debug("RX raw: <timeout, no SOH>")
            return b""
        if soh[0] != SOH:
            raise TransportError(f"Expected SOH, got 0x{soh[0]:02X}")

        len_byte = self._serial.read(1)
        if not len_byte:
            return b""
        packet_len = len_byte[0] - 32          # unchar(LEN) = SEQ+TYPE+DATA+CHKSUM count
        rest = self._serial.read(packet_len + 1)  # +1 for the EOL terminator byte
        raw = soh + len_byte + rest
        logging.debug("RX raw: %s", self._hex_bytes(raw))
        return raw
