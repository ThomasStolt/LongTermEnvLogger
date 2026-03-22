# Battery Optimization & Programmer Tool — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce ESP8266 awake time by ~1050–1480ms per 5-minute cycle and provide an interactive Python tool that flashes setup + production firmware with all sensor-specific values baked in.

**Architecture:** Two Arduino sketches (setup sketch outputs hardware info over serial; production sketch has hardcoded DS18B20 address, room number, optional BSSID). Python tool orchestrates two-step flash via arduino-cli, reads serial data, substitutes template placeholders, and maintains a CSV sensor registry.

**Tech Stack:** Arduino/ESP8266, C++, Python 3.8+, `rich`, `pyserial`, `pytest`, `arduino-cli`

**Spec:** `docs/superpowers/specs/2026-03-22-battery-optimization-programmer-tool-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `code/LTL_sensor/LTL_sensor.ino` | Create | Optimized production firmware template |
| `code/LTL_setup/LTL_setup.ino` | Create | One-time setup sketch (MAC, DS18B20 addr, WiFi scan) |
| `tool/ltl_programmer.py` | Create | Interactive two-step programmer tool |
| `tool/arduino_config.py` | Create | Board FQBN, baud rate, timeout constants |
| `tool/requirements.txt` | Create | Python dependencies |
| `tool/tests/__init__.py` | Create | Makes tests a package |
| `tool/tests/test_utils.py` | Create | Unit tests for all pure utility functions |
| `credentials.example.h` | Create | Credential template for the repository |
| `.gitignore` | Modify | Add `credentials_*.h` pattern |
| `README.md` | Modify | Add programmer tool workflow section |

---

## Task 1: Project Scaffolding

**Files:**
- Modify: `.gitignore`
- Create: `credentials.example.h`
- Create: `tool/requirements.txt`
- Create: `tool/pytest.ini`
- Create: `tool/tests/__init__.py`

- [ ] **Step 1: Update .gitignore**

Replace current content of `.gitignore`:
```
credentials.h
credentials_*.h
.DS_Store
tool/sensors.csv
```

- [ ] **Step 2: Create credentials.example.h**

Create `credentials.example.h` in project root:
```cpp
// Copy this file to credentials_<location>.h (e.g. credentials_Home.h)
// and fill in your WiFi credentials.
// credentials_*.h files are gitignored — never commit real credentials.
const char* ssid = "YOUR_SSID_HERE";
const char* password = "YOUR_PASSWORD_HERE";
```

- [ ] **Step 3: Create tool/requirements.txt**

```
rich>=13.0.0
pyserial>=3.5
pytest>=7.0.0
```

- [ ] **Step 4: Create tool/pytest.ini**

```ini
[pytest]
testpaths = tests
```

- [ ] **Step 5: Create tool/tests/__init__.py**

Empty file:
```python
```

- [ ] **Step 6: Install dependencies**

```bash
cd tool && pip install -r requirements.txt
```

Expected: packages install without errors.

- [ ] **Step 7: Commit**

```bash
git add .gitignore credentials.example.h tool/requirements.txt tool/pytest.ini tool/tests/__init__.py
git commit -m "feat: add project scaffolding for programmer tool"
```

---

## Task 2: LTL_sensor.ino — Optimized Production Firmware

**Files:**
- Create: `code/LTL_sensor/LTL_sensor.ino`

This is the production firmware template. Placeholders (C-style comment tokens before default values) are substituted by `ltl_programmer.py` at flash time.

- [ ] **Step 1: Create code/LTL_sensor/LTL_sensor.ino**

```cpp
#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include "credentials.h"

// Room number — substituted by ltl_programmer.py (must be 1–254, used as IP last octet)
const int roomNumber = /*ROOM_NUMBER*/101;

// DS18B20 sensor address — substituted by ltl_programmer.py
// Flash LTL_setup.ino once to discover this address
DeviceAddress sensorAddr = /*DS18B20_ADDR*/{ 0x28, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 };

// Voltage limit (~2.7V) — prevents LiIon deep discharge
const int volt_limit = 560;

// Static IP (last octet = room number)
IPAddress staticIP(192, 168, 120, roomNumber);
IPAddress gateway(192, 168, 120, 1);
IPAddress subnet(255, 255, 255, 0);
IPAddress dns(192, 168, 120, 1);

