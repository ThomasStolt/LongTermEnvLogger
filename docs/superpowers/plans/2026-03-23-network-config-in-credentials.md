# Network Config in credentials.h — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move all hardcoded network parameters (IP prefix, subnet mask, MQTT broker) out of `LTL_sensor.ino` and into `credentials_<location>.h` so that selecting a credentials file is the only step required to target a different network.

**Architecture:** Four files are touched. `credentials.example.h` gains five new constants. `LTL_sensor.ino` replaces its hardcoded `192.168.120.x` values with those constants, using a compile-time CIDR-to-mask conversion guarded by a `static_assert`. `ltl_programmer.py` gains a pure helper function `read_network_from_credentials()` and a new `#creds-info` Static widget that shows the parsed network info for the selected credentials file. All existing real `credentials_*.h` files must be updated before flashing.

**Tech Stack:** Arduino/C++ (ESP8266), Python 3.10+, Textual TUI framework, pytest.

---

## File Map

| File | Action | What changes |
|---|---|---|
| `credentials.example.h` | Modify | Add `net_a/b/c`, `net_mask`, `mqtt_server`, `mqtt_port` |
| `code/LTL_sensor/LTL_sensor.ino` | Modify | Remove hardcoded IPs; add `static_assert` + `constexpr` subnet; use credentials constants |
| `tool/ltl_programmer.py` | Modify | Add `read_network_from_credentials()`; add `#creds-info` widget; handle `DataTable.RowHighlighted` |
| `tool/tests/test_utils.py` | Modify | Add import + 5 test cases for `read_network_from_credentials()` |

---

## Task 1: Update credentials.example.h

**Files:**
- Modify: `credentials.example.h`

- [ ] **Step 1: Open the file and confirm current contents**

  Read `credentials.example.h`. It should contain only `ssid` and `password`. Confirm before editing.

