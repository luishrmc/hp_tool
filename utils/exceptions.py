"""Custom exception hierarchy for hp_tool."""

from __future__ import annotations


class HPConnError(Exception):
    """Base exception for project-specific runtime errors."""


class TransportError(HPConnError):
    """Raised when serial transport setup or I/O fails."""


class PacketError(HPConnError):
    """Raised when Kermit packet encoding or decoding fails."""


class SessionError(HPConnError):
    """Raised when a file transfer session cannot complete."""
