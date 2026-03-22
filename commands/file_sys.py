"""Minimal calculator file-system command focused on remote directory creation."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import logging
from pathlib import PurePosixPath

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
    ) -> FileSystemResult:
        """Convert a host-command result into a minimal filesystem result."""
        return FileSystemResult(
            operation=operation,
            path=path,
            command=host_result.command,
            output_text=host_result.output_text,
        )

    def create_dir(self, path: str) -> FileSystemResult:
        """Create a directory on the calculator."""
        validated_path = self._validate_create_dir_path(path)
        host_result = self.client.run_rpl(RPLCommandBuilder.create_remote_dir(validated_path))
        return self._result_from_host("create_dir", validated_path, host_result)

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
        )


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
        group.add_argument(
            "--change-dir",
            nargs=2,
            metavar=("SRC_PATH", "DEST_PATH"),
            help="Rename or move a calculator directory within one parent folder",
        )

    def run(self, args: argparse.Namespace) -> RunResult:
        """Execute remote directory creation."""
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
            if getattr(args, "create_dir", None):
                result = file_system.create_dir(args.create_dir)
            elif getattr(args, "change_dir", None):
                src_path, dest_path = args.change_dir
                result = file_system.change_dir(src_path, dest_path)
            else:
                raise ValueError("No file-sys operation selected")
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
        return RunResult(
            ok=True,
            message=message,
            data={
                "operation": result.operation,
                "path": result.path,
                "command": result.command,
                "output_text": result.output_text,
                "dest_path": result.dest_path,
            },
        )
