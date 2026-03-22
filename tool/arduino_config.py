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
