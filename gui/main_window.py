"""Main window for the HP 50g Kermit File System GUI."""

import logging
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QPushButton, QLabel,
    QMessageBox, QLineEdit, QFileDialog
)
from PyQt6.QtCore import Qt

from gui.worker import KermitWorker


class DropListWidget(QListWidget):
    """A list widget that accepts drag-and-drop file uploads."""
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            urls = event.mimeData().urls()
            local_files = []
            for url in urls:
                if url.isLocalFile():
                    local_files.append(url.toLocalFile())

            if len(local_files) == 1:
                self.main_window.upload_file(local_files[0])
            elif len(local_files) > 1:
                self.main_window.upload_files(local_files)
        else:
            event.ignore()


class MainWindow(QMainWindow):
    """Main application window for the file explorer GUI."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("HP 50g File System Explorer")
        self.resize(600, 400)

        self.current_path = "HOME"

        # UI Setup
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)

        # Connection Layout
        conn_layout = QHBoxLayout()
        self.port_input = QLineEdit("/dev/ttyUSB0")
        conn_layout.addWidget(QLabel("Serial Port:"))
        conn_layout.addWidget(self.port_input)

        self.refresh_btn = QPushButton("Connect / Refresh")
        self.refresh_btn.clicked.connect(self.refresh_directory)
        conn_layout.addWidget(self.refresh_btn)
        main_layout.addLayout(conn_layout)

        # Navigation Layout
        nav_layout = QHBoxLayout()
        self.path_label = QLabel(f"Current Path: {self.current_path}")
        nav_layout.addWidget(self.path_label)
        nav_layout.addStretch()

        self.up_btn = QPushButton("Up (UPDIR)")
        self.up_btn.clicked.connect(self.navigate_up)
        nav_layout.addWidget(self.up_btn)
        main_layout.addLayout(nav_layout)

        # File List View
        self.file_list = DropListWidget(self)
        self.file_list.itemDoubleClicked.connect(self.on_item_double_clicked)
        main_layout.addWidget(self.file_list)

        # Action Layout
        action_layout = QHBoxLayout()
        self.upload_btn = QPushButton("Upload File")
        self.upload_btn.clicked.connect(self.open_file_dialog)
        action_layout.addWidget(self.upload_btn)

        self.status_label = QLabel("Ready")
        action_layout.addWidget(self.status_label)
        main_layout.addLayout(action_layout)

    def refresh_directory(self):
        """Fetch and list the contents of the current directory."""
        self.status_label.setText("Listing directory...")
        self.file_list.clear()

        worker = self._create_worker()
        worker.set_action("list_dir", self.current_path)
        worker.list_dir_done.connect(self._on_list_dir_done)
        worker.error_occurred.connect(self._on_error)
        worker.finished.connect(self._on_worker_finished)
        worker.start()

    def navigate_up(self):
        """Navigate to the parent directory."""
        self.status_label.setText("Navigating up...")
        new_path = "HOME"
        if self.current_path != "HOME":
            parent = Path(self.current_path).parent
            new_path = str(parent).replace("\\", "/")
            if new_path == ".":
                new_path = "HOME"

        worker = self._create_worker()
        worker.set_action("up_dir")
        worker.operation_done.connect(lambda result: self._on_dir_changed(new_path))
        worker.error_occurred.connect(self._on_error)
        worker.start()

    def on_item_double_clicked(self, item):
        """Handle double-clicking a directory or file in the list."""
        # We assume for navigation that clicking it enters it (as a dir).
        # We evaluate the selected folder's name to change into it.
        name = item.text()
        self.status_label.setText(f"Entering {name}...")
        new_path = f"{self.current_path}/{name}"

        worker = self._create_worker()
        worker.set_action("change_dir", new_path)
        worker.operation_done.connect(self._on_dir_changed)
        worker.error_occurred.connect(self._on_error)
        worker.start()

    def _on_dir_changed(self, new_path: str):
        """Callback to update path and refresh directory on success."""
        self.current_path = new_path
        self.refresh_directory()

    def open_file_dialog(self):
        """Open a file dialog to select a file to upload."""
        file_path, _ = QFileDialog.getOpenFileName(self, "Select File to Upload")
        if file_path:
            self.upload_file(file_path)

    def upload_file(self, file_path: str):
        """Upload a local file to the current remote directory."""
        self.status_label.setText(f"Uploading {Path(file_path).name}...")

        worker = self._create_worker()
        worker.set_action("upload_file", file_path, self.current_path)
        worker.operation_done.connect(lambda result: self.status_label.setText("Upload successful."))
        worker.operation_done.connect(lambda result: self.refresh_directory())
        worker.error_occurred.connect(self._on_error)
        worker.start()

    def upload_files(self, file_paths: list[str]):
        """Upload multiple local files to the current remote directory."""
        self.status_label.setText(f"Uploading {len(file_paths)} files...")

        worker = self._create_worker()
        worker.set_action("upload_files", file_paths, self.current_path)
        worker.operation_done.connect(lambda result: self.status_label.setText("Upload successful."))
        worker.operation_done.connect(lambda result: self.refresh_directory())
        worker.error_occurred.connect(self._on_error)
        worker.start()

    def _create_worker(self):
        """Create a new KermitWorker, keeping a reference to prevent GC."""
        worker = KermitWorker(self.port_input.text())

        if not hasattr(self, 'workers'):
            self.workers = set()

        self.workers.add(worker)
        worker.finished.connect(lambda: self.workers.discard(worker))
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(self._on_worker_finished)

        self.set_ui_enabled(False)
        return worker

    def _on_list_dir_done(self, entries):
        """Callback for when list_dir finishes."""
        self.file_list.clear()
        for entry in entries:
            QListWidgetItem(entry.name, self.file_list)
        self.path_label.setText(f"Current Path: {self.current_path}")
        self.status_label.setText("Ready")

    def _on_error(self, message: str):
        """Callback for when an error occurs in the worker."""
        QMessageBox.critical(self, "Error", message)
        self.status_label.setText("Error occurred.")

    def _on_worker_finished(self):
        """Callback for when the worker thread completes."""
        if not hasattr(self, 'workers') or not self.workers:
            self.set_ui_enabled(True)

    def set_ui_enabled(self, enabled: bool):
        """Toggle UI elements during background operations."""
        self.refresh_btn.setEnabled(enabled)
        self.up_btn.setEnabled(enabled)
        self.upload_btn.setEnabled(enabled)
        self.file_list.setEnabled(enabled)
