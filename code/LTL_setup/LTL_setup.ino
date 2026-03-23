#include <ESP8266WiFi.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include "credentials.h"

// LTL Setup Sketch
// Flash once to discover DS18B20 address, ESP MAC address, and nearby WiFi networks.
// Also verifies WiFi credentials by attempting a real connection.
// Output is read by ltl_programmer.py to configure the production firmware.
// Serial: 115200 baud. Output ends with SETUP_DONE.

#define ONE_WIRE_BUS 12
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

void setup() {
  Serial.begin(115200);
  delay(500);  // Let serial port stabilise after boot

  Serial.println("DBG:START");

  // MAC address
  Serial.println("DBG:WIFI_MODE");
  WiFi.mode(WIFI_STA);
  Serial.print("MAC:");
  Serial.println(WiFi.macAddress());

  // DS18B20 address
  Serial.println("DBG:DS18B20");
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

  // WiFi scan (passive scan — no connection yet)
  Serial.println("DBG:WIFI_SCAN");
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

  // WiFi connection test using credentials from credentials.h
  Serial.println("DBG:WIFI_CONNECT");
  WiFi.begin(ssid, password);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 15000) {
    delay(100);
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("WIFI_OK");
  } else {
    Serial.println("WIFI_FAIL");
  }
  WiFi.disconnect(true);

  Serial.println("SETUP_DONE");
}

void loop() {}  // nothing to do after setup
