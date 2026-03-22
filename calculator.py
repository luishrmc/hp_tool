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
    def create_remote_dir(path: str) -> RPLCommand:
        """Build an RPL command that creates a remote directory."""
        return RPLCommand(name="create_remote_dir", expression=f"'{path}' CRDIR")

    @staticmethod
    def change_remote_dir(path: str) -> RPLCommand:
        """Build an RPL command that changes the current remote directory."""
        return RPLCommand(name="change_remote_dir", expression=f"'{path}' EVAL")

    @staticmethod
    def remove_dir(path: str, purge: bool = False) -> RPLCommand:
        """Build an RPL command that removes a remote directory."""
        if purge:
            return RPLCommand(name="purge_dir", expression=f"'{path}' PGDIR")
        return RPLCommand(name="remove_dir", expression=f"'{path}' RMDIR")

    @staticmethod
    def rename(old_path: str, new_path: str) -> RPLCommand:
        """Build an RPL command that renames a file or directory."""
        return RPLCommand(name="rename", expression=f"'{old_path}' '{new_path}' RENAME")

    @staticmethod
    def list_dir(path: str) -> RPLCommand:
        """Build an RPL command that lists directory contents (evals the path and gets VARS)."""
        # This switches to the path, gets variables, and returns the list of names
        # Note: A real directory listing might need more complex RPL, but for now we do the basics.
        # EVAL changes the dir, VARS gets the list of variables in the current dir.
        # Alternatively, we just CD to the dir and return VARS.
        return RPLCommand(name="list_dir", expression=f"'{path}' EVAL VARS")

    @staticmethod
    def remove_file(path: str) -> RPLCommand:
        """Build an RPL command that removes a file or variable."""
        return RPLCommand(name="remove_file", expression=f"'{path}' PURGE")

    @staticmethod
    def create_variable(name: str, value: str, folder: str | None = None) -> RPLCommand:
        """Build an RPL command that creates a variable."""
        base_expr = f"{value} '{name}' STO"
        if folder:
            return RPLCommand(name="create_variable", expression=f"'{folder}' EVAL {base_expr}")
        return RPLCommand(name="create_variable", expression=base_expr)

    @staticmethod
    def create_equation(name: str, expression: str, folder: str | None = None) -> RPLCommand:
        """Build an RPL command that creates an equation."""
        base_expr = f"'{expression}' '{name}' STO"
        if folder:
            return RPLCommand(name="create_equation", expression=f"'{folder}' EVAL {base_expr}")
        return RPLCommand(name="create_equation", expression=base_expr)

    @staticmethod
    def create_constant(name: str, value: str, folder: str | None = None) -> RPLCommand:
        """Build an RPL command that creates a constant."""
        return RPLCommandBuilder.create_variable(name, value, folder)


class CalculatorClient:
    """Thin facade exposing higher-level calculator operations."""

    def __init__(self, session: KermitSession) -> None:
        """Store the active session used for all calculator interactions."""
        self.session = session

    def run_rpl(self, command: str | RPLCommand) -> KermitPacket:
        """Execute a raw or prebuilt RPL command via Kermit Server."""
        expression = command.expression if isinstance(command, RPLCommand) else command
        return self.session.send_host_command(expression)

    def create_remote_dir(self, path: str) -> KermitPacket:
        """Create a directory on the calculator."""
        return self.run_rpl(RPLCommandBuilder.create_remote_dir(path))

    def change_remote_dir(self, path: str) -> KermitPacket:
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
