#!/usr/bin/env python3
"""LTL Sensor Programmer — TUI-based two-step ESP8266 flash tool."""

import csv
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

import serial
import serial.tools.list_ports
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button, DataTable, Footer, Header, Input, Label, ProgressBar, RichLog, Select, Static,
)
from textual.widget import Widget

sys.path.insert(0, str(Path(__file__).parent))
from arduino_config import BAUD_RATE, BOARD_FQBN, BOOT_DELAY_S, SERIAL_TIMEOUT_S

# ── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
SETUP_SKETCH_DIR = PROJECT_ROOT / "code" / "LTL_setup"
SENSOR_SKETCH = PROJECT_ROOT / "code" / "LTL_sensor" / "LTL_sensor.ino"
CSV_FIELDNAMES = [
    "timestamp", "room_number", "mac_address", "ds18b20_address",
    "location", "ssid", "bssid", "channel",
]


# ── Pure utility functions (unit-tested in tests/test_utils.py) ───────────────

def parse_serial_output(lines: list) -> dict:
    """Parse lines from LTL_setup sketch serial output."""
    result = {
        "mac": None,
        "ds18b20": None,
        "ds18b20_error": False,
        "wifi_networks": [],
        "wifi_none": False,
        "wifi_ok": False,
        "wifi_fail": False,
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
            parts = line[5:].split("|", 3)
            if len(parts) == 4:
                result["wifi_networks"].append({
                    "ssid": parts[0],
                    "bssid": parts[1],
                    "channel": int(parts[2]),
                    "rssi": int(parts[3]),
                })
        elif line == "WIFI_OK":
            result["wifi_ok"] = True
        elif line == "WIFI_FAIL":
            result["wifi_fail"] = True
        elif line == "SETUP_DONE":
            result["done"] = True
    return result


def format_ds18b20_c_array(raw: str) -> str:
    """Convert DS18B20 serial format to C array literal."""
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 8:
        raise ValueError(f"DS18B20 address must be 8 bytes, got {len(parts)}: {raw!r}")
    return "{ " + ", ".join(parts) + " }"


def format_bssid_c_array(bssid: str) -> str:
    """Convert BSSID string (AA:BB:CC:DD:EE:FF) to C array literal."""
    parts = [p.strip() for p in bssid.split(":")]
    if len(parts) != 6:
        raise ValueError(f"BSSID must be 6 bytes, got {len(parts)}: {bssid!r}")
    return "{ " + ", ".join(f"0x{p.upper()}" for p in parts) + " }"


def substitute_template(
    content: str,
    room_number: int,
    ds18b20_array: str,
    bssid_array: str = None,
    channel: int = None,
) -> str:
    """Apply placeholder substitutions to LTL_sensor.ino content."""
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
    """Return sorted list of location names from credentials_<location>.h files."""
    return sorted(
        f.stem.replace("credentials_", "")
        for f in project_root.glob("credentials_*.h")
        if f.stem != "credentials_example"
    )


def read_ssid_from_credentials(cred_path: Path) -> str | None:
    """Extract SSID value from a credentials_*.h file."""
    try:
        content = cred_path.read_text()
        m = re.search(r'const\s+char\s*\*\s*ssid\s*=\s*"([^"]*)"', content)
        return m.group(1) if m else None
    except OSError:
        return None


def read_network_from_credentials(cred_path: Path) -> dict | None:
    """Parse network config from a credentials_*.h file.

    Returns a dict with keys: net_prefix (str), net_mask (int),
    mqtt_server (str), mqtt_port (int), gateway (str), dns_server (str).
    gateway and dns_server fall back to net_a.net_b.net_c.1 if not present.
    Returns None if any required field is missing or the file is unreadable.
    """
    try:
        content = cred_path.read_text()
    except OSError:
        return None
    octets = re.findall(r'const\s+uint8_t\s+net_([abc])\s*=\s*(\d+)', content)
    octet_map = {k: int(v) for k, v in octets}
    if not all(k in octet_map for k in ("a", "b", "c")):
        return None
    m_mask = re.search(r'const\s+uint8_t\s+net_mask\s*=\s*(\d+)', content)
    m_server = re.search(r'const\s+char\s*\*\s*mqtt_server\s*=\s*"([^"]*)"', content)
    m_port = re.search(r'const\s+int\s+mqtt_port\s*=\s*(\d+)', content)
    if not all([m_mask, m_server, m_port]):
        return None

    def _parse_ip(prefix: str) -> str | None:
        """Parse gw_a/b/c/d or dns_a/b/c/d into a dotted IP string."""
        parts = re.findall(rf'const\s+uint8_t\s+{prefix}_([abcd])\s*=\s*(\d+)', content)
        m = {k: int(v) for k, v in parts}
        if all(k in m for k in ("a", "b", "c", "d")):
            return f"{m['a']}.{m['b']}.{m['c']}.{m['d']}"
        return None

    fallback = f"{octet_map['a']}.{octet_map['b']}.{octet_map['c']}.1"
    return {
        "net_prefix": f"{octet_map['a']}.{octet_map['b']}.{octet_map['c']}",
        "net_mask": int(m_mask.group(1)),
        "mqtt_server": m_server.group(1),
        "mqtt_port": int(m_port.group(1)),
        "gateway": _parse_ip("gw") or fallback,
        "dns_server": _parse_ip("dns") or fallback,
    }


def write_network_to_credentials(cred_path: Path, updates: dict) -> None:
    """Write network config back to a credentials_*.h file.

    updates keys: net_prefix (str "a.b.c"), net_mask (int),
    gateway (str "a.b.c.d"), dns_server (str "a.b.c.d"),
    mqtt_server (str), mqtt_port (int).
    Only the network constants are modified; ssid/password are left untouched.
    """
    content = cred_path.read_text()

    def _set_uint8(name: str, value: int) -> None:
        nonlocal content
        content = re.sub(
            rf'(const\s+uint8_t\s+{name}\s*=\s*)\d+',
            rf'\g<1>{value}',
            content,
        )

    def _set_int(name: str, value: int) -> None:
        nonlocal content
        content = re.sub(
            rf'(const\s+int\s+{name}\s*=\s*)\d+',
            rf'\g<1>{value}',
            content,
        )

    def _set_str(name: str, value: str) -> None:
        nonlocal content
        content = re.sub(
            rf'(const\s+char\s*\*\s*{name}\s*=\s*")[^"]*(")',
            rf'\g<1>{value}\g<2>',
            content,
        )

    net = [int(x) for x in updates["net_prefix"].split(".")]
    gw  = [int(x) for x in updates["gateway"].split(".")]
    dns = [int(x) for x in updates["dns_server"].split(".")]

    _set_uint8("net_a", net[0]); _set_uint8("net_b", net[1]); _set_uint8("net_c", net[2])
    _set_uint8("net_mask", updates["net_mask"])
    _set_uint8("gw_a",  gw[0]);  _set_uint8("gw_b",  gw[1])
    _set_uint8("gw_c",  gw[2]);  _set_uint8("gw_d",  gw[3])
    _set_uint8("dns_a", dns[0]); _set_uint8("dns_b", dns[1])
    _set_uint8("dns_c", dns[2]); _set_uint8("dns_d", dns[3])
    _set_str("mqtt_server", updates["mqtt_server"])
    _set_int("mqtt_port", updates["mqtt_port"])

    cred_path.write_text(content)


def write_credentials_file(cred_path: Path, fields: dict) -> None:
    """Create a credentials_*.h file from scratch.

    fields keys: location (str), ssid (str), password (str),
    net_prefix (str "a.b.c"), net_mask (int),
    gateway (str "a.b.c.d"), dns_server (str "a.b.c.d"),
    mqtt_server (str), mqtt_port (int).
    """
    net = [int(x) for x in fields["net_prefix"].split(".")]
    gw  = [int(x) for x in fields["gateway"].split(".")]
    dns = [int(x) for x in fields["dns_server"].split(".")]
    content = (
        f"// credentials_{fields['location']}.h — created by ltl_programmer\n"
        "// credentials_*.h files are gitignored — never commit real credentials.\n"
        "#include <stdint.h>\n"
        f'const char*    ssid        = "{fields["ssid"]}";\n'
        f'const char*    password    = "{fields["password"]}";\n'
        "\n"
        "// Netzwerk-Präfix (erste 3 Oktette der statischen Sensor-IP)\n"
        f"const uint8_t  net_a       = {net[0]};\n"
        f"const uint8_t  net_b       = {net[1]};\n"
        f"const uint8_t  net_c       = {net[2]};\n"
        "\n"
        "// Subnetzmaske als CIDR-Präfixlänge (1–30)\n"
        f"const uint8_t  net_mask    = {fields['net_mask']};\n"
        "\n"
        "// Gateway-IP\n"
        f"const uint8_t  gw_a        = {gw[0]};\n"
        f"const uint8_t  gw_b        = {gw[1]};\n"
        f"const uint8_t  gw_c        = {gw[2]};\n"
        f"const uint8_t  gw_d        = {gw[3]};\n"
        "\n"
        "// DNS-Server-IP\n"
        f"const uint8_t  dns_a       = {dns[0]};\n"
        f"const uint8_t  dns_b       = {dns[1]};\n"
        f"const uint8_t  dns_c       = {dns[2]};\n"
        f"const uint8_t  dns_d       = {dns[3]};\n"
        "\n"
        "// MQTT-Broker\n"
        f'const char*    mqtt_server = "{fields["mqtt_server"]}";\n'
        f"const int      mqtt_port   = {fields['mqtt_port']};\n"
    )
    cred_path.write_text(content)


def load_csv_rooms(csv_path: Path) -> set:
    """Return set of room numbers (int) already recorded in sensors.csv."""
    if not csv_path.exists():
        return set()
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        return {int(row["room_number"]) for row in reader if row.get("room_number")}


def append_csv_row(csv_path: Path, row: dict) -> None:
    """Append a row to sensors.csv, writing the header if the file is new."""
    write_header = not csv_path.exists()
    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def upsert_csv_row(csv_path: Path, row: dict) -> None:
    """Insert or update a row in sensors.csv, keyed by room_number (numeric match)."""
    rows = []
    if csv_path.exists():
        with open(csv_path, newline="") as f:
            rows = list(csv.DictReader(f))
    try:
        key = int(row["room_number"])
    except (KeyError, ValueError):
        key = None
    updated = False
    for i, r in enumerate(rows):
        try:
            if int(r.get("room_number", "")) == key:
                rows[i] = row
                updated = True
                break
        except ValueError:
            pass
    if not updated:
        rows.append(row)
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def delete_csv_row(csv_path: Path, room_number: int) -> None:
    """Remove the row with the given room_number from sensors.csv."""
    if not csv_path.exists():
        return
    with open(csv_path, newline="") as f:
        rows = list(csv.DictReader(f))
    rows = [r for r in rows if _room_int(r.get("room_number", "")) != room_number]
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _room_int(value: str) -> int | None:
    """Parse a room_number string to int, returning None on failure."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def detect_ports() -> list:
    """Return merged list of dicts with keys: port, description, fqbn."""
    ports_map = {}
    for p in serial.tools.list_ports.comports():
        ports_map[p.device] = {"port": p.device, "description": p.description, "fqbn": None}
    try:
        result = subprocess.run(
            ["arduino-cli", "board", "list"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines()[1:]:
            parts = line.split()
            if not parts or (len(parts) > 1 and parts[1] == "network"):
                continue
            port = parts[0]
            fqbn = next((p for p in parts if ":" in p and p.count(":") == 2), None)
            if port in ports_map:
                ports_map[port]["fqbn"] = fqbn
            else:
                ports_map[port] = {"port": port, "description": " ".join(parts[1:3]), "fqbn": fqbn}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return sorted(ports_map.values(), key=lambda x: x["port"])



# ── GPIO instruction strings ───────────────────────────────────────────────────

_FLASH_INSTRUCTIONS = (
    "To bring the ESP8266 into Flash mode:\n\n"
    "  1.  Press and hold  [bold]RST[/bold]\n"
    "  2.  Press and hold  [bold]FLASH[/bold]\n"
    "  3.  Release  [bold]RST[/bold]\n"
    "  4.  Release  [bold]FLASH[/bold]"
)
_FLASH_AND_RUN_INSTRUCTIONS = (
    "  1.  Press and hold  [bold]RST[/bold]\n"
    "  2.  Press and hold  [bold]FLASH[/bold]\n"
    "  3.  Release  [bold]RST[/bold]\n"
    "  4.  Release  [bold]FLASH[/bold]\n\n"
    "[dim]Setup sketch will upload automatically.[/dim]\n\n"
    "  5.  Press  [bold]RST[/bold]  to reboot\n\n"
    "[dim]Data will be read automatically.[/dim]"
)
_RUN_AFTER_PRODUCTION = (
    "1.  Disconnect the  [bold]FTDI adapter[/bold]\n"
    "2.  Remove the  [bold]FLASH jumper[/bold]\n"
    "3.  Press  [bold]RST[/bold]\n\n"
    "The sensor is now ready to deploy."
)



class RoomInputModal(ModalScreen):
    CSS = """
    RoomInputModal { align: center middle; }
    #room-box {
        background: #181825;
        border: solid #cba6f7;
        padding: 2 4;
        width: 54;
        height: auto;
    }
    #room-title {
        text-style: bold;
        color: #cba6f7;
        margin-bottom: 1;
        text-align: center;
    }
    #room-input {
        margin-bottom: 1;
        background: #313244;
        border: tall #45475a;
        color: #cdd6f4;
    }
    #room-input:focus { border: tall #cba6f7; }
    #room-error { color: #f38ba8; height: 1; margin-bottom: 1; }
    #room-warning {
        color: #f9e2af;
        border: solid #f9e2af;
        padding: 1 2;
        margin-bottom: 1;
        display: none;
    }
    #room-confirm-buttons { height: 3; display: none; }
    #room-confirm-buttons Button { margin-right: 1; }
    #room-ok { width: 100%; background: #cba6f7; color: #1e1e2e; text-style: bold; border: none; }
    #room-ok:hover { background: #b4befe; }
    #room-overwrite { background: #f38ba8; color: #1e1e2e; text-style: bold; border: none; }
    #room-overwrite:hover { background: #eba0ac; }
    #room-cancel { background: #313244; color: #a6adc8; border: none; }
    #room-cancel:hover { background: #45475a; }
    """

    def __init__(self, existing_rooms: set):
        super().__init__()
        self._existing_rooms = set(existing_rooms)
        self._pending_room: int | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="room-box"):
            yield Label("Enter Room Number (1–254)", id="room-title")
            yield Input(value="101", id="room-input", type="integer")
            yield Label("", id="room-error")
            yield Static("", id="room-warning")
            with Horizontal(id="room-confirm-buttons"):
                yield Button("Overwrite", variant="error", id="room-overwrite")
                yield Button("Cancel", id="room-cancel")
            yield Button("OK", variant="primary", id="room-ok")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "room-ok":
            self._try_submit()
        elif event.button.id == "room-overwrite":
            self.dismiss(self._pending_room)
        elif event.button.id == "room-cancel":
            self._reset_warning()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if self._pending_room is not None:
            self.dismiss(self._pending_room)
        else:
            self._try_submit()

    def _try_submit(self) -> None:
        error = self.query_one("#room-error", Label)
        try:
            room = int(self.query_one("#room-input", Input).value)
        except ValueError:
            error.update("Enter a valid number.")
            return
        if not (1 <= room <= 254):
            error.update("Must be between 1 and 254.")
            return
        if room in self._existing_rooms:
            self._pending_room = room
            self.query_one("#room-warning", Static).update(
                f"⚠  Room {room} already exists in sensors.csv.\nOverwrite the existing entry?"
            )
            self.query_one("#room-warning").display = True
            self.query_one("#room-confirm-buttons").display = True
            self.query_one("#room-ok").display = False
            return
        self.dismiss(room)

    def _reset_warning(self) -> None:
        self._pending_room = None
        self.query_one("#room-warning").display = False
        self.query_one("#room-confirm-buttons").display = False
        self.query_one("#room-ok").display = True


# ── Network config edit modal ─────────────────────────────────────────────────

class NetworkConfigModal(ModalScreen):
    CSS = """
    NetworkConfigModal { align: center middle; }
    #nc-box {
        background: #181825;
        border: solid #74c7ec;
        padding: 2 4;
        width: 60;
        height: auto;
    }
    #nc-title {
        text-style: bold;
        color: #74c7ec;
        margin-bottom: 1;
        text-align: center;
    }
    .nc-label { color: #a6adc8; height: 1; margin-top: 1; }
    .nc-input {
        background: #313244;
        border: tall #45475a;
        color: #cdd6f4;
        margin-bottom: 0;
    }
    .nc-input:focus { border: tall #74c7ec; }
    #nc-error { color: #f38ba8; height: 1; margin-top: 1; }
    #nc-save {
        width: 100%;
        margin-top: 1;
        background: #74c7ec;
        color: #1e1e2e;
        text-style: bold;
        border: none;
    }
    #nc-save:hover { background: #89dceb; }
    #nc-cancel {
        width: 100%;
        margin-top: 1;
        background: #313244;
        color: #a6adc8;
        border: none;
    }
    #nc-cancel:hover { background: #45475a; }
    """

    def __init__(self, net: dict):
        super().__init__()
        self._net = net

    def compose(self) -> ComposeResult:
        with Vertical(id="nc-box"):
            yield Label("Netzwerkkonfiguration bearbeiten", id="nc-title")
            yield Label("Netz-Präfix  (z.B. 192.168.2)", classes="nc-label")
            yield Input(value=self._net["net_prefix"], id="nc-net-prefix", classes="nc-input")
            yield Label("Subnetz-Maske  (CIDR, z.B. 24)", classes="nc-label")
            yield Input(value=str(self._net["net_mask"]), id="nc-net-mask", classes="nc-input", type="integer")
            yield Label("Gateway  (z.B. 192.168.2.1)", classes="nc-label")
            yield Input(value=self._net["gateway"], id="nc-gateway", classes="nc-input")
            yield Label("DNS-Server  (z.B. 8.8.8.8)", classes="nc-label")
            yield Input(value=self._net["dns_server"], id="nc-dns", classes="nc-input")
            yield Label("MQTT-Server  (IP-Adresse)", classes="nc-label")
            yield Input(value=self._net["mqtt_server"], id="nc-mqtt-server", classes="nc-input")
            yield Label("MQTT-Port", classes="nc-label")
            yield Input(value=str(self._net["mqtt_port"]), id="nc-mqtt-port", classes="nc-input", type="integer")
            yield Label("", id="nc-error")
            yield Button("Speichern", id="nc-save")
            yield Button("Abbrechen", id="nc-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "nc-save":
            self._try_save()
        elif event.button.id == "nc-cancel":
            self.dismiss(None)

    def on_input_submitted(self, _: Input.Submitted) -> None:
        self._try_save()

    def _try_save(self) -> None:
        error = self.query_one("#nc-error", Label)

        def _get(id_: str) -> str:
            return self.query_one(f"#{id_}", Input).value.strip()

        def _valid_ip4(s: str) -> bool:
            parts = s.split(".")
            if len(parts) != 4:
                return False
            return all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)

        def _valid_ip3(s: str) -> bool:
            parts = s.split(".")
            if len(parts) != 3:
                return False
            return all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)

        net_prefix  = _get("nc-net-prefix")
        net_mask    = _get("nc-net-mask")
        gateway     = _get("nc-gateway")
        dns_server  = _get("nc-dns")
        mqtt_server = _get("nc-mqtt-server")
        mqtt_port   = _get("nc-mqtt-port")

        if not _valid_ip3(net_prefix):
            error.update("Netz-Präfix ungültig (z.B. 192.168.2)")
            return
        if not net_mask.isdigit() or not (1 <= int(net_mask) <= 30):
            error.update("Subnetz-Maske muss 1–30 sein")
            return
        if not _valid_ip4(gateway):
            error.update("Gateway-IP ungültig (z.B. 192.168.2.1)")
            return
        if not _valid_ip4(dns_server):
            error.update("DNS-IP ungültig (z.B. 8.8.8.8)")
            return
        if not mqtt_server:
            error.update("MQTT-Server darf nicht leer sein")
            return
        if not mqtt_port.isdigit() or not (1 <= int(mqtt_port) <= 65535):
            error.update("MQTT-Port muss 1–65535 sein")
            return

        self.dismiss({
            "net_prefix":   net_prefix,
            "net_mask":     int(net_mask),
            "gateway":      gateway,
            "dns_server":   dns_server,
            "mqtt_server":  mqtt_server,
            "mqtt_port":    int(mqtt_port),
        })


# ── New credentials modal ────────────────────────────────────────────────────

class NewCredentialsModal(ModalScreen):
    CSS = """
    NewCredentialsModal { align: center middle; }
    #ncf-box {
        background: #181825;
        border: solid #74c7ec;
        padding: 2 4;
        width: 62;
        height: auto;
    }
    #ncf-title {
        text-style: bold;
        color: #74c7ec;
        margin-bottom: 1;
        text-align: center;
    }
    .ncf-label { color: #a6adc8; height: 1; margin-top: 1; }
    .ncf-input {
        background: #313244;
        border: tall #45475a;
        color: #cdd6f4;
    }
    .ncf-input:focus { border: tall #74c7ec; }
    #ncf-pw-row { height: 3; }
    #ncf-password { width: 1fr; }
    #ncf-reveal {
        width: 14;
        margin-left: 1;
        background: #45475a;
        color: #cdd6f4;
        border: none;
        min-width: 14;
    }
    #ncf-reveal:hover { background: #585b70; }
    #ncf-error { color: #f38ba8; height: 1; margin-top: 1; }
    #ncf-save {
        width: 100%;
        margin-top: 1;
        background: #74c7ec;
        color: #1e1e2e;
        text-style: bold;
        border: none;
    }
    #ncf-save:hover { background: #89dceb; }
    #ncf-cancel {
        width: 100%;
        margin-top: 1;
        background: #313244;
        color: #a6adc8;
        border: none;
    }
    #ncf-cancel:hover { background: #45475a; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="ncf-box"):
            yield Label("Neue Netzwerkkonfiguration", id="ncf-title")
            yield Label("Standort-Name  (z.B. Home, School)", classes="ncf-label")
            yield Input(id="ncf-location", classes="ncf-input")
            yield Label("WLAN SSID", classes="ncf-label")
            yield Input(id="ncf-ssid", classes="ncf-input", password=True)
            yield Label("WLAN Passwort", classes="ncf-label")
            with Horizontal(id="ncf-pw-row"):
                yield Input(id="ncf-password", classes="ncf-input", password=True)
                yield Button("[R] Anzeigen", id="ncf-reveal")
            yield Label("Netz-Präfix  (z.B. 192.168.2)", classes="ncf-label")
            yield Input(id="ncf-net-prefix", classes="ncf-input")
            yield Label("Subnetz-Maske  (CIDR, z.B. 24)", classes="ncf-label")
            yield Input(value="24", id="ncf-net-mask", classes="ncf-input", type="integer")
            yield Label("Gateway  (z.B. 192.168.2.1)", classes="ncf-label")
            yield Input(id="ncf-gateway", classes="ncf-input")
            yield Label("DNS-Server  (z.B. 8.8.8.8)", classes="ncf-label")
            yield Input(id="ncf-dns", classes="ncf-input")
            yield Label("MQTT-Server  (IP-Adresse)", classes="ncf-label")
            yield Input(id="ncf-mqtt-server", classes="ncf-input")
            yield Label("MQTT-Port", classes="ncf-label")
            yield Input(value="1883", id="ncf-mqtt-port", classes="ncf-input", type="integer")
            yield Label("", id="ncf-error")
            yield Button("Speichern", id="ncf-save")
            yield Button("Abbrechen", id="ncf-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ncf-reveal":
            pw = self.query_one("#ncf-password", Input)
            ssid = self.query_one("#ncf-ssid", Input)
            revealing = pw.password  # currently masked → about to reveal
            pw.password = not revealing
            ssid.password = not revealing
            event.button.label = "[R] Verstecken" if revealing else "[R] Anzeigen"
        elif event.button.id == "ncf-save":
            self._try_save()
        elif event.button.id == "ncf-cancel":
            self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)

    def _try_save(self) -> None:
        error = self.query_one("#ncf-error", Label)

        def _get(id_: str) -> str:
            return self.query_one(f"#{id_}", Input).value.strip()

        def _valid_ip4(s: str) -> bool:
            parts = s.split(".")
            return len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)

        def _valid_ip3(s: str) -> bool:
            parts = s.split(".")
            return len(parts) == 3 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)

        location    = _get("ncf-location")
        ssid        = _get("ncf-ssid")
        password    = _get("ncf-password")
        net_prefix  = _get("ncf-net-prefix")
        net_mask    = _get("ncf-net-mask")
        gateway     = _get("ncf-gateway")
        dns_server  = _get("ncf-dns")
        mqtt_server = _get("ncf-mqtt-server")
        mqtt_port   = _get("ncf-mqtt-port")

        if not location or not location.replace("_", "").replace("-", "").isalnum():
            error.update("Standort-Name darf nur Buchstaben, Zahlen, - und _ enthalten.")
            return
        if not ssid:
            error.update("SSID darf nicht leer sein.")
            return
        if not _valid_ip3(net_prefix):
            error.update("Netz-Präfix ungültig  (z.B. 192.168.2)")
            return
        if not net_mask.isdigit() or not (1 <= int(net_mask) <= 30):
            error.update("Subnetz-Maske muss 1–30 sein.")
            return
        if not _valid_ip4(gateway):
            error.update("Gateway-IP ungültig  (z.B. 192.168.2.1)")
            return
        if not _valid_ip4(dns_server):
            error.update("DNS-IP ungültig  (z.B. 8.8.8.8)")
            return
        if not mqtt_server:
            error.update("MQTT-Server darf nicht leer sein.")
            return
        if not mqtt_port.isdigit() or not (1 <= int(mqtt_port) <= 65535):
            error.update("MQTT-Port muss 1–65535 sein.")
            return

        self.dismiss({
            "location":    location,
            "ssid":        ssid,
            "password":    password,
            "net_prefix":  net_prefix,
            "net_mask":    int(net_mask),
            "gateway":     gateway,
            "dns_server":  dns_server,
            "mqtt_server": mqtt_server,
            "mqtt_port":   int(mqtt_port),
        })


