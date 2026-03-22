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
