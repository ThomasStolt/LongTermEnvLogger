import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import csv
import tempfile
from ltl_programmer import (
    parse_serial_output,
    format_ds18b20_c_array,
    format_bssid_c_array,
    substitute_template,
    find_credentials_files,
    read_network_from_credentials,
    write_network_to_credentials,
    write_credentials_file,
    load_csv_rooms,
    append_csv_row,   # keep — used by existing test_append_csv_row_* tests
    upsert_csv_row,
    delete_csv_row,
    _room_int,
    CSV_FIELDNAMES,
)


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


# ── Address formatter tests ───────────────────────────────────────────────────

def test_format_ds18b20_c_array():
    raw = "0x28,0xFF,0xA1,0xB2,0xC3,0xD4,0xE5,0x06"
    assert format_ds18b20_c_array(raw) == "{ 0x28, 0xFF, 0xA1, 0xB2, 0xC3, 0xD4, 0xE5, 0x06 }"


def test_format_ds18b20_c_array_wrong_length():
    with pytest.raises(ValueError, match="8 bytes"):
        format_ds18b20_c_array("0x28,0xFF,0xA1,0xB2,0xC3,0xD4,0xE5")  # only 7 bytes


def test_format_bssid_c_array():
    assert format_bssid_c_array("AA:BB:CC:DD:EE:FF") == "{ 0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF }"


def test_format_bssid_c_array_lowercase():
    """pyserial/ESP may return lowercase hex — must uppercase."""
    assert format_bssid_c_array("aa:bb:cc:dd:ee:ff") == "{ 0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF }"


def test_format_bssid_c_array_wrong_length():
    with pytest.raises(ValueError, match="6 bytes"):
        format_bssid_c_array("AA:BB:CC:DD:EE")  # only 5 bytes


# ── Template substitution tests ───────────────────────────────────────────────

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
        result = substitute_template(
            TEMPLATE,
            room_number=room,
            ds18b20_array="{ 0x28, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 }",
        )
        assert f"/*ROOM_NUMBER*/{room}" in result


def test_substitute_bssid_only_no_substitution():
    """Passing bssid_array without channel leaves USE_BSSID commented out."""
    result = substitute_template(
        TEMPLATE,
        room_number=101,
        ds18b20_array="{ 0x28, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 }",
        bssid_array="{ 0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF }",
        channel=None,  # channel missing — pinning should NOT be activated
    )
    assert "// #define USE_BSSID" in result  # must stay commented


# ── CSV handler and credentials finder tests ──────────────────────────────────

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


# ── read_network_from_credentials tests ───────────────────────────────────────

