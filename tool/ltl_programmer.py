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
    Button, DataTable, Footer, Header, Input, Label, ProgressBar, RichLog, Static,
)
from textual.widget import Widget

sys.path.insert(0, str(Path(__file__).parent))
from arduino_config import BAUD_RATE, BOARD_FQBN, BOOT_DELAY_S, SERIAL_TIMEOUT_S

# ── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
SETUP_SKETCH_DIR = PROJECT_ROOT / "code" / "LTL_setup"
SENSOR_SKETCH = PROJECT_ROOT / "code" / "LTL_sensor" / "LTL_sensor.ino"
CSV_PATH = Path(__file__).parent / "sensors.csv"
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
    """Convert BSSID string to C array literal."""
    parts = [f"0x{b.upper()}" for b in bssid.split(":")]
    return "{ " + ", ".join(parts) + " }"


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


def load_csv_rooms(csv_path: Path) -> set:
    """Return set of room numbers (int) already recorded in sensors.csv."""
    if not csv_path.exists():
        return set()
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        return {int(row["room_number"]) for row in reader if row.get("room_number")}


def upsert_csv_row(csv_path: Path, row: dict) -> None:
    """Insert or update a row in sensors.csv, keyed by room_number."""
    rows = []
    if csv_path.exists():
        with open(csv_path, newline="") as f:
            rows = list(csv.DictReader(f))
    updated = False
    for i, r in enumerate(rows):
        if r.get("room_number") == row["room_number"]:
            rows[i] = row
            updated = True
            break
    if not updated:
        rows.append(row)
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


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
            if not parts:
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._continue_event: threading.Event | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="fo-box"):
            yield Label("", id="fo-title")
            yield Static("", id="fo-steps")
            with Vertical(id="fo-instr"):
                yield Static("", id="fo-instr-text")
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
        padding: 0 1;
    }
    #creds-panel {
        width: 1fr;
        background: #181825;
        border: solid #74c7ec;
        padding: 0 1;
    }
    #ports-title {
        color: #89b4fa;
        text-style: bold;
        padding: 0 0 0 1;
    }
    #creds-title {
        color: #74c7ec;
        text-style: bold;
        padding: 0 0 0 1;
    }

    /* ── Bottom panels ── */
    #status-panel {
        width: 2fr;
        background: #181825;
        border: solid #a6e3a1;
        padding: 0 1;
    }
    #status-title {
        color: #a6e3a1;
        text-style: bold;
        padding: 0 0 0 1;
    }
    #registry-panel {
        width: 1fr;
        background: #181825;
        border: solid #cba6f7;
        padding: 0 1;
    }
    #registry-title {
        color: #cba6f7;
        text-style: bold;
        padding: 0 0 0 1;
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
    #registry-table DataTable > .datatable--header { color: #cba6f7; }

    /* ── Log ── */
    #log {
        height: 1fr;
        background: #11111b;
        color: #cdd6f4;
        scrollbar-color: #45475a;
        scrollbar-background: #181825;
    }

    """

    BINDINGS = [
        Binding("f", "flash", "F Flash"),
        Binding("r", "refresh_ports", "R Refresh"),
        Binding("q", "quit", "Q Quit"),
    ]

    def __init__(self):
        super().__init__()
        self._ports: list = []
        self._credentials: list = []
        self._flashing = False
        self._quit_event = threading.Event()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="top-panels"):
            with Vertical(id="ports-panel"):
                yield Label(" ⬡  Serial Ports", id="ports-title")
                yield DataTable(id="ports-table", cursor_type="row")
            with Vertical(id="creds-panel"):
                yield Label(" ✦  Credentials", id="creds-title")
                yield DataTable(id="creds-table", cursor_type="row")
        with Horizontal(id="bottom-panels"):
            with Vertical(id="status-panel"):
                yield Label(" ◈  Status", id="status-title")
                yield RichLog(id="log", auto_scroll=True, markup=True)
            with Vertical(id="registry-panel"):
                yield Label(" ◉  Sensor Registry", id="registry-title")
                yield DataTable(id="registry-table", cursor_type="row")
        yield FlashOverlay(id="flash-overlay")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#ports-table", DataTable).add_columns("Port", "Description", "FQBN")
        self.query_one("#creds-table", DataTable).add_columns("Location", "File")
        reg = self.query_one("#registry-table", DataTable)
        reg.add_columns("Room", "Location", "MAC", "Flashed at")
        self._do_refresh()
        self._refresh_registry()
        self.set_interval(2.0, self._do_refresh)

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

    def _refresh_registry(self) -> None:
        table = self.query_one("#registry-table", DataTable)
        table.clear()
        if not CSV_PATH.exists():
            return
        with open(CSV_PATH, newline="") as f:
            rows = list(csv.DictReader(f))
        for row in reversed(rows):  # newest first
            ts = row.get("timestamp", "")
            # Format: 2026-03-22T21:30:00 → 22.03. 21:30
            try:
                dt = datetime.fromisoformat(ts)
                ts_display = dt.strftime("%d.%m. %H:%M")
            except ValueError:
                ts_display = ts
            table.add_row(
                row.get("room_number", ""),
                row.get("location", ""),
                row.get("mac_address", ""),
                ts_display,
            )

    def on_key(self, event) -> None:
        if event.key == "enter":
            overlay = self.query_one("#flash-overlay", FlashOverlay)
            if overlay.display and overlay._continue_event:
                btn = overlay.query_one("#fo-continue-btn", Button)
                if not btn.disabled:
                    overlay._continue_event.set()

    def action_quit(self) -> None:
        self._quit_event.set()
        self.exit()

    def action_refresh_ports(self) -> None:
        self._do_refresh()

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
        self._flashing = True
        self._flash_worker(port_info["port"], fqbn, location, cred_path)

    # ── helpers callable from worker thread ───────────────────────────────────

    def _log(self, msg: str) -> None:
        self.call_from_thread(self.query_one("#log", RichLog).write, msg)

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
    def _flash_worker(self, port: str, fqbn: str, location: str, cred_path: Path) -> None:
        try:
            self._run_workflow(port, fqbn, location, cred_path)
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

    def _run_workflow(self, port: str, fqbn: str, location: str, cred_path: Path) -> None:
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
        lines = []
        setup_data = None
        try:
            with serial.Serial(port, BAUD_RATE, timeout=1) as ser:
                deadline = time.time() + SERIAL_TIMEOUT_S
                while time.time() < deadline:
                    raw = ser.readline().decode("utf-8", errors="replace").strip()
                    if raw:
                        lines.append(raw)
                    parsed = parse_serial_output(lines)
                    if parsed["done"]:
                        setup_data = parsed
                        break
        except serial.SerialException as exc:
            self._log(f"[red]Serial error: {exc}[/red]")
            return

        # Clean up temporary credentials.h from setup sketch dir
        setup_cred.unlink(missing_ok=True)

        if not setup_data:
            self._log(f"[red]✗ Timeout — no SETUP_DONE within {SERIAL_TIMEOUT_S}s[/red]")
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

        # ── BSSID auto-selection (best signal for credentials SSID) ──────────
        selected_net = None
        if setup_data["wifi_networks"]:
            preselect_ssid = read_ssid_from_credentials(cred_path)
            candidates = [n for n in setup_data["wifi_networks"] if n["ssid"] == preselect_ssid]
            if candidates:
                selected_net = max(candidates, key=lambda n: n["rssi"])
                self._log(
                    f"[green]✓ BSSID pinned: {selected_net['bssid']} "
                    f"ch {selected_net['channel']} ({selected_net['rssi']} dBm)[/green]"
                )
            else:
                self._log("[dim]No matching network found — BSSID pinning skipped[/dim]")

        # ── Room number ───────────────────────────────────────────────────────
        room_number = self._wait_modal(RoomInputModal(load_csv_rooms(CSV_PATH)))
        if room_number is None:
            self._log("[red]Flash cancelled[/red]")
            return
        self._log(f"[green]✓ Room: {room_number}[/green]")

        # ── Phase 2: build production firmware content ────────────────────────
        ds18b20_array = format_ds18b20_c_array(setup_data["ds18b20"])
        bssid_array = format_bssid_c_array(selected_net["bssid"]) if selected_net else None
        channel = selected_net["channel"] if selected_net else None
        ssid = selected_net["ssid"] if selected_net else None

        final_content = substitute_template(
            SENSOR_SKETCH.read_text(),
            room_number=room_number,
            ds18b20_array=ds18b20_array,
            bssid_array=bssid_array,
            channel=channel,
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
        upsert_csv_row(CSV_PATH, {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "room_number": str(room_number),
            "mac_address": setup_data["mac"] or "",
            "ds18b20_address": setup_data["ds18b20"] or "",
            "location": location,
            "ssid": ssid or "",
            "bssid": selected_net["bssid"] if selected_net else "",
            "channel": str(channel) if channel else "",
        })

        self._clear_step()
        self._log(f"[bold green]━━ Sensor {room_number} programmed successfully! ━━[/bold green]")
        self._log(f"[green]Registry updated: {CSV_PATH}[/green]")
        self.call_from_thread(self._refresh_registry)
        self.call_from_thread(
            self.notify, f"Room {room_number} ready to deploy!", severity="information"
        )


if __name__ == "__main__":
    LTLProgrammerApp().run()
