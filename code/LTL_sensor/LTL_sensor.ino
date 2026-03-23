#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include "credentials.h"

static_assert(net_mask >= 1 && net_mask <= 30,
    "net_mask in credentials.h must be between 1 and 30 (e.g. 24 for /24)");

// Convert CIDR prefix length to 4-octet subnet mask.
// net_mask is guaranteed 1–30 by static_assert above, so the shift is always defined.
// _subnet_bits must be declared here (global scope, before the IPAddress objects below).
constexpr uint32_t _subnet_bits = 0xFFFFFFFFu << (32 - net_mask);

// Room number — substituted by ltl_programmer.py (must be 1–254, used as IP last octet)
const int roomNumber = /*ROOM_NUMBER*/101;

// DS18B20 sensor address — substituted by ltl_programmer.py
// Flash LTL_setup.ino once to discover this address
DeviceAddress sensorAddr = /*DS18B20_ADDR*/{ 0x28, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 };

// Voltage limit (~2.7V) — prevents LiIon deep discharge
const int volt_limit = 560;

// Static IP (last octet = room number) — prefix from credentials.h
IPAddress staticIP(net_a, net_b, net_c, roomNumber);
IPAddress gateway (gw_a,  gw_b,  gw_c,  gw_d);
IPAddress subnet  ((_subnet_bits>>24)&0xFF, (_subnet_bits>>16)&0xFF,
                   (_subnet_bits>>8)&0xFF,   _subnet_bits&0xFF);
IPAddress dns     (dns_a, dns_b, dns_c, dns_d);

// Optional BSSID/channel pinning — saves ~200-400ms per cycle by skipping WiFi channel scan.
// Only reliable with a single fixed access point on a manually configured fixed channel.
// ltl_programmer.py uncomments this line when a BSSID is selected during programming.
// #define USE_BSSID
#ifdef USE_BSSID
  const uint8_t wifi_bssid[6] = /*BSSID*/{ 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 };
  const int wifi_channel = /*WIFI_CHANNEL*/1;
#endif

char temp_topic[30];
char volt_topic[30];

#define ONE_WIRE_BUS 12
#define DONE 15
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

WiFiClient espClient;
PubSubClient client(espClient);

void setup_wifi() {
  unsigned long startAttemptTime = millis();
  WiFi.forceSleepWake();
  char hostname[11];
  sprintf(hostname, "sensor_%03d", roomNumber);
  WiFi.hostname(hostname);
  WiFi.config(staticIP, gateway, subnet, dns);
#ifdef USE_BSSID
  WiFi.begin(ssid, password, wifi_channel, wifi_bssid);
#else
  WiFi.begin(ssid, password);
#endif
  while (WiFi.status() != WL_CONNECTED && millis() - startAttemptTime < 5000) {
    delay(100);
  }
  if (WiFi.status() != WL_CONNECTED) {
    digitalWrite(DONE, HIGH);
    return;  // hardware cuts power immediately; return ensures no further code runs
  }
}

void reconnect() {
  char clientId[20];
  sprintf(clientId, "room_%03d", roomNumber);
  sprintf(temp_topic, "sensor/temp/%03d", roomNumber);
  sprintf(volt_topic, "sensor/volt/%03d", roomNumber);
  client.setServer(mqtt_server, mqtt_port);
  unsigned long startAttemptTime = millis();  // unsigned long matches millis() return type
  while (!client.connected()) {
    if (client.connect(clientId)) {
      break;
    } else {
      delay(100);
      if (millis() - startAttemptTime > 5000) {
        digitalWrite(DONE, HIGH);
        return;  // hardware cuts power immediately; return ensures no further code runs
      }
    }
  }
}

void setup() {
  WiFi.forceSleepBegin();
  sensors.begin();
  sensors.setResolution(sensorAddr, 9);  // 9-bit: ~94ms conversion, ±0.5°C. Persists in sensor EEPROM.
  pinMode(DONE, OUTPUT);
}

void loop() {
  // Check battery voltage — power off immediately if below deep-discharge limit
  int adcValue = analogRead(A0);
  if (adcValue < volt_limit) {
    digitalWrite(DONE, HIGH);
    return;
  }
  char voltPayload[5];
  snprintf(voltPayload, sizeof(voltPayload), "%d", adcValue);

  // Start async temperature conversion (94ms at 9-bit resolution).
  // WiFi + MQTT connect (~2s total) runs while the DS18B20 converts in the background,
  // so the conversion adds zero time to the critical path.
  sensors.setWaitForConversion(false);
  sensors.requestTemperatures();

  setup_wifi();
  if (!client.connected()) { reconnect(); }
  client.loop();

#ifdef USE_BSSID
  // With BSSID pinning, WiFi may connect in <94ms — add guard to ensure conversion is complete.
  delay(100);
#endif

  // Read temperature — conversion guaranteed complete by now
  float temperature = sensors.getTempC(sensorAddr);
  char tempString[8];
  dtostrf(temperature, 1, 2, tempString);

  client.publish(temp_topic, tempString);
  client.publish(volt_topic, voltPayload);
  client.loop();  // flush send buffer
  delay(200);     // allow lwIP TCP stack to transmit before power is cut

  // Cut power to the entire circuit
  digitalWrite(DONE, HIGH);
}
