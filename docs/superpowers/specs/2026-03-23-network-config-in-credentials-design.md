# Design: Network Configuration in credentials.h

**Date:** 2026-03-23
**Status:** Draft

## Problem

Network parameters (IP prefix, gateway, MQTT broker) are hardcoded in `LTL_sensor.ino` as `192.168.120.x`. Sensors deployed at different locations (Home, School, …) require different subnets and MQTT broker addresses. Today, switching locations requires manually editing the firmware source.

## Goal

Move all network-specific parameters into `credentials_<location>.h` so that selecting a credentials file in the programmer is the only step needed to target a different network. No firmware source edits required.

## Scope

- `credentials.example.h` — add new fields with comments
- `LTL_sensor.ino` — replace hardcoded values with constants from `credentials.h`
- `tool/ltl_programmer.py` — parse and display network info for the selected credentials file
- Existing unit tests — add coverage for the new `read_network_from_credentials()` helper

Out of scope: BSSID pinning, MQTT authentication, IPv6.

---

## Design

### 1. credentials.h Format

All `credentials_<location>.h` files (and `credentials.example.h`) gain five new constants:

```c
const char*    ssid        = "YOUR_SSID_HERE";
const char*    password    = "YOUR_PASSWORD_HERE";

// Netzwerk-Präfix (erste 3 Oktette der statischen Sensor-IP)
// Statische IP wird zu net_a.net_b.net_c.<Raumnummer>
// Gateway und DNS werden als net_a.net_b.net_c.1 abgeleitet
const uint8_t  net_a       = 192;
const uint8_t  net_b       = 168;
const uint8_t  net_c       = 120;

// Subnetzmaske als CIDR-Präfixlänge
// 24 → 255.255.255.0  (Class C, typisch Heimnetz / Schulnetz)
// 16 → 255.255.0.0    (Class B)
//  8 → 255.0.0.0      (Class A)
const uint8_t  net_mask    = 24;

// MQTT-Broker
const char*    mqtt_server = "192.168.120.2";
const int      mqtt_port   = 1883;
```

**Constraints:**
- Gateway and DNS are always derived as `net_a.net_b.net_c.1`. There is no independent gateway field — all supported networks follow this convention.
- `net_mask` is a CIDR prefix length (1–30). Values outside this range are invalid.
- `mqtt_port` defaults to 1883 (standard MQTT); change only if the broker is on a non-standard port.

### 2. Firmware (`LTL_sensor.ino`)

Remove hardcoded network values. Replace with expressions using the new credentials constants.

**Before:**
```cpp
IPAddress staticIP(192, 168, 120, roomNumber);
IPAddress gateway(192, 168, 120, 1);
IPAddress subnet(255, 255, 255, 0);
IPAddress dns(192, 168, 120, 1);
const char* mqtt_server = "192.168.120.2";
const int mqtt_port = 1883;
```

**After:**
```cpp
// Subnet mask derived from CIDR prefix length defined in credentials.h
uint32_t _m = net_mask ? (0xFFFFFFFFu << (32 - net_mask)) : 0;
IPAddress staticIP(net_a, net_b, net_c, roomNumber);
IPAddress gateway (net_a, net_b, net_c, 1);
IPAddress subnet  ((_m>>24)&0xFF, (_m>>16)&0xFF, (_m>>8)&0xFF, _m&0xFF);
IPAddress dns     (net_a, net_b, net_c, 1);
// mqtt_server and mqtt_port come from credentials.h
```

The `mqtt_server` and `mqtt_port` declarations are removed from the firmware entirely; they are now provided by `credentials.h` via `#include "credentials.h"` (already present).

### 3. Programmer TUI (`tool/ltl_programmer.py`)

#### 3a. New helper function

```python
def read_network_from_credentials(cred_path: Path) -> dict | None:
    """
    Parse net_a/b/c, net_mask, mqtt_server, mqtt_port from a credentials_*.h file.
    Returns a dict with keys: net_prefix (str), net_mask (int), mqtt_server (str),
    mqtt_port (int). Returns None if any required field is missing.
    """
```

Implemented with regex, analogous to the existing `read_ssid_from_credentials()`.

Returns `None` on parse failure (missing fields, unreadable file) so callers can display a warning gracefully.

#### 3b. TUI display

The existing `#creds-panel` (top-right) currently shows only a two-column table (Location | File). Below the table, a new static info block is added. It updates whenever the cursor moves in the credentials table:

```
 ✦  Credentials
 ┌──────────────────────────────┐
 │ Home          credentials_H  │  ← selected row
 │ School        credentials_S  │
 └──────────────────────────────┘

 Netz   192.168.120.0/24
 MQTT   192.168.120.2:1883
```

If `read_network_from_credentials()` returns `None` (e.g. credentials file missing the new fields), the info block shows a yellow warning: `⚠ Netzwerkkonfiguration fehlt`.

The info block is a `Static` widget with id `#creds-info`, styled in the existing Catppuccin Mocha palette.

#### 3c. No flash-workflow changes

The credentials file is already copied verbatim into the sketch temp directory (`shutil.copy(cred_path, sketch_dir / "credentials.h")`). No changes needed to the flash workflow — the new constants are compiled in automatically.

### 4. Unit Tests

`tool/tests/test_utils.py` gets new test cases for `read_network_from_credentials()`:
- Valid file → correct dict returned
- Missing `net_mask` field → returns `None`
- Unreadable file → returns `None`
- Non-standard port → parsed correctly

---

## Data Flow

```
credentials_Home.h
  net_a=192, net_b=168, net_c=120, net_mask=24
  mqtt_server="192.168.120.2", mqtt_port=1883
        │
        ├─→ Programmer TUI reads on cursor-select → shows Netz/MQTT info block
        │
        └─→ shutil.copy → sketch_dir/credentials.h
                │
                └─→ arduino-cli compile → LTL_sensor firmware
                        IPAddress uses net_a/b/c/mask
                        MQTT connects to mqtt_server:mqtt_port
```

---

## Alternatives Considered

- **Full explicit subnet bytes** (`subnet_a/b/c/d`): More flexible but verbose and unnecessary given the CIDR approach covers all realistic cases.
- **MQTT host as string with embedded port** (`"192.168.120.2:1883"`): Requires string splitting in firmware — avoided.
- **Separate gateway field**: All target networks follow the `.1` gateway convention; an independent field adds complexity without benefit.
