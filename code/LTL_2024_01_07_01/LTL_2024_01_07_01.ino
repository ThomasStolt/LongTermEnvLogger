#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include "credentials.h"

// define a 3-digit room number
const int roomNumber = 210; 

// define voltage limit to prevent deep discharge
const int volt_limit = 560;

// Static IP configuration
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
  // we track time to make sure that we stop connecting after 5 seconds, in case WiFi is down
  unsigned long startAttemptTime = millis();

  // Waking up WiFi modem and connect to WiFi
  WiFi.forceSleepWake();
  char hostname[11];
  sprintf(hostname, "sensor_%03d", roomNumber);
  WiFi.hostname(hostname);
  WiFi.config(staticIP, gateway, subnet, dns);
  WiFi.begin(ssid, password, wifi_channel, wifi_bssid);
  // Try for 5 seconds to connect to WiFi (should take about 2 seconds)
  while (WiFi.status() != WL_CONNECTED && millis() - startAttemptTime < 5000) {
    delay(100);
  }

  // if no connection, directly switch off circuit until next try
  if(WiFi.status() != WL_CONNECTED) {
    digitalWrite(DONE, HIGH);
  }
}

void reconnect() {
  char clientId[20];
  // Define room number as Client ID
  sprintf(clientId, "room_%03d", roomNumber);
  // Format the MQTT topics
  sprintf(temp_topic, "temp_%03d", roomNumber);
  sprintf(volt_topic, "volt_%03d", roomNumber);

  client.setServer(mqtt_server, mqtt_port);
  
  // Start timer
  signed long startAttemptTime = millis();

  while (!client.connected()) {
    if (client.connect(clientId)) {
      // Connected to the MQTT broker
      break; // Exit the loop
    } else {
      delay(100); // Wait for a short period before retrying
      
      if (millis() - startAttemptTime > 5000) {
        // If more than 5 seconds have passed without a connection,
        // set DONE high to indicate the device should go to sleep
        digitalWrite(DONE, HIGH);
      }
    }
  }
}

void setup() {
  // Ensure WiFi is turned off to save energy
  WiFi.forceSleepBegin();
  // Start sensors
  sensors.begin();
  // Set DONE pin to be output
  pinMode(DONE, OUTPUT);
}

void loop() {
  // Measure voltage first
  // if voltage is below 2.7V, go asleep to make sure
  // the battery is not below its discharge limit
  int adcValue = analogRead(A0);
  if (adcValue < volt_limit) {
    // If voltage is lower than 560, go to sleep
    digitalWrite(DONE, HIGH);
    return; // Stop execution here
  }

  char payload[5];
  snprintf(payload, sizeof(payload), "%d", adcValue);

  // Measure temperature
  sensors.requestTemperatures();
  float temperature = sensors.getTempCByIndex(0);
  char tempString[8];
  dtostrf(temperature, 1, 2, tempString);
  
  
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
