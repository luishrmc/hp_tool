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
    """Structured outcome returned by the minimal filesystem operation."""

    operation: str
    path: str
    command: str
    output_text: str = ""


class CalculatorFileSystem:
    """Minimal calculator file-system service for remote directory creation."""

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


class FileSystemCommand(Command):
    """CLI command exposing only remote directory creation for now."""

    name = "file-sys"
    help = "Create a calculator directory via Kermit Server host commands"

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        """Register CLI arguments for the file-sys subcommand."""
        parser.add_argument("port", help="Serial port, for example /dev/ttyUSB0")
        parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate")
        parser.add_argument("--packet-size", type=int, default=80, help="Payload size for D packets")
        parser.add_argument("--retries", type=int, default=5, help="Maximum retries per packet")
        parser.add_argument("--create-dir", required=True, metavar="REMOTE_DIR", help="Create a calculator directory")

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
            result = file_system.create_dir(args.create_dir)
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
            },
        )
