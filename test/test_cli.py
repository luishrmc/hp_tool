"""Unit tests for the file-sys CLI command registration and output shaping."""

from __future__ import annotations

from argparse import Namespace
import unittest
from unittest.mock import patch

from cli import build_parser
from commands.file_sys import FileSystemCommand, FileSystemResult, RemoteEntry


class FileSystemCliTests(unittest.TestCase):
    """Verify the thin CLI layer delegates to the filesystem service."""

    def test_parser_includes_file_sys_command(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["file-sys", "/dev/ttyUSB0", "--view-dir", "/HOME"])

        self.assertEqual(args.command, "file-sys")
        self.assertEqual(args.view_dir, "/HOME")

    def test_command_formats_listing_output(self) -> None:
        command = FileSystemCommand()
        result = FileSystemResult(
            operation="list_dir",
            path="/HOME",
            command="'/HOME' EVAL VARS",
            entries=(
                RemoteEntry(path="/HOME/A", name="A", entry_type="variable"),
                RemoteEntry(path="/HOME/B", name="B", entry_type="directory"),
            ),
        )

        run_result = command._to_run_result(result)

        self.assertTrue(run_result.ok)
        self.assertIn("list_dir /HOME", run_result.message)
        self.assertIn("- A [variable]", run_result.message)
        self.assertIn("- B [directory]", run_result.message)

    @patch("commands.file_sys.SerialTransport")
    @patch("commands.file_sys.KermitSession")
    @patch("commands.file_sys.CalculatorClient")
    @patch("commands.file_sys.CalculatorFileSystem")
    def test_run_dispatches_create_var(
        self,
        file_system_cls,
        client_cls,
        session_cls,
        transport_cls,
    ) -> None:
        file_system = file_system_cls.return_value
        file_system.create_variable.return_value = FileSystemResult(
            operation="create_variable",
            path="/HOME/TEST/A",
            command="'/HOME/TEST' EVAL 1 'A' STO",
        )
        args = Namespace(
            port="/dev/ttyUSB0",
            baud=115200,
            packet_size=80,
            retries=5,
            purge=False,
            folder="/HOME/TEST",
            view_dir=None,
            create_dir=None,
            remove_dir=None,
            save_file=None,
            remove_file=None,
            list_vars=None,
            create_var=["A", "1"],
        )

        result = FileSystemCommand().run(args)

        transport_cls.return_value.open.assert_called_once()
        transport_cls.return_value.flush_input.assert_called_once()
        file_system.create_variable.assert_called_once_with("A", "1", folder="/HOME/TEST")
        self.assertTrue(result.ok)
        self.assertIn("create_variable completed", result.message)


if __name__ == "__main__":
    unittest.main()
