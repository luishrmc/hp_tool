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

    @staticmethod
    def _is_absolute_path(path: str) -> bool:
        """Return whether a calculator path should resolve from HOME."""
        return path.strip().startswith("/")

    @classmethod
    def _navigation_from_segments(cls, segments: list[str]) -> str:
        """Build stepwise folder navigation from a list of folder segments."""
        return ' '.join(f"{cls._quote_name(segment)} EVAL" for segment in segments)

    @classmethod
    def _split_directory_target(cls, path: str) -> tuple[list[str], str]:
        """Split a remote directory path into parent segments and leaf name."""
        segments = cls._folder_segments(path)
        if not segments:
            raise ValueError(f"Remote directory path must include a directory name: {path!r}")
        return segments[:-1], segments[-1]

    @classmethod
    def _directory_prefix(cls, path: str, parents: list[str]) -> str:
        """Build an optional HOME/current-directory navigation prefix."""
        if not parents:
            if cls._is_absolute_path(path) and len(cls._folder_segments(path)) > 1:
                return "HOME"
            return ""

        navigation = cls._navigation_from_segments(parents)
        if cls._is_absolute_path(path):
            return f"HOME {navigation}"
        return navigation

    @classmethod
    def create_remote_dir(cls, path: str) -> RPLCommand:
        """Build an RPL command that creates a remote directory."""
        parents, leaf = cls._split_directory_target(path)
        if not parents:
            expression = f"{cls._quote_name(leaf)} CRDIR"
        else:
            navigation = cls._navigation_from_segments(parents)
            expression = f"{navigation} {cls._quote_name(leaf)} CRDIR"
        return RPLCommand(name="create_remote_dir", expression=expression)

    @classmethod
    def create_nested_remote_dir(cls, path: str) -> RPLCommand:
        """Build an RPL command that creates each missing folder along one nested path."""
        segments = cls._folder_segments(path)
        if not segments:
            raise ValueError(f"Remote directory path must include a directory name: {path!r}")

        steps: list[str] = []
        if cls._is_absolute_path(path) and len(segments) > 1:
            steps.append("HOME")

        for index, segment in enumerate(segments):
            steps.append(f"{cls._quote_name(segment)} CRDIR")
            if index < len(segments) - 1:
                steps.append(f"{cls._quote_name(segment)} EVAL")

        return RPLCommand(name="create_nested_remote_dir", expression=" ".join(steps))

    @classmethod
    def delete_remote_dir(cls, path: str) -> RPLCommand:
        """Build an RPL command that deletes a directory."""
        parents, leaf = cls._split_directory_target(path)
        prefix = cls._directory_prefix(path, parents)
        expression = f"{cls._quote_name(leaf)} PGDIR"
        if prefix:
            expression = f"{prefix} {expression}"
        return RPLCommand(name="delete_remote_dir", expression=expression)

    @classmethod
    def move_remote_dir(cls, src_path: str, dest_path: str) -> RPLCommand:
        """Build an RPL command that renames or moves a directory within one parent folder."""
        src_parents, src_leaf = cls._split_directory_target(src_path)
        dest_parents, dest_leaf = cls._split_directory_target(dest_path)
        if src_parents != dest_parents or cls._is_absolute_path(src_path) != cls._is_absolute_path(dest_path):
            raise ValueError(
                "change-dir currently requires source and destination to share the same parent directory"
            )

        rename_expression = (
            f"{cls._quote_name(src_leaf)} RCL {cls._quote_name(dest_leaf)} STO "
            f"{cls._quote_name(src_leaf)} PURGE"
        )
        prefix = cls._directory_prefix(src_path, src_parents)
        expression = rename_expression if not prefix else f"{prefix} {rename_expression}"
        return RPLCommand(name="move_remote_dir", expression=expression)

    @classmethod
    def list_home_dir(cls) -> RPLCommand:
        """Build an RPL command that lists entries starting from HOME."""
        return RPLCommand(name="list_home_dir", expression="HOME VARS")

    @classmethod
    def list_current_dir(cls) -> RPLCommand:
        """Build an RPL command that lists entries in the current directory."""
        return RPLCommand(name="list_current_dir", expression="VARS")

    @classmethod
    def list_relative_dir(cls, path: str) -> RPLCommand:
        """Build an RPL command that lists entries from a relative subdirectory path."""
        segments = cls._folder_segments(path)
        if not segments:
            expression = "VARS"
        else:
            navigation = cls._navigation_from_segments(segments)
            expression = f"{navigation} VARS"
        return RPLCommand(name="list_relative_dir", expression=expression)

    @classmethod
    def list_absolute_dir(cls, path: str) -> RPLCommand:
        """Build an RPL command that lists entries from an absolute HOME-based path."""
        segments = cls._folder_segments(path)
        if not segments:
            expression = "HOME VARS"
        else:
            navigation = cls._navigation_from_segments(segments)
            expression = f"HOME {navigation} VARS"
        return RPLCommand(name="list_absolute_dir", expression=expression)

    @classmethod
    def cd_remote_dir(cls, path: str) -> RPLCommand:
        """Build an RPL command that changes to the requested directory."""
        segments = cls._folder_segments(path)
        if cls._is_absolute_path(path):
            if not segments:
                expression = "HOME"
            else:
                navigation = cls._navigation_from_segments(segments)
                expression = f"HOME {navigation}"
        else:
            if not segments:
                raise ValueError(f"Remote directory path must include a directory name: {path!r}")
            navigation = cls._navigation_from_segments(segments)
            expression = navigation
        return RPLCommand(name="cd_remote_dir", expression=expression)

    @classmethod
    def clear_stack(cls) -> RPLCommand:
        """Build an RPL command that clears the calculator stack."""
        return RPLCommand(name="clear_stack", expression="CLEAR")

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
