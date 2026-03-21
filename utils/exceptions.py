"""Custom exceptions for hp_conn."""

from __future__ import annotations


class HPConnError(Exception):
    """Base exception for the project."""


class TransportError(HPConnError):
    """Raised for serial port errors."""


class PacketError(HPConnError):
    """Raised for malformed or unsupported packets."""


class SessionError(HPConnError):
    """Raised when the transfer session fails."""
