"""Serial transport wrapper."""

from __future__ import annotations

import logging

import serial

from utils.constants import DEFAULT_BAUDRATE, DEFAULT_TIMEOUT, SOH
from utils.exceptions import TransportError


class SerialTransport:
    """Wrap raw serial operations needed by the Kermit sender."""

    def __init__(
        self,
        port: str,
        baudrate: int = DEFAULT_BAUDRATE,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """Store serial connection settings.

        Args:
            port: Serial device path.
            baudrate: Serial baud rate.
            timeout: Read timeout in seconds.
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial: serial.Serial | None = None

    def open(self) -> None:
        """Open the configured serial port.

        Raises:
            TransportError: If the serial port cannot be opened.
        """
        try:
            self._serial = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            logging.debug("Opened serial port %s @ %d", self.port, self.baudrate)
        except serial.SerialException as exc:
            raise TransportError(f"Failed to open serial port {self.port}: {exc}") from exc

    def close(self) -> None:
        """Close the serial port if it is open."""
        if self._serial and self._serial.is_open:
            self._serial.close()
            logging.debug("Closed serial port %s", self.port)

    def flush_input(self) -> None:
        """Discard unread bytes from the input buffer.

        Raises:
            TransportError: If the serial port is not open.
        """
        if not self._serial:
            raise TransportError("Serial port is not open")
        self._serial.reset_input_buffer()
        logging.debug("Input buffer flushed")

    @staticmethod
    def _hex_bytes(data: bytes) -> str:
        """Format bytes as uppercase hex separated by spaces.

        Args:
            data: Bytes to format.

        Returns:
            str: Human-readable hex string.
        """
        return " ".join(f"{byte:02X}" for byte in data)

    def write(self, data: bytes) -> None:
        """Write raw bytes to the serial port.

        Args:
            data: Bytes to transmit.

        Raises:
            TransportError: If the serial port is not open.
        """
        if not self._serial:
            raise TransportError("Serial port is not open")
        self._serial.write(data)
        logging.debug("TX raw: %s", self._hex_bytes(data))

    def read_packet(self, max_bytes: int = 1024) -> bytes:
        """Read one framed Kermit packet from the serial port.

        Args:
            max_bytes: Maximum raw packet size supported by the caller. Present
                for interface compatibility with future transport variants.

        Returns:
            bytes: Raw packet bytes, or ``b''`` on timeout.

        Raises:
            TransportError: If the serial port is not open or framing is invalid.
        """
        del max_bytes

        if not self._serial:
            raise TransportError("Serial port is not open")

        discarded = bytearray()
        while True:
            soh = self._serial.read(1)
            if not soh:
                if discarded:
                    logging.debug(
                        "RX raw: discarded preamble before timeout: %s",
                        self._hex_bytes(bytes(discarded)),
                    )
                else:
                    logging.debug("RX raw: <timeout, no SOH>")
                return b""

            if soh[0] == SOH:
                break

            discarded.append(soh[0])

        if discarded:
            logging.debug(
                "RX raw: discarded non-SOH preamble bytes before packet: %s",
                self._hex_bytes(bytes(discarded)),
            )

        len_byte = self._serial.read(1)
        if not len_byte:
            logging.debug("RX raw: <timeout after SOH>")
            return b""
        packet_len = len_byte[0] - 32
        rest = self._serial.read(packet_len + 1)
        raw = soh + len_byte + rest
        logging.debug("RX raw: %s", self._hex_bytes(raw))
        return raw