// Optional BSSID/channel pinning — saves ~200-400ms per cycle by skipping WiFi channel scan.
// Only reliable with a single fixed access point on a manually configured fixed channel.
// ltl_programmer.py uncomments this line when a BSSID is selected during programming.
// #define USE_BSSID
#ifdef USE_BSSID
  const uint8_t wifi_bssid[6] = /*BSSID*/{ 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 };
  const int wifi_channel = /*WIFI_CHANNEL*/1;
#endif

const char* mqtt_server = "192.168.120.2";
const int mqtt_port = 1883;
char temp_topic[30];
char volt_topic[30];

#define ONE_WIRE_BUS 12
#define DONE 15
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

WiFiClient espClient;
PubSubClient client(espClient);

void setup_wifi() {
  unsigned long startAttemptTime = millis();
  WiFi.forceSleepWake();
  char hostname[11];
  sprintf(hostname, "sensor_%03d", roomNumber);
  WiFi.hostname(hostname);
  WiFi.config(staticIP, gateway, subnet, dns);
#ifdef USE_BSSID
  WiFi.begin(ssid, password, wifi_channel, wifi_bssid);
#else
  WiFi.begin(ssid, password);
#endif
  while (WiFi.status() != WL_CONNECTED && millis() - startAttemptTime < 5000) {
    delay(100);
  }
  if (WiFi.status() != WL_CONNECTED) {
    digitalWrite(DONE, HIGH);
    return;  // hardware cuts power immediately; return ensures no further code runs
  }
}

void reconnect() {
  char clientId[20];
  sprintf(clientId, "room_%03d", roomNumber);
  sprintf(temp_topic, "sensor/temp/%03d", roomNumber);
  sprintf(volt_topic, "sensor/volt/%03d", roomNumber);
  client.setServer(mqtt_server, mqtt_port);
  unsigned long startAttemptTime = millis();  // unsigned long matches millis() return type
  while (!client.connected()) {
    if (client.connect(clientId)) {
      break;
    } else {
      delay(100);
      if (millis() - startAttemptTime > 5000) {
        digitalWrite(DONE, HIGH);
        return;  // hardware cuts power immediately; return ensures no further code runs
      }
    }
  }
}

void setup() {
  WiFi.forceSleepBegin();
  sensors.begin();
  sensors.setResolution(sensorAddr, 9);  // 9-bit: ~94ms conversion, ±0.5°C. Persists in sensor EEPROM.
  pinMode(DONE, OUTPUT);
}

void loop() {
  // Check battery voltage — power off immediately if below deep-discharge limit
  int adcValue = analogRead(A0);
  if (adcValue < volt_limit) {
    digitalWrite(DONE, HIGH);
    return;
  }
  char voltPayload[5];
  snprintf(voltPayload, sizeof(voltPayload), "%d", adcValue);

  // Start async temperature conversion (94ms at 9-bit resolution).
  // WiFi + MQTT connect (~2s total) runs while the DS18B20 converts in the background,
  // so the conversion adds zero time to the critical path.
  sensors.setWaitForConversion(false);
  sensors.requestTemperatures();

  setup_wifi();
  if (!client.connected()) { reconnect(); }
  client.loop();

#ifdef USE_BSSID
  // With BSSID pinning, WiFi may connect in <94ms — add guard to ensure conversion is complete.
  delay(100);
#endif

  // Read temperature — conversion guaranteed complete by now
  float temperature = sensors.getTempC(sensorAddr);
  char tempString[8];
  dtostrf(temperature, 1, 2, tempString);

  client.publish(temp_topic, tempString);
  // delay(100);  // original delay — purpose unknown; re-enable if publish reliability issues occur
  client.publish(volt_topic, voltPayload);
  // delay(200);  // original delay — purpose unknown; re-enable if publish reliability issues occur

  // Cut power to the entire circuit
  digitalWrite(DONE, HIGH);
}
```

- [ ] **Step 2: Verify the template compiles in Arduino IDE (manual check)**

Open `code/LTL_sensor/LTL_sensor.ino` in Arduino IDE with a `credentials.h` present. It should compile without errors. The default DS18B20 placeholder address `{ 0x28, 0x00, ... }` is valid C++ and will compile fine (it just won't work until substituted).

- [ ] **Step 3: Commit**

```bash
git add code/LTL_sensor/LTL_sensor.ino
git commit -m "feat: add optimized LTL_sensor firmware template with async DS18B20 and placeholder tokens"
```

---

## Task 3: LTL_setup.ino — Setup Sketch

**Files:**
- Create: `code/LTL_setup/LTL_setup.ino`

This sketch runs once during programming. It outputs MAC address, DS18B20 address, and WiFi scan results over serial at 115200 baud. It does **not** need `credentials.h` (it scans WiFi without connecting).

- [ ] **Step 1: Create code/LTL_setup/LTL_setup.ino**

```cpp
#include <ESP8266WiFi.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// LTL Setup Sketch
// Flash once to discover DS18B20 address, ESP MAC address, and nearby WiFi networks.
// Output is read by ltl_programmer.py to configure the production firmware.
// Serial: 115200 baud. Output ends with SETUP_DONE.

