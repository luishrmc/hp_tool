"""Top-level CLI registration and dispatch for hp_tool."""

from __future__ import annotations

import argparse
import logging

from commands.base import Command, RunResult
from commands.build_tgv import BuildTGVCommand
from commands.transfer import TransferCommand
from utils.logging import setup_logging

COMMANDS: list[Command] = [
    BuildTGVCommand(),
    TransferCommand(),
]


def build_parser() -> argparse.ArgumentParser:
    """Build the root argument parser for the CLI.

    Returns:
        argparse.ArgumentParser: Configured parser with all subcommands registered.
    """
    root = argparse.ArgumentParser(
        prog="hp_tool",
        description="HP49g+/HP50g toolchain for TGV build and transfer workflows.",
    )
    root.add_argument("--debug", action="store_true", help="Enable debug logging")

    subparsers = root.add_subparsers(dest="command", required=True)
    for command in COMMANDS:
        parser = subparsers.add_parser(command.name, help=command.help)
        command.add_args(parser)

    return root


def main() -> int:
    """Parse CLI arguments, run the selected command, and derive an exit code.

    Returns:
        int: Process exit code derived from the selected command result.
    """
    parser = build_parser()
    args = parser.parse_args()
    setup_logging(debug=args.debug)

    for command in COMMANDS:
        if command.name == args.command:
            result = command.run(args)
            _log_result(result)
            return 0 if result.ok else 1

    parser.error(f"Unknown command: {args.command}")
    return 2


def _log_result(result: RunResult) -> None:
    """Log a command result using success-aware severity.

    Args:
        result: Outcome returned by a command implementation.
    """
    if not result.message:
        return

    if result.ok:
        logging.info(result.message)
    else:
        logging.error(result.message)
