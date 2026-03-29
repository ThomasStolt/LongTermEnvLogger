# Changelog

## [Unreleased]

## [1.2.0] — 2026-03-29 — Credentials UX, Debug Panel & Code Quality

### Added

- **`tool/ltl_programmer.py`** — Per-location sensor registry
  - Separate `sensors_<location>.csv` per credentials file (e.g. `sensors_home.csv`, `sensors_school.csv`)
  - Auto-creates the CSV when switching credentials if none exists yet
  - Switching credentials in the panel immediately reloads the matching registry

- **`tool/ltl_programmer.py`** — Always-visible Serial Debug panel
  - Dedicated `RichLog` strip at the bottom showing every raw line received from the ESP during setup-sketch read
  - Non-focusable (excluded from Tab order and active-panel highlighting)

- **`tool/ltl_programmer.py`** — Baud rate selector and serial retry loop
  - `Select` widget in the flash overlay lets the user pick 9600 / 74880 / 115200 / 230400 / 460800 baud before flashing
  - On serial read timeout, the overlay re-appears with a "Retry →" button; user can change baud and retry without reflashing

- **`tool/ltl_programmer.py`** — Two-column credentials panel
  - Left column: scrollable file list with `>` indicator and bright-green highlight on selected file; blue "Location / File" sub-header
  - Right column: network info (IP, Network, Gateway, DNS, MQTT Broker) with blue "Contents" sub-header
  - `CredsList` custom widget renders with Rich `Text` (no-wrap, ellipsis overflow)

### Changed

- **`tool/ltl_programmer.py`** — Panel title styling
  - All panel titles always shown with inverted colours (blue background, dark text)
  - Active panel title highlighted in neon yellow (`#ffff00`) matching the active frame border
  - "Status" panel renamed to "System Log"

- **`tool/ltl_programmer.py`** — OTA port filtering
  - `detect_ports()` skips ports where `arduino-cli board list` reports `protocol == "network"`, eliminating OTA device noise from the Serial Ports panel

- **`tool/ltl_programmer.py`** — All UI strings now English
  - Modals (`NewCredentialsModal`, `ConfirmModal`, `RegistryEntryModal`) previously used German labels, buttons, and error messages — all translated
  - Inline comments in `write_credentials_file` translated

### Fixed

- **`tool/ltl_programmer.py`** — Thread safety: `baud_rate` is now read via `_get_baud_rate()` which schedules a `call_from_thread` read, eliminating the DOM race condition in the serial retry worker
- **`tool/ltl_programmer.py`** — `TemporaryDirectory` for production firmware now uses a `with` block — guaranteed cleanup even if compilation or upload raises
- **`tool/ltl_programmer.py`** — `credentials.h` copy in setup sketch directory is now always removed via `try/finally`, even on early-exit compile/upload failures
- **`tool/ltl_programmer.py`** — `write_network_to_credentials` and `write_credentials_file` raise `ValueError` on malformed IP segment counts instead of `IndexError`
- **`tool/ltl_programmer.py`** — `NewCredentialsModal` rejects SSID/password containing `"` to prevent C-string injection in generated `.h` files
- **`tool/ltl_programmer.py`** — Compile error log now shows `stdout` when `stderr` is empty (`arduino-cli` writes error detail to `stdout` in some failure modes)
- **`tool/ltl_programmer.py`** — `detect_ports` now catches all exceptions (not just `FileNotFoundError` and `TimeoutExpired`)
- **`tool/ltl_programmer.py`** — `load_csv_rooms` uses `_room_int` helper — no `ValueError` crash on manually-edited CSVs with non-integer room numbers
- **`tool/ltl_programmer.py`** — `parse_serial_output` guards `int()` conversion on WIFI `channel`/`rssi` fields — malformed ESP lines are silently skipped

### Refactored

- **`tool/ltl_programmer.py`** — `_compile` promoted to module-level `_compile_sketch()` — independently unit-testable, no class dependency
- **`tool/ltl_programmer.py`** — `FlashOverlay` exposes `trigger_continue()` public method; `LTLProgrammerApp.on_key` no longer accesses private `_continue_event` directly
- **`tool/ltl_programmer.py`** — `_PANEL_IDS` no longer includes the debug panel; active-panel CSS for debug removed
- **`tool/ltl_programmer.py`** — Dead attribute `self._button_label` removed from `FlashOverlay.show_instructions`

