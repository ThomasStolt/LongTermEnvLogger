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

def parse_serial_output(lines: list) -> dict:
    """Parse lines from LTL_setup sketch serial output.

    Returns dict with keys:
      mac (str|None), ds18b20 (str|None), ds18b20_error (bool),
      wifi_networks (list[dict]), wifi_none (bool), done (bool)
    Each wifi_networks entry: {ssid, bssid, channel (int), rssi (int)}
    """
    result = {
        "mac": None,
        "ds18b20": None,
        "ds18b20_error": False,
        "wifi_networks": [],
        "wifi_none": False,
        "done": False,
    }
    for line in lines:
        line = line.strip()
        if line.startswith("MAC:"):
            result["mac"] = line[4:]
        elif line == "DS18B20:NOT_FOUND":
            result["ds18b20_error"] = True
        elif line.startswith("DS18B20:"):
            result["ds18b20"] = line[8:]
        elif line == "WIFI:NONE":
            result["wifi_none"] = True
        elif line.startswith("WIFI:"):
            parts = line[5:].split("|", 3)  # maxsplit=3 handles SSIDs containing '|'
            if len(parts) == 4:
                result["wifi_networks"].append({
                    "ssid": parts[0],
                    "bssid": parts[1],
                    "channel": int(parts[2]),
                    "rssi": int(parts[3]),
                })
        elif line == "SETUP_DONE":
            result["done"] = True
    return result


def format_ds18b20_c_array(raw: str) -> str:
    """Convert DS18B20 serial format to C array literal.

    '0x28,0xFF,0xA1,0xB2,0xC3,0xD4,0xE5,0x06' -> '{ 0x28, 0xFF, ... }'
    Raises ValueError if the address does not contain exactly 8 bytes.
    """
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 8:
        raise ValueError(f"DS18B20 address must be 8 bytes, got {len(parts)}: {raw!r}")
    return "{ " + ", ".join(parts) + " }"


def format_bssid_c_array(bssid: str) -> str:
    """Convert BSSID string to C array literal.

    'AA:BB:CC:DD:EE:FF' -> '{ 0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF }'
    """
    parts = [f"0x{b.upper()}" for b in bssid.split(":")]
    return "{ " + ", ".join(parts) + " }"


def substitute_template(
    content: str,
    room_number: int,
    ds18b20_array: str,
    bssid_array: str = None,
    channel: int = None,
) -> str:
    """Apply placeholder substitutions to LTL_sensor.ino content.

    Placeholders use /*TOKEN*/default_value format so the template compiles
    standalone. Substitution preserves the placeholder comment for readability.
    """
    content = re.sub(
        r"/\*ROOM_NUMBER\*/\d+",
        f"/*ROOM_NUMBER*/{room_number}",
        content,
    )
    content = re.sub(
        r"/\*DS18B20_ADDR\*/\{[^}]+\}",
        f"/*DS18B20_ADDR*/{ds18b20_array}",
        content,
    )
    if bssid_array is not None and channel is not None:
        content = content.replace("// #define USE_BSSID", "#define USE_BSSID")
        content = re.sub(
            r"/\*BSSID\*/\{[^}]+\}",
            f"/*BSSID*/{bssid_array}",
            content,
        )
        content = re.sub(
            r"/\*WIFI_CHANNEL\*/\d+",
            f"/*WIFI_CHANNEL*/{channel}",
            content,
        )
    return content


def find_credentials_files(project_root: Path) -> list:
    """Return sorted list of location names from credentials_<location>.h files.

    Excludes credentials.example.h.
    Example: ['Home', 'School'] for credentials_Home.h, credentials_School.h
    """
    return sorted(
        f.stem.replace("credentials_", "")
        for f in project_root.glob("credentials_*.h")
        if f.stem != "credentials_example"
    )


def load_csv_rooms(csv_path: Path) -> set:
    """Return set of room numbers (int) already recorded in sensors.csv."""
    if not csv_path.exists():
        return set()
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        return {int(row["room_number"]) for row in reader if row.get("room_number")}


def append_csv_row(csv_path: Path, row: dict) -> None:
    """Append a row to sensors.csv, creating with header if the file is new."""
    write_header = not csv_path.exists()
    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


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