#define ONE_WIRE_BUS 12
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

void setup() {
  Serial.begin(115200);
  delay(500);  // Let serial port stabilise after boot

  // MAC address
  WiFi.mode(WIFI_STA);
  Serial.print("MAC:");
  Serial.println(WiFi.macAddress());

  // DS18B20 address
  sensors.begin();
  if (sensors.getDeviceCount() == 0) {
    Serial.println("DS18B20:NOT_FOUND");
  } else {
    DeviceAddress addr;
    sensors.getAddress(addr, 0);
    Serial.print("DS18B20:");
    for (int i = 0; i < 8; i++) {
      if (i > 0) Serial.print(",");
      Serial.print("0x");
      if (addr[i] < 0x10) Serial.print("0");  // zero-pad single hex digits
      Serial.print(addr[i], HEX);
    }
    Serial.println();
  }

  // WiFi scan (no connection needed — passive scan only)
  int n = WiFi.scanNetworks();
  if (n == 0) {
    Serial.println("WIFI:NONE");
  } else {
    for (int i = 0; i < n; i++) {
      // Format: WIFI:SSID|BSSID|channel|RSSI
      Serial.print("WIFI:");
      Serial.print(WiFi.SSID(i));
      Serial.print("|");
      Serial.print(WiFi.BSSIDstr(i));
      Serial.print("|");
      Serial.print(WiFi.channel(i));
      Serial.print("|");
      Serial.println(WiFi.RSSI(i));
    }
  }

  Serial.println("SETUP_DONE");
}

void loop() {}  // nothing to do after setup
```

- [ ] **Step 2: Verify the sketch compiles in Arduino IDE (manual check)**

No `credentials.h` needed. Should compile cleanly.

- [ ] **Step 3: Commit**

```bash
git add code/LTL_setup/LTL_setup.ino
git commit -m "feat: add LTL_setup sketch for hardware discovery"
```

---

## Task 4: Tool Foundation — arduino_config.py and ltl_programmer.py Skeleton

**Files:**
- Create: `tool/arduino_config.py`
- Create: `tool/ltl_programmer.py`

- [ ] **Step 1: Create tool/arduino_config.py**

```python
# arduino_config.py — board configuration for ltl_programmer.py
# Adjust BOARD_FQBN to match your ESP8266 variant.
# Common values:
#   esp8266:esp8266:generic          — bare ESP-01/ESP-12 modules
#   esp8266:esp8266:nodemcuv2        — NodeMCU v2 / Lolin
#   esp8266:esp8266:d1_mini          — Wemos D1 Mini
BOARD_FQBN = "esp8266:esp8266:generic"
BAUD_RATE = 115200
SERIAL_TIMEOUT_S = 30  # seconds to wait for SETUP_DONE before aborting
BOOT_DELAY_S = 2       # seconds to wait for ESP8266 to boot after upload
```

- [ ] **Step 2: Create tool/ltl_programmer.py skeleton**

```python
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
```

- [ ] **Step 3: Verify the skeleton runs**

```bash
cd tool && python ltl_programmer.py
```

Expected: prints the cyan header panel and the "Not yet implemented" message.

- [ ] **Step 4: Commit**

```bash
git add tool/arduino_config.py tool/ltl_programmer.py
git commit -m "feat: add tool foundation — arduino_config.py and ltl_programmer.py skeleton"
```

---

## Task 5: Serial Output Parser (TDD)

**Files:**
- Modify: `tool/ltl_programmer.py` (add `parse_serial_output`)
- Modify: `tool/tests/test_utils.py` (add parser tests)

- [ ] **Step 1: Write failing tests**

Create `tool/tests/test_utils.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ltl_programmer import parse_serial_output


