# Design Spec: Battery Optimization & Programmer Tool
**Date:** 2026-03-22
**Project:** LongTermEnvLogger

---

## Overview

This spec covers two related improvements to the LongTermEnvLogger project:

1. **Optimized production firmware** (`LTL_sensor.ino`) — reduces ESP8266 awake time per cycle by ~1050–1480ms through sensor resolution reduction, async measurement overlap, hardcoded sensor address, and optional BSSID/channel pinning.
2. **Interactive programmer tool** (`ltl_programmer.py`) — a Python CLI tool that guides a two-step flash workflow: first a setup sketch to read hardware addresses and scan WiFi, then the final production firmware with all values baked in.

---

## Context

The ESP8266 is woken by external hardware every 5 minutes, measures temperature and battery voltage, publishes both to an MQTT broker, then cuts its own power by setting GPIO15 HIGH. Minimizing awake time directly extends battery life.

The existing code (`LTL_2024_01_07_01.ino`) already uses static IP and WiFi sleep before measurement. The main remaining inefficiencies are:
- DS18B20 operating at 12-bit resolution (750ms conversion, blocking)
- OneWire bus enumeration on every boot (~10–30ms)
- 300ms of post-publish delays of unclear necessity
- No BSSID/channel pinning (channel scan on every WiFi connect, ~200–400ms)

---

## Directory Structure

```
LongTermEnvLogger/
├── code/
│   ├── LTL_sensor/
│   │   └── LTL_sensor.ino          # optimized production firmware
│   └── LTL_setup/
│       └── LTL_setup.ino           # one-time setup sketch for configuration
├── tool/
│   ├── ltl_programmer.py           # interactive programmer tool
│   ├── sensors.csv                 # auto-maintained sensor registry (path relative to script)
│   └── arduino_config.py           # board FQBN and baud rate constants
├── credentials_Home.h              # gitignored, real credentials
├── credentials_School.h            # gitignored, real credentials
├── credentials.example.h           # in repo, template for new setups
└── README.md                       # updated with full workflow documentation
```

---

## Firmware Optimizations (`LTL_sensor.ino`)

### DS18B20 Resolution

Call `sensors.begin()` in `setup()` as before, then immediately call `sensors.setResolution(sensorAddr, 9)` to set 9-bit resolution. This must happen in `setup()`, after `sensors.begin()`, before `loop()` runs. It reduces conversion time from ~750ms to ~94ms.

```cpp
void setup() {
  WiFi.forceSleepBegin();
  sensors.begin();
  sensors.setResolution(sensorAddr, 9);   // set once; persists in sensor EEPROM
  pinMode(DONE, OUTPUT);
}
```

### Async Temperature Conversion

In `loop()`, use `sensors.setWaitForConversion(false)` before `requestTemperatures()`. The conversion runs in the background while WiFi connects (~2s) and the MQTT broker connects. The full blocking conversion time (~750ms at 12-bit) is removed from the critical path.

**Order of operations:**
```
setup():
  1. WiFi.forceSleepBegin()
  2. sensors.begin()
  3. sensors.setResolution(sensorAddr, 9)
  4. pinMode(DONE, OUTPUT)

loop():
  1. ADC voltage read (abort if below volt_limit)
  2. sensors.setWaitForConversion(false)
  3. requestTemperatures()          (returns immediately, starts 94ms conversion)
  4. setup_wifi()                   (~2000ms — conversion completes during this)
  5. reconnect()                    (MQTT connect — additional time buffer)
  6. sensors.getTempC(sensorAddr)   (data already ready; uses address, not index)
  7. publish temp + volt
  8. digitalWrite(DONE, HIGH)
```

**Note:** `getTempC(sensorAddr)` must be used (not `getTempCByIndex(0)`). `getTempCByIndex` triggers a bus re-enumeration and defeats the hardcoded-address optimisation.

**Race condition guard:** If BSSID pinning is enabled and WiFi connects faster than 94ms, the conversion may not be complete when `getTempC()` is called. The `reconnect()` call after `setup_wifi()` adds additional time (its internal `delay(100)` polling loop), but this is not guaranteed to be sufficient if the broker also responds immediately. Therefore: when `USE_BSSID` is defined, place `delay(100)` immediately before `getTempC(sensorAddr)` — after both `setup_wifi()` and `reconnect()` have returned — to guarantee 94ms has elapsed since `requestTemperatures()`. Without BSSID pinning the ~2s WiFi connect time makes this guard unnecessary.

