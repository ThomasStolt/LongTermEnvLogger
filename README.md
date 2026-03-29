# Long Term Environment Logger

The aim of this project is to measure, store, display and evaluate the temperature in the rooms of a large building over an extended time period. This project has 2 main components:

A. The hardware of the sensor.

B. The server infrastructure to receive, store and display the measurements.

## The Hardware

1. An ultra-low power timer circuit that uses nano-Amps only when asleep and wakes up the entire circuit every approx. 5 minutes for measurement.

2. An LDO voltage regulator that regulates the incoming battery voltage from a LiIon battery to 3.3V

3. A battery voltage sensor that sends the battery voltage to the ESP8266 ADC pin with a voltage divider so that the battery voltage can be monitored.

4. The ESP8266 with a DS18B20 temperature sensor.

5. A small solar cell with a charging circuit, to keep the battery charged for as long as possible.

... and some additional mechanical and electronic components.

The ESP8266 was chosen as the microcontroller. It is versatile, very affordable, has more than enough functionality and information is easy to find.

If you think about it in detail, this project is not quite as trivial as it first appears. Some of the things to consider are:

* Runtime - How long does a single battery last?

  * As the battery-operated temperature sensors are to be distributed throughout a very large building, you want the individual sensors to run for as long as possible, so that you don't have to run around the building changing or charging batteries all the time. One option is the energy-saving mode ("DeepSleep") of the microcontroller. This would reduce the current draw during deep sleep to about 14µA. However, we want to achieve sleep current of less than 100nA! So, the normal Deep-Sleep will not do it.

* Update OTA(?)
	* It might be worth considering adding this capability. This would probably affect the runtime as well, because if we check for updates every time the circuit wakes up, it will cost runtime and energy. So, the question here is, how much runtime this would cost and is this really necessary?

* WiFi Connection Time
	* When the ESP8266 wakes up and has WiFi switched on, it draws about 70mA, which is a lot. So, all efforts need to be taken to reduce the connection time to be a short as possible.

* Power supply / battery
	* Li-Ion batteries are a good energy source for this type of project, especially the 18650 type. They are relatively inexpensive for their capacity. However, as these batteries are very sensitive to mishandling, it is important to take appropriate precautions.
		* How can you ensure that the LiIon battery will not be deep discharged?
		* How can I ensure that the LiIon battery cannot be overcharged?
		* How can I monitor the voltage of the power supply (of the LiIo battery) in order to replace or charge the battery in good time?
		* All batteries must be checked regularly for their capacity and possible health issues.

## Overview

First a short diagram for an overview:

![alt text](<https://github.com/ThomasStolt/LongTermEnvLogger/blob/master/images/PrincipleArchitecture.png>)

---

## Programmer Tool

An interactive TUI (terminal user interface) that programs each sensor in two steps. Built with [Textual](https://textual.textualize.io/) for a comfortable dark-mode interface.

### Features

- Auto-detects USB serial ports (OTA/network ports filtered out) and pre-selects the right one
- Live hotplug detection — plug in the adapter and it appears immediately
- Parallel background compilation while you prepare the hardware
- Auto-selects the WiFi network from your credentials file (strongest signal)
- Two-column credentials panel — file list on the left, network config on the right; press `E` to edit
- Per-location sensor registry (`sensors_home.csv`, `sensors_school.csv`, …) — switches automatically with the selected credentials file
- Always-visible Serial Debug panel showing raw ESP output during setup-sketch read
- Adjustable baud rate selector and automatic retry loop on serial read timeout
- Full keyboard navigation — no mouse required
- Clean two-step workflow with progress feedback

### Prerequisites

- [arduino-cli](https://arduino.github.io/arduino-cli/) with the ESP8266 core installed:
  ```bash
  arduino-cli core install esp8266:esp8266
  ```
- Python 3.10+
  ```bash
  pip install -r tool/requirements.txt
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
cd tool && python3 ltl_programmer.py
```

**Keyboard shortcuts:**

| Key | Action |
|-----|--------|
| `F` | Start flash workflow |
| `R` | Refresh port list |
| `E` | Edit network config for selected credentials |
| `Q` | Quit |
| `Enter` | Confirm / Continue |

**Workflow:**

1. Select your USB-TTL adapter port (pre-selected automatically)
2. Select the credentials location (Home, School, …)
3. Press `F` to start — the tool guides you through:
   - Enter flash mode (RST + FLASH button sequence)
   - Setup sketch uploads and reads MAC address, DS18B20 address, and nearby WiFi
   - WiFi network is auto-selected from your credentials file
   - Enter a room number (1–254)
   - Production firmware compiles and uploads with all values baked in
4. Sensor is recorded in `tool/sensors_<location>.csv` (one file per credentials location)

### Flash Mode (ESP-12 / bare modules)

Bare ESP8266 modules without an auto-reset circuit require manual flash mode entry:

1. Press and hold **RST**
2. Press and hold **FLASH**
3. Release **RST**
4. Release **FLASH**

The tool will prompt you at the right moment.

### Manual Flash Fallback

If arduino-cli is not available, you can flash manually using the Arduino IDE:

1. Flash `code/LTL_setup/LTL_setup.ino` and open Serial Monitor at 115200 baud
2. Note the MAC address and DS18B20 address
3. Edit `code/LTL_sensor/LTL_sensor.ino` — replace the placeholder values
4. Copy your `credentials_<location>.h` to `credentials.h` in the same folder
5. Flash `code/LTL_sensor/LTL_sensor.ino`

### Sensor Registry

`tool/sensors_<location>.csv` tracks all programmed sensors per location (gitignored). For example, `sensors_home.csv` and `sensors_school.csv` are created automatically when you first flash a sensor using that credentials file.

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

The production firmware (`code/LTL_sensor/LTL_sensor.ino`) reduces ESP8266 awake time by ~1060–1480ms per 5-minute cycle compared to the original firmware:

| Optimization | Saving |
|---|---|
| 9-bit DS18B20 resolution (±0.5°C) + async overlap | ~750ms |
| Hardcoded DS18B20 address (no bus scan) | ~10–30ms |
| Post-publish delays removed | ~300ms |
| **Total without BSSID pinning** | **~1060–1080ms** |
| Optional BSSID/channel pinning | +~200–400ms |
| **Total with BSSID pinning** | **~1260–1480ms** |
