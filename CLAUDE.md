# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LongTermEnvLogger is a battery-powered WiFi environmental sensor system for long-term temperature monitoring in buildings. It consists of:
- **ESP8266 firmware** (Arduino/C++) — two sketches: setup discovery and production measurement
- **Python TUI programmer** (`tool/ltl_programmer.py`) — flashes and configures sensors via Textual
- **KiCad PCB** — hardware schematic and layout

## Development Commands

### Python Tool

```bash
# Install dependencies
pip install -r tool/requirements.txt

# Run the programmer TUI
cd tool && python3 ltl_programmer.py

# Run all tests
cd tool && pytest

# Run a single test file
cd tool && pytest tests/test_utils.py -v
```

### Arduino / ESP8266 Firmware

The programmer tool handles compilation internally. For manual operations:

```bash
# Install ESP8266 core (one-time)
arduino-cli core install esp8266:esp8266

# Compile manually
arduino-cli compile --fqbn esp8266:esp8266:generic code/LTL_setup
arduino-cli compile --fqbn esp8266:esp8266:generic code/LTL_sensor

# Upload manually
arduino-cli upload --fqbn esp8266:esp8266:generic --port /dev/ttyUSB0 code/LTL_setup
```

Board FQBN is set in `tool/arduino_config.py`. Common values: `esp8266:esp8266:generic`, `esp8266:esp8266:nodemcuv2`, `esp8266:esp8266:d1_mini`.

## Architecture

### Two-Sketch Workflow

Programming a sensor is always a two-phase process:

1. **LTL_setup.ino** — runs once; discovers MAC address, DS18B20 sensor address, nearby WiFi networks, and tests credentials. Outputs a structured serial protocol (`MAC:`, `DS18B20:`, `WIFI:`, `WIFI_OK/FAIL`, `SETUP_DONE`).
2. **LTL_sensor.ino** — production firmware; pre-configured with all addresses and credentials at compile time. No runtime discovery.

This separation enables firmware optimization: all bus scanning, network scanning, and dynamic configuration is eliminated from the production sketch.

### Production Firmware Cycle

Every ~5 minutes (triggered by external hardware timer):
1. Check battery ADC — power off if below threshold to prevent LiIon deep discharge
2. Start async DS18B20 temperature conversion (9-bit, ~94ms)
3. Connect WiFi + MQTT (conversion runs in background)
4. Read temperature (now ready), publish to `sensor/temp/<room>` and `sensor/volt/<room>`
5. GPIO15 HIGH → external latch circuit cuts power completely

Key pins: GPIO12 (OneWire/DS18B20), GPIO15 (DONE/power-cut), A0 (battery ADC).

Static IP: `192.168.120.<room_number>`. Room number (1–254) also serves as the MQTT topic identifier.

### Programmer Tool (`tool/ltl_programmer.py`)

Textual TUI (Catppuccin Mocha theme) with background worker threads:

- **Utility functions** (pure, unit-tested): `parse_serial_output`, `substitute_template`, `format_ds18b20_c_array`, `find_credentials_files`, `load_csv_rooms`, `upsert_csv_row`, `detect_ports`
- **Parallel compilation**: Compiles firmware in background while user prepares hardware for flashing
- **Sensor registry**: `tool/sensors.csv` (gitignored) — upserted by room number after each successful flash
- **Credential files**: `credentials_*.h` pattern (gitignored); `credentials.example.h` is the template in-repo

### Template Substitution

`substitute_template()` injects room number, DS18B20 address, WiFi SSID/password, and static IP into `LTL_sensor.ino` via regex substitution. The firmware source contains placeholder values that are replaced per-sensor at flash time.

### Testing

Tests cover all pure utility functions in `tool/tests/test_utils.py`. Tests use `pytest` with `tmp_path` fixtures for file-system operations. No mocking of Arduino/serial calls — those are integration concerns handled by the TUI workflow.
