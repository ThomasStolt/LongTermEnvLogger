# Changelog

## [Unreleased]

## [2026-03-23] — Battery Optimization & Programmer Tool

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

## [2024-03-08] — Hardware Prototyping

- KiCad schematic and PCB layout for sensor hardware
- LiIon battery circuit with protection and solar charging

## [2024-03-06] — Initial Firmware

- First working ESP8266 sketch with DS18B20 and MQTT
- WiFi credentials moved to separate `credentials.h` (gitignored)