# ── Confirm modal ─────────────────────────────────────────────────────────────

class ConfirmModal(ModalScreen):
    CSS = """
    ConfirmModal { align: center middle; }
    #confirm-box {
        background: #181825;
        border: solid #f38ba8;
        padding: 2 4;
        width: 54;
        height: auto;
    }
    #confirm-msg {
        color: #cdd6f4;
        margin-bottom: 2;
        text-align: center;
    }
    #confirm-yes {
        width: 1fr;
        background: #f38ba8;
        color: #1e1e2e;
        text-style: bold;
        border: none;
    }
    #confirm-yes:hover { background: #eba0ac; }
    #confirm-no {
        width: 1fr;
        margin-left: 1;
        background: #313244;
        color: #a6adc8;
        border: none;
    }
    #confirm-no:hover { background: #45475a; }
    """

    def __init__(self, message: str):
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box"):
            yield Label(self._message, id="confirm-msg")
            with Horizontal():
                yield Button("Ja, löschen", id="confirm-yes")
                yield Button("Abbrechen", id="confirm-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-yes")

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(False)


# ── Registry entry edit modal ──────────────────────────────────────────────────

class RegistryEntryModal(ModalScreen):
    CSS = """
    RegistryEntryModal { align: center middle; }
    #re-box {
        background: #181825;
        border: solid #cba6f7;
        padding: 2 4;
        width: 60;
        height: auto;
    }
    #re-title {
        text-style: bold;
        color: #cba6f7;
        margin-bottom: 1;
        text-align: center;
    }
    .re-label { color: #a6adc8; height: 1; margin-top: 1; }
    .re-input {
        background: #313244;
        border: tall #45475a;
        color: #cdd6f4;
        margin-bottom: 0;
    }
    .re-input:focus { border: tall #cba6f7; }
    .re-input.-disabled { color: #585b70; }
    #re-error { color: #f38ba8; height: 1; margin-top: 1; }
    #re-save {
        width: 100%;
        margin-top: 1;
        background: #cba6f7;
        color: #1e1e2e;
        text-style: bold;
        border: none;
    }
    #re-save:hover { background: #b4befe; }
    #re-cancel {
        width: 100%;
        margin-top: 1;
        background: #313244;
        color: #a6adc8;
        border: none;
    }
    #re-cancel:hover { background: #45475a; }
    """

    def __init__(self, row: dict | None = None, existing_rooms: set | None = None):
        """row=None → add mode; row=dict → edit mode."""
        super().__init__()
        self._row = row or {}
        self._edit_mode = row is not None
        self._existing_rooms = existing_rooms or set()

    def compose(self) -> ComposeResult:
        title = "Eintrag bearbeiten" if self._edit_mode else "Neuer Eintrag"
        room_val = self._row.get("room_number", "")
        with Vertical(id="re-box"):
            yield Label(title, id="re-title")
            yield Label("Raumnummer (1–254)", classes="re-label")
            yield Input(
                value=room_val,
                id="re-room",
                classes="re-input",
                type="integer",
                disabled=self._edit_mode,
            )
            yield Label("Standort", classes="re-label")
            yield Input(value=self._row.get("location", ""), id="re-location", classes="re-input")
            yield Label("MAC-Adresse", classes="re-label")
            yield Input(value=self._row.get("mac_address", ""), id="re-mac", classes="re-input")
            yield Label("DS18B20-Adresse", classes="re-label")
            yield Input(value=self._row.get("ds18b20_address", ""), id="re-ds18b20", classes="re-input")
            yield Label("", id="re-error")
            yield Button("Speichern", id="re-save")
            yield Button("Abbrechen", id="re-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "re-save":
            self._try_save()
        elif event.button.id == "re-cancel":
            self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)

    def on_input_submitted(self, _: Input.Submitted) -> None:
        self._try_save()

    def _try_save(self) -> None:
        error = self.query_one("#re-error", Label)

        if self._edit_mode:
            room_num = _room_int(self._row.get("room_number", ""))
        else:
            try:
                room_num = int(self.query_one("#re-room", Input).value)
            except ValueError:
                error.update("Raumnummer muss eine Zahl sein.")
                return
            if not (1 <= room_num <= 254):
                error.update("Raumnummer muss zwischen 1 und 254 liegen.")
                return
            if room_num in self._existing_rooms:
                error.update(f"Raum {room_num:03d} existiert bereits.")
                return

        self.dismiss({
            "timestamp":      datetime.now().isoformat(timespec="seconds"),
            "room_number":    f"{room_num:03d}",
            "location":       self.query_one("#re-location", Input).value.strip(),
            "mac_address":    self.query_one("#re-mac", Input).value.strip(),
            "ds18b20_address": self.query_one("#re-ds18b20", Input).value.strip(),
            "ssid":           self._row.get("ssid", ""),
            "bssid":          self._row.get("bssid", ""),
            "channel":        self._row.get("channel", ""),
        })


