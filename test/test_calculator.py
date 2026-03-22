"""Unit tests for the calculator facade and filesystem service."""

from __future__ import annotations

import unittest
from pathlib import Path

from calculator import CalculatorClient, RPLCommandBuilder
from commands.file_sys import CalculatorFileSystem


class FakeSession:
    """Minimal session double used to capture client interactions."""

    def __init__(self) -> None:
        self.host_commands: list[str] = []
        self.files: list[Path] = []

    def send_host_command(self, command: str) -> tuple[str, bytes]:
        self.host_commands.append(command)
        return command, b""

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

    def test_remove_remote_dir_uses_pgdir_when_requested(self) -> None:
        command = RPLCommandBuilder.remove_remote_dir("FLOWTEST", purge=True)
        self.assertEqual(command.name, "remove_remote_dir")
        self.assertEqual(command.expression, "'FLOWTEST' PGDIR")

    def test_store_equation_in_folder(self) -> None:
        command = RPLCommandBuilder.store_equation("EQ1", "X^2+1", folder="/HOME/ALG")
        self.assertEqual(command.name, "store_equation")
        self.assertEqual(command.expression, "'/HOME/ALG' EVAL 'X^2+1' 'EQ1' STO")


class CalculatorClientTests(unittest.TestCase):
    """Verify that the client delegates to the existing session object."""

    def test_upload_files_switches_directory_once(self) -> None:
        session = FakeSession()
        client = CalculatorClient(session)

        client.upload_files(["a.T49", "b.T49"], remote_dir="FLOWTEST")

        self.assertEqual(session.host_commands, ["'FLOWTEST' EVAL"])
        self.assertEqual(session.files, [Path("a.T49"), Path("b.T49")])


class CalculatorFileSystemTests(unittest.TestCase):
    """Verify that filesystem helpers stay above the session layer."""

    def test_create_variable_uses_rpl_builder(self) -> None:
        session = FakeSession()
        client = CalculatorClient(session)
        file_system = CalculatorFileSystem(client)

        file_system.create_variable("A", "1", folder="/HOME/TEST")

        self.assertEqual(session.host_commands, ["'/HOME/TEST' EVAL 1 'A' STO"])

    def test_save_file_routes_upload_to_parent_directory(self) -> None:
        session = FakeSession()
        client = CalculatorClient(session)
        file_system = CalculatorFileSystem(client)

        file_system.save_file("/tmp/example.T49", "/HOME/TEST/example.T49")

        self.assertEqual(session.host_commands, ["'/HOME/TEST' EVAL"])
        self.assertEqual(session.files, [Path("/tmp/example.T49")])

    def test_save_file_rejects_remote_rename_for_now(self) -> None:
        session = FakeSession()
        client = CalculatorClient(session)
        file_system = CalculatorFileSystem(client)

        with self.assertRaises(ValueError):
            file_system.save_file("/tmp/example.T49", "/HOME/TEST/renamed.T49")

    def test_list_dir_parses_rpl_list(self) -> None:
        class FakeSessionListDir(FakeSession):
            def send_host_command(self, command: str) -> tuple[str, bytes]:
                self.host_commands.append(command)
                return command, b'{ "A" "DIR1" }'

        session = FakeSessionListDir()
        client = CalculatorClient(session)
        file_system = CalculatorFileSystem(client)

        entries = file_system.list_dir("/HOME")

        self.assertEqual(session.host_commands, ["'/HOME' EVAL VARS"])
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].name, "A")
        self.assertEqual(entries[0].path, "/HOME/A")
        self.assertEqual(entries[1].name, "DIR1")
        self.assertEqual(entries[1].path, "/HOME/DIR1")


if __name__ == "__main__":
    unittest.main()