### Hardcoded DS18B20 Address

The sensor address (8 bytes) is stored as a constant. This skips OneWire bus enumeration on every boot (~10–30ms).

```cpp
DeviceAddress sensorAddr = { 0x28, 0xXX, 0xXX, 0xXX, 0xXX, 0xXX, 0xXX, 0xXX };
```

This value is substituted by the programmer tool. See Template Substitution section.

### Optional BSSID/Channel Pinning

A compile-time flag enables BSSID + channel hardcoding, skipping the WiFi channel scan (~200–400ms). Disabled by default.

```cpp
// #define USE_BSSID   // uncomment to enable BSSID/channel pinning
#ifdef USE_BSSID
  const uint8_t wifi_bssid[6] = { 0xXX, 0xXX, 0xXX, 0xXX, 0xXX, 0xXX };
  const int wifi_channel = X;
#endif
```

The `WiFi.begin()` call must also be conditional:

```cpp
#ifdef USE_BSSID
  WiFi.begin(ssid, password, wifi_channel, wifi_bssid);
#else
  WiFi.begin(ssid, password);
#endif
```

When `USE_BSSID` is active, add `delay(100)` immediately before `getTempC(sensorAddr)` in `loop()` (see race condition guard above).

Note: The existing firmware has an unconditional `wifi_bssid` array (unused). The new code replaces this with the `#ifdef USE_BSSID` guard.

### Post-Publish Delays

The `delay(100)` and `delay(200)` after MQTT publishes are commented out. Their original purpose is unknown. A comment marks them for easy re-enabling if publish reliability issues arise.

```cpp
client.publish(temp_topic, tempString);
// delay(100);  // original delay, purpose unknown — re-enable if publish reliability issues occur
client.publish(volt_topic, payload);
// delay(200);  // original delay, purpose unknown — re-enable if publish reliability issues occur
```

### Timing Summary

| Optimisation | Critical-path saving |
|---|---|
| 9-bit + async overlap (removes full 750ms blocking call) | ~750ms |
| Hardcoded DS18B20 address (no bus enumeration) | ~10–30ms |
| Post-publish delays removed | ~300ms |
| **Total (without BSSID pinning)** | **~1060–1080ms** |
| Optional: BSSID/channel pinning | +~200–400ms |
| **Total (with BSSID pinning)** | **~1260–1480ms** |

---

## Setup Sketch (`LTL_setup.ino`)

Flashed once before the production firmware. On boot it outputs structured data over Serial at **115200 baud**.

### Output Format

Each line is prefixed with a token. The tool parses by prefix.

**MAC address** (one line):
```
MAC:AA:BB:CC:DD:EE:FF
```

**DS18B20 address** (one line, 8 bytes as uppercase hex, comma-separated, C-array style):
```
DS18B20:0x28,0xFF,0xA1,0xB2,0xC3,0xD4,0xE5,0x06
```

**WiFi networks** (one line per network, pipe-delimited fields: SSID|BSSID|channel|RSSI):
```
WIFI:MyNetwork|AA:BB:CC:DD:EE:FF|6|-72
WIFI:OtherNet|11:22:33:44:55:66|11|-85
```

**End marker** (signals all data has been sent):
```
SETUP_DONE
```

### Error Outputs

If no DS18B20 is found on the bus:
```
DS18B20:NOT_FOUND
```

If WiFi scan returns zero results:
```
WIFI:NONE
```

---

## Programmer Tool (`ltl_programmer.py`)

**Requirements:** Python 3.8+, `rich`, `pyserial`, `arduino-cli` in PATH.

### Board Configuration (`arduino_config.py`)

```python
BOARD_FQBN = "esp8266:esp8266:generic"   # adjust for your ESP8266 variant
BAUD_RATE = 115200
SERIAL_TIMEOUT_S = 30  # seconds to wait for SETUP_DONE before aborting
```

The FQBN can also be auto-detected via `arduino-cli board list` after connecting the device; the tool attempts auto-detection first and falls back to the configured constant.

### Tool Workflow