# ── Flash progress overlay ────────────────────────────────────────────────────

class FlashOverlay(Widget):
    """Full-screen overlay with two modes: instructions and progress."""

    can_focus = True

    DEFAULT_CSS = """
    FlashOverlay {
        layer: overlay;
        display: none;
        width: 100%;
        height: 100%;
        align: center middle;
    }
    #fo-box {
        width: 68;
        background: #181825;
        border: double #a6e3a1;
        padding: 1 3;
        height: auto;
    }
    #fo-title {
        text-align: center;
        color: #a6e3a1;
        text-style: bold;
        width: 100%;
        margin-bottom: 1;
    }
    #fo-steps {
        text-align: center;
        color: #585b70;
        width: 100%;
        margin-bottom: 1;
    }
    /* ── Instruction panel ── */
    #fo-instr {
        width: 100%;
        height: auto;
    }
    #fo-instr-text {
        color: #cdd6f4;
        width: 100%;
        margin-bottom: 1;
        padding: 0 2;
    }
    #fo-baud-row {
        height: auto;
        margin-bottom: 1;
    }
    #fo-baud-label {
        width: auto;
        color: #585b70;
        padding: 0 1 0 0;
    }
    #fo-baud-select {
        width: 1fr;
        border: tall #45475a;
    }
    #fo-continue-btn {
        width: 100%;
        background: #f9e2af;
        color: #1e1e2e;
        text-style: bold;
        border: none;
        margin-top: 1;
    }
    #fo-continue-btn:hover { background: #fab387; }
    /* ── Progress panel ── */
    #fo-progress {
        display: none;
        width: 100%;
        height: auto;
    }
    #fo-label {
        text-align: center;
        color: #f9e2af;
        text-style: bold;
        width: 100%;
        margin-bottom: 1;
    }
    #fo-bar {
        width: 100%;
        height: 3;
    }
    #fo-bar Bar { width: 100%; height: 3; }
    #fo-bar > .bar--bar      { color: #a6e3a1; background: #313244; }
    #fo-bar > .bar--complete { color: #94e2d5; background: #313244; }
    #fo-pct {
        text-align: center;
        color: #a6e3a1;
        text-style: bold;
        width: 100%;
        margin-top: 1;
    }
    """

    _BAUD_OPTIONS = [9600, 74880, 115200, 230400, 460800]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._continue_event: threading.Event | None = None

    @property
    def baud_rate(self) -> int:
        return self.query_one("#fo-baud-select", Select).value or BAUD_RATE

    def compose(self) -> ComposeResult:
        with Vertical(id="fo-box"):
            yield Label("", id="fo-title")
            yield Static("", id="fo-steps")
            with Vertical(id="fo-instr"):
                yield Static("", id="fo-instr-text")
                with Horizontal(id="fo-baud-row"):
                    yield Label("Baud rate:", id="fo-baud-label")
                    yield Select(
                        [(str(b), b) for b in self._BAUD_OPTIONS],
                        value=BAUD_RATE,
                        id="fo-baud-select",
                        allow_blank=False,
                    )
                yield Button("Continue →", id="fo-continue-btn")
            with Vertical(id="fo-progress"):
                yield Static("", id="fo-label")
                yield ProgressBar(id="fo-bar", total=100, show_eta=False, show_percentage=False)
                yield Static("", id="fo-pct")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "fo-continue-btn" and self._continue_event:
            self._continue_event.set()

    def on_key(self, event) -> None:
        if event.key == "enter" and self._continue_event:
            self._continue_event.set()

    def show_instructions(self, title: str, step_label: str, instructions: str,
                          event: threading.Event,
                          button_label: str = "Continue →",
                          ready: bool = True) -> None:
        self._continue_event = event
        self._button_label = button_label
        self.query_one("#fo-title", Label).update(title)
        self.query_one("#fo-steps", Static).update(step_label)
        self.query_one("#fo-instr-text", Static).update(instructions)
        btn = self.query_one("#fo-continue-btn", Button)
        if ready:
            btn.label = button_label
            btn.disabled = False
        else:
            btn.label = "Waiting for compiler…"
            btn.disabled = True
        self.query_one("#fo-instr").display = True
        self.query_one("#fo-progress").display = False
        self.display = True

    def enable_continue(self, button_label: str = "Continue →") -> None:
        btn = self.query_one("#fo-continue-btn", Button)
        btn.label = button_label
        btn.disabled = False

    def start_progress(self, label: str) -> None:
        self.query_one("#fo-instr").display = False
        self.query_one("#fo-progress").display = True
        self.query_one("#fo-label", Static).update(label)
        self.query_one("#fo-bar", ProgressBar).update(progress=0)
        self.query_one("#fo-pct", Static).update("0 %")

    def update_progress(self, pct: int, label: str) -> None:
        self.query_one("#fo-bar", ProgressBar).update(progress=pct)
        self.query_one("#fo-label", Static).update(label)
        self.query_one("#fo-pct", Static).update(f"{pct} %")

    def hide_flash(self) -> None:
        self.display = False
        self._continue_event = None