def test_parse_full_output():
    lines = [
        "MAC:AA:BB:CC:DD:EE:FF",
        "DS18B20:0x28,0xFF,0xA1,0xB2,0xC3,0xD4,0xE5,0x06",
        "WIFI:HomeNet|AA:BB:CC:DD:EE:FF|6|-72",
        "WIFI:OtherNet|11:22:33:44:55:66|11|-85",
        "SETUP_DONE",
    ]
    result = parse_serial_output(lines)
    assert result["mac"] == "AA:BB:CC:DD:EE:FF"
    assert result["ds18b20"] == "0x28,0xFF,0xA1,0xB2,0xC3,0xD4,0xE5,0x06"
    assert result["ds18b20_error"] is False
    assert len(result["wifi_networks"]) == 2
    assert result["wifi_networks"][0] == {
        "ssid": "HomeNet", "bssid": "AA:BB:CC:DD:EE:FF", "channel": 6, "rssi": -72
    }
    assert result["wifi_none"] is False
    assert result["done"] is True


def test_parse_ds18b20_not_found():
    lines = ["MAC:AA:BB:CC:DD:EE:FF", "DS18B20:NOT_FOUND", "WIFI:NONE", "SETUP_DONE"]
    result = parse_serial_output(lines)
    assert result["ds18b20_error"] is True
    assert result["ds18b20"] is None
    assert result["wifi_none"] is True
    assert result["wifi_networks"] == []


def test_parse_incomplete_output():
    """Partial output — SETUP_DONE not yet received."""
    lines = ["MAC:AA:BB:CC:DD:EE:FF"]
    result = parse_serial_output(lines)
    assert result["mac"] == "AA:BB:CC:DD:EE:FF"
    assert result["done"] is False


def test_parse_crlf_line_endings():
    """Serial ports often produce \\r\\n — strip() must handle it."""
    lines = ["MAC:AA:BB:CC:DD:EE:FF\r", "SETUP_DONE\r"]
    result = parse_serial_output(lines)
    assert result["mac"] == "AA:BB:CC:DD:EE:FF"
    assert result["done"] is True
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd tool && pytest tests/test_utils.py -v
```

Expected: `ImportError` or `AttributeError` — `parse_serial_output` not yet defined.

- [ ] **Step 3: Add parse_serial_output to ltl_programmer.py**

Add under the `# ── Pure utility functions` comment:

```python
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
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd tool && pytest tests/test_utils.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tool/ltl_programmer.py tool/tests/test_utils.py
git commit -m "feat: add serial output parser with tests"
```

---

## Task 6: Address Formatter Utilities (TDD)

**Files:**
- Modify: `tool/ltl_programmer.py` (add `format_ds18b20_c_array`, `format_bssid_c_array`)
- Modify: `tool/tests/test_utils.py`

- [ ] **Step 1: Add failing tests to test_utils.py**

Append to `tool/tests/test_utils.py`:

```python
from ltl_programmer import format_ds18b20_c_array, format_bssid_c_array


def test_format_ds18b20_c_array():
    raw = "0x28,0xFF,0xA1,0xB2,0xC3,0xD4,0xE5,0x06"
    assert format_ds18b20_c_array(raw) == "{ 0x28, 0xFF, 0xA1, 0xB2, 0xC3, 0xD4, 0xE5, 0x06 }"


def test_format_ds18b20_c_array_wrong_length():
    import pytest
    with pytest.raises(ValueError, match="8 bytes"):
        format_ds18b20_c_array("0x28,0xFF,0xA1,0xB2,0xC3,0xD4,0xE5")  # only 7 bytes


def test_format_bssid_c_array():
    assert format_bssid_c_array("AA:BB:CC:DD:EE:FF") == "{ 0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF }"


def test_format_bssid_c_array_lowercase():
    """pyserial/ESP may return lowercase hex — must uppercase."""
    assert format_bssid_c_array("aa:bb:cc:dd:ee:ff") == "{ 0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF }"
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd tool && pytest tests/test_utils.py -v
```

Expected: 3 new tests fail with `ImportError`.

- [ ] **Step 3: Add formatter functions to ltl_programmer.py**

Add after `parse_serial_output`:

```python
def format_ds18b20_c_array(raw: str) -> str:
    """Convert DS18B20 serial format to C array literal.

    '0x28,0xFF,0xA1,0xB2,0xC3,0xD4,0xE5,0x06' → '{ 0x28, 0xFF, ... }'
    Raises ValueError if the address does not contain exactly 8 bytes.
    """
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 8:
        raise ValueError(f"DS18B20 address must be 8 bytes, got {len(parts)}: {raw!r}")
    return "{ " + ", ".join(parts) + " }"


def format_bssid_c_array(bssid: str) -> str:
    """Convert BSSID string to C array literal.

    'AA:BB:CC:DD:EE:FF' → '{ 0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF }'
    """
    parts = [f"0x{b.upper()}" for b in bssid.split(":")]
    return "{ " + ", ".join(parts) + " }"
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
cd tool && pytest tests/test_utils.py -v
```

