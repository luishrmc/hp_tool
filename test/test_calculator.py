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

    def test_remove_dir_command(self) -> None:
        cmd1 = RPLCommandBuilder.remove_dir("FLOWTEST")
        self.assertEqual(cmd1.name, "remove_dir")
        self.assertEqual(cmd1.expression, "'FLOWTEST' RMDIR")

        cmd2 = RPLCommandBuilder.remove_dir("FLOWTEST", purge=True)
        self.assertEqual(cmd2.name, "purge_dir")
        self.assertEqual(cmd2.expression, "'FLOWTEST' PGDIR")

    def test_rename_command(self) -> None:
        cmd = RPLCommandBuilder.rename("OLD", "NEW")
        self.assertEqual(cmd.name, "rename")
        self.assertEqual(cmd.expression, "'OLD' 'NEW' RENAME")

    def test_list_dir_command(self) -> None:
        cmd = RPLCommandBuilder.list_dir("FLOWTEST")
        self.assertEqual(cmd.name, "list_dir")
        self.assertEqual(cmd.expression, "'FLOWTEST' EVAL VARS")

    def test_remove_file_command(self) -> None:
        cmd = RPLCommandBuilder.remove_file("DATA")
        self.assertEqual(cmd.name, "remove_file")
        self.assertEqual(cmd.expression, "'DATA' PURGE")

    def test_create_variable_command(self) -> None:
        cmd1 = RPLCommandBuilder.create_variable("A", "42")
        self.assertEqual(cmd1.name, "create_variable")
        self.assertEqual(cmd1.expression, "42 'A' STO")

        cmd2 = RPLCommandBuilder.create_variable("B", "3.14", folder="MATH")
        self.assertEqual(cmd2.name, "create_variable")
        self.assertEqual(cmd2.expression, "'MATH' EVAL 3.14 'B' STO")

    def test_create_equation_command(self) -> None:
        cmd1 = RPLCommandBuilder.create_equation("EQ1", "X+Y")
        self.assertEqual(cmd1.name, "create_equation")
        self.assertEqual(cmd1.expression, "'X+Y' 'EQ1' STO")

        cmd2 = RPLCommandBuilder.create_equation("EQ2", "A*B", folder="MATH")
        self.assertEqual(cmd2.name, "create_equation")
        self.assertEqual(cmd2.expression, "'MATH' EVAL 'A*B' 'EQ2' STO")

    def test_create_constant_command(self) -> None:
        cmd = RPLCommandBuilder.create_constant("PI", "3.14159")
        self.assertEqual(cmd.name, "create_variable")
        self.assertEqual(cmd.expression, "3.14159 'PI' STO")


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
