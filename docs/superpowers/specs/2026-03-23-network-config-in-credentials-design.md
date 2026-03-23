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

Out of scope: BSSID pinning, MQTT authentication, IPv6, hostname support for `mqtt_server`.

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

// Subnetzmaske als CIDR-Präfixlänge (1–30)
// 24 → 255.255.255.0  (Class C, typisch Heimnetz / Schulnetz)
// 16 → 255.255.0.0    (Class B)
//  8 → 255.0.0.0      (Class A)
const uint8_t  net_mask    = 24;

// MQTT-Broker (IP-Adresse als String; Hostname wird nicht unterstützt)
const char*    mqtt_server = "192.168.120.2";
const int      mqtt_port   = 1883;
```

**Constraints:**
- `net_mask` must be in the range 1–30. Values of 0, 31, and 32 are rejected at compile time via `static_assert` (see Section 2).
- Gateway and DNS are always derived as `net_a.net_b.net_c.1`. All supported networks follow this convention.
- `mqtt_server` must be an IPv4 address string. Hostnames are out of scope.
- `mqtt_port` defaults to 1883 (standard MQTT); change only if the broker is on a non-standard port.

**Migration:** Existing `credentials_*.h` files must be updated to add the five new fields before flashing. The TUI will display a yellow warning (`⚠ Netzwerkkonfiguration fehlt`) when a credentials file is selected that lacks the new fields, but it does not block the flash attempt. `arduino-cli` will produce a compile error if the fields are absent.

`credentials.example.h` is tracked by git (as a template). All `credentials_*.h` files are gitignored and must never be committed.

### 2. Firmware (`LTL_sensor.ino`)

Remove hardcoded network values. Replace with expressions using the new credentials constants.

A `static_assert` immediately after `#include "credentials.h"` validates `net_mask` at compile time:

```cpp
static_assert(net_mask >= 1 && net_mask <= 30,
    "net_mask in credentials.h must be between 1 and 30 (e.g. 24 for /24)");
```

The CIDR-to-mask conversion is placed at the top of the file (global scope) using a `constexpr` helper so the result is a compile-time constant:

```cpp
// Convert CIDR prefix length to 4-octet subnet mask
// net_mask is guaranteed 1–30 by static_assert above, so the shift is always defined.
constexpr uint32_t _subnet_bits = 0xFFFFFFFFu << (32 - net_mask);
IPAddress subnet((_subnet_bits>>24)&0xFF, (_subnet_bits>>16)&0xFF,
                 (_subnet_bits>>8)&0xFF,   _subnet_bits&0xFF);
```

The remaining IP objects replace `192, 168, 120` with the credentials constants:

```cpp
IPAddress staticIP(net_a, net_b, net_c, roomNumber);
IPAddress gateway (net_a, net_b, net_c, 1);
IPAddress dns     (net_a, net_b, net_c, 1);
// subnet defined above
```

The `mqtt_server` and `mqtt_port` declarations are removed from the firmware entirely; they are now provided by `credentials.h` via the existing `#include "credentials.h"`.

### 3. Programmer TUI (`tool/ltl_programmer.py`)

#### 3a. New helper function

```python
def read_network_from_credentials(cred_path: Path) -> dict | None:
    """
    Parse network configuration from a credentials_*.h file.

    Returns a dict with keys:
        net_prefix  str  Three-octet prefix, e.g. "192.168.120"
                         (constructed as f"{net_a}.{net_b}.{net_c}")
        net_mask    int  CIDR prefix length, e.g. 24
        mqtt_server str  Broker IP string, e.g. "192.168.120.2"
        mqtt_port   int  Broker port, e.g. 1883

    Returns None if any required field cannot be parsed or the file is unreadable.
    """
```

Implemented with four regex patterns — one per field type:

| Field | C declaration | Regex pattern |
|---|---|---|
| `net_a/b/c` | `const uint8_t net_a = 192;` | `r'const\s+uint8_t\s+net_[abc]\s*=\s*(\d+)'` |
| `net_mask` | `const uint8_t net_mask = 24;` | `r'const\s+uint8_t\s+net_mask\s*=\s*(\d+)'` |
| `mqtt_server` | `const char* mqtt_server = "…";` | `r'const\s+char\s*\*\s*mqtt_server\s*=\s*"([^"]*)"'` |
| `mqtt_port` | `const int mqtt_port = 1883;` | `r'const\s+int\s+mqtt_port\s*=\s*(\d+)'` |