# ── Main TUI App ──────────────────────────────────────────────────────────────

class LTLProgrammerApp(App):
    TITLE = "LTL Sensor Programmer"
    SUB_TITLE = "Two-step ESP8266 flash tool"

    CSS = """
    /* ── Base ── */
    Screen {
        background: #11111b;
        color: #cdd6f4;
        layers: base overlay;
    }
    Header {
        background: #181825;
        color: #89b4fa;
        text-style: bold;
        border: double #89b4fa;
        height: 3;
    }
    Footer {
        background: #181825;
        color: #6c7086;
    }
    Footer .footer--key {
        background: #313244;
        color: #cdd6f4;
    }

    /* ── Layout ── */
    #top-panels { height: 12; }
    #bottom-panels { height: 1fr; }

    /* ── Top panels ── */
    #ports-panel {
        width: 2fr;
        background: #181825;
        border: solid #89b4fa;
        padding: 0 0;
    }
    #creds-panel {
        width: 2fr;
        background: #181825;
        border: solid #89b4fa;
        padding: 0 0;
    }
    #ports-title {
        background: #181825;
        color: #89b4fa;
        text-style: bold;
        text-align: center;
        width: 100%;
    }
    #creds-title {
        background: #181825;
        color: #89b4fa;
        text-style: bold;
        text-align: center;
        width: 100%;
    }
    #creds-info {
        color: #cdd6f4;
        padding: 0 1;
        height: auto;
    }

    /* ── Bottom panels ── */
    #status-panel {
        width: 2fr;
        background: #181825;
        border: solid #89b4fa;
        padding: 0 0;
    }
    #status-title {
        background: #181825;
        color: #89b4fa;
        text-style: bold;
        text-align: center;
        width: 100%;
    }
    #registry-panel {
        width: 2fr;
        background: #181825;
        border: solid #89b4fa;
        padding: 0 0;
    }
    #registry-title {
        background: #181825;
        color: #89b4fa;
        text-style: bold;
        text-align: center;
        width: 100%;
    }

    /* ── DataTable ── */
    DataTable {
        background: #181825;
        color: #cdd6f4;
        height: 1fr;
    }
    DataTable > .datatable--header {
        background: #313244;
        color: #89b4fa;
        text-style: bold;
    }
    DataTable > .datatable--cursor {
        background: #45475a;
        color: #cdd6f4;
    }
    DataTable > .datatable--hover {
        background: #313244;
    }
    #registry-table DataTable > .datatable--header { color: #89b4fa; }

    /* ── Active panel highlight ── */
    #ports-panel.panel-active,
    #creds-panel.panel-active,
    #status-panel.panel-active,
    #registry-panel.panel-active  { border: heavy #ffff00; }
    .panel-active #ports-title,
    .panel-active #creds-title,
    .panel-active #status-title,
    .panel-active #registry-title { background: #89b4fa; color: #1e1e2e; }

    /* ── Log ── */
    #log {
        height: 1fr;
        background: #11111b;
        color: #cdd6f4;
        scrollbar-color: #45475a;
        scrollbar-background: #181825;
    }

    /* ── Debug panel ── */
    #debug-panel {
        height: 12;
        background: #181825;
        border: solid #89b4fa;
        display: none;
    }
    #debug-panel.panel-active { border: heavy #ffff00; }
    #debug-title {
        background: #181825;
        color: #89b4fa;
        text-style: bold;
        text-align: center;
        width: 100%;
    }
    .panel-active #debug-title { background: #89b4fa; color: #1e1e2e; }
    #debug-log {
        height: 1fr;
        background: #11111b;
        color: #a6e3a1;
        scrollbar-color: #45475a;
        scrollbar-background: #181825;
    }

    """

    _PANEL_IDS = {
        "ports":    "#ports-panel",
        "creds":    "#creds-panel",
        "status":   "#status-panel",
        "registry": "#registry-panel",
        "debug":    "#debug-panel",
    }

    @property
    def _csv_path(self) -> Path:
        """Return the sensors CSV for the currently selected credentials location."""
        table = self.query_one("#creds-table", DataTable)
        idx = table.cursor_row
        if self._credentials and 0 <= idx < len(self._credentials):
            return Path(__file__).parent / f"sensors_{self._credentials[idx]}.csv"
        return Path(__file__).parent / "sensors.csv"

    BINDINGS = [
        Binding("f", "flash", "F Flash"),
        Binding("e", "ctx_edit", "E Edit"),
        Binding("n", "ctx_new", "N New"),
        Binding("d", "ctx_delete", "D Delete"),
        Binding("r", "refresh_ports", "R Refresh"),
        Binding("t", "toggle_debug", "T Debug"),
        Binding("q", "quit", "Q Quit"),
    ]

    def __init__(self):
        super().__init__()
        self._ports: list = []
        self._credentials: list = []
        self._registry_rows: list[dict] = []
        self._active_panel: str = "creds"
        self._flashing = False
        self._quit_event = threading.Event()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="top-panels"):
            with Vertical(id="ports-panel"):
                yield Label("Serial Ports", id="ports-title")
                yield DataTable(id="ports-table", cursor_type="row")
            with Vertical(id="creds-panel"):
                yield Label("Credentials", id="creds-title")
                yield DataTable(id="creds-table", cursor_type="row")
                yield Static("", id="creds-info")
        with Horizontal(id="bottom-panels"):
            with Vertical(id="status-panel"):
                yield Label("Status", id="status-title")
                yield RichLog(id="log", auto_scroll=True, markup=True)
            with Vertical(id="registry-panel"):
                yield Label("Sensor Registry", id="registry-title")
                yield DataTable(id="registry-table", cursor_type="row")
        with Vertical(id="debug-panel"):
            yield Label("Serial Debug", id="debug-title")
            yield RichLog(id="debug-log", auto_scroll=True, markup=False)
        yield FlashOverlay(id="flash-overlay")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#ports-table", DataTable).add_columns("Port", "Description", "FQBN")
        self.query_one("#creds-table", DataTable).add_columns("Location", "File")
        reg = self.query_one("#registry-table", DataTable)
        reg.add_columns("Room", "Location", "MAC", "DS18B20", "Flashed at")
        self._do_refresh()
        self._refresh_registry()
        self.set_interval(2.0, self._do_refresh)
        self.call_after_refresh(self._set_active_panel, "ports")

    def _do_refresh(self) -> None:
        """Kick off a background port scan — never blocks the UI thread."""
        self._bg_refresh()

    @work(thread=True, exclusive=True, group="port-scan")
    def _bg_refresh(self) -> None:
        ports = detect_ports()
        creds = find_credentials_files(PROJECT_ROOT)
        self.call_from_thread(self._apply_refresh, ports, creds)

    def _apply_refresh(self, ports: list, creds: list) -> None:
        """Apply port/credentials data to the UI — runs on the main thread."""
        new_keys = [p["port"] for p in ports]
        old_keys = [p["port"] for p in self._ports]
        if new_keys != old_keys:
            table = self.query_one("#ports-table", DataTable)
            table.clear()
            for p in ports:
                table.add_row(p["port"], p["description"], p["fqbn"] or "unknown")
            usb_idx = next(
                (i for i, p in enumerate(ports) if "usbserial" in p["port"]), 0
            )
            table.move_cursor(row=usb_idx)
            log = self.query_one("#log", RichLog)
            for port in set(new_keys) - set(old_keys):
                log.write(f"[green]► Device connected: {port}[/green]")
            for port in set(old_keys) - set(new_keys):
                log.write(f"[red]◄ Device disconnected: {port}[/red]")
            self._ports = ports

        if creds != self._credentials:
            table = self.query_one("#creds-table", DataTable)
            table.clear()
            for loc in creds:
                table.add_row(loc, f"credentials_{loc}.h")
            self._credentials = creds
            table.move_cursor(row=0)
            self._update_creds_info()

    def _update_creds_info(self) -> None:
        """Refresh the network info block for the currently selected credentials row."""
        info = self.query_one("#creds-info", Static)
        if not self._credentials:
            info.update("")
            return
        table = self.query_one("#creds-table", DataTable)
        idx = table.cursor_row
        if idx < 0 or idx >= len(self._credentials):
            info.update("")
            return
        location = self._credentials[idx]
        cred_path = PROJECT_ROOT / f"credentials_{location}.h"
        net = read_network_from_credentials(cred_path)
        if net is None:
            info.update("[yellow]⚠ Netzwerkkonfiguration fehlt[/yellow]")
        else:
            info.update(
                f"[#585b70]IP  [/#585b70]   {net['net_prefix']}.[bold #89b4fa]<room>[/bold #89b4fa]\n"
                f"[#585b70]Netz[/#585b70]   {net['net_prefix']}.0/{net['net_mask']}\n"
                f"[#585b70]GW  [/#585b70]   {net['gateway']}\n"
                f"[#585b70]DNS [/#585b70]   {net['dns_server']}\n"
                f"[#585b70]MQTT[/#585b70]   {net['mqtt_server']}:{net['mqtt_port']}"
            )

    def _refresh_registry(self) -> None:
        table = self.query_one("#registry-table", DataTable)
        table.clear()
        self._registry_rows = []
        if not self._csv_path.exists():
            with open(self._csv_path, "w", newline="") as f:
                csv.DictWriter(f, fieldnames=CSV_FIELDNAMES).writeheader()
        with open(self._csv_path, newline="") as f:
            rows = list(csv.DictReader(f))
        display_rows = list(reversed(rows))  # newest first
        self._registry_rows = display_rows
        for row in display_rows:
            ts = row.get("timestamp", "")
            try:
                dt = datetime.fromisoformat(ts)
                ts_display = dt.strftime("%d.%m. %H:%M")
            except ValueError:
                ts_display = ts
            table.add_row(
                row.get("room_number", ""),
                row.get("location", ""),
                row.get("mac_address", ""),
                row.get("ds18b20_address", ""),
                ts_display,
            )

    def on_key(self, event) -> None:
        if event.key == "enter":
            overlay = self.query_one("#flash-overlay", FlashOverlay)
            if overlay.display and overlay._continue_event:
                btn = overlay.query_one("#fo-continue-btn", Button)
                if not btn.disabled:
                    overlay._continue_event.set()

    def _set_active_panel(self, panel: str) -> None:
        if self._active_panel == panel:
            return
        self._active_panel = panel
        for pid in self._PANEL_IDS.values():
            self.query_one(pid).remove_class("panel-active")
        self.query_one(self._PANEL_IDS[panel]).add_class("panel-active")

    def on_descendant_focus(self, event) -> None:
        widget_id = getattr(event.widget, "id", None)
        if widget_id == "ports-table":
            self._set_active_panel("ports")
        elif widget_id == "creds-table":
            self._set_active_panel("creds")
        elif widget_id == "log":
            self._set_active_panel("status")
        elif widget_id == "registry-table":
            self._set_active_panel("registry")

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id == "creds-table":
            if event.data_table.has_focus:
                self._set_active_panel("creds")
            self._update_creds_info()
            self._refresh_registry()
        elif event.data_table.id == "registry-table":
            if event.data_table.has_focus:
                self._set_active_panel("registry")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "registry-table":
            self._set_active_panel("registry")
            self._open_registry_edit(event.cursor_row)

    def action_quit(self) -> None:
        self._quit_event.set()
        self.exit()

    def action_refresh_ports(self) -> None:
        self._do_refresh()

    def action_toggle_debug(self) -> None:
        panel = self.query_one("#debug-panel")
        panel.display = not panel.display
        if panel.display:
            self.query_one("#debug-log", RichLog).clear()
            self._set_active_panel("debug")

    def action_ctx_edit(self) -> None:
        if self._active_panel == "creds":
            if not self._credentials:
                self.notify("Keine Credentials-Datei ausgewählt.", severity="warning")
                return
            idx = self.query_one("#creds-table", DataTable).cursor_row
            if idx < 0 or idx >= len(self._credentials):
                return
            location = self._credentials[idx]
            cred_path = PROJECT_ROOT / f"credentials_{location}.h"
            net = read_network_from_credentials(cred_path)
            if net is None:
                self.notify("Netzwerkkonfiguration fehlt in der Datei.", severity="error")
                return

            def _on_save(updates: dict | None) -> None:
                if updates is None:
                    return
                write_network_to_credentials(cred_path, updates)
                self._update_creds_info()
                self.notify(f"Gespeichert: credentials_{location}.h", severity="information")

            self.push_screen(NetworkConfigModal(net), _on_save)
        else:
            self._open_registry_edit(self.query_one("#registry-table", DataTable).cursor_row)

    def action_ctx_new(self) -> None:
        if self._active_panel == "creds":
            def _on_save(fields: dict | None) -> None:
                if fields is None:
                    return
                cred_path = PROJECT_ROOT / f"credentials_{fields['location']}.h"
                if cred_path.exists():
                    self.notify(f"credentials_{fields['location']}.h existiert bereits.", severity="warning")
                    return
                write_credentials_file(cred_path, fields)
                self._do_refresh()
                self.notify(f"credentials_{fields['location']}.h erstellt.", severity="information")

            self.push_screen(NewCredentialsModal(), _on_save)
        else:
            existing = load_csv_rooms(self._csv_path)

            def _on_save(new_row: dict | None) -> None:
                if new_row is None:
                    return
                upsert_csv_row(self._csv_path, new_row)
                self._refresh_registry()
                self.notify(f"Raum {new_row['room_number']} hinzugefügt.", severity="information")

            self.push_screen(RegistryEntryModal(existing_rooms=existing), _on_save)

    def action_ctx_delete(self) -> None:
        if self._active_panel != "registry":
            self.notify("Löschen ist nur in der Registry möglich.", severity="warning")
            return
        table = self.query_one("#registry-table", DataTable)
        idx = table.cursor_row
        if idx < 0 or idx >= len(self._registry_rows):
            self.notify("Kein Eintrag ausgewählt.", severity="warning")
            return
        row = self._registry_rows[idx]
        room_str = row.get("room_number", "?")

        def _on_confirm(confirmed: bool) -> None:
            if not confirmed:
                return
            room_num = _room_int(room_str)
            if room_num is not None:
                delete_csv_row(self._csv_path, room_num)
            self._refresh_registry()
            self.notify(f"Raum {room_str} gelöscht.", severity="information")

        self.push_screen(ConfirmModal(f"Raum {room_str} wirklich löschen?"), _on_confirm)

    def _open_registry_edit(self, row_idx: int) -> None:
        if row_idx < 0 or row_idx >= len(self._registry_rows):
            return
        row = self._registry_rows[row_idx]

        def _on_save(updated: dict | None) -> None:
            if updated is None:
                return
            upsert_csv_row(self._csv_path, updated)
            self._refresh_registry()
            self.notify(f"Raum {updated['room_number']} aktualisiert.", severity="information")

        self.push_screen(RegistryEntryModal(row=row), _on_save)

    def action_flash(self) -> None:
        if self._flashing:
            self.notify("Flash already in progress!", severity="warning")
            return
        if not self._ports:
            self.notify("No serial port available!", severity="error")
            return
        if not self._credentials:
            self.notify("No credentials file found!", severity="error")
            return
        port_info = self._ports[self.query_one("#ports-table", DataTable).cursor_row]
        location = self._credentials[self.query_one("#creds-table", DataTable).cursor_row]
        cred_path = PROJECT_ROOT / f"credentials_{location}.h"
        fqbn = port_info["fqbn"] or BOARD_FQBN
        baud = self.query_one("#flash-overlay", FlashOverlay).baud_rate
        self._flashing = True
        self._flash_worker(port_info["port"], fqbn, location, cred_path, baud)

    # ── helpers callable from worker thread ───────────────────────────────────

    def _log(self, msg: str) -> None:
        self.call_from_thread(self.query_one("#log", RichLog).write, msg)

    def _debug_line(self, line: str) -> None:
        self.call_from_thread(self.query_one("#debug-log", RichLog).write, line)

    _STEP_LABELS = [
        "[#a6e3a1]◉ Step 1/2: Setup Sketch[/#a6e3a1]     [#585b70]◯ Step 2/2: Production Firmware[/#585b70]",
        "[#585b70]◉ Step 1/2: Setup Sketch[/#585b70]     [#a6e3a1]◉ Step 2/2: Production Firmware[/#a6e3a1]",
    ]

    def _show_progress(self, pct: int, label: str = "") -> None:
        self.call_from_thread(
            self.query_one("#flash-overlay", FlashOverlay).update_progress, pct, label
        )

    def _hide_progress(self) -> None:
        self.call_from_thread(self.query_one("#flash-overlay", FlashOverlay).hide_flash)

    def _start_flash_progress(self, label: str) -> None:
        self.call_from_thread(
            self.query_one("#flash-overlay", FlashOverlay).start_progress, label
        )

    def _clear_step(self) -> None:
        self.call_from_thread(self.query_one("#flash-overlay", FlashOverlay).hide_flash)

    def _show_flash_instructions(
        self, title: str, step_label: str, instructions: str,
        button_label: str = "Continue →",
        ready_event: threading.Event | None = None,
    ) -> None:
        """Show instructions in FlashOverlay and block worker thread until Continue pressed.

        If ready_event is given, the Continue button stays disabled until that event fires,
        then becomes active. This allows parallel compilation while showing instructions.
        """
        continue_event = threading.Event()
        overlay = self.query_one("#flash-overlay", FlashOverlay)
        self.call_from_thread(
            overlay.show_instructions,
            title, step_label, instructions, continue_event, button_label,
            ready_event is None,  # ready=True only when no compiler wait needed
        )
        if ready_event is not None:
            def _enable_when_ready():
                ready_event.wait()
                if not self._quit_event.is_set():
                    self.call_from_thread(overlay.enable_continue, button_label)
            threading.Thread(target=_enable_when_ready, daemon=True).start()
        while not self._quit_event.is_set():
            if continue_event.wait(timeout=0.5):
                break

    def _wait_modal(self, screen: ModalScreen) -> object:
        """Push a modal from a worker thread and block until it's dismissed."""
        result_box: list = [None]
        done = threading.Event()

        def callback(value):
            result_box[0] = value
            done.set()

        self.call_from_thread(self.push_screen, screen, callback)
        while not self._quit_event.is_set():
            if done.wait(timeout=0.5):
                break
        return result_box[0]

    # ── flash workflow (runs in background thread) ────────────────────────────

    @work(thread=True, exclusive=True)
    def _flash_worker(self, port: str, fqbn: str, location: str, cred_path: Path, baud: int) -> None:
        try:
            self._run_workflow(port, fqbn, location, cred_path, baud)
        except Exception as exc:
            self._log(f"[red]Unexpected error: {exc}[/red]")
        finally:
            self._flashing = False

    def _upload(self, sketch_dir: Path, port: str, fqbn: str, label: str = "Flashing…") -> bool:
        """Run arduino-cli upload, streaming progress to the progress bar. Returns success."""
        self._start_flash_progress(label)
        proc = subprocess.Popen(
            ["arduino-cli", "upload", "--fqbn", fqbn, "--port", port, str(sketch_dir)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        for line in proc.stdout:
            m = re.search(r"\((\d+)\s*%\)", line)
            if m:
                self._show_progress(int(m.group(1)), label)
            elif "Connecting" in line:
                self._show_progress(0, "Connecting to ESP…")
            elif "Hash of data verified" in line:
                self._show_progress(100, "Verifying…")
        proc.wait()
        self._hide_progress()
        return proc.returncode == 0

    @staticmethod
    def _compile(fqbn: str, sketch_dir: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["arduino-cli", "compile", "--fqbn", fqbn, str(sketch_dir)],
            capture_output=True, text=True,
        )

    def _run_workflow(self, port: str, fqbn: str, location: str, cred_path: Path, baud: int) -> None:
        self._log(f"[bold cyan]━━ Flash workflow started ━━[/bold cyan]")
        self._log(f"Port: [cyan]{port}[/cyan]   Location: [cyan]{location}[/cyan]")

        # ── Phase 1: compile setup sketch IN BACKGROUND while user prepares hardware ──
        # Copy credentials so the setup sketch can attempt a WiFi connection test
        setup_cred = SETUP_SKETCH_DIR / "credentials.h"
        shutil.copy(cred_path, setup_cred)

        self._log("[yellow]► Compiling setup sketch in background...[/yellow]")
        compile1_result: list = [None]
        compile1_done = threading.Event()

        def _compile_setup():
            compile1_result[0] = self._compile(fqbn, SETUP_SKETCH_DIR)
            compile1_done.set()

        threading.Thread(target=_compile_setup, daemon=True).start()

        # Show combined flash+run instructions — Continue unlocks when compiler finishes
        self._show_flash_instructions(
            "⚡  Enter Flash Mode  —  Step 1 / 2",
            self._STEP_LABELS[0],
            _FLASH_AND_RUN_INSTRUCTIONS,
            ready_event=compile1_done,
        )

        # Compiler is guaranteed done here (Continue was only enabled after it finished)
        compile1_done.wait()
        if compile1_result[0].returncode != 0:
            self._log(f"[red]✗ Setup sketch compilation failed:[/red] {compile1_result[0].stderr.strip()}")
            return
        self._log("[green]✓ Setup sketch compiled[/green]")

        # ── Upload setup sketch ───────────────────────────────────────────────
        self._log("[yellow]► Uploading setup sketch...[/yellow]")
        if not self._upload(SETUP_SKETCH_DIR, port, fqbn, "Step 1/2 — Writing setup sketch…"):
            self._log("[red]✗ Upload failed — repeat: RST+FLASH sequence[/red]")
            return
        self._log("[green]✓ Setup sketch uploaded[/green]")
        self._clear_step()

        self._log("[yellow]► Reading setup data from ESP...[/yellow]")
        time.sleep(BOOT_DELAY_S)
        setup_data = None
        while not self._quit_event.is_set():
            lines = []
            try:
                with serial.Serial(port, baud, timeout=1) as ser:
                    deadline = time.time() + SERIAL_TIMEOUT_S
                    while time.time() < deadline and not self._quit_event.is_set():
                        raw = ser.readline().decode("utf-8", errors="replace").strip()
                        if raw:
                            lines.append(raw)
                            self._debug_line(raw)
                        parsed = parse_serial_output(lines)
                        if parsed["done"]:
                            setup_data = parsed
                            break
            except serial.SerialException as exc:
                self._log(f"[red]Serial error: {exc}[/red]")
                return

            if setup_data or self._quit_event.is_set():
                break

            self._log(f"[red]✗ Timeout — no SETUP_DONE within {SERIAL_TIMEOUT_S}s[/red]")
            self._show_flash_instructions(
                title="Serial Read Timeout",
                step_label=self._STEP_LABELS[0],
                instructions=(
                    f"No valid data received at [bold]{baud}[/bold] baud.\n\n"
                    "• Try [bold]74880[/bold] if you see garbled output (ROM bootloader)\n"
                    "• Power-cycle the ESP, then click Retry\n\n"
                    "Adjust the baud rate below, then click Retry."
                ),
                button_label="Retry →",
            )
            overlay = self.query_one("#flash-overlay", FlashOverlay)
            baud = overlay.baud_rate
            self._log(f"[yellow]► Retrying at {baud} baud...[/yellow]")

        # Clean up temporary credentials.h from setup sketch dir
        setup_cred.unlink(missing_ok=True)

        if not setup_data:
            return

        self._log(f"[green]✓ MAC: {setup_data['mac']}[/green]")
        if setup_data["ds18b20_error"]:
            self._log("[red]✗ DS18B20 not found — check wiring (GPIO12, 4.7kΩ pull-up)[/red]")
            return
        self._log(f"[green]✓ DS18B20: {setup_data['ds18b20']}[/green]")
        self._log(f"[green]✓ WiFi networks: {len(setup_data['wifi_networks'])}[/green]")

        if setup_data["wifi_ok"]:
            self._log("[green]✓ WiFi connection OK[/green]")
        elif setup_data["wifi_fail"]:
            self._log("[red]✗ WiFi connection failed — check SSID and password in credentials file[/red]")
            return

        # ── Room number ───────────────────────────────────────────────────────
        room_number = self._wait_modal(RoomInputModal(load_csv_rooms(self._csv_path)))
        if room_number is None:
            self._log("[red]Flash cancelled[/red]")
            return
        self._log(f"[green]✓ Room: {room_number}[/green]")

        # ── Phase 2: build production firmware content ────────────────────────
        ds18b20_array = format_ds18b20_c_array(setup_data["ds18b20"])

        final_content = substitute_template(
            SENSOR_SKETCH.read_text(),
            room_number=room_number,
            ds18b20_array=ds18b20_array,
        )

        # Use a manually managed temp dir so it stays alive until upload is done
        tmpdir_obj = tempfile.TemporaryDirectory()
        tmpdir = Path(tmpdir_obj.name)
        sketch_dir = tmpdir / "LTL_sensor"
        sketch_dir.mkdir()
        (sketch_dir / "LTL_sensor.ino").write_text(final_content)
        shutil.copy(cred_path, sketch_dir / "credentials.h")

        # ── Compile production firmware IN BACKGROUND while user prepares hardware ──
        self._log("[yellow]► Compiling production firmware in background...[/yellow]")
        compile2_result: list = [None]
        compile2_done = threading.Event()

        def _compile_production():
            compile2_result[0] = self._compile(fqbn, sketch_dir)
            compile2_done.set()

        threading.Thread(target=_compile_production, daemon=True).start()

        # Show flash instructions — Continue button unlocks when compiler finishes
        self._show_flash_instructions(
            "⚡  Enter Flash Mode  —  Step 2 / 2",
            self._STEP_LABELS[1],
            _FLASH_INSTRUCTIONS,
            ready_event=compile2_done,
        )

        compile2_done.wait()
        if compile2_result[0].returncode != 0:
            self._log(f"[red]✗ Production firmware compilation failed:[/red] {compile2_result[0].stderr.strip()}")
            tmpdir_obj.cleanup()
            return
        self._log("[green]✓ Production firmware compiled[/green]")

        # ── Upload production firmware ────────────────────────────────────────
        self._log("[yellow]► Uploading production firmware...[/yellow]")
        upload_ok = self._upload(sketch_dir, port, fqbn, "Step 2/2 — Writing production firmware…")
        tmpdir_obj.cleanup()
        if not upload_ok:
            self._log("[red]✗ Upload failed[/red]")
            return
        self._log("[green]✓ Production firmware uploaded[/green]")

        self._show_flash_instructions(
            "✓  Done  —  Step 2 / 2",
            self._STEP_LABELS[1],
            _RUN_AFTER_PRODUCTION,
            button_label="Finish →",
        )

        # Step 9 — Save to CSV
        upsert_csv_row(self._csv_path, {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "room_number": f"{room_number:03d}",
            "mac_address": setup_data["mac"] or "",
            "ds18b20_address": setup_data["ds18b20"] or "",
            "location": location,
            "ssid": read_ssid_from_credentials(cred_path) or "",
            "bssid": "",
            "channel": "",
        })

        self._clear_step()
        self._log(f"[bold green]━━ Sensor {room_number} programmed successfully! ━━[/bold green]")
        self._log(f"[green]Registry updated: {self._csv_path}[/green]")
        self.call_from_thread(self._refresh_registry)
        self.call_from_thread(
            self.notify, f"Room {room_number} ready to deploy!", severity="information"
        )


if __name__ == "__main__":
    LTLProgrammerApp().run()
