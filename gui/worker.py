"""Worker thread for Kermit communication to prevent freezing UI."""

import logging
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal

from conn.transport import SerialTransport
from conn.session import KermitSession
from calculator import CalculatorClient
from commands.file_sys import CalculatorFileSystem, RemoteEntry
from utils.exceptions import HPConnError, TransportError, SessionError, PacketError


class KermitWorker(QThread):
    """Thread for running calculator operations asynchronously."""

    # Signals to communicate back to the main thread
    list_dir_done = pyqtSignal(list)
    operation_done = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, port: str):
        super().__init__()
        self.port = port
        self.action = None
        self.args = ()
        self.kwargs = {}

    def set_action(self, action: str, *args, **kwargs):
        """Set the action to be performed in the next thread execution."""
        self.action = action
        self.args = args
        self.kwargs = kwargs

    def run(self):
        """Execute the requested action in the background."""
        if not self.action:
            return

        try:
            transport = SerialTransport(self.port)
            transport.open()
            session = KermitSession(transport)
            client = CalculatorClient(session)
            file_sys = CalculatorFileSystem(client)

            pending_signal = None
            pending_args = None

            if self.action == "list_dir":
                path = self.args[0]
                entries = file_sys.list_dir(path)
                pending_signal = self.list_dir_done
                pending_args = (entries,)

            elif self.action == "change_dir":
                path = self.args[0]
                client.change_remote_dir(path)
                pending_signal = self.operation_done
                pending_args = (path,)

            elif self.action == "upload_file":
                local_path = self.args[0]
                remote_dir = self.args[1]
                remote_path = f"{remote_dir}/{Path(local_path).name}".replace("//", "/")
                file_sys.save_file(local_path, remote_path)
                pending_signal = self.operation_done
                pending_args = ("upload_file",)

            elif self.action == "upload_files":
                local_paths = self.args[0]
                remote_dir = self.args[1]
                client.upload_files(local_paths, remote_dir=remote_dir)
                pending_signal = self.operation_done
                pending_args = ("upload_file",)

            elif self.action == "up_dir":
                client.run_rpl("UPDIR")
                pending_signal = self.operation_done
                pending_args = ("up_dir",)

            else:
                pending_signal = self.error_occurred
                pending_args = (f"Unknown action: {self.action}",)

        except (TransportError, SessionError, PacketError, HPConnError) as e:
            logging.error(f"Calculator communication error: {e}")
            pending_signal = self.error_occurred
            pending_args = (str(e),)
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            pending_signal = self.error_occurred
            pending_args = (str(e),)
        finally:
            if 'transport' in locals():
                try:
                    transport.close()
                except Exception:
                    pass

        # Emit signal AFTER transport is closed
        if pending_signal and pending_args is not None:
            pending_signal.emit(*pending_args)
