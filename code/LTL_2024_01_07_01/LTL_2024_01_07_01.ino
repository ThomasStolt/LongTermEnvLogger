#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// Network credentials
const char* ssid = "linksys-n";
const char* password = "Nadine21";

// MQTT Server
const char* mqtt_server = "192.168.2.53";
const int mqtt_port = 1883;
const char* temperature_topic = "home/room/temperature";
const char* voltage_topic = "home/room/voltage"; // Voltage MQTT topic

// Data wire is connected to GPIO4
#define ONE_WIRE_BUS 4
#define DONE 15  // GPIO15

OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

WiFiClient espClient;
PubSubClient client(espClient);

void setup_wifi() {
  delay(10);
  Serial.println("Connecting to WiFi...");
  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("WiFi connected");
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Attempting MQTT connection...");
    if (client.connect("ESP8266Client")) {
      client.loop();
      Serial.println("connected");
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" try again in 5 seconds");
      delay(5000);
    }
  }
}

// Function to read and convert ADC value to voltage
float readVoltage() {
  int sensorValue = analogRead(A0);
  float voltage = sensorValue * (1.0 / 1023.0) * 6.052; // Adjust the multiplier for your voltage divider
  return voltage;
}

void setup() {
  Serial.begin(115200);
  setup_wifi();
  client.setServer(mqtt_server, mqtt_port);

  // Ensure MQTT connection
  if (!client.connected()) {
    reconnect();
  }

  sensors.begin();
  sensors.requestTemperatures();
  yield();
  float temperature = sensors.getTempCByIndex(0);

  char tempString[8];
  dtostrf(temperature, 1, 2, tempString);

  if (client.publish(temperature_topic, tempString)) {
    yield();
    Serial.println("Temperature published successfully");
  } else {
    Serial.println("Failed to publish temperature");
  }

  // Read and publish the voltage
  float voltage = readVoltage();
  char voltageString[8];
  dtostrf(voltage, 1, 2, voltageString); // Format voltage as a string

  if (client.publish(voltage_topic, voltageString)) {
    Serial.println("Voltage published successfully");
  } else {
    Serial.println("Failed to publish voltage");
  }

  client.loop();
  yield();

  Serial.print("Temperature: ");
  Serial.print(temperature);
  Serial.println(" °C");
  Serial.print("Voltage: ");
  Serial.print(voltage);
  Serial.println(" V");

  delay(100);

  Serial.println("Setting GPIO15 as output here... ");
  delay(100);
  pinMode(DONE, OUTPUT);
  yield();
  Serial.println("Setting GPIO15 high here... ");
  delay(100);
  digitalWrite(DONE, HIGH);
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();
}
