# Long Term Environment Logger

The aim of this project is to measure, store, display and evaluate the temperature in the rooms of a large building over an extended time period. This project has 2 main components:

A. The hardware of the sensor.

B. The server infrastructure to receive, store and display the measurements.

## The Hardware

1. A low power timer circuit that uses nano-Amps only when asleep and wakes up the entire circuit every approx. 5 minutes for measurement.

2. An LDO voltage regulator that regulates the incoming battery voltage from a LiIon battery to 3.3V

3. A battery voltage sensor that sends the battery voltage to the ESP8266 ADC pin with a voltage divider so that the battery voltage can be monitored.

4. The ESP8266 with a DS18B20 temperature sensor. 

... and some additional mechanical and electronic components.

The ESP8266 was chosen as the microcontroller. It is versatile, very affordable, has more than enough functionality and information is easy to find.

If you think about it in detail, this project is not quite as trivial as it first appears. Some of the things to consider are:

* Runtime - How long does a single battery last?

  * As the battery-operated temperature sensors are to be distributed throughout a building, you want the individual sensors to run for as long as possible, so that you don't have to run around the building changing or charging batteries all the time. One option is the energy-saving mode ("DeepSleep") of the microcontroller. This would reduce the current draw during deep sleep to about 14µA. However, we want to achieve single digit µA or less sleep current.

* Update OTA(?)
	* It might be worth considering adding this capability. This would probably affect the runtime as well, because if we check for updates every time the circuit wakes up, it will cost runtime and energy. So, the question here is, how much runtime this would cost.

* WiFi Connection Time
	* When the ESP8266 wakes up and has WiFi switched on, it draws about 70mA, which is a lot. So, all efforts need to be taken to reduce the connection time to be a short as possible.

* Power supply / battery
	* Li-Ion batteries are a good energy source for this type of project, especially the 18650 type. They are relatively inexpensive for their capacity. However, as these batteries are very sensitive to mishandling, it is important to take appropriate precautions.
		* How can you ensure that the LiIon battery will not be deep discharged?
		* How can I ensure that the LiIon battery cannot be overcharged?
		* How can I monitor the voltage of the power supply (of the LiIo battery) in order to replace or charge the battery in good time?
		* All batteries must be checked regularly for their capacity and possible health issues.

## Overview

First a short diagram for an overview:

![alt text](<https://github.com/ThomasStolt/LongTermEnvLogger/blob/master/images/PrincipleArchitecture.png>)


