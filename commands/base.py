"""Base command contract and return type for hp_tool subcommands."""

from __future__ import annotations

from abc import ABC, abstractmethod
import argparse
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RunResult:
    """Represents the outcome of running a CLI command.

    Attributes:
        ok: Whether the command completed successfully.
        message: Human-readable summary suitable for CLI logging.
        data: Optional structured payload for callers that need extra context.
    """

    ok: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)


class Command(ABC):
    """Minimal interface every CLI command must implement."""

    name: str
    help: str

    @abstractmethod
    def add_args(self, parser: argparse.ArgumentParser) -> None:
        """Declare subcommand-specific CLI arguments.

        Args:
            parser: Parser instance for this subcommand.
        """

    @abstractmethod
    def run(self, args: argparse.Namespace) -> RunResult:
        """Execute the command.

        Args:
            args: Parsed arguments for the subcommand.

        Returns:
            RunResult: Structured command outcome.
        """
