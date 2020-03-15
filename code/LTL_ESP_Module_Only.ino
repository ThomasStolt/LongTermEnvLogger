// Wemos D1 board, connected to a battery box and a DS18B20 temperature sensor
//
 
// For temperature reading
// Libraries needed:
// * OneWire
// * DallasTemperature
//
// Pinout: https://wiki.wemos.cc/products:d1:d1_mini
// D0 = GPIO16 --> Connect D0 to RST for Deep Sleep-Wakeup
 
#include <OneWire.h> 
#include <DallasTemperature.h>
 
const char* ssid = "";
const char* password = "";
 
#define DEVICENAME "HCG"
#define TOPIC DEVICENAME"/045"
#define ONLINETOPIC DEVICENAME"/online"
#define MQTTSERVER IPAddress(192, 168, 2, 146)
const int sleepTimeS = 300; // 300 Reduce this value for debugging. Increase if you want more battery life
 
#define VCCPIN 7 // D7
#define ONE_WIRE_BUS 2 // D2
#define GNDPIN 5 // D5
 
OneWire oneWire(ONE_WIRE_BUS); 
DallasTemperature sensors(&oneWire);
 
float tempC;
 
// For WLAN & MQTT
#include <ESP8266WiFi.h>
#include <AsyncMqttClient.h>
AsyncMqttClient mqttClient;
uint16_t packetId1Pub;
bool packet1Ack = false;
 
bool ready = false;
 
char *ftoa( double f, char *a, int precision)
{
 long p[] = {0,10,100,1000,10000,100000,1000000,10000000,100000000};
 
 char *ret = a;
 long heiltal = (long)f;
 itoa(heiltal, a, 10);
 while (*a != '\0') a++;
 *a++ = '.';
 long desimal = abs((long)((f - heiltal) * p[precision]));
 itoa(desimal, a, 10);
 return ret;
}
 
void onMqttPublish(uint16_t packetId) {
  Serial.println("** Publish acknowledged **");
  Serial.print("  packetId: ");
  Serial.println(packetId);
  if (packetId == packetId1Pub) {
    packet1Ack = true;
  }
  if (packet1Ack) {
    ready = true;
  }
}
 
void onMqttConnect(bool sessionPresent) {
  char buf[7];
  packetId1Pub = mqttClient.publish(TOPIC, 1, true, ftoa(tempC, buf, 2));
}
 
void setup() {
  // ## pinMode(GNDPIN, OUTPUT);
  // ## pinMode(VCCPIN, OUTPUT);
  // ## digitalWrite(GNDPIN, LOW);
  // ## digitalWrite(VCCPIN, HIGH);
  Serial.begin(115200); 
  Serial.println("ESP-Temperature-Reader-and-MQTT-Poster-via-WiFi"); 
  // Start up the sensors library 
  // ## sensors.begin(); 
}
 
void loop() {
  // Send the command to get temperature readings 
  Serial.println("Requesting Temperature"); 
  sensors.requestTemperatures();
 
  // You can have more than one DS18B20 on the same bus.  
  // 0 refers to the first IC on the wire 
  Serial.println("Requesting Temperature from Device 0"); 
  tempC = sensors.getTempCByIndex(0);
  Serial.println(tempC);
  Serial.println("Connecting to WIFI"); 
  // Connect to WiFi
  WiFi.begin(ssid, password);
  int timeout = 0;
  while (WiFi.status() != WL_CONNECTED) {
    timeout++;
    if (timeout>20) {
        // WIFI isn't available after 10 seconds -> abort mission, mission's a failure
        initiateDeepSleep();
      }
    delay(500);
    Serial.print(".");
  }
  Serial.println("");
  Serial.println("WiFi connected");
 
  // Print the IP address
  Serial.println(WiFi.localIP());
 
  // Publish result to MQTT
  mqttClient.onConnect(onMqttConnect);
  mqttClient.onPublish(onMqttPublish);
  mqttClient.setServer(MQTTSERVER, 1883);
  // mqttClient.setKeepAlive(5).setCleanSession(false).setWill(ONLINETOPIC, 2, true, "no"); // .setCredentials("user", "pass").setClientId(DEVICENAME);
  mqttClient.setKeepAlive(5).setCleanSession(false).setWill(ONLINETOPIC, 2, true, "no").setCredentials("iobroker", "Benjamin_04").setClientId(DEVICENAME);
  Serial.println("Connecting to MQTT...");
  mqttClient.connect();
 
  timeout = 0;
  while (!ready) {
    delay(250);
    timeout++;
    if (timeout > 40)
    {
        // MQTT isn't available after 10 seconds -> abort mission, mission's a failure
        initiateDeepSleep();
    }
    Serial.print(".");
  }
  Serial.println("going to sleep");
  initiateDeepSleep();
  delay(1000);
}
 
void initiateDeepSleep()
{
  ESP.deepSleep(sleepTimeS * 1000000);
  delay(100); 
}
