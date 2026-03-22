"""Logging helpers for hp_tool."""

from __future__ import annotations

import logging


def setup_logging(debug: bool = False) -> None:
    """Configure application-wide logging.

    Args:
        debug: When True, enable debug-level logging; otherwise use info-level.
    """
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="[%(levelname)s] %(message)s")