- [ ] **Step 2: Replace the file with the updated template**

  Replace the entire file content with:

  ```c
  // Copy this file to credentials_<location>.h (e.g. credentials_Home.h)
  // and fill in your WiFi credentials and network configuration.
  // credentials_*.h files are gitignored — never commit real credentials.
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

- [ ] **Step 3: Commit**

  ```bash
  git add credentials.example.h
  git commit -m "feat: add network config fields to credentials.example.h"
  ```

---

## Task 2: Add read_network_from_credentials() with tests (TDD)

**Files:**
- Modify: `tool/tests/test_utils.py`
- Modify: `tool/ltl_programmer.py`

> **Pre-existing state to be aware of:** Before this task begins, `tool/tests/test_utils.py` currently imports `format_bssid_c_array` and `append_csv_row`, but **neither function exists in `ltl_programmer.py`**. This means the full test suite is already failing before any of our changes. Running `pytest` before Step 1 will show errors for those missing imports. This is a pre-existing gap; our import update in Step 1 restores both names. The expected failure in Step 3 below targets the new `read_network_from_credentials` import only — if you see failures on `format_bssid_c_array` or `append_csv_row` first, that confirms the pre-existing state and is expected to be resolved by Step 1.

### Step 2a — Write the failing tests first

- [ ] **Step 1: Add the import to test_utils.py**

  In `tool/tests/test_utils.py`, find the import block at the top (lines 8–17). Add `read_network_from_credentials` to the import list:

  ```python
  from ltl_programmer import (
      parse_serial_output,
      format_ds18b20_c_array,
      format_bssid_c_array,
      substitute_template,
      find_credentials_files,
      read_network_from_credentials,
      load_csv_rooms,
      append_csv_row,   # keep — used by existing test_append_csv_row_* tests
      CSV_FIELDNAMES,
  )
  ```

- [ ] **Step 2: Append the five new test cases to test_utils.py**

  Add at the end of `tool/tests/test_utils.py`:

  ```python
  # ── read_network_from_credentials tests ───────────────────────────────────────

  _VALID_CREDS = """\
  const char*    ssid        = "TestNet";
  const char*    password    = "secret";
  const uint8_t  net_a       = 10;
  const uint8_t  net_b       = 0;
  const uint8_t  net_c       = 5;
  const uint8_t  net_mask    = 24;
  const char*    mqtt_server = "10.0.5.2";
  const int      mqtt_port   = 1883;
  """


  def test_read_network_valid(tmp_path):
      cred = tmp_path / "credentials_Test.h"
      cred.write_text(_VALID_CREDS)
      result = read_network_from_credentials(cred)
      assert result == {
          "net_prefix": "10.0.5",
          "net_mask": 24,
          "mqtt_server": "10.0.5.2",
          "mqtt_port": 1883,
      }


  def test_read_network_missing_net_mask(tmp_path):
      cred = tmp_path / "credentials_Test.h"
      cred.write_text(_VALID_CREDS.replace("const uint8_t  net_mask    = 24;\n", ""))
      assert read_network_from_credentials(cred) is None


  def test_read_network_missing_mqtt_server(tmp_path):
      cred = tmp_path / "credentials_Test.h"
      cred.write_text(_VALID_CREDS.replace('const char*    mqtt_server = "10.0.5.2";\n', ""))
      assert read_network_from_credentials(cred) is None


  def test_read_network_unreadable_file(tmp_path):
      assert read_network_from_credentials(tmp_path / "nonexistent.h") is None


  def test_read_network_nonstandard_port(tmp_path):
      cred = tmp_path / "credentials_Test.h"
      cred.write_text(_VALID_CREDS.replace("mqtt_port   = 1883", "mqtt_port   = 8883"))
      result = read_network_from_credentials(cred)
      assert result is not None
      assert result["mqtt_port"] == 8883
  ```

- [ ] **Step 3: Run the tests — confirm they fail with ImportError**

  ```bash
  cd tool && pytest tests/test_utils.py::test_read_network_valid -v
  ```

  Expected: `ImportError: cannot import name 'read_network_from_credentials'`

### Step 2b — Implement the function

- [ ] **Step 4: Add read_network_from_credentials() to ltl_programmer.py**

  In `tool/ltl_programmer.py`, find the `read_ssid_from_credentials` function (around line 134). Add the new function immediately after it:

  ```python
  def read_network_from_credentials(cred_path: Path) -> dict | None:
      """Parse network config from a credentials_*.h file.

      Returns a dict with keys: net_prefix (str), net_mask (int),
      mqtt_server (str), mqtt_port (int).
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
      return {
          "net_prefix": f"{octet_map['a']}.{octet_map['b']}.{octet_map['c']}",
          "net_mask": int(m_mask.group(1)),
          "mqtt_server": m_server.group(1),
          "mqtt_port": int(m_port.group(1)),
      }
  ```

- [ ] **Step 5: Run all tests — confirm all pass**

  ```bash
  cd tool && pytest tests/test_utils.py -v
  ```

  Expected: All tests PASS (including the 5 new ones).

- [ ] **Step 6: Commit**

  ```bash
  git add tool/ltl_programmer.py tool/tests/test_utils.py
  git commit -m "feat: add read_network_from_credentials() with tests"
  ```

---

## Task 3: Update LTL_sensor.ino

**Files:**
- Modify: `code/LTL_sensor/LTL_sensor.ino`

- [ ] **Step 1: Open the file and locate the hardcoded values**

  Read `code/LTL_sensor/LTL_sensor.ino`. Identify these three blocks to change (exact text, not line numbers — the file may shift as edits are applied):
  - The `IPAddress staticIP/gateway/subnet/dns` block with `192, 168, 120`
  - The `const char* mqtt_server` and `const int mqtt_port` declarations

- [ ] **Step 2: Add static_assert and constexpr subnet after the #include "credentials.h" line**

  Find `#include "credentials.h"` and add immediately after it (before any other declarations):

  ```cpp
  static_assert(net_mask >= 1 && net_mask <= 30,
      "net_mask in credentials.h must be between 1 and 30 (e.g. 24 for /24)");

  // Convert CIDR prefix length to 4-octet subnet mask.
  // net_mask is guaranteed 1–30 by static_assert above, so the shift is always defined.
  // _subnet_bits must be declared here (global scope, before the IPAddress objects below).
  constexpr uint32_t _subnet_bits = 0xFFFFFFFFu << (32 - net_mask);
  ```

- [ ] **Step 3: Replace the hardcoded IPAddress block**

  Replace:
  ```cpp
  // Static IP (last octet = room number)
  IPAddress staticIP(192, 168, 120, roomNumber);
  IPAddress gateway(192, 168, 120, 1);
  IPAddress subnet(255, 255, 255, 0);
  IPAddress dns(192, 168, 120, 1);
  ```

  With:
  ```cpp
  // Static IP (last octet = room number) — prefix from credentials.h
  IPAddress staticIP(net_a, net_b, net_c, roomNumber);
  IPAddress gateway (net_a, net_b, net_c, 1);
  IPAddress subnet  ((_subnet_bits>>24)&0xFF, (_subnet_bits>>16)&0xFF,
                     (_subnet_bits>>8)&0xFF,   _subnet_bits&0xFF);
  IPAddress dns     (net_a, net_b, net_c, 1);
  ```

- [ ] **Step 4: Remove the hardcoded mqtt_server and mqtt_port declarations**

  Delete these two lines entirely (they are now provided by `credentials.h`):
  ```cpp
  const char* mqtt_server = "192.168.120.2";
  const int mqtt_port = 1883;
  ```

- [ ] **Step 5: Verify the file looks correct**

  Read the full updated file and confirm:
  - `static_assert` appears after `#include "credentials.h"`
  - `_subnet_bits` `constexpr` appears before the `IPAddress` declarations
  - All four `IPAddress` objects use `net_a/b/c` (no `192, 168, 120` literals remain)
  - `mqtt_server` and `mqtt_port` are not declared in the firmware (they come from credentials)

- [ ] **Step 6: Commit**

  ```bash
  git add code/LTL_sensor/LTL_sensor.ino
  git commit -m "feat: replace hardcoded network values with credentials.h constants"
  ```

---

## Task 4: Update TUI — show network info in credentials panel

**Files:**
- Modify: `tool/ltl_programmer.py`

### What to change

The `#creds-panel` currently contains a `DataTable` only. We need to:
1. Add a `Static` widget (`#creds-info`) below the table in `compose()`
2. Add CSS for `#creds-info`
3. Handle `DataTable.RowHighlighted` to update `#creds-info` when the cursor moves

- [ ] **Step 1: Add the CSS rule for #creds-info**

  In the `CSS` string of `LTLProgrammerApp` (around line 481), find the `#creds-title` rule block. Add after it:

  ```css
  #creds-info {
      color: #cdd6f4;
      padding: 0 1;
      height: auto;
  }
  ```

- [ ] **Step 2: Add the Static widget to compose()**

  In `compose()` (around line 598), find the `with Vertical(id="creds-panel"):` block:

  ```python
  with Vertical(id="creds-panel"):
      yield Label(" ✦  Credentials", id="creds-title")
      yield DataTable(id="creds-table", cursor_type="row")
  ```

  Add the info widget after the DataTable:

  ```python
  with Vertical(id="creds-panel"):
      yield Label(" ✦  Credentials", id="creds-title")
      yield DataTable(id="creds-table", cursor_type="row")
      yield Static("", id="creds-info")
  ```

- [ ] **Step 3: Add the _update_creds_info() helper method**

  Add this method to `LTLProgrammerApp`, after `_apply_refresh` (around line 636):

  ```python
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
              f"[#585b70]Netz[/#585b70]   {net['net_prefix']}.0/{net['net_mask']}\n"
              f"[#585b70]MQTT[/#585b70]   {net['mqtt_server']}:{net['mqtt_port']}"
          )
  ```

- [ ] **Step 4: Call _update_creds_info() from _apply_refresh()**

  Note: `#creds-info` will appear blank for the first ~2s at startup (until the background port scan completes). Once the scan finishes, `_apply_refresh()` populates the credentials table, moves the cursor to row 0, and calls `_update_creds_info()` — after which the info block is always populated when credentials are present.

  In `_apply_refresh()` (around line 656), find the block that updates the credentials table:

  ```python
  if creds != self._credentials:
      table = self.query_one("#creds-table", DataTable)
      table.clear()
      for loc in creds:
          table.add_row(loc, f"credentials_{loc}.h")
      self._credentials = creds
  ```

  Add `table.move_cursor(row=0)` and `self._update_creds_info()` at the end of that block. The cursor move triggers the `RowHighlighted` event and ensures `#creds-info` is populated immediately after the credentials list loads — without it, the info widget stays blank until the user manually navigates.

  ```python
  if creds != self._credentials:
      table = self.query_one("#creds-table", DataTable)
      table.clear()
      for loc in creds:
          table.add_row(loc, f"credentials_{loc}.h")
      self._credentials = creds
      table.move_cursor(row=0)
      self._update_creds_info()
  ```

- [ ] **Step 5: Handle DataTable.RowHighlighted to update on cursor movement**

  Add this event handler to `LTLProgrammerApp`, after the `on_key` handler (around line 685):

  ```python
  def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
      if event.data_table.id == "creds-table":
          self._update_creds_info()
  ```

- [ ] **Step 6: Run the TUI manually and verify**

  ```bash
  cd tool && python3 ltl_programmer.py
  ```

  Move the cursor in the credentials table. The `#creds-info` area should show:
  ```
  Netz   192.168.120.0/24
  MQTT   192.168.120.2:1883
  ```
  For a credentials file that lacks the new fields, it should show:
  ```
  ⚠ Netzwerkkonfiguration fehlt
  ```

- [ ] **Step 7: Commit**

  ```bash
  git add tool/ltl_programmer.py
  git commit -m "feat: show network config in credentials panel"
  ```

---

## Task 5: Update real credentials_*.h files

**Files:**
- Modify: Any `credentials_*.h` files present locally (gitignored, not in repo)

- [ ] **Step 1: Find all local credentials files**

  Run from the project root (`LongTermEnvLogger/`):

  ```bash
  ls credentials_*.h 2>/dev/null
  ```

- [ ] **Step 2: Add the five new fields to each file**

  For each `credentials_<location>.h`, add the five new constants with the correct values for that location. Use `credentials.example.h` as reference for the comment format. Example for a home network `192.168.120.x`:

  ```c
  const uint8_t  net_a       = 192;
  const uint8_t  net_b       = 168;
  const uint8_t  net_c       = 120;
  const uint8_t  net_mask    = 24;
  const char*    mqtt_server = "192.168.120.2";
  const int      mqtt_port   = 1883;
  ```

  Adjust values for each location (School, etc.) as appropriate.

  Note: These files are gitignored and must NOT be committed.

- [ ] **Step 3: Verify TUI shows correct info**

  Run `python3 ltl_programmer.py` and confirm the network info block shows the correct values for each credentials file.

---

## Task 6: Final check and run all tests

- [ ] **Step 1: Run the full test suite**

  ```bash
  cd tool && pytest -v
  ```

  Expected: All tests PASS.

- [ ] **Step 2: Confirm no hardcoded 192.168.120 octets remain in firmware**

  ```bash
  grep -n "192, 168, 120\|192\.168\.120\|mqtt_server\s*=\|mqtt_port\s*=" code/LTL_sensor/LTL_sensor.ino
  ```

  Expected: No output (all hardcoded values removed).
