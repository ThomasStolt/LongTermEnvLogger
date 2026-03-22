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

def _resolve_fqbn(port_fqbn: str) -> str:
    """Return port FQBN if known, otherwise fall back to arduino_config.BOARD_FQBN."""
    return port_fqbn if port_fqbn else BOARD_FQBN


def flash_sketch(sketch_dir: Path, port: str, fqbn: str) -> None:
    """Compile and upload a sketch directory via arduino-cli.

    Aborts with a message if arduino-cli is not in PATH or compilation fails.
    """
    if not shutil.which("arduino-cli"):
        console.print(
            "[red]arduino-cli not found in PATH.[/red]\n"
            "Install it from: https://arduino.github.io/arduino-cli/\n"
            "Then install the ESP8266 core: "
            "[cyan]arduino-cli core install esp8266:esp8266[/cyan]"
        )
        sys.exit(1)

    with console.status(f"[cyan]Compiling {sketch_dir.name}...[/cyan]"):
        result = subprocess.run(
            ["arduino-cli", "compile", "--fqbn", fqbn, str(sketch_dir)],
            capture_output=True, text=True,
        )
    if result.returncode != 0:
        console.print(f"[red]Compilation failed:[/red]\n{result.stderr}")
        sys.exit(1)
    console.print("[green]Compilation successful.[/green]")

    with console.status(f"[cyan]Uploading to {port}...[/cyan]"):
        result = subprocess.run(
            ["arduino-cli", "upload", "--fqbn", fqbn, "--port", port, str(sketch_dir)],
            capture_output=True, text=True,
        )
    if result.returncode != 0:
        console.print(f"[red]Upload failed:[/red]\n{result.stderr}")
        sys.exit(1)
    console.print("[green]Upload successful.[/green]")


def read_setup_data(port: str) -> dict:
    """Open serial port, read lines until SETUP_DONE or timeout.

    Returns parsed result dict from parse_serial_output().
    Aborts on timeout with a helpful error message.
    """
    console.print(f"[cyan]Reading setup data from {port} (timeout: {SERIAL_TIMEOUT_S}s)...[/cyan]")
    lines = []
    try:
        with serial.Serial(port, BAUD_RATE, timeout=1) as ser:
            deadline = time.time() + SERIAL_TIMEOUT_S
            with console.status("[cyan]Waiting for SETUP_DONE...[/cyan]"):
                while time.time() < deadline:
                    line = ser.readline().decode("utf-8", errors="replace").strip()
                    if line:
                        lines.append(line)
                    result = parse_serial_output(lines)
                    if result["done"]:
                        return result
    except serial.SerialException as e:
        console.print(f"[red]Serial error: {e}[/red]")
        sys.exit(1)

    console.print(
        f"[red]Timeout — no SETUP_DONE received within {SERIAL_TIMEOUT_S}s.[/red]\n"
        "Troubleshooting:\n"
        "  • Verify baud rate is 115200 in arduino_config.py\n"
        "  • Ensure device booted in run mode (not flash mode)\n"
        "  • Check that the correct port was selected"
    )
    sys.exit(1)


# ── UI functions ─────────────────────────────────────────────────────────────

def _rssi_bar(rssi: int) -> str:
    """Render a 5-block signal strength bar with color."""
    strength = min(max(rssi + 100, 0), 60) / 60
    bars = max(1, int(strength * 5))
    color = ["red", "red", "yellow", "green", "green"][min(bars - 1, 4)]
    return f"[{color}]{'█' * bars}{'░' * (5 - bars)}[/{color}] {rssi} dBm"


