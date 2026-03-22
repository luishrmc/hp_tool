"""Unit tests for the minimal file-sys CLI command."""

from __future__ import annotations

from argparse import Namespace
import unittest
from unittest.mock import patch

from cli import build_parser
from commands.file_sys import FileSystemCommand, FileSystemResult


class FileSystemCliTests(unittest.TestCase):
    """Verify the reduced CLI layer delegates only create-dir."""

    def test_parser_includes_file_sys_create_dir(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["file-sys", "/dev/ttyUSB0", "--create-dir", "/HOME/TESTDIR"])

        self.assertEqual(args.command, "file-sys")
        self.assertEqual(args.create_dir, "/HOME/TESTDIR")

    @patch("commands.file_sys.SerialTransport")
    @patch("commands.file_sys.KermitSession")
    @patch("commands.file_sys.CalculatorClient")
    @patch("commands.file_sys.CalculatorFileSystem")
    def test_run_dispatches_create_dir(
        self,
        file_system_cls,
        client_cls,
        session_cls,
        transport_cls,
    ) -> None:
        del client_cls, session_cls
        file_system = file_system_cls.return_value
        file_system.create_dir.return_value = FileSystemResult(
            operation="create_dir",
            path="/HOME/TESTDIR",
            command="'TESTDIR' CRDIR",
        )
        args = Namespace(
            port="/dev/ttyUSB0",
            baud=115200,
            packet_size=80,
            retries=5,
            create_dir="/HOME/TESTDIR",
        )

        result = FileSystemCommand().run(args)

        transport_cls.return_value.open.assert_called_once()
        transport_cls.return_value.flush_input.assert_called_once()
        file_system.create_dir.assert_called_once_with("/HOME/TESTDIR")
        self.assertTrue(result.ok)
        self.assertIn("create_dir completed for /HOME/TESTDIR", result.message)
