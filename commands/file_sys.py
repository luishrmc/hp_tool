"""Calculator file-system service and CLI command built on top of host-command flows."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import logging
from pathlib import Path, PurePosixPath

from calculator import CalculatorClient, RPLCommandBuilder
from commands.base import Command, RunResult
from conn.session import HostCommandResult, KermitSession
from conn.transport import SerialTransport
from utils.exceptions import HPConnError


@dataclass(frozen=True, slots=True)
class RemoteEntry:
    """Describe one calculator-side entry addressable by path."""

    path: str
    name: str
    entry_type: str = "unknown"


@dataclass(frozen=True, slots=True)
class RemoteFile(RemoteEntry):
    """Describe a remote file-like entry."""


@dataclass(frozen=True, slots=True)
class RemoteDirectory(RemoteEntry):
    """Describe a remote directory entry."""


@dataclass(frozen=True, slots=True)
class VariableSpec:
    """Describe a variable-like object that should be created remotely."""

    name: str
    value: str
    folder: str | None = None


@dataclass(frozen=True, slots=True)
class FileSystemResult:
    """Structured outcome returned by high-level filesystem operations."""

    operation: str
    path: str | None = None
    command: str | None = None
    output_text: str = ""
    transfer_name: str | None = None
    entries: tuple[RemoteEntry, ...] = field(default_factory=tuple)
    local_path: str | None = None


class CalculatorFileSystem:
    """Higher-level file-system style operations for the calculator."""

    def __init__(self, client: CalculatorClient) -> None:
        """Bind the service to an existing calculator client."""
        self.client = client

    @staticmethod
    def _split_remote_path(path: str) -> tuple[str | None, str]:
        """Split a calculator path into parent folder and leaf name."""
        normalized = PurePosixPath(path)
        name = normalized.name
        if not name:
            raise ValueError(f"Remote path must include a final name: {path!r}")

        parent = str(normalized.parent)
        if parent in ("", "."):
            parent = None
        return parent, name

    @classmethod
    def _resolve_name_and_folder(cls, name: str, folder: str | None = None) -> tuple[str | None, str]:
        """Resolve a leaf name plus optional folder into a normalized pair."""
        parent, leaf = cls._split_remote_path(name)
        if parent is not None:
            if folder and folder != parent:
                raise ValueError(
                    f"Conflicting remote folders provided: name={name!r}, folder={folder!r}"
                )
            return parent, leaf
        return folder, leaf

    def _result_from_host(
        self,
        operation: str,
        host_result: HostCommandResult,
        path: str | None = None,
        entries: tuple[RemoteEntry, ...] = (),
    ) -> FileSystemResult:
        """Normalize a host-command result into a filesystem-layer result."""
        transfer_name = None if host_result.transfer is None else host_result.transfer.file_name
        return FileSystemResult(
            operation=operation,
            path=path,
            command=host_result.command,
            output_text=host_result.output_text,
            transfer_name=transfer_name,
            entries=entries,
        )

    @staticmethod
    def _output_lines(output_text: str) -> list[str]:
        """Return clean non-empty output lines from calculator text output."""
        return [line.strip() for line in output_text.splitlines() if line.strip()]

    @staticmethod
    def _entry_type_for_name(name: str) -> str:
        """Best-effort classification for list output lines."""
        if name.endswith("/"):
            return "directory"
        return "variable"

    @staticmethod
    def _join_remote_path(folder: str, name: str) -> str:
        """Join a remote folder and child name into one POSIX-like path."""
        base = folder.rstrip("/") or "/"
        if base == "/":
            return f"/{name}"
        return f"{base}/{name}"

    def create_dir(self, path: str) -> FileSystemResult:
        """Create a directory on the calculator."""
        host_result = self.client.run_rpl(RPLCommandBuilder.create_remote_dir(path))
        return self._result_from_host("create_dir", host_result, path=path)

    def remove_dir(self, path: str, purge: bool = False) -> FileSystemResult:
        """Remove a directory, optionally purging non-empty contents first."""
        host_result = self.client.run_rpl(RPLCommandBuilder.remove_remote_dir(path, purge=purge))
        return self._result_from_host("remove_dir", host_result, path=path)

    def list_dir(self, path: str) -> FileSystemResult:
        """List directory contents using calculator-side RPL output."""
        host_result = self.client.run_rpl(RPLCommandBuilder.view_remote_dir(path))
        lines = self._output_lines(host_result.output_text)
        entries = tuple(
            RemoteEntry(
                path=self._join_remote_path(path, line.rstrip("/")),
                name=line.rstrip("/"),
                entry_type=self._entry_type_for_name(line),
            )
            for line in lines
        )
        return self._result_from_host("list_dir", host_result, path=path, entries=entries)

    def list_vars(self, path: str) -> FileSystemResult:
        """List calculator variables in a folder using the same observable output path."""
        host_result = self.client.run_rpl(RPLCommandBuilder.list_current_dir(folder=path))
        lines = self._output_lines(host_result.output_text)
        entries = tuple(
            RemoteEntry(
                path=self._join_remote_path(path, line.rstrip("/")),
                name=line.rstrip("/"),
                entry_type="variable",
            )
            for line in lines
        )
        return self._result_from_host("list_vars", host_result, path=path, entries=entries)

    def save_file(self, local_path: str | Path, remote_path: str) -> FileSystemResult:
        """Upload a local file to a remote folder using the existing transfer flow."""
        local = Path(local_path)
        remote_dir, remote_name = self._split_remote_path(remote_path)
        if local.name != remote_name:
            raise ValueError(
                "Remote filename must currently match the local filename; "
                "renamed uploads require a follow-up remote rename primitive."
            )
        self.client.upload_file(local, remote_dir=remote_dir)
        return FileSystemResult(
            operation="save_file",
            path=remote_path,
            local_path=str(local),
        )

    def remove_file(self, path: str) -> FileSystemResult:
        """Remove a file or variable-like object from the calculator."""
        host_result = self.client.run_rpl(RPLCommandBuilder.remove_remote_object(path))
        return self._result_from_host("remove_file", host_result, path=path)

    def create_variable(self, name: str, value: str, folder: str | None = None) -> FileSystemResult:
        """Create a generic remote variable by storing an RPL value expression."""
        resolved_folder, resolved_name = self._resolve_name_and_folder(name, folder=folder)
        host_result = self.client.run_rpl(
            RPLCommandBuilder.store_variable(resolved_name, value, folder=resolved_folder)
        )
        path = resolved_name if resolved_folder is None else self._join_remote_path(resolved_folder, resolved_name)
        return self._result_from_host("create_variable", host_result, path=path)

    def create_equation(self, name: str, expression: str, folder: str | None = None) -> FileSystemResult:
        """Create a remote equation object stored under the requested name."""
        resolved_folder, resolved_name = self._resolve_name_and_folder(name, folder=folder)
        host_result = self.client.run_rpl(
            RPLCommandBuilder.store_equation(resolved_name, expression, folder=resolved_folder)
        )
        path = resolved_name if resolved_folder is None else self._join_remote_path(resolved_folder, resolved_name)
        return self._result_from_host("create_equation", host_result, path=path)

    def create_constant(self, name: str, value: str, folder: str | None = None) -> FileSystemResult:
        """Create a remote constant-like value stored under the requested name."""
        resolved_folder, resolved_name = self._resolve_name_and_folder(name, folder=folder)
        host_result = self.client.run_rpl(
            RPLCommandBuilder.store_constant(resolved_name, value, folder=resolved_folder)
        )
        path = resolved_name if resolved_folder is None else self._join_remote_path(resolved_folder, resolved_name)
        return self._result_from_host("create_constant", host_result, path=path)


class FileSystemCommand(Command):
    """CLI command exposing calculator file-system operations."""

    name = "file-sys"
    help = "Run calculator file-system and variable operations"

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        """Register CLI arguments for the file-sys subcommand."""
        parser.add_argument("port", help="Serial port, for example /dev/ttyUSB0")
        parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate")
        parser.add_argument("--packet-size", type=int, default=80, help="Payload size for D packets")
        parser.add_argument("--retries", type=int, default=5, help="Maximum retries per packet")
        parser.add_argument("--purge", action="store_true", help="Use purge semantics when removing a directory")
        parser.add_argument("--folder", help="Target folder for variable-oriented operations")

        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--view-dir", metavar="REMOTE_DIR", help="View/list one calculator directory")
        group.add_argument("--create-dir", metavar="REMOTE_DIR", help="Create a calculator directory")
        group.add_argument("--remove-dir", metavar="REMOTE_DIR", help="Remove a calculator directory")
        group.add_argument(
            "--save-file",
            nargs=2,
            metavar=("LOCAL_PATH", "REMOTE_PATH"),
            help="Upload one local file to a calculator path",
        )
        group.add_argument("--remove-file", metavar="REMOTE_PATH", help="Remove a calculator file or variable")
        group.add_argument("--list-vars", metavar="REMOTE_DIR", help="List variables in a calculator folder")
        group.add_argument(
            "--create-var",
            nargs=2,
            metavar=("NAME", "VALUE"),
            help="Create a variable by storing an RPL value expression",
        )

    def run(self, args: argparse.Namespace) -> RunResult:
        """Execute the selected calculator filesystem operation."""
        logging.info("file-sys command selected")

        transport = SerialTransport(port=args.port, baudrate=args.baud)
        try:
            transport.open()
            transport.flush_input()

            session = KermitSession(
                transport=transport,
                packet_size=args.packet_size,
                max_retries=args.retries,
            )
            file_system = CalculatorFileSystem(CalculatorClient(session))
            result = self._run_operation(file_system, args)
            return self._to_run_result(result)
        except (HPConnError, ValueError) as exc:
            message = f"file-sys failed: {exc}"
            logging.error(message)
            return RunResult(ok=False, message=message)
        finally:
            transport.close()

    def _run_operation(self, file_system: CalculatorFileSystem, args: argparse.Namespace) -> FileSystemResult:
        """Dispatch the selected CLI action to the filesystem service."""
        if args.view_dir:
            return file_system.list_dir(args.view_dir)
        if args.create_dir:
            return file_system.create_dir(args.create_dir)
        if args.remove_dir:
            return file_system.remove_dir(args.remove_dir, purge=args.purge)
        if args.save_file:
            local_path, remote_path = args.save_file
            return file_system.save_file(local_path, remote_path)
        if args.remove_file:
            return file_system.remove_file(args.remove_file)
        if args.list_vars:
            return file_system.list_vars(args.list_vars)
        if args.create_var:
            name, value = args.create_var
            return file_system.create_variable(name, value, folder=args.folder)
        raise ValueError("No file-system operation selected")

    def _to_run_result(self, result: FileSystemResult) -> RunResult:
        """Convert a filesystem-layer result into the shared CLI result shape."""
        message = self._message_for_result(result)
        return RunResult(
            ok=True,
            message=message,
            data={
                "operation": result.operation,
                "path": result.path,
                "command": result.command,
                "output_text": result.output_text,
                "transfer_name": result.transfer_name,
                "entries": [
                    {"path": entry.path, "name": entry.name, "entry_type": entry.entry_type}
                    for entry in result.entries
                ],
                "local_path": result.local_path,
            },
        )

    @staticmethod
    def _message_for_result(result: FileSystemResult) -> str:
        """Build a human-readable CLI message for a filesystem result."""
        if result.operation in {"list_dir", "list_vars"}:
            header = f"{result.operation} {result.path}" if result.path else result.operation
            lines = [header]
            if result.entries:
                lines.extend(f"- {entry.name} [{entry.entry_type}]" for entry in result.entries)
            elif result.output_text:
                lines.append(result.output_text.strip())
            else:
                lines.append("<no output>")
            return "\n".join(lines)

        if result.operation == "save_file":
            return f"Uploaded {result.local_path} to {result.path}"

        return f"{result.operation} completed for {result.path}"
