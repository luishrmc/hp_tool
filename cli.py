"""Top-level CLI registration and dispatch for hp_tool."""

from __future__ import annotations

import argparse

from commands.base import Command
from commands.build_tgv import BuildTGVCommand
from commands.transfer import TransferCommand
from utils.logging import setup_logging

COMMANDS: list[Command] = [
    BuildTGVCommand(),
    TransferCommand(),
]

def build_parser() -> argparse.ArgumentParser:
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
    parser = build_parser()
    args = parser.parse_args()
    setup_logging(debug=args.debug)

    for command in COMMANDS:
        if command.name == args.command:
            return command.run(args)

    parser.error(f"Unknown command: {args.command}")
    return 2