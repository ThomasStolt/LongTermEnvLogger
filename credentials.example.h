// Copy this file to credentials_<location>.h (e.g. credentials_Home.h)
// and fill in your WiFi credentials and network configuration.
// credentials_*.h files are gitignored — never commit real credentials.
#include <stdint.h>  // uint8_t — already available via Arduino.h in sketch context
const char*    ssid        = "YOUR_SSID_HERE";
const char*    password    = "YOUR_PASSWORD_HERE";

// Netzwerk-Präfix (erste 3 Oktette der statischen Sensor-IP)
// Statische IP wird zu net_a.net_b.net_c.<Raumnummer>
const uint8_t  net_a       = 192;
const uint8_t  net_b       = 168;
const uint8_t  net_c       = 120;

// Subnetzmaske als CIDR-Präfixlänge (1–30)
// 24 → 255.255.255.0  (Class C, typisch Heimnetz / Schulnetz)
// 16 → 255.255.0.0    (Class B)
//  8 → 255.0.0.0      (Class A)
const uint8_t  net_mask    = 24;

// Gateway-IP (typisch der Router, z.B. 192.168.120.1)
const uint8_t  gw_a        = 192;
const uint8_t  gw_b        = 168;
const uint8_t  gw_c        = 120;
const uint8_t  gw_d        = 1;

// DNS-Server-IP (oft identisch mit Gateway, oder z.B. 8.8.8.8)
const uint8_t  dns_a       = 192;
const uint8_t  dns_b       = 168;
const uint8_t  dns_c       = 120;
const uint8_t  dns_d       = 1;

// MQTT-Broker (IP-Adresse als String; Hostname wird nicht unterstützt)
const char*    mqtt_server = "192.168.120.2";
const int      mqtt_port   = 1883;