Integer fields (`net_a/b/c`, `net_mask`, `mqtt_port`) are returned as `int`. `net_prefix` is built as `f"{net_a}.{net_b}.{net_c}"`. `mqtt_server` is returned as `str`.

No Python-side range validation is applied to the parsed integer values (e.g. octet range 0–255, `net_mask` range 1–30). The values are parsed and returned as-is. The firmware `static_assert` is the authoritative guard for `net_mask`; invalid octets in `net_a/b/c` would produce a visually invalid TUI display string but are developer-authored configuration errors, not security concerns.

Returns `None` on any parse failure (missing field, unreadable file) so callers can display a warning gracefully.

#### 3b. TUI display

The existing `#creds-panel` (top-right) gains a `Static` widget with id `#creds-info` below the credentials `DataTable`. It updates via Textual's `DataTable.RowHighlighted` event whenever the cursor moves in the credentials table.

Display format when network info is available:

```
 ✦  Credentials
 ┌──────────────────────────────┐
 │ Home          credentials_H  │  ← selected row
 │ School        credentials_S  │
 └──────────────────────────────┘

 Netz   192.168.120.0/24
 MQTT   192.168.120.2:1883
```

The display string for the network line is:
`f"Netz   {net_prefix}.0/{net_mask}"` and `f"MQTT   {mqtt_server}:{mqtt_port}"`.

If `read_network_from_credentials()` returns `None`, the `#creds-info` widget shows:
`[yellow]⚠ Netzwerkkonfiguration fehlt[/yellow]`

Styling follows the existing Catppuccin Mocha palette (`#cdd6f4` text, `#585b70` for labels).

#### 3c. No flash-workflow changes

The credentials file is already copied verbatim into the sketch temp directory (`shutil.copy(cred_path, sketch_dir / "credentials.h")`). No changes needed to the flash workflow.

### 4. Unit Tests

`tool/tests/test_utils.py` gets new test cases for `read_network_from_credentials()`:

| Test | Input | Expected |
|---|---|---|
| Valid file | All five new fields present | Correct dict with typed values |
| Missing `net_mask` | Field absent | `None` |
| Missing `mqtt_server` | Field absent | `None` |
| Unreadable file | Non-existent path | `None` |
| Non-standard port | `mqtt_port = 8883` | `{"mqtt_port": 8883, …}` |

Note: The CIDR-to-mask conversion is validated at compile time via `static_assert` in the firmware. No Python-side range test is needed for the conversion itself. Python-side validation (e.g. rejecting `net_mask` outside 1–30) is out of scope for this change; the firmware `static_assert` is the authoritative guard.

---

## Data Flow

```
credentials_Home.h
  net_a=192, net_b=168, net_c=120, net_mask=24
  mqtt_server="192.168.120.2", mqtt_port=1883
        │
        ├─→ Programmer TUI: DataTable.RowHighlighted
        │       → read_network_from_credentials()
        │       → #creds-info shows:
        │             "Netz   192.168.120.0/24"
        │             "MQTT   192.168.120.2:1883"
        │
        └─→ shutil.copy → sketch_dir/credentials.h
                │
                └─→ arduino-cli compile → LTL_sensor firmware
                        static_assert validates net_mask at compile time
                        IPAddress built from net_a/b/c + CIDR conversion
                        MQTT connects to mqtt_server:mqtt_port
```

---

## Alternatives Considered

- **Full explicit subnet bytes** (`subnet_a/b/c/d`): More flexible but verbose and unnecessary given CIDR covers all realistic cases.
- **Derive broker IP from net prefix** (fix it at `.2` like gateway at `.1`): Rejected — the broker may not always be at `.2`, and a free string field costs nothing.
- **MQTT host as hostname string**: Would require DNS resolution on the ESP8266 before WiFi is fully up; out of scope.
- **Separate gateway field**: All target networks follow the `.1` gateway convention; an independent field adds complexity without benefit.
