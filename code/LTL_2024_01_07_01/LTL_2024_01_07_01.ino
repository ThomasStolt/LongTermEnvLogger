#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// define a 3-digit room number
const int roomNumber = 208; 

// Network credentials and static IP configuration
const char* ssid = "";
const char* password = "";
IPAddress staticIP(192, 168, 100, roomNumber); // Static IP address
IPAddress gateway(192, 168, 100, 1);    // Gateway (usually your router IP)
IPAddress subnet(255, 255, 255, 0);     // Subnet mask
IPAddress dns(192, 168, 100, 1);        // DNS (can be the same as the Gateway)

// Example BSSID of the WiFi network and channel
const uint8_t wifi_bssid[6] = {0x82, 0x8A, 0x20, 0xD1, 0x77, 0x51};
const int wifi_channel = 6;

// MQTT Server
const char* mqtt_server = "192.168.2.53";
const int mqtt_port = 1883;

// Format MQTT topics to include the device number
char temp_topic[30];
char volt_topic[30];

// Data wire is plugged into GPIO12
#define ONE_WIRE_BUS 12
// GPIO15, to be set HIGH when finished
#define DONE 15
// Setup temperature sensor
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

WiFiClient espClient;
PubSubClient client(espClient);

void setup_wifi() {
  WiFi.forceSleepWake();
  char hostname[11];
  sprintf(hostname, "sensor_%03d", roomNumber);
  WiFi.hostname(hostname);
  WiFi.config(staticIP, gateway, subnet, dns);
  WiFi.begin(ssid, password, wifi_channel, wifi_bssid);
  while (WiFi.status() != WL_CONNECTED) { delay(100); }
}

void reconnect() {
  char clientId[20];
  sprintf(clientId, "room_%03d", roomNumber);
  client.setServer(mqtt_server, mqtt_port);
  while (!client.connected()) { if (client.connect(clientId)) { } else { delay(100); } }
}

void setup() {
  WiFi.forceSleepBegin(); // Ensure WiFi starts off to save power
  sensors.begin();
  pinMode(DONE, OUTPUT);
  // Format the MQTT topics
  sprintf(temp_topic, "temp_%03d", roomNumber);
  sprintf(volt_topic, "volt_%03d", roomNumber);
}

void loop() {
  // Measure temperature and voltage first
  sensors.requestTemperatures();
  float temperature = sensors.getTempCByIndex(0);
  char tempString[8];
  dtostrf(temperature, 1, 2, tempString);
  char payload[5];
  int adcValue = analogRead(A0);
  snprintf(payload, sizeof(payload), "%d", adcValue);
  // Then turn on WiFi
  setup_wifi();
  // Ensure MQTT connection
  if (!client.connected()) { reconnect(); }
  client.loop();
  // Publish temperature and voltage
  if (!client.publish(temp_topic, tempString)) { }
  delay(1);
  if (!client.publish(volt_topic, payload)) { }
  delay(1);
  // Switch off circuit
  digitalWrite(DONE, HIGH);
}
