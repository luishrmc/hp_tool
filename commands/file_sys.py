"""Calculator file system operations and CLI commands."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

from calculator import CalculatorClient, RPLCommandBuilder
from commands.base import Command, RunResult
from conn.session import KermitSession
from conn.transport import SerialTransport
from utils.exceptions import HPConnError


class CalculatorFileSystem:
    """Service for managing the calculator's file system via Kermit Server."""

    def __init__(self, client: CalculatorClient) -> None:
        """Initialize the file system service with an active client.

        Args:
            client: The calculator client connected to the device.
        """
        self.client = client

    def create_dir(self, path: str) -> None:
        """Create a directory on the calculator."""
        logging.info("Creating directory '%s'...", path)
        self.client.run_rpl(RPLCommandBuilder.create_remote_dir(path))

    def remove_dir(self, path: str, purge: bool = False) -> None:
        """Remove a directory on the calculator."""
        logging.info("Removing directory '%s' (purge=%s)...", path, purge)
        self.client.run_rpl(RPLCommandBuilder.remove_dir(path, purge=purge))

    def rename(self, old_path: str, new_path: str) -> None:
        """Rename a file or directory on the calculator."""
        logging.info("Renaming '%s' to '%s'...", old_path, new_path)
        self.client.run_rpl(RPLCommandBuilder.rename(old_path, new_path))

    def list_dir(self, path: str) -> None:
        """List contents of a directory on the calculator."""
        logging.info("Listing contents of '%s'...", path)
        # Note: the host command will be sent and processed, but returning
        # actual data from RPL execution over Kermit requires sinking/parsing
        # the transfer which KermitSession currently just consumes.
        self.client.run_rpl(RPLCommandBuilder.list_dir(path))

    def save_file(self, local_path: str | Path, remote_path: str) -> None:
        """Upload a file to a specific remote path on the calculator."""
        logging.info("Saving '%s' to '%s'...", local_path, remote_path)
        # Assuming remote_path might be a dir + filename. For now, we change
        # dir if it's a directory structure, or rely on Kermit's save.
        # Here we just use the simple upload_file from CalculatorClient.
        # A more sophisticated implementation might parse the directory from remote_path.

        # simple parsing:
        parts = str(remote_path).rsplit("/", 1)
        remote_dir = parts[0] if len(parts) > 1 else None
        self.client.upload_file(local_path, remote_dir=remote_dir)

    def remove_file(self, path: str) -> None:
        """Remove a file or variable on the calculator."""
        logging.info("Removing file/variable '%s'...", path)
        self.client.run_rpl(RPLCommandBuilder.remove_file(path))

    def create_variable(self, name: str, value: str, folder: str | None = None) -> None:
        """Create a variable on the calculator."""
        logging.info("Creating variable '%s'...", name)
        self.client.run_rpl(RPLCommandBuilder.create_variable(name, value, folder=folder))

    def create_equation(self, name: str, expression: str, folder: str | None = None) -> None:
        """Create an equation on the calculator."""
        logging.info("Creating equation '%s'...", name)
        self.client.run_rpl(RPLCommandBuilder.create_equation(name, expression, folder=folder))

    def create_constant(self, name: str, value: str, folder: str | None = None) -> None:
        """Create a constant on the calculator."""
        logging.info("Creating constant '%s'...", name)
        self.client.run_rpl(RPLCommandBuilder.create_constant(name, value, folder=folder))


class FileSysCommand(Command):
    """File system commands for the HP50g calculator."""

    name = "file-sys"
    help = "Manage the calculator file system (directories, files, variables)"

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        """Register CLI arguments for the file-sys subcommand."""
        parser.add_argument("port", help="Serial port, for example /dev/ttyUSB0")
        parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate")
        parser.add_argument("--packet-size", type=int, default=80, help="Payload size for D packets")
        parser.add_argument("--retries", type=int, default=5, help="Maximum retries per packet")

        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--create-dir", metavar="PATH", help="Create a directory")
        group.add_argument("--remove-dir", metavar="PATH", help="Remove a directory")
        group.add_argument("--view-dir", metavar="PATH", help="List contents of a directory")
        group.add_argument("--save-file", nargs=2, metavar=("LOCAL", "REMOTE"), help="Save local file to remote path")
        group.add_argument("--remove-file", metavar="PATH", help="Remove a file or variable")

    def run(self, args: argparse.Namespace) -> RunResult:
        """Execute the selected file system operation."""
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
            client = CalculatorClient(session)
            fs = CalculatorFileSystem(client)

            data: dict[str, Any] = {}

            if args.create_dir:
                fs.create_dir(args.create_dir)
                data["action"] = "create_dir"
                data["path"] = args.create_dir

            elif args.remove_dir:
                fs.remove_dir(args.remove_dir)
                data["action"] = "remove_dir"
                data["path"] = args.remove_dir

            elif args.view_dir:
                fs.list_dir(args.view_dir)
                data["action"] = "view_dir"
                data["path"] = args.view_dir

            elif args.save_file:
                local_path, remote_path = args.save_file
                fs.save_file(local_path, remote_path)
                data["action"] = "save_file"
                data["local_path"] = local_path
                data["remote_path"] = remote_path

            elif args.remove_file:
                fs.remove_file(args.remove_file)
                data["action"] = "remove_file"
                data["path"] = args.remove_file

            return RunResult(
                ok=True,
                message="File system operation completed successfully",
                data=data,
            )
        except HPConnError as exc:
            message = f"File system operation failed: {exc}"
            logging.error(message)
            return RunResult(ok=False, message=message)
        finally:
            transport.close()