## [1.1.0] — 2026-03-23 — TUI Panel Highlight & Network Config

### Changed

- **`tool/ltl_programmer.py`** — Visual improvements to panel selection
  - All four panels unified to the same blue (`#89b4fa`) border and title colour
  - Active panel highlighted with a heavy neon-yellow (`#ffff00`) border and filled blue title
  - Initial active panel correctly set to Serial Ports (matching Textual's default focus)
  - Fixed: programmatic `move_cursor()` calls no longer steal the active highlight from the focused panel
  - `_set_active_panel` short-circuits when the panel hasn't changed (eliminates 5 redundant DOM queries per focus event)
  - Panel ID mapping extracted to a class-level constant `_PANEL_IDS`
  - App header styled with a double blue frame and increased height

- **`tool/ltl_programmer.py`** — Network config write-back
  - `write_network_to_credentials()` — writes gateway, DNS, MQTT, and subnet back to `credentials_*.h`
  - Network edit dialog (`NetworkConfigScreen`) for editing config in-TUI

- **`credentials.example.h`** — Gateway and DNS now explicit fields instead of derived from `net_prefix.1`

- **`code/LTL_sensor/LTL_sensor.ino`** — Uses explicit `gw_*` / `dns_*` constants from credentials

## [1.0.0] — 2026-03-23 — Battery Optimization & Programmer Tool

### Added

- **`tool/ltl_programmer.py`** — Interactive TUI programmer tool (Textual, Catppuccin Mocha dark theme)
  - Two-step ESP8266 flash workflow (setup sketch → production firmware)
  - Auto-detection of USB serial ports with live hotplug refresh every 2 s
  - Pre-selection of `usbserial` port and matching credentials SSID
  - Auto-selection of strongest WiFi signal matching the credentials SSID (BSSID pinning)
  - Parallel background compilation while user prepares hardware
  - Continue button disabled until compiler finishes (visual feedback)
  - Combined flash-mode + run-mode instruction screen (single screen per step)
  - Sensor registry panel (newest entry first, timestamp display)
  - CSV upsert — each room appears only once, newest flash overwrites
  - Room number overwrite warning with Enter-to-confirm support
  - Full keyboard navigation: F Flash, R Refresh, Q Quit, Enter Confirm
  - Clean shutdown on Q without hanging background threads

- **`code/LTL_setup/LTL_setup.ino`** — Setup/discovery sketch for ESP8266
  - Reads DS18B20 OneWire address, MAC address, and nearby WiFi networks
  - Outputs structured lines (`MAC:`, `DS18B20:`, `WIFI:`, `SETUP_DONE`) at 115200 baud

- **`code/LTL_sensor/LTL_sensor.ino`** — Optimized production firmware
  - 9-bit DS18B20 resolution (±0.5°C) with async conversion overlapped with WiFi connect
  - Hardcoded DS18B20 address (no bus scan on each wake)
  - Optional BSSID + channel pinning for faster WiFi reconnection (~200–400 ms saved)
  - Low-battery cutoff (ADC threshold, prevents LiIon deep discharge)
  - Publishes temperature and voltage via MQTT
  - Hardware power-off via GPIO15 DONE signal

- **`tool/arduino_config.py`** — Board FQBN and timing constants
- **`tool/requirements.txt`** — Python dependencies (`textual`, `pyserial`, `rich`, `pytest`)
- **`tool/tests/test_utils.py`** — Unit tests for all pure utility functions
- **`credentials.example.h`** — Template for WiFi credentials (never commit real credentials)

### Changed

- README updated: TUI tool documentation, keyboard shortcuts, updated prerequisites (Python 3.10+, `pip install -r tool/requirements.txt`)

---

## [0.2.0] — 2024-03-08 — Hardware Prototyping

- KiCad schematic and PCB layout for sensor hardware
- LiIon battery circuit with protection and solar charging

## [0.1.0] — 2024-03-06 — Initial Firmware

- First working ESP8266 sketch with DS18B20 and MQTT
- WiFi credentials moved to separate `credentials.h` (gitignored)