Expected: all tests up to this point PASS.

- [ ] **Step 5: Commit**

```bash
git add tool/ltl_programmer.py tool/tests/test_utils.py
git commit -m "feat: add DS18B20 and BSSID address formatter utilities with tests"
```

---

## Task 7: Template Substitution (TDD)

**Files:**
- Modify: `tool/ltl_programmer.py` (add `substitute_template`)
- Modify: `tool/tests/test_utils.py`

- [ ] **Step 1: Add failing tests**

Append to `tool/tests/test_utils.py`:

```python
from ltl_programmer import substitute_template

TEMPLATE = """\
const int roomNumber = /*ROOM_NUMBER*/101;
DeviceAddress sensorAddr = /*DS18B20_ADDR*/{ 0x28, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 };
// #define USE_BSSID
#ifdef USE_BSSID
  const uint8_t wifi_bssid[6] = /*BSSID*/{ 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 };
  const int wifi_channel = /*WIFI_CHANNEL*/1;
#endif
"""


def test_substitute_room_and_ds18b20():
    result = substitute_template(
        TEMPLATE,
        room_number=202,
        ds18b20_array="{ 0x28, 0xFF, 0xA1, 0xB2, 0xC3, 0xD4, 0xE5, 0x06 }",
    )
    assert "/*ROOM_NUMBER*/202" in result
    assert "/*DS18B20_ADDR*/{ 0x28, 0xFF, 0xA1" in result
    assert "// #define USE_BSSID" in result  # BSSID not selected — stays commented


def test_substitute_with_bssid():
    result = substitute_template(
        TEMPLATE,
        room_number=101,
        ds18b20_array="{ 0x28, 0xFF, 0xA1, 0xB2, 0xC3, 0xD4, 0xE5, 0x06 }",
        bssid_array="{ 0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF }",
        channel=6,
    )
    assert "#define USE_BSSID" in result
    assert "// #define USE_BSSID" not in result  # comment removed
    assert "/*BSSID*/{ 0xAA, 0xBB" in result
    assert "/*WIFI_CHANNEL*/6" in result


def test_substitute_room_number_range():
    """Room 1 and 254 are boundary values."""
    for room in (1, 254):
        result = substitute_template(TEMPLATE, room_number=room, ds18b20_array="{ 0x28, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 }")
        assert f"/*ROOM_NUMBER*/{room}" in result


def test_substitute_bssid_only_no_substitution():
    """Passing bssid_array without channel (or vice versa) leaves USE_BSSID commented out."""
    result = substitute_template(
        TEMPLATE,
        room_number=101,
        ds18b20_array="{ 0x28, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 }",
        bssid_array="{ 0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF }",
        channel=None,  # channel missing — pinning should NOT be activated
    )
    assert "// #define USE_BSSID" in result  # must stay commented
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd tool && pytest tests/test_utils.py -v
```

- [ ] **Step 3: Add substitute_template to ltl_programmer.py**

```python
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
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
cd tool && pytest tests/test_utils.py -v
```

Expected: all tests up to this point PASS.

- [ ] **Step 5: Commit**

```bash
git add tool/ltl_programmer.py tool/tests/test_utils.py
git commit -m "feat: add template substitution with tests"
```

---

## Task 8: CSV Handler and Credentials Finder (TDD)

**Files:**
- Modify: `tool/ltl_programmer.py` (add `find_credentials_files`, `load_csv_rooms`, `append_csv_row`)
- Modify: `tool/tests/test_utils.py`

- [ ] **Step 1: Add failing tests**

Append to `tool/tests/test_utils.py`:

```python
import csv
import tempfile
from pathlib import Path
from ltl_programmer import find_credentials_files, load_csv_rooms, append_csv_row, CSV_FIELDNAMES


def test_find_credentials_files(tmp_path):
    (tmp_path / "credentials_Home.h").write_text('const char* ssid = "x";')
    (tmp_path / "credentials_School.h").write_text('const char* ssid = "y";')
    (tmp_path / "credentials.example.h").write_text("example")
    locations = find_credentials_files(tmp_path)
    assert set(locations) == {"Home", "School"}
    assert "example" not in locations  # example file excluded


def test_find_credentials_files_empty(tmp_path):
    assert find_credentials_files(tmp_path) == []


def test_load_csv_rooms_nonexistent(tmp_path):
    assert load_csv_rooms(tmp_path / "sensors.csv") == set()


def test_load_csv_rooms_with_data(tmp_path):
    csv_path = tmp_path / "sensors.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        w.writeheader()
        w.writerow({"room_number": "101", "mac_address": "AA:BB:CC:DD:EE:FF",
                    "ds18b20_address": "", "location": "Home", "ssid": "",
                    "bssid": "", "channel": "", "timestamp": "2026-01-01T00:00:00"})
        w.writerow({"room_number": "202", "mac_address": "11:22:33:44:55:66",
                    "ds18b20_address": "", "location": "School", "ssid": "",
                    "bssid": "", "channel": "", "timestamp": "2026-01-02T00:00:00"})
    assert load_csv_rooms(csv_path) == {101, 202}


def test_append_csv_row_creates_file(tmp_path):
    csv_path = tmp_path / "sensors.csv"
    row = {"timestamp": "2026-03-22T14:30:00", "room_number": "101",
           "mac_address": "AA:BB:CC:DD:EE:FF", "ds18b20_address": "0x28,0xFF",
           "location": "Home", "ssid": "HomeNet", "bssid": "AA:BB:CC:DD:EE:FF", "channel": "6"}
    append_csv_row(csv_path, row)
    assert csv_path.exists()
    with open(csv_path) as f:
        lines = f.readlines()
    assert lines[0].startswith("timestamp")  # header present
    assert "101" in lines[1]


def test_append_csv_row_no_duplicate_header(tmp_path):
    csv_path = tmp_path / "sensors.csv"
    row = {"timestamp": "t", "room_number": "1", "mac_address": "", "ds18b20_address": "",
           "location": "", "ssid": "", "bssid": "", "channel": ""}
    append_csv_row(csv_path, row)
    append_csv_row(csv_path, row)
    with open(csv_path) as f:
        lines = [l for l in f.readlines() if l.strip()]
    # 1 header + 2 data rows = 3 lines
    assert len(lines) == 3
    assert lines[0].startswith("timestamp")
    assert lines[1].startswith("t")
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd tool && pytest tests/test_utils.py -v
```

- [ ] **Step 3: Add CSV and credentials functions to ltl_programmer.py**

```python
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
```

- [ ] **Step 4: Run all tests — expect all pass**

```bash
cd tool && pytest tests/test_utils.py -v
```

Expected: all 18 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tool/ltl_programmer.py tool/tests/test_utils.py
git commit -m "feat: add CSV handler and credentials finder with tests"
```

---

## Task 9: UI — Port Detection and Credentials Selection

**Files:**
- Modify: `tool/ltl_programmer.py` (add `detect_ports`, `select_port`, `select_credentials`)

These functions interact with the user — no automated tests. Verify manually.

- [ ] **Step 1: Add port detection and UI functions to ltl_programmer.py**

Add under `# ── UI functions`:

```python
def _rssi_bar(rssi: int) -> str:
    """Render a 5-block signal strength bar with color."""
    strength = min(max(rssi + 100, 0), 60) / 60
    bars = max(1, int(strength * 5))
    color = ["red", "red", "yellow", "green", "green"][min(bars - 1, 4)]
    return f"[{color}]{'█' * bars}{'░' * (5 - bars)}[/{color}] {rssi} dBm"


def detect_ports() -> list:
    """Return merged list of dicts with keys: port, description, fqbn.

    Runs `arduino-cli board list` first (gives FQBN for known boards).
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
```

- [ ] **Step 2: Manual verification**

Update `main()` temporarily to call these functions:
```python
def main():
    console.print(Panel.fit("[bold cyan]LTL Sensor Programmer[/bold cyan]", border_style="cyan"))
    port_info = select_port()
    location, cred_path = select_credentials()
    console.print(f"Port: {port_info['port']}, Credentials: {cred_path}")
```

Run `python ltl_programmer.py` with an ESP8266 connected. Verify:
- Port table shows connected device
- Credentials table shows your `credentials_*.h` files
- Selection works correctly

Revert the temporary main() change after verification (it will be replaced in Task 12).

- [ ] **Step 3: Commit**

```bash
git add tool/ltl_programmer.py
git commit -m "feat: add port detection and credentials selection UI"
```

---

## Task 10: UI — Flash Setup Sketch and Read Serial Data

