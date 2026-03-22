"""Unit tests for the calculator facade and minimal filesystem service."""

from __future__ import annotations

import unittest
from pathlib import Path

from calculator import CalculatorClient, RPLCommandBuilder
from commands.file_sys import CalculatorFileSystem
from conn.session import HostCommandResult


class FakeSession:
    """Minimal session double used to capture client interactions."""

    def __init__(self) -> None:
        self.host_commands: list[str] = []
        self.files: list[Path] = []

    def send_host_command(self, command: str) -> HostCommandResult:
        self.host_commands.append(command)
        return HostCommandResult(command=command, reply_packet="ACK")

    def send_file(self, file_path: str | Path) -> None:
        self.files.append(Path(file_path))


class RPLCommandBuilderTests(unittest.TestCase):
    """Verify that the create-dir command is centralized and normalized."""

    def test_create_remote_dir_command_for_home_child(self) -> None:
        command = RPLCommandBuilder.create_remote_dir("/HOME/TESTDIR")
        self.assertEqual(command.name, "create_remote_dir")
        self.assertEqual(command.expression, "'TESTDIR' CRDIR")

    def test_create_remote_dir_command_for_nested_folder(self) -> None:
        command = RPLCommandBuilder.create_remote_dir("/HOME/PARENT/CHILD")
        self.assertEqual(command.expression, "'PARENT' EVAL 'CHILD' CRDIR")


class CalculatorClientTests(unittest.TestCase):
    """Verify that the client delegates to the existing session object."""

    def test_upload_files_switches_directory_once(self) -> None:
        session = FakeSession()
        client = CalculatorClient(session)

        client.upload_files(["a.T49", "b.T49"], remote_dir="FLOWTEST")

        self.assertEqual(session.host_commands, ["'FLOWTEST' EVAL"])
        self.assertEqual(session.files, [Path("a.T49"), Path("b.T49")])


class CalculatorFileSystemTests(unittest.TestCase):
    """Verify that the minimal filesystem helper stays above the session layer."""

    def test_create_dir_uses_normalized_rpl_builder(self) -> None:
        session = FakeSession()
        client = CalculatorClient(session)
        file_system = CalculatorFileSystem(client)

        result = file_system.create_dir("/HOME/TESTDIR")

        self.assertEqual(session.host_commands, ["'TESTDIR' CRDIR"])
        self.assertEqual(result.command, "'TESTDIR' CRDIR")
        self.assertEqual(result.path, "/HOME/TESTDIR")

    def test_create_dir_rejects_root_only_path(self) -> None:
        session = FakeSession()
        client = CalculatorClient(session)
        file_system = CalculatorFileSystem(client)

        with self.assertRaises(ValueError):
            file_system.create_dir("/")
