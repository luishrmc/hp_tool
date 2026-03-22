"""High-level calculator operations built on top of ``KermitSession``."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Iterable

from conn.session import HostCommandResult, KermitSession


@dataclass(frozen=True, slots=True)
class RPLCommand:
    """Describe one RPL command sent through Kermit Server host-command mode."""

    name: str
    expression: str


class RPLCommandBuilder:
    """Centralize construction of calculator-side RPL commands."""

    @staticmethod
    def _quote_name(name: str) -> str:
        """Quote a calculator object or directory name for UserRPL."""
        return f"'{name}'"

    @staticmethod
    def _folder_segments(path: str) -> list[str]:
        """Normalize a calculator folder path into parent/child segments."""
        parts = [segment for segment in path.strip().split('/') if segment]
        if parts and parts[0].upper() == 'HOME':
            parts = parts[1:]
        return parts

    @classmethod
    def _navigation_from_segments(cls, segments: list[str]) -> str:
        """Build stepwise folder navigation from a list of folder segments."""
        return ' '.join(f"{cls._quote_name(segment)} EVAL" for segment in segments)

    @classmethod
    def create_remote_dir(cls, path: str) -> RPLCommand:
        """Build an RPL command that creates a remote directory."""
        segments = cls._folder_segments(path)
        if not segments:
            raise ValueError(f"Remote directory path must include a directory name: {path!r}")

        *parents, leaf = segments
        if not parents:
            expression = f"{cls._quote_name(leaf)} CRDIR"
        else:
            navigation = cls._navigation_from_segments(parents)
            expression = f"{navigation} {cls._quote_name(leaf)} CRDIR"
        return RPLCommand(name="create_remote_dir", expression=expression)

    @classmethod
    def change_remote_dir(cls, path: str) -> RPLCommand:
        """Build an RPL command that changes the current remote directory."""
        return RPLCommand(name="change_remote_dir", expression=f"{cls._quote_name(path)} EVAL")


class CalculatorClient:
    """Thin facade exposing higher-level calculator operations."""

    def __init__(self, session: KermitSession) -> None:
        """Store the active session used for all calculator interactions."""
        self.session = session

    def run_rpl(self, command: str | RPLCommand) -> HostCommandResult:
        """Execute a raw or prebuilt RPL command via Kermit Server."""
        expression = command.expression if isinstance(command, RPLCommand) else command
        logging.debug("Running RPL command: %s", expression)
        return self.session.send_host_command(expression)

    def create_remote_dir(self, path: str) -> HostCommandResult:
        """Create a directory on the calculator."""
        return self.run_rpl(RPLCommandBuilder.create_remote_dir(path))

    def change_remote_dir(self, path: str) -> HostCommandResult:
        """Change the current directory on the calculator."""
        return self.run_rpl(RPLCommandBuilder.change_remote_dir(path))

    def upload_file(self, file_path: str | Path, remote_dir: str | None = None) -> None:
        """Upload one local file, optionally after switching remote directory."""
        if remote_dir:
            self.change_remote_dir(remote_dir)
        self.session.send_file(file_path)

    def upload_files(self, file_paths: Iterable[str | Path], remote_dir: str | None = None) -> None:
        """Upload multiple local files, optionally after switching remote directory."""
        paths = [Path(path) for path in file_paths]
        if remote_dir:
            self.change_remote_dir(remote_dir)
        for path in paths:
            self.session.send_file(path)