**Files:**
- Modify: `tool/ltl_programmer.py` (add `flash_sketch`, `read_setup_data`)

- [ ] **Step 1: Add arduino-cli flash function**

Add under `# ── arduino-cli functions`:

```python
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
```

- [ ] **Step 2: Add serial reader function**

```python
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
        "[red]Timeout — no SETUP_DONE received within "
        f"{SERIAL_TIMEOUT_S}s.[/red]\n"
        "Troubleshooting:\n"
        "  • Verify baud rate is 115200 in arduino_config.py\n"
        "  • Ensure device booted in run mode (not flash mode)\n"
        "  • Check that the correct port was selected"
    )
    sys.exit(1)
```

- [ ] **Step 3: Manual verification with hardware**

Temporarily in `main()`:
```python
port_info = select_port()
location, cred_path = select_credentials()
fqbn = _resolve_fqbn(port_info["fqbn"])
flash_sketch(SETUP_SKETCH_DIR, port_info["port"], fqbn)
import time; time.sleep(2)  # wait for ESP8266 to boot
data = read_setup_data(port_info["port"])
console.print(data)
```

Run and verify:
- Sketch compiles and uploads
- MAC address printed correctly
- DS18B20 address printed (or NOT_FOUND if no sensor connected)
- WiFi networks listed

Revert temporary main() after verification.

- [ ] **Step 4: Commit**

```bash
git add tool/ltl_programmer.py
git commit -m "feat: add arduino-cli flash and serial data reader"
```

---

## Task 11: UI — WiFi Table Display and Configuration Input

**Files:**
- Modify: `tool/ltl_programmer.py` (add `display_setup_results`, `get_configuration`)

- [ ] **Step 1: Add display and input functions**

```python
def display_setup_results(data: dict) -> None:
    """Display MAC address and WiFi networks from setup data."""
    console.print(Panel(
        f"[bold]MAC Address:[/bold] [cyan]{data['mac']}[/cyan]",
        title="ESP8266 Hardware Info",
        border_style="green",
    ))

    if data["ds18b20_error"]:
        console.print("[red]DS18B20 not found on OneWire bus.[/red] "
                      "Check wiring (data wire to GPIO12, 4.7kΩ pull-up to 3.3V).")
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
    # BSSID selection
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

    # Room number
    while True:
        room_number = IntPrompt.ask("\nEnter room number", default=101)
        if not (1 <= room_number <= 254):
            console.print("[red]Room number must be between 1 and 254.[/red]")
            continue
        if room_number in existing_rooms:
            console.print(
                f"[yellow]Room {room_number} already exists in sensors.csv.[/yellow]"
            )
            if not Confirm.ask("Continue anyway?", default=False):
                continue
        break

    return {"room_number": room_number, "bssid": bssid, "channel": channel, "ssid": ssid}
```

- [ ] **Step 2: Manual verification with hardware**

Temporarily call `display_setup_results(data)` and `get_configuration(data, set())` in main() with real data from Task 10 verification. Verify the WiFi table renders with colored signal bars, BSSID selection works, room number validation rejects 0 and 255.

- [ ] **Step 3: Commit**

```bash
git add tool/ltl_programmer.py
git commit -m "feat: add WiFi display and configuration input UI"
```

---

## Task 12: UI — Generate + Flash Production Firmware + Update CSV + main()

**Files:**
- Modify: `tool/ltl_programmer.py` (add `build_and_flash_production`, complete `main()`)

- [ ] **Step 1: Add production firmware builder**

```python
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
```

- [ ] **Step 2: Complete main()**

Replace the placeholder `main()` with:

```python
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

    # Step 4 — Read setup data
    time.sleep(BOOT_DELAY_S)  # wait for ESP8266 to boot after upload
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
    ssid = config["ssid"] or ""
    row = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "room_number": str(config["room_number"]),
        "mac_address": setup_data["mac"] or "",
        "ds18b20_address": setup_data["ds18b20"] or "",
        "location": location,
        "ssid": ssid,
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
```

- [ ] **Step 3: Full end-to-end test with hardware**

Run the complete tool:
```bash
cd tool && python ltl_programmer.py
```

Verify the full workflow:
1. Port table appears and selection works
2. Credentials selection works
3. LTL_setup sketch compiles and uploads
4. MAC, DS18B20, WiFi networks displayed correctly
5. BSSID selection and room number input work
6. Production firmware compiles with correct values
7. Production firmware uploads
8. sensors.csv created/updated with correct row
9. Success panel shown

