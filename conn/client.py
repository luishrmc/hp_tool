"""Calculator client facade for high-level operations over Kermit."""

from __future__ import annotations

import logging
from pathlib import Path

from conn.session import KermitSession


class CalculatorClient:
    """Provides high-level RPL operations wrapping a Kermit session.

    This layer separates calculator-specific commands (like folder creation
    and navigation) from the underlying Kermit protocol mechanics. It is
    designed to be consumed by both CLI commands and future graphical interfaces.
    """

    def __init__(self, session: KermitSession) -> None:
        """Initialize the client with an active Kermit session.

        Args:
            session: An established KermitSession ready to send commands.
        """
        self.session = session

    def create_dir(self, name: str) -> None:
        """Create a directory on the calculator.

        Args:
            name: The name of the directory to create.
        """
        logging.info("Creating directory %r on calculator", name)
        rpl_command = f"'{name}' CRDIR"
        self.session.send_host_command(rpl_command)

    def change_dir(self, name: str) -> None:
        """Change the current directory on the calculator.

        Args:
            name: The name of the directory to evaluate/enter.
        """
        logging.info("Changing to directory %r on calculator", name)
        rpl_command = f"'{name}' EVAL"
        self.session.send_host_command(rpl_command)

    def upload_file(self, path: str | Path) -> None:
        """Upload a local file to the current calculator directory.

        Args:
            path: Local path to the file to transfer.
        """
        self.session.send_file(path)