_VALID_CREDS = """\
const char*    ssid        = "TestNet";
const char*    password    = "secret";
const uint8_t  net_a       = 10;
const uint8_t  net_b       = 0;
const uint8_t  net_c       = 5;
const uint8_t  net_mask    = 24;
const uint8_t  gw_a        = 10;
const uint8_t  gw_b        = 0;
const uint8_t  gw_c        = 5;
const uint8_t  gw_d        = 1;
const uint8_t  dns_a       = 8;
const uint8_t  dns_b       = 8;
const uint8_t  dns_c       = 8;
const uint8_t  dns_d       = 8;
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
        "gateway": "10.0.5.1",
        "dns_server": "8.8.8.8",
    }


def test_read_network_gateway_dns_fallback(tmp_path):
    """Without gw_*/dns_* fields, gateway and dns fall back to net_a.net_b.net_c.1."""
    cred = tmp_path / "credentials_Test.h"
    cred.write_text("\n".join(
        line for line in _VALID_CREDS.splitlines()
        if not line.startswith("const uint8_t  gw_") and not line.startswith("const uint8_t  dns_")
    ))
    result = read_network_from_credentials(cred)
    assert result is not None
    assert result["gateway"] == "10.0.5.1"
    assert result["dns_server"] == "10.0.5.1"


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


# ── write_network_to_credentials tests ────────────────────────────────────────

def test_write_network_roundtrip(tmp_path):
    """Writing then reading back should return the same values."""
    cred = tmp_path / "credentials_Test.h"
    cred.write_text(_VALID_CREDS)
    updates = {
        "net_prefix":  "172.16.0",
        "net_mask":    16,
        "gateway":     "172.16.0.1",
        "dns_server":  "8.8.4.4",
        "mqtt_server": "172.16.0.10",
        "mqtt_port":   8883,
    }
    write_network_to_credentials(cred, updates)
    result = read_network_from_credentials(cred)
    assert result["net_prefix"]  == "172.16.0"
    assert result["net_mask"]    == 16
    assert result["gateway"]     == "172.16.0.1"
    assert result["dns_server"]  == "8.8.4.4"
    assert result["mqtt_server"] == "172.16.0.10"
    assert result["mqtt_port"]   == 8883


def test_write_network_preserves_ssid(tmp_path):
    """ssid and password must not be modified."""
    cred = tmp_path / "credentials_Test.h"
    cred.write_text(_VALID_CREDS)
    updates = {
        "net_prefix":  "10.0.5",
        "net_mask":    24,
        "gateway":     "10.0.5.1",
        "dns_server":  "10.0.5.1",
        "mqtt_server": "10.0.5.2",
        "mqtt_port":   1883,
    }
    write_network_to_credentials(cred, updates)
    content = cred.read_text()
    assert 'ssid        = "TestNet"' in content
    assert 'password    = "secret"' in content


# ── upsert / delete / _room_int tests ─────────────────────────────────────────

def _make_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        w.writeheader()
        w.writerows(rows)


def _read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def test_room_int_valid():
    assert _room_int("040") == 40
    assert _room_int("101") == 101


def test_room_int_invalid():
    assert _room_int("") is None
    assert _room_int("abc") is None


def test_upsert_numeric_match(tmp_path):
    """upsert should match '40' and '040' as the same room."""
    csv_path = tmp_path / "sensors.csv"
    _make_csv(csv_path, [
        {f: "" for f in CSV_FIELDNAMES} | {"room_number": "40", "location": "old"},
    ])
    upsert_csv_row(csv_path, {f: "" for f in CSV_FIELDNAMES} | {"room_number": "040", "location": "new"})
    rows = _read_csv(csv_path)
    assert len(rows) == 1
    assert rows[0]["location"] == "new"
    assert rows[0]["room_number"] == "040"


def test_upsert_adds_new_room(tmp_path):
    csv_path = tmp_path / "sensors.csv"
    _make_csv(csv_path, [
        {f: "" for f in CSV_FIELDNAMES} | {"room_number": "101"},
    ])
    upsert_csv_row(csv_path, {f: "" for f in CSV_FIELDNAMES} | {"room_number": "040"})
    rows = _read_csv(csv_path)
    assert len(rows) == 2


def test_delete_csv_row(tmp_path):
    csv_path = tmp_path / "sensors.csv"
    _make_csv(csv_path, [
        {f: "" for f in CSV_FIELDNAMES} | {"room_number": "040"},
        {f: "" for f in CSV_FIELDNAMES} | {"room_number": "101"},
    ])
    delete_csv_row(csv_path, 40)
    rows = _read_csv(csv_path)
    assert len(rows) == 1
    assert rows[0]["room_number"] == "101"


def test_delete_csv_row_nonexistent(tmp_path):
    """Deleting a room that doesn't exist should not raise and leave file intact."""
    csv_path = tmp_path / "sensors.csv"
    _make_csv(csv_path, [
        {f: "" for f in CSV_FIELDNAMES} | {"room_number": "101"},
    ])
    delete_csv_row(csv_path, 999)
    assert len(_read_csv(csv_path)) == 1


# ── write_credentials_file tests ──────────────────────────────────────────────

def test_write_credentials_file_roundtrip(tmp_path):
    """A newly created credentials file can be read back by read_network_from_credentials."""
    cred = tmp_path / "credentials_Test.h"
    write_credentials_file(cred, {
        "location":    "Test",
        "ssid":        "MyNet",
        "password":    "secret",
        "net_prefix":  "10.0.1",
        "net_mask":    24,
        "gateway":     "10.0.1.1",
        "dns_server":  "8.8.8.8",
        "mqtt_server": "10.0.1.5",
        "mqtt_port":   1883,
    })
    result = read_network_from_credentials(cred)
    assert result is not None
    assert result["net_prefix"]  == "10.0.1"
    assert result["net_mask"]    == 24
    assert result["gateway"]     == "10.0.1.1"
    assert result["dns_server"]  == "8.8.8.8"
    assert result["mqtt_server"] == "10.0.1.5"
    assert result["mqtt_port"]   == 1883


def test_write_credentials_file_contains_ssid(tmp_path):
    cred = tmp_path / "credentials_Home.h"
    write_credentials_file(cred, {
        "location": "Home", "ssid": "HomeNet", "password": "pw123",
        "net_prefix": "192.168.1", "net_mask": 24,
        "gateway": "192.168.1.1", "dns_server": "192.168.1.1",
        "mqtt_server": "192.168.1.10", "mqtt_port": 1883,
    })
    content = cred.read_text()
    assert 'ssid        = "HomeNet"' in content
    assert 'password    = "pw123"' in content
