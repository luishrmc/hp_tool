"""GUI Command for launching the file system explorer."""

import argparse

from commands.base import Command, RunResult

class GUICommand(Command):
    """Launch the PyQt GUI application."""

    name = "gui"
    help = "Launch the graphical file explorer."

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        pass

    def run(self, args: argparse.Namespace) -> RunResult:
        """Import and run the GUI, returning success when it closes."""
        try:
            from gui import run_gui
        except ImportError as exc:
            return RunResult(False, f"Could not import GUI dependencies. Is PyQt6 installed? {exc}")

        run_gui()
        return RunResult(True, "GUI closed successfully.")
