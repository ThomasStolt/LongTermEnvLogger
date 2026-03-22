#!/usr/bin/env python3
"""LTL Sensor Programmer — interactive two-step ESP8266 flash tool.

Workflow:
  1. Select serial port
  2. Select WiFi credentials location
  3. Flash LTL_setup sketch → read MAC, DS18B20 address, WiFi networks
  4. Configure room number and optional BSSID pinning
  5. Flash production firmware with values baked in
  6. Record to sensors.csv
"""

import csv
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import serial
import serial.tools.list_ports
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

sys.path.insert(0, str(Path(__file__).parent))
from arduino_config import BAUD_RATE, BOARD_FQBN, BOOT_DELAY_S, SERIAL_TIMEOUT_S

console = Console()

# ── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
SETUP_SKETCH_DIR = PROJECT_ROOT / "code" / "LTL_setup"
SENSOR_SKETCH = PROJECT_ROOT / "code" / "LTL_sensor" / "LTL_sensor.ino"
CSV_PATH = Path(__file__).parent / "sensors.csv"
CSV_FIELDNAMES = [
    "timestamp", "room_number", "mac_address", "ds18b20_address",
    "location", "ssid", "bssid", "channel",
]


# ── Pure utility functions (unit-tested in tests/test_utils.py) ──────────────


# ── arduino-cli functions ────────────────────────────────────────────────────


# ── UI functions ─────────────────────────────────────────────────────────────


# ── Main workflow ─────────────────────────────────────────────────────────────

def main():
    console.print(Panel.fit(
        "[bold cyan]LTL Sensor Programmer[/bold cyan]\n"
        "Two-step ESP8266 flash tool",
        border_style="cyan",
    ))
    console.print("[yellow]Not yet implemented — run after completing all tasks.[/yellow]")


if __name__ == "__main__":
    main()
