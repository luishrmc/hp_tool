"""transfer command implementation."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from commands.base import Command, RunResult
from conn.session import KermitSession
from conn.transport import SerialTransport
from utils.exceptions import HPConnError


class TransferCommand(Command):
    """Transfer built .T49 files from a project directory to the calculator."""

    name = "transfer"
    help = "Transfer all .T49 files from a project directory to the calculator"

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        """Register CLI arguments for the transfer subcommand.

        Args:
            parser: Parser dedicated to this subcommand.
        """
        parser.add_argument("target_dir", help="Path to the project directory containing the HP output directory")
        parser.add_argument("port", help="Serial port, for example /dev/ttyUSB0")
        parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate")
        parser.add_argument("--input-dir", default="HP", help="Relative directory inside target_dir where .T49 files are searched (default: HP)")
        parser.add_argument("--packet-size", type=int, default=80, help="Payload size for D packets")
        parser.add_argument("--retries", type=int, default=5, help="Maximum retries per packet")

    def run(self, args: argparse.Namespace) -> RunResult:
        """Transfer every discovered .T49 file to the calculator.

        Args:
            args: Parsed CLI arguments for this command.

        Returns:
            RunResult: Structured outcome describing success or failure.
        """
        logging.info("transfer command selected")

        target_dir = Path(args.target_dir).resolve()
        if not target_dir.is_dir():
            message = f"Target directory does not exist: {target_dir}"
            logging.error(message)
            return RunResult(ok=False, message=message)
        logging.info("Target directory: %s", target_dir)

        args_dict = vars(args)
        logging.debug("CLI arguments:\n%s", json.dumps(args_dict, indent=4))

        input_dir = target_dir / args.input_dir
        if not input_dir.is_dir():
            message = f"Input directory does not exist: {input_dir}"
            logging.error(message)
            return RunResult(ok=False, message=message)
        logging.debug("Resolved input directory: %s", input_dir)

        t49_files = sorted(input_dir.glob("*.T49"))
        if not t49_files:
            message = f"No .T49 files found in: {input_dir}"
            logging.error(message)
            return RunResult(ok=False, message=message)

        logging.info("Found %d .T49 file(s) to transfer", len(t49_files))
        for path in t49_files:
            logging.info("Queued for transfer: %s", path.name)

        transport = SerialTransport(port=args.port, baudrate=args.baud)

        try:
            transport.open()
            transport.flush_input()

            session = KermitSession(
                transport=transport,
                packet_size=args.packet_size,
                max_retries=args.retries,
            )

            NEW_DIR_NAME = "OKDIR2"
            logging.info(f"Creating directory '{NEW_DIR_NAME}' on the calculator...")
            rpl_command = f"'{NEW_DIR_NAME}' CRDIR"
            session.send_host_command(rpl_command)

            logging.info(f"Moving to the DIR")
            rpl_command = f"'{NEW_DIR_NAME}' EVAL"
            session.send_host_command(rpl_command)

            for t49_path in t49_files:
                logging.info("[Transferring: %s]", t49_path.name)
                session.send_file(t49_path)

            logging.info("[transfer completed]")
            return RunResult(
                ok=True,
                message="transfer completed successfully",
                data={
                    "target_dir": str(target_dir),
                    "input_dir": str(input_dir),
                    "files": [path.name for path in t49_files],
                },
            )
        except HPConnError as exc:
            message = f"Transfer failed: {exc}"
            logging.error(message)
            return RunResult(ok=False, message=message)
        finally:
            transport.close()