After the ESP resets, open MQTT broker and confirm temperature and voltage messages arrive on `sensor/temp/XXX` and `sensor/volt/XXX`.

- [ ] **Step 4: Run full test suite one final time**

```bash
cd tool && pytest tests/test_utils.py -v
```

Expected: all 18 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tool/ltl_programmer.py
git commit -m "feat: add production firmware builder and complete main() workflow"
```

---

## Task 13: README.md Update

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add programmer tool section to README.md**

Append the following section to `README.md` (after the existing Hardware section):

```markdown
## Programmer Tool

An interactive Python tool that programs each sensor in two steps:
1. Flashes a setup sketch that reads the DS18B20 address, MAC address, and nearby WiFi networks
2. Flashes the optimized production firmware with all values baked in

### Prerequisites

- [arduino-cli](https://arduino.github.io/arduino-cli/) with the ESP8266 core installed:
  ```bash
  arduino-cli core install esp8266:esp8266
  ```
- Python 3.8+
  ```bash
  pip install rich pyserial
  ```

### Credentials Setup

```bash
cp credentials.example.h credentials_Home.h
# Edit credentials_Home.h and fill in your SSID and password
```

You can have multiple credential files for different locations:
- `credentials_Home.h`
- `credentials_School.h`

These files are gitignored — never commit real credentials.

### Board Configuration

Edit `tool/arduino_config.py` if needed:
```python
BOARD_FQBN = "esp8266:esp8266:generic"  # change for your ESP8266 variant
```

Common FQBNs:
- `esp8266:esp8266:generic` — bare ESP-01/ESP-12 modules
- `esp8266:esp8266:nodemcuv2` — NodeMCU v2 / Lolin
- `esp8266:esp8266:d1_mini` — Wemos D1 Mini

### Running the Tool

Connect the ESP8266 via USB-TTL adapter, then:

```bash
cd tool && python ltl_programmer.py
```

The tool will:
1. Show available serial ports — select your USB-TTL adapter
2. Show available credential locations — select the right one
3. Flash the setup sketch and read hardware info
4. Show nearby WiFi networks — optionally pin a BSSID for faster connection
5. Ask for the room number (1–254)
6. Flash the production firmware with all values hardcoded
7. Record the sensor to `tool/sensors.csv`

### Manual Flash Fallback

If arduino-cli is not available, you can flash manually using the Arduino IDE:

1. Flash `code/LTL_setup/LTL_setup.ino` and open Serial Monitor at 115200 baud
2. Note the MAC address, DS18B20 address, and chosen WiFi network
3. Edit `code/LTL_sensor/LTL_sensor.ino` manually — replace the placeholder values
4. Copy your `credentials_<location>.h` to `credentials.h` in the same folder
5. Flash `code/LTL_sensor/LTL_sensor.ino`

### Sensor Registry

`tool/sensors.csv` tracks all programmed sensors:

| Field | Description |
|---|---|
| timestamp | When the sensor was programmed |
| room_number | Room number (also last IP octet) |
| mac_address | ESP8266 MAC address |
| ds18b20_address | DS18B20 OneWire address |
| location | Credentials location used |
| ssid | WiFi network name |
| bssid | Pinned BSSID (empty if not pinned) |
| channel | Pinned channel (empty if not pinned) |

### Battery Life Optimization

The production firmware reduces ESP8266 awake time by ~1060–1480ms per 5-minute cycle:

| Optimization | Saving |
|---|---|
| 9-bit DS18B20 resolution (±0.5°C) + async overlap | ~750ms |
| Hardcoded DS18B20 address (no bus scan) | ~10–30ms |
| Post-publish delays removed | ~300ms |
| **Total without BSSID pinning** | **~1060–1080ms** |
| Optional BSSID/channel pinning | +~200–400ms |
| **Total with BSSID pinning** | **~1260–1480ms** |
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add programmer tool documentation to README"
```

---

## Final Verification Checklist

- [ ] All 18 pytest tests pass: `cd tool && pytest -v`
- [ ] `LTL_sensor.ino` compiles in Arduino IDE with a `credentials.h` present
- [ ] `LTL_setup.ino` compiles without `credentials.h`
- [ ] Full programmer tool workflow runs end-to-end with real hardware
- [ ] `sensors.csv` is created/updated correctly
- [ ] MQTT broker receives messages on `sensor/temp/XXX` and `sensor/volt/XXX`
- [ ] `credentials_*.h` files are gitignored (run `git status` to verify)
