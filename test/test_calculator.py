"""Unit tests for the calculator facade."""

from __future__ import annotations

import unittest
from pathlib import Path

from calculator import CalculatorClient, RPLCommandBuilder


class FakeSession:
    """Minimal session double used to capture client interactions."""

    def __init__(self) -> None:
        self.host_commands: list[str] = []
        self.files: list[Path] = []

    def send_host_command(self, command: str) -> str:
        self.host_commands.append(command)
        return command

    def send_file(self, file_path: str | Path) -> None:
        self.files.append(Path(file_path))


class RPLCommandBuilderTests(unittest.TestCase):
    """Verify that RPL commands are centralized and consistently built."""

    def test_create_remote_dir_command(self) -> None:
        command = RPLCommandBuilder.create_remote_dir("FLOWTEST")
        self.assertEqual(command.name, "create_remote_dir")
        self.assertEqual(command.expression, "'FLOWTEST' CRDIR")

    def test_change_remote_dir_command(self) -> None:
        command = RPLCommandBuilder.change_remote_dir("FLOWTEST")
        self.assertEqual(command.name, "change_remote_dir")
        self.assertEqual(command.expression, "'FLOWTEST' EVAL")


class CalculatorClientTests(unittest.TestCase):
    """Verify that the client delegates to the existing session object."""

    def test_upload_files_switches_directory_once(self) -> None:
        session = FakeSession()
        client = CalculatorClient(session)

        client.upload_files(["a.T49", "b.T49"], remote_dir="FLOWTEST")

        self.assertEqual(session.host_commands, ["'FLOWTEST' EVAL"])
        self.assertEqual(session.files, [Path("a.T49"), Path("b.T49")])


if __name__ == "__main__":
    unittest.main()
