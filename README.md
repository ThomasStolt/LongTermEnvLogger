# Long Term Environment Logger

The aim of this project is to measure, store, evaluate and display the temperature in the rooms of a building over as long a period as possible (1 year +). A simple circuit around the ESP8266 microprocessor is used for this purpose. Essentially, this circuit consists of 4 components:

1. A low power timer circuit that wakes up the entire circuit every approx. 5 minutes

2. A voltage regulator that regulates the incoming battery voltage from 4.2V nominal to 3.3V

3. A battery sensor that sends the battery voltage to the ESP8266 ADC pin with a voltage divider so that the battery voltage can be monitored

4. The ESP8266 with a DS18B20 temperature sensor 

... and some additional mechanical and electronic components.

The ESP8266 was chosen as the microcontroller. It is versatile, very affordable, has more than enough functionality and information is easy to find.

If you think about it in detail, this project is not quite as trivial as it first appears. Some of the things to consider are

* Running time - How can you achieve a long running time?

	* As the battery-operated temperature sensors are to be distributed throughout a building, you want the individual sensors to run for as long as possible. One option is the energy-saving mode ("DeepSleep") of the microcontroller. This would reduce the current draw during deep sleep to about 14uA. However, we want to achieve single digit uA sleep current.

* Update OTA

	* Is it possible to ensure update capability without having to physically access all LTELs all the time?

* Power supply / battery
	* Li-ion batteries are a good energy source for this type of project, especially the 18650 type. They are relatively inexpensive for their capacity. However, as these batteries are very sensitive to mishandling, it is important to take appropriate precautions.
		* How can you ensure that the LiIon battery cannot be deep discharged?
		* How can I ensure that the LiIon battery cannot be overcharged?
		* How can I monitor the voltage of the power supply (of the LiIo battery) in order to replace or charge the battery in good time?

## Overview

First a short diagram for an overview:

![alt text](<https://github.com/ThomasStolt/LongTermEnvLogger/blob/master/images/PrincipleArchitecture.png>)


