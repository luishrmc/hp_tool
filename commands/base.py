"""Base command contract for hp_tool subcommands."""

from __future__ import annotations

from abc import ABC, abstractmethod
import argparse


class Command(ABC):
    """Minimal interface every CLI command must implement."""

    name: str
    help: str

    @abstractmethod
    def add_args(self, parser: argparse.ArgumentParser) -> None:
        """Declare every argument this subcommand needs."""

    @abstractmethod
    def run(self, args: argparse.Namespace) -> int:
        """Execute the command and return a process exit code."""
