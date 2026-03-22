"""High-level calculator operations built on top of ``KermitSession``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from conn.packet import KermitPacket
from conn.session import KermitSession


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

    @classmethod
    def _in_folder(cls, expression: str, folder: str | None = None) -> str:
        """Prefix a command with a folder change when a target folder is provided."""
        if not folder:
            return expression
        return f"{cls._quote_name(folder)} EVAL {expression}"

    @classmethod
    def create_remote_dir(cls, path: str) -> RPLCommand:
        """Build an RPL command that creates a remote directory."""
        return RPLCommand(name="create_remote_dir", expression=f"{cls._quote_name(path)} CRDIR")

    @classmethod
    def change_remote_dir(cls, path: str) -> RPLCommand:
        """Build an RPL command that changes the current remote directory."""
        return RPLCommand(name="change_remote_dir", expression=f"{cls._quote_name(path)} EVAL")

    @classmethod
    def remove_remote_dir(cls, path: str, purge: bool = False) -> RPLCommand:
        """Build an RPL command that removes a remote directory."""
        operation = "PGDIR" if purge else "PURGE"
        return RPLCommand(name="remove_remote_dir", expression=f"{cls._quote_name(path)} {operation}")

    @classmethod
    def remove_remote_object(cls, path: str) -> RPLCommand:
        """Build an RPL command that removes a variable or file-like object."""
        return RPLCommand(name="remove_remote_object", expression=f"{cls._quote_name(path)} PURGE")

    @classmethod
    def list_current_dir(cls, folder: str | None = None) -> RPLCommand:
        """Build an RPL command that lists the current directory entries."""
        expression = cls._in_folder("VARS", folder=folder)
        return RPLCommand(name="list_current_dir", expression=expression)

    @classmethod
    def store_variable(cls, name: str, value: str, folder: str | None = None) -> RPLCommand:
        """Build an RPL command that stores an arbitrary value in a named variable."""
        expression = cls._in_folder(
            f"{value} {cls._quote_name(name)} STO",
            folder=folder,
        )
        return RPLCommand(name="store_variable", expression=expression)

    @classmethod
    def store_equation(cls, name: str, expression: str, folder: str | None = None) -> RPLCommand:
        """Build an RPL command that stores an algebraic expression as a variable."""
        return RPLCommand(
            name="store_equation",
            expression=cls._in_folder(
                f"'{expression}' {cls._quote_name(name)} STO",
                folder=folder,
            ),
        )

    @classmethod
    def store_constant(cls, name: str, value: str, folder: str | None = None) -> RPLCommand:
        """Build an RPL command that stores a constant-like value."""
        return RPLCommand(
            name="store_constant",
            expression=cls._in_folder(
                f"{value} {cls._quote_name(name)} STO",
                folder=folder,
            ),
        )


class CalculatorClient:
    """Thin facade exposing higher-level calculator operations."""

    def __init__(self, session: KermitSession) -> None:
        """Store the active session used for all calculator interactions."""
        self.session = session

    def run_rpl(self, command: str | RPLCommand) -> tuple[KermitPacket, bytes]:
        """Execute a raw or prebuilt RPL command via Kermit Server."""
        expression = command.expression if isinstance(command, RPLCommand) else command
        return self.session.send_host_command(expression)

    def create_remote_dir(self, path: str) -> KermitPacket:
        """Create a directory on the calculator."""
        reply, _ = self.run_rpl(RPLCommandBuilder.create_remote_dir(path))
        return reply

    def change_remote_dir(self, path: str) -> KermitPacket:
        """Change the current directory on the calculator."""
        reply, _ = self.run_rpl(RPLCommandBuilder.change_remote_dir(path))
        return reply

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
