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