def detect_ports() -> list:
    """Return merged list of dicts with keys: port, description, fqbn.

    Runs arduino-cli board list first (gives FQBN for known boards).
    Falls back to pyserial for unrecognised ports.
    arduino-cli entries take precedence when a port appears in both.
    """
    ports_map = {}

    # pyserial baseline
    for p in serial.tools.list_ports.comports():
        ports_map[p.device] = {"port": p.device, "description": p.description, "fqbn": None}

    # arduino-cli overlay (may provide FQBN)
    try:
        result = subprocess.run(
            ["arduino-cli", "board", "list"],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.splitlines()[1:]:  # skip header
            parts = line.split()
            if not parts:
                continue
            port = parts[0]
            fqbn = next((p for p in parts if ":" in p and p.count(":") == 2), None)
            if port in ports_map:
                ports_map[port]["fqbn"] = fqbn
            else:
                ports_map[port] = {"port": port, "description": " ".join(parts[1:3]), "fqbn": fqbn}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass  # arduino-cli not available — pyserial list is sufficient

    return sorted(ports_map.values(), key=lambda x: x["port"])


def select_port() -> dict:
    """Display available serial ports and prompt user to select one.

    Returns dict with keys: port (str), fqbn (str|None).
    Aborts if no ports found.
    """
    ports = detect_ports()
    if not ports:
        console.print("[red]No serial ports found. Connect the ESP8266 via USB-TTL and retry.[/red]")
        sys.exit(1)

    table = Table(title="Available Serial Ports", border_style="blue")
    table.add_column("#", style="bold cyan", width=4)
    table.add_column("Port", style="white")
    table.add_column("Description", style="dim")
    table.add_column("Board (FQBN)", style="green")

    for i, p in enumerate(ports, 1):
        fqbn_display = p["fqbn"] or "[dim]unknown[/dim]"
        table.add_row(str(i), p["port"], p["description"], fqbn_display)

    console.print(table)
    while True:
        choice = IntPrompt.ask("Select port number", default=1)
        if 1 <= choice <= len(ports):
            break
        console.print(f"[red]Enter a number between 1 and {len(ports)}.[/red]")
    selected = ports[choice - 1]
    console.print(f"[green]Selected:[/green] {selected['port']}")
    return selected


def select_credentials() -> tuple:
    """Display available credentials_<location>.h files and prompt user to select.

    Returns (location_name: str, file_path: Path).
    Aborts if no credentials files found.
    """
    locations = find_credentials_files(PROJECT_ROOT)
    if not locations:
        console.print(
            "[red]No credentials files found.[/red]\n"
            f"Copy [cyan]credentials.example.h[/cyan] to "
            f"[cyan]credentials_<location>.h[/cyan] in [cyan]{PROJECT_ROOT}[/cyan] "
            "and fill in your WiFi credentials."
        )
        sys.exit(1)

    table = Table(title="Available Credentials", border_style="blue")
    table.add_column("#", style="bold cyan", width=4)
    table.add_column("Location", style="white")
    table.add_column("File", style="dim")

    for i, loc in enumerate(locations, 1):
        table.add_row(str(i), loc, f"credentials_{loc}.h")

    console.print(table)
    while True:
        choice = IntPrompt.ask("Select location number", default=1)
        if 1 <= choice <= len(locations):
            break
        console.print(f"[red]Enter a number between 1 and {len(locations)}.[/red]")
    location = locations[choice - 1]
    file_path = PROJECT_ROOT / f"credentials_{location}.h"
    console.print(f"[green]Selected:[/green] {location}")
    return location, file_path


def display_setup_results(data: dict) -> None:
    """Display MAC address, DS18B20 address, and WiFi networks from setup data."""
    console.print(Panel(
        f"[bold]MAC Address:[/bold] [cyan]{data['mac']}[/cyan]",
        title="ESP8266 Hardware Info",
        border_style="green",
    ))

    if data["ds18b20_error"]:
        console.print(
            "[red]DS18B20 not found on OneWire bus.[/red] "
            "Check wiring (data wire to GPIO12, 4.7kΩ pull-up to 3.3V)."
        )
        sys.exit(1)

    console.print(f"[bold]DS18B20 address:[/bold] [cyan]{data['ds18b20']}[/cyan]")

    if data["wifi_none"]:
        console.print("[yellow]No WiFi networks found — BSSID pinning not available.[/yellow]")
        return

    table = Table(title="Nearby WiFi Networks", border_style="blue")
    table.add_column("#", style="bold cyan", width=4)
    table.add_column("SSID", style="white", min_width=20)
    table.add_column("BSSID", style="dim")
    table.add_column("Ch", style="yellow", width=4)
    table.add_column("Signal", min_width=18)

    for i, net in enumerate(data["wifi_networks"], 1):
        table.add_row(
            str(i),
            net["ssid"],
            net["bssid"],
            str(net["channel"]),
            _rssi_bar(net["rssi"]),
        )
    console.print(table)


def get_configuration(data: dict, existing_rooms: set) -> dict:
    """Prompt user for room number and optional BSSID selection.

    Returns dict with keys:
      room_number (int), bssid (str|None), channel (int|None), ssid (str|None)
    """
    bssid = None
    channel = None
    ssid = None

    if not data["wifi_none"] and data["wifi_networks"]:
        console.print("\n[bold]BSSID Pinning[/bold] (optional — saves ~200–400ms per cycle)")
        console.print("Only use this if the ESP will always connect to a single, fixed access point.")
        raw = Prompt.ask(
            "Select network # to pin BSSID, or press [bold]Enter[/bold] to skip",
            default="",
        )
        if raw.strip().isdigit():
            idx = int(raw.strip()) - 1
            if 0 <= idx < len(data["wifi_networks"]):
                net = data["wifi_networks"][idx]
                bssid = net["bssid"]
                channel = net["channel"]
                ssid = net["ssid"]
                console.print(f"[green]BSSID pinned:[/green] {bssid} (channel {channel})")
            else:
                console.print("[yellow]Invalid selection — skipping BSSID pinning.[/yellow]")
        else:
            console.print("[dim]BSSID pinning skipped.[/dim]")

    while True:
        room_number = IntPrompt.ask("\nEnter room number", default=101)
        if not (1 <= room_number <= 254):
            console.print("[red]Room number must be between 1 and 254.[/red]")
            continue
        if room_number in existing_rooms:
            console.print(f"[yellow]Room {room_number} already exists in sensors.csv.[/yellow]")
            if not Confirm.ask("Continue anyway?", default=False):
                continue
        break

    return {"room_number": room_number, "bssid": bssid, "channel": channel, "ssid": ssid}


# ── Main workflow ─────────────────────────────────────────────────────────────

def build_and_flash_production(
    config: dict,
    setup_data: dict,
    cred_path: Path,
    port: str,
    fqbn: str,
) -> None:
    """Substitute template, copy credentials, compile and upload production firmware."""
    template_content = SENSOR_SKETCH.read_text()

    ds18b20_array = format_ds18b20_c_array(setup_data["ds18b20"])
    bssid_array = format_bssid_c_array(config["bssid"]) if config["bssid"] else None

    final_content = substitute_template(
        template_content,
        room_number=config["room_number"],
        ds18b20_array=ds18b20_array,
        bssid_array=bssid_array,
        channel=config["channel"],
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        sketch_dir = Path(tmpdir) / "LTL_sensor"
        sketch_dir.mkdir()
        (sketch_dir / "LTL_sensor.ino").write_text(final_content)
        shutil.copy(cred_path, sketch_dir / "credentials.h")

        console.print(Panel(
            f"Room:     [cyan]{config['room_number']}[/cyan]\n"
            f"DS18B20:  [cyan]{ds18b20_array}[/cyan]\n"
            f"BSSID:    [cyan]{config['bssid'] or 'not pinned'}[/cyan]\n"
            f"Channel:  [cyan]{config['channel'] or '—'}[/cyan]\n"
            f"Location: [cyan]{cred_path.stem.replace('credentials_', '')}[/cyan]",
            title="Production Firmware Configuration",
            border_style="green",
        ))

        flash_sketch(sketch_dir, port, fqbn)

    console.print(Panel(
        f"[bold green]Sensor {config['room_number']} programmed successfully![/bold green]",
        border_style="green",
    ))


def main():
    console.print(Panel.fit(
        "[bold cyan]LTL Sensor Programmer[/bold cyan]\n"
        "Two-step ESP8266 flash tool",
        border_style="cyan",
    ))

    # Step 1 — Hardware selection
    port_info = select_port()
    fqbn = _resolve_fqbn(port_info["fqbn"])
    port = port_info["port"]

    # Step 2 — Credentials selection
    location, cred_path = select_credentials()

    # Step 3 — Flash setup sketch
    console.rule("[bold]Step 1/2 — Setup Sketch[/bold]")
    flash_sketch(SETUP_SKETCH_DIR, port, fqbn)

    # Step 4 — Read setup data (wait for ESP8266 to boot)
    time.sleep(BOOT_DELAY_S)
    setup_data = read_setup_data(port)

    # Step 5 — Display results and configure
    console.rule("[bold]Configuration[/bold]")
    display_setup_results(setup_data)
    existing_rooms = load_csv_rooms(CSV_PATH)
    config = get_configuration(setup_data, existing_rooms)

    # Step 6 — Build and flash production firmware
    console.rule("[bold]Step 2/2 — Production Firmware[/bold]")
    build_and_flash_production(config, setup_data, cred_path, port, fqbn)

    # Step 7 — Update CSV
    row = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "room_number": str(config["room_number"]),
        "mac_address": setup_data["mac"] or "",
        "ds18b20_address": setup_data["ds18b20"] or "",
        "location": location,
        "ssid": config["ssid"] or "",
        "bssid": config["bssid"] or "",
        "channel": str(config["channel"]) if config["channel"] else "",
    }
    append_csv_row(CSV_PATH, row)
    console.print(f"[green]Sensor registry updated:[/green] {CSV_PATH}")

    console.print(Panel(
        f"[bold green]Done![/bold green]\n"
        f"Room [cyan]{config['room_number']}[/cyan] is ready to deploy.",
        border_style="green",
    ))


if __name__ == "__main__":
    main()