```
Step 1 — Hardware selection
  ├── Run `arduino-cli board list` to detect connected boards
  ├── Also enumerate serial ports via pyserial
  ├── Merge both lists into a single numbered list, deduplicated by port name
  │    (arduino-cli entry takes precedence when a port appears in both lists)
  └── User selects port (numbered list)

Step 2 — Location / credentials selection
  ├── Scan for credentials_*.h files in project root (relative to script location)
  └── User selects location (e.g. Home, School)

Step 3 — Flash setup sketch
  └── arduino-cli compile --fqbn <FQBN> + upload --port <PORT> LTL_setup.ino
      Error: if arduino-cli not found → print install instructions and abort

Step 4 — Read setup data (serial, timeout = SERIAL_TIMEOUT_S)
  ├── Read lines until SETUP_DONE or timeout
  ├── On timeout → print error, suggest checking baud rate and boot mode, abort
  ├── Parse MAC:     → store and display
  ├── Parse DS18B20: → if NOT_FOUND → print error "No DS18B20 detected", abort
  ├── Parse WIFI:    → collect all networks
  └── If WIFI:NONE   → print warning "No WiFi networks found", BSSID selection skipped

Step 5 — Configuration
  ├── Display WiFi networks as colored rich table (columns: #, SSID, BSSID, Ch, Signal bar)
  ├── Ask: "Select network number for BSSID pinning, or press Enter to skip"
  │    └── If skipped: BSSID/channel columns in CSV are written as empty string ""
  └── Enter room number (validated: integer 1–254, checked for uniqueness in sensors.csv)

Step 6 — Build and flash production firmware
  ├── Copy code/LTL_sensor/LTL_sensor.ino to a temp build directory
  ├── Apply template substitutions (see Template Substitution section)
  ├── Copy selected credentials_<location>.h to temp dir as credentials.h
  ├── arduino-cli compile + upload from temp dir
  └── On success: print confirmation panel

Step 7 — Update sensor registry
  └── Append row to tool/sensors.csv (path relative to script location)
```

### Template Substitution

`LTL_sensor.ino` contains placeholder tokens (C-style comments) that the tool replaces with `str.replace()`:

| Placeholder in .ino | Replaced with |
|---|---|
| `/*ROOM_NUMBER*/101` | actual room number |
| `/*DS18B20_ADDR*/{ 0x28, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 }` | sensor address bytes |
| `// #define USE_BSSID` | `#define USE_BSSID` (if BSSID selected) |
| `/*BSSID*/{ 0x00,0x00,0x00,0x00,0x00,0x00 }` | selected BSSID bytes |
| `/*WIFI_CHANNEL*/1` | selected channel number |

The placeholder includes a default value so the template `.ino` compiles standalone in Arduino IDE without substitution.

**When BSSID pinning is skipped:** only the `USE_BSSID` line substitution is omitted (the line stays commented out). The `/*BSSID*/` and `/*WIFI_CHANNEL*/` placeholders are inside the disabled `#ifdef USE_BSSID` block and are compiled out — the tool does not need to substitute them in this case.

### CSV Schema

File: `tool/sensors.csv` (relative to script location).

```
timestamp,room_number,mac_address,ds18b20_address,location,ssid,bssid,channel
2026-03-22T14:30:00,101,AA:BB:CC:DD:EE:FF,0x28:0xFF:...,Home,MyNetwork,EE:55:A8:2C:A8:64,6
```

One row per programming event. Multiple rows for the same room number are allowed (history preserved). The tool warns if a room number already exists in the CSV and asks for confirmation before proceeding.

---

## Credentials Management

### File Format

`credentials_<location>.h`:
```cpp
const char* ssid = "MyNetwork";
const char* password = "MyPassword";
```

### Build-time inclusion

The tool copies the selected `credentials_<location>.h` to the temp build directory as `credentials.h`. The sketch `#include "credentials.h"` therefore always resolves. The original location-named file is never modified.

### Repository

- `credentials_*.h` files are listed in `.gitignore`
- `credentials.example.h` is committed as a template with placeholder values
- `README.md` documents: copy example → rename to `credentials_<location>.h` → fill in real values

---

## README Updates

The README will document:
1. **Prerequisites:** `arduino-cli` (with ESP8266 core installed), Python 3.8+, `pip install rich pyserial`
2. **Credentials setup:** copy `credentials.example.h`, rename to `credentials_<location>.h`, fill in values
3. **Full programmer tool workflow:** step-by-step with expected terminal output
4. **`arduino_config.py`:** how to set the correct FQBN for your ESP8266 variant
5. **Manual flash fallback:** for environments without arduino-cli

---

## Out of Scope

- No OTA update support
- No change to MQTT topic structure
- No change to 5-minute wake interval (controlled by external hardware)
- `volt_limit` constant remains hardcoded in the sketch (not configurable via tool)
- No Windows-specific serial port handling beyond what pyserial provides natively
