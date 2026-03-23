"""Minimal calculator file-system command focused on remote directory creation."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import logging
from pathlib import PurePosixPath
import re

from calculator import CalculatorClient, RPLCommandBuilder
from commands.base import Command, RunResult
from conn.session import HostCommandResult, KermitSession
from conn.transport import SerialTransport
from utils.exceptions import HPConnError


@dataclass(frozen=True, slots=True)
class FileSystemResult:
    """Structured outcome returned by the minimal filesystem operations."""

    operation: str
    path: str
    command: str
    output_text: str = ""
    dest_path: str | None = None
    raw_output_text: str = ""


class CalculatorFileSystem:
    """Minimal calculator file-system service for remote directory operations."""

    def __init__(self, client: CalculatorClient) -> None:
        """Bind the service to an existing calculator client."""
        self.client = client

    @staticmethod
    def _validate_create_dir_path(path: str) -> str:
        """Validate that the requested remote directory path has a final folder name."""
        if not path.strip():
            raise ValueError("Remote directory path must not be empty")

        normalized = PurePosixPath(path)
        if not normalized.name:
            raise ValueError(f"Remote directory path must include a directory name: {path!r}")
        return path

    def _result_from_host(
        self,
        operation: str,
        path: str,
        host_result: HostCommandResult,
        output_text: str | None = None,
    ) -> FileSystemResult:
        """Convert a host-command result into a minimal filesystem result."""
        raw_output_text = host_result.output_text
        if raw_output_text:
            logging.debug("Raw stack output for %s (%s):\n%s", operation, path, raw_output_text)
        return FileSystemResult(
            operation=operation,
            path=path,
            command=host_result.command,
            output_text=raw_output_text if output_text is None else output_text,
            raw_output_text=raw_output_text,
        )

    @staticmethod
    def _stack_lines(output_text: str) -> list[str]:
        """Normalize calculator stack output into non-empty lines."""
        return [line.strip() for line in output_text.splitlines() if line.strip()]

    @staticmethod
    def _strip_stack_prefix(line: str) -> str:
        """Remove an optional stack-line prefix such as ``1:``."""
        cleaned = line.strip()
        if ":" not in cleaned:
            return cleaned
        prefix, remainder = cleaned.split(":", 1)
        return remainder.strip() if prefix.strip().isdigit() else cleaned

    @classmethod
    def _parse_listing_entries(cls, output_text: str) -> list[str]:
        """Parse calculator ``VARS`` output into individual entry names."""
        entries: list[str] = []
        for line in cls._stack_lines(output_text):
            cleaned = cls._strip_stack_prefix(line)
            if cleaned in {"{ }", "{}"}:
                continue
            tokens = re.findall(r"'[^']*'|[^\s{}]+", cleaned)
            if not tokens and cleaned and cleaned not in {"{", "}"}:
                tokens = [cleaned]
            entries.extend(token.strip("'") for token in tokens if token.strip("'"))
        logging.debug("Parsed listing entries: %s", entries)
        return entries

    @classmethod
    def _entry_is_dir(cls, entry: str) -> bool:
        """Best-effort directory detection for recursive listing."""
        if entry.endswith("/"):
            return True
        return "." not in entry and entry.upper().endswith("DIR")

    @classmethod
    def _clean_entry_name(cls, entry: str) -> str:
        """Return a normalized entry name without tree-specific suffixes."""
        return entry.rstrip("/")

    @classmethod
    def _entry_is_file(cls, entry: str) -> bool:
        """Best-effort file detection for tree rendering."""
        return "." in entry and not entry.endswith("/")

    def _fetch_listing(self, operation: str, label: str, command) -> tuple[list[str], str]:
        """Run one list command and return parsed stack lines plus raw text."""
        logging.debug("Recursive listing traversal for %s: label=%s command=%s", operation, label, command.expression)
        host_result = self.client.run_rpl(command)
        raw_output = host_result.output_text
        if raw_output:
            logging.debug("Raw returned calculator text for %s (%s):\n%s", operation, label, raw_output)
        entries = self._parse_listing_entries(raw_output)
        return entries, raw_output

    def _build_tree(self, operation: str, root_label: str, start_mode: str) -> FileSystemResult:
        """Build a recursive file tree for HOME or current-directory listing."""
        raw_outputs: list[str] = []
        tree_lines = [root_label]

        def recurse(path_key: str, label: str, prefix: str, absolute: bool) -> None:
            if start_mode == "home" and absolute:
                lines, raw_output = self._fetch_listing(operation, label, RPLCommandBuilder.list_absolute_dir(path_key))
            elif start_mode == "current" and not path_key:
                lines, raw_output = self._fetch_listing(operation, label, RPLCommandBuilder.list_current_dir())
            else:
                lines, raw_output = self._fetch_listing(operation, label, RPLCommandBuilder.list_relative_dir(path_key))

            if raw_output:
                raw_outputs.append(f"[{label}]\n{raw_output}")

            logging.debug(
                "Final tree rendering inputs for %s: label=%s path_key=%s absolute=%s raw_entries=%s",
                operation,
                label,
                path_key,
                absolute,
                lines,
            )
            entries = [
                self._clean_entry_name(line)
                for line in lines
                if self._entry_is_dir(line) or self._entry_is_file(line)
            ]
            dir_names = {self._clean_entry_name(line) for line in lines if self._entry_is_dir(line)}
            if not entries:
                tree_lines.append(f"{prefix}└── <empty>")
                return

            for index, entry in enumerate(entries):
                is_last = index == len(entries) - 1
                branch = "└──" if is_last else "├──"
                tree_lines.append(f"{prefix}{branch} {entry}")
                if entry in dir_names:
                    child_prefix = f"{prefix}{'    ' if is_last else '│   '}"
                    child_path = entry if not path_key else f"{path_key}/{entry}"
                    child_label = entry if label == "." else f"{label.rstrip('/')}/{entry}"
                    logging.debug(
                        "Recursive traversal step for %s: parent=%s child=%s child_path=%s child_label=%s",
                        operation,
                        label,
                        entry,
                        child_path,
                        child_label,
                    )
                    recurse(child_path, child_label, child_prefix, absolute)

        if start_mode == "home":
            recurse("/HOME", "HOME/", "", True)
            display_path = "/HOME"
            tree_lines[0] = "HOME/"
        else:
            recurse("", ".", "", False)
            display_path = "."

        return FileSystemResult(
            operation=operation,
            path=display_path,
            command="recursive-list",
            output_text="\n".join(tree_lines),
            raw_output_text="\n\n".join(raw_outputs),
        )

    def create_dir(self, path: str) -> FileSystemResult:
        """Create a directory on the calculator."""
        validated_path = self._validate_create_dir_path(path)
        if RPLCommandBuilder._is_absolute_path(validated_path) and len(RPLCommandBuilder._folder_segments(validated_path)) > 1:
            logging.debug("Nested directory creation steps for %s", validated_path)
            command = RPLCommandBuilder.create_nested_remote_dir(validated_path)
        else:
            command = RPLCommandBuilder.create_remote_dir(validated_path)
        host_result = self.client.run_rpl(command)
        return self._result_from_host("create_dir", validated_path, host_result)

    def delete_dir(self, path: str) -> FileSystemResult:
        """Delete a directory on the calculator."""
        validated_path = self._validate_create_dir_path(path)
        host_result = self.client.run_rpl(RPLCommandBuilder.delete_remote_dir(validated_path))
        return self._result_from_host("delete_dir", validated_path, host_result)

    def change_dir(self, src_path: str, dest_path: str) -> FileSystemResult:
        """Rename or move a directory within a single parent folder."""
        validated_src = self._validate_create_dir_path(src_path)
        validated_dest = self._validate_create_dir_path(dest_path)
        host_result = self.client.run_rpl(RPLCommandBuilder.move_remote_dir(validated_src, validated_dest))
        result = self._result_from_host("change_dir", validated_src, host_result)
        return FileSystemResult(
            operation=result.operation,
            path=result.path,
            command=result.command,
            output_text=result.output_text,
            dest_path=validated_dest,
            raw_output_text=result.raw_output_text,
        )

    def list_home(self) -> FileSystemResult:
        """List entries starting from the calculator HOME directory."""
        return self._build_tree("list_home", "/HOME", start_mode="home")

    def list_dir(self) -> FileSystemResult:
        """List entries from the current calculator directory."""
        return self._build_tree("list_dir", ".", start_mode="current")

    def cd_dir(self, path: str) -> FileSystemResult:
        """Change to the requested calculator directory."""
        validated_path = self._validate_create_dir_path(path)
        if validated_path.startswith("/"):
            logging.debug("Current-directory resolution for --cd-dir: treating %s as absolute from HOME", validated_path)
        else:
            logging.debug("Current-directory resolution for --cd-dir: treating %s as relative to current directory", validated_path)
        host_result = self.client.run_rpl(RPLCommandBuilder.cd_remote_dir(validated_path))
        return self._result_from_host("cd_dir", validated_path, host_result)

    def clear_stack(self) -> None:
        """Clear the calculator stack after a command completes."""
        logging.debug("Clearing calculator stack with CLEAR")
        self.client.run_rpl(RPLCommandBuilder.clear_stack())


class FileSystemCommand(Command):
    """CLI command exposing minimal remote directory operations."""

    name = "file-sys"
    help = "Create or change a calculator directory via Kermit Server host commands"

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        """Register CLI arguments for the file-sys subcommand."""
        parser.add_argument("port", help="Serial port, for example /dev/ttyUSB0")
        parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate")
        parser.add_argument("--packet-size", type=int, default=80, help="Payload size for D packets")
        parser.add_argument("--retries", type=int, default=5, help="Maximum retries per packet")
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--create-dir", metavar="REMOTE_DIR", help="Create a calculator directory")
        group.add_argument("--delete-dir", metavar="REMOTE_DIR", help="Delete a calculator directory")
        group.add_argument(
            "--change-dir",
            nargs=2,
            metavar=("SRC_PATH", "DEST_PATH"),
            help="Rename or move a calculator directory within one parent folder",
        )
        group.add_argument("--list-home", action="store_true", help="List entries starting from /HOME")
        group.add_argument("--list-dir", action="store_true", help="List entries in the current calculator directory")
        group.add_argument("--cd-dir", metavar="REMOTE_PATH", help="Change to the requested calculator directory")

    def run(self, args: argparse.Namespace) -> RunResult:
        """Execute remote directory creation."""
        logging.info("file-sys command selected")

        transport = SerialTransport(port=args.port, baudrate=args.baud)
        file_system: CalculatorFileSystem | None = None
        result: FileSystemResult | None = None
        try:
            transport.open()
            transport.flush_input()

            session = KermitSession(
                transport=transport,
                packet_size=args.packet_size,
                max_retries=args.retries,
            )
            file_system = CalculatorFileSystem(CalculatorClient(session))
            if getattr(args, "create_dir", None):
                result = file_system.create_dir(args.create_dir)
            elif getattr(args, "delete_dir", None):
                result = file_system.delete_dir(args.delete_dir)
            elif getattr(args, "change_dir", None):
                src_path, dest_path = args.change_dir
                result = file_system.change_dir(src_path, dest_path)
            elif getattr(args, "list_home", False):
                result = file_system.list_home()
            elif getattr(args, "list_dir", False):
                result = file_system.list_dir()
            elif getattr(args, "cd_dir", None):
                result = file_system.cd_dir(args.cd_dir)
            else:
                raise ValueError("No file-sys operation selected")

            if file_system is not None:
                file_system.clear_stack()
            return self._to_run_result(result)
        except (HPConnError, ValueError) as exc:
            message = f"file-sys failed: {exc}"
            logging.error(message)
            return RunResult(ok=False, message=message)
        finally:
            transport.close()

    @staticmethod
    def _to_run_result(result: FileSystemResult) -> RunResult:
        """Convert a minimal filesystem result into the shared CLI result shape."""
        if result.operation == "change_dir" and result.dest_path is not None:
            message = f"{result.operation} completed from {result.path} to {result.dest_path}"
        else:
            message = f"{result.operation} completed for {result.path}"

        if result.output_text.strip():
            message = f"{message}\n{result.output_text.strip()}"
        elif result.operation in {"list_home", "list_dir"}:
            message = f"{message}\n<no output>"

        return RunResult(
            ok=True,
            message=message,
            data={
                "operation": result.operation,
                "path": result.path,
                "command": result.command,
                "output_text": result.output_text,
                "raw_output_text": result.raw_output_text,
                "dest_path": result.dest_path,
            },
        )
