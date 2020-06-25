#####################################################
# tlt.py = Long Term Temperatur Logger Project
#####################################################
# Autor: Thomas Stolt
# Last update (this line): 16.10.2017
#####################################################

#####################################################
# Imports
#####################################################
import machine, time, sys, onewire, ds18x20, network, utime
from umqtt.simple import MQTTClient

#####################################################
# Global definitions
#####################################################
WLAN_ESSID = "WIFI_SSID"
WLAN_PASSWORD = "WIFI_PASSWORD"
MQTT_URL = "MQTT_URL"
MQTT_PORT = 1884
MQTT_CLIENT = "LTL_00"
DS1820_PIN = 5
LED = machine.Pin(2, machine.Pin.OUT)
DS_TIME = 300000 # Deep sleep time in ms, set to 5 mins
# DS_TIME = 20000 # Deep sleep time in ms, set to 20 seconds (for testing)
RUN = True

#####################################################
# Start indication
#####################################################
for i in range(1):
    LED.off()
    time.sleep(0.05)
    LED.on()
    time.sleep(0.01)


#####################################################
# Configuring Deep Sleep
#####################################################
# configure RTC.ALARM0 to be able to wake the device
rtc = machine.RTC()
rtc.irq(trigger=rtc.ALARM0, wake=machine.DEEPSLEEP)

# set RTC.ALARM0 to fire after 10 seconds (waking the device)
rtc.alarm(rtc.ALARM0, DS_TIME)


#####################################################
# Configuring voltage object
#####################################################
vcc = machine.ADC(0)


#####################################################
# WiFi Setup
#####################################################
sta_if = network.WLAN(network.STA_IF)
# sta_if.ifconfig(('192.168.2.160','255.255.255.0','192.168.2.1','192.168.2.1'))
sta_if.ifconfig(('172.20.10.2', '255.255.255.240', '172.20.10.1', '172.20.10.1'))
retries = 0
if not sta_if.isconnected():
    sta_if.active(True)
    sta_if.connect(WLAN_ESSID, WLAN_PASSWORD)
    while not sta_if.isconnected():
        time.sleep_ms(1000)
        retries = retries + 1
        print('.', end='')
        if retries == 20:
            sys.exit()
print('Netzwerk verbunden, Konfiguration:', sta_if.ifconfig())

#####################################################
# Check for new firmware - tbd
#####################################################


#####################################################
# Temperatursensor Setup
#####################################################
DAT = machine.Pin(DS1820_PIN)
DS = ds18x20.DS18X20(onewire.OneWire(DAT))
roms = DS.scan()
print('found devices:', roms)


#####################################################
# Setup MQTT Call Back function
#####################################################
def sub_cb(topic, msg):
    global RUN
    print("MQTT Call Back Function")
    if "stop" in topic:
        RUN = False
        print("Stop empfangen!")

#####################################################
# Setup MQTT Object
#####################################################
c = MQTTClient(MQTT_CLIENT, MQTT_URL, MQTT_PORT)
c.set_callback(sub_cb)
print("MQTT call back function set up")

#####################################################
# Main program
#####################################################

# Read voltage
voltage = vcc.read()
# still to be done using RTC buckets
# need to figure out previous voltage value to eliminate rogue values
# if (voltage > 1.5 * voltage_old):
#        print("Bereinigt! voltage was =", voltage, "set to =", end='')
#        voltage = voltage_old
#        print(voltage)
# Read temperature
for rom in roms:
    DS.convert_temp()
    time.sleep_ms(750)
    temp = str(DS.read_temp(rom))
# Send values through MQTT
print("Connecting to MQTT")
c.status = c.connect()
c.subscribe("temp")
c.subscribe("voltage")
c.subscribe("stop", qos=2)
print("Publishing temperature", temp, " and voltage", voltage)
c.publish("temp", temp)
c.publish("voltage", str(voltage))

c.check_msg()
print("nach MQTT Nachrichten geguckt!")
if RUN == False:
    sys.exit()
    
c.disconnect()
print("Disconnected from MQTT")



if rtc.memory() == b'init':
    print("War im Deep Sleep")
else:
    print("War noch nicht im Deep Sleep")

rtc.memory(b'init')

# Go to deep sleep
print("Going to deep sleep")
machine.deepsleep()


#####################################################
# End                                               #
#####################################################
