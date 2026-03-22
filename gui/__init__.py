"""Main entry point for the GUI application."""

import sys
from PyQt6.QtWidgets import QApplication

from gui.main_window import MainWindow

def run_gui():
    """Launch the PyQt main loop."""
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    run_gui()
