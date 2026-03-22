"""test/mkdir.py — smoke-test: create a directory on the HP 50g via Kermit REMOTE HOST."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from conn.transport import SerialTransport
from conn.session import KermitSession
from utils.exceptions import HPConnError, SessionError, TransportError

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

def main():
    # Configure logging to see the packet exchange
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(levelname)s: %(message)s'
    )

    # --- CONFIGURATION ---
    # Update PORT to match your connection (e.g., "COM3" on Windows or "/dev/ttyUSB0" on Linux)
    PORT = "/dev/ttyUSB0" 
    BAUDRATE = 115200  # Default HP 50g baudrate
    NEW_DIR_NAME = "MYTESTDIR"
    # ---------------------

    transport = SerialTransport(port=PORT, baudrate=BAUDRATE)
    session = KermitSession(transport)

    try:
        print(f"Opening port {PORT}...")
        transport.open()
        
        # 1. Initialize the Kermit session (Negotiation)
        print("Negotiating session parameters...")
        session.send_init()

        # 2. Send the RPL command to create a directory
        # The HP 50g expects the command to be valid RPL.
        # Syntax: 'NAME' CRDIR
        print(f"Creating directory '{NEW_DIR_NAME}' on the calculator...")
        rpl_command = f"'{NEW_DIR_NAME}' CRDIR"
        
        # Using the existing host command functionality
        session.send_host_command(rpl_command)
        
        print(f"Successfully sent command to create '{NEW_DIR_NAME}'.")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        transport.close()
        print("Connection closed.")

if __name__ == "__main__":
    main()
