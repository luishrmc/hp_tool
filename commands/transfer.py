"""transfer command.

Transfer all .T49 files from a target directory to the calculator.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from commands.base import Command

from conn.session import KermitSession
from conn.transport import SerialTransport
from utils.exceptions import HPConnError


class TransferCommand(Command):
    name = "transfer"
    help = "Transfer all .T49 files from a project directory to the calculator"

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("target_dir", help="Path to the project directory containing the HP output directory")
        parser.add_argument("port", help="Serial port, for example /dev/ttyUSB0")
        parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate")
        parser.add_argument("--input-dir", default="HP", help="Relative directory inside target_dir where .T49 files are searched (default: HP)")
        parser.add_argument("--packet-size", type=int, default=80, help="Payload size for D packets")
        parser.add_argument("--retries", type=int, default=5, help="Maximum retries per packet")

    def run(self, args: argparse.Namespace) -> int:
        logging.info("transfer command selected")

        # Validate target directory
        target_dir = Path(args.target_dir).resolve()
        if not target_dir.is_dir():
            logging.error("Target directory does not exist: %s", target_dir)
            return 1
        logging.info("Target directory: %s", target_dir)

        # Validate arguments
        args_dict = vars(args)
        logging.debug("CLI arguments:\n%s", json.dumps(args_dict, indent=4))

        # Resolve input directory containing .T49 files
        input_dir = target_dir / args.input_dir
        if not input_dir.is_dir():
            logging.error("Input directory does not exist: %s", input_dir)
            return 2
        logging.debug("Resolved input directory: %s", input_dir)

        # Find .T49 files
        t49_files = sorted(input_dir.glob("*.T49"))
        if not t49_files:
            logging.error("No .T49 files found in: %s", input_dir)
            return 3

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

            for t49_path in t49_files:
                logging.info("[Transferring: %s]", t49_path.name)
                session.send_file(t49_path)

            logging.info("[transfer completed]")
            return 0

        except HPConnError as exc:
            logging.error("Transfer failed: %s", exc)
            return 2
        finally:
            transport.close()
