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
	* Li-ion batteries are a good energy source for this type of project, especially the 18650 type. They are very inexpensive, but also have a high capacity. However, as these batteries are very sensitive to mishandling, it is important to take appropriate precautions
How can you ensure that the LiIon battery cannot be deep discharged?
How can I ensure that the LiIon battery cannot be overcharged?
How can I monitor the voltage of the power supply (of the LiIo battery) in order to replace or charge the battery in good time?


* Laufzeit - Wie kann man eine lange Laufzeit erreichen?
	* Wenn die batteriebetriebenen Temperatursensoren in vielen RDiumen in einem Geb??ude verteilt werden sollen, m????chte man eine m????glichst lange Laufzeit der einzelnen Sensoren haben. Hierzu muss der Energiesparmodus ("DeepSleep") des Mikrocontrollers genutzt werden. Allderdings vergisst der ESP8266 alle seine Stati und Variablen. Das muss also bedacht werden.
* Update OTA
	* Ist es m????glich, eine Updatef????higkeit gew????hrleisten ohne st????ndig an alle LTELs physisch ran zu m????ssen?
* Energieversorgung / Batterie
	* Eine gute Energiequelle f????r diese Art von Projekten sind Li-Ionen-Akkus, insbesondere die Bauform 18650. Sie sind zum einen sehr preiswert, haben zum anderen aber eine hohe Kapazit????t. Da diese Akkus aber gegen Fehlbehandlung sehr empfindlich sind, gilt es entsprechende Vorkehrungen zu treffen
	* Wie kann man sicherstellen, dass der LiIon Akku nicht tiefentladen werden kann? 
	* Wie kann man sicherstellen, dass der LiIon Akku nicht ????berladen werden kann?
	* Wie kann ich die Spannung der Stromversorung (des LiIo Akkus) ????berwachen um rechtzeitig den Akku auszutauschen oder zu laden?

## ????berblick

Zun????chst ein kurzes Schaubild f????r den ????berblick:

![alt text](<https://github.com/ThomasStolt/LongTermEnvLogger/blob/master/Solution%20Architecture%2020200317.png>)

Bei mir l????uft diese L????sung momentan in der Alternative 1. Da iobroker relativ hohe Anforderungen an das System stellt, k????nnte sicherlich auch NodeRED zum Einsatz kommen. Dadurch d????rften sich die Anforderungen etwas verbessern.

Das Projekt besteht somit aus mehreren Teilprojekten:

1. Der Logger (Hardware)
2. Das Programm - Micropython w????re hier ideal, leider gibt es schlechte Erfahrungen mit MQTT unter MicroPython
3. MQTT Broker
4. Logging in eine Datenbank (MariaDB)
4. Darstellung der Wert in einem Dashboard


## 1. Temperatur Logger
Bestehend aus:
* 1 x ESP8266 als Mikroprozessor
* 1 x Geh????use / Schachtel
* 2 x Taster (Reset & Flash)
* 1 x LiIon 18650 Akku
* 1 x 1000????A Elektrolytkondensator
* 1 x Diode (zur Spannungsabsenkung)
* 1 x Temperatursensor DS18B20
* diverse Widerst????nde
* 1 x TP4605 Lade/Entladeschutzmodul
* 1 x 3-Pin-Buchse (JST-XH) f????r seriellen Port

Die Schaltung findet sich [hier](https://github.com/Crayfish68/LongTermEnvLogger/blob/master/kicad/PDF/LTEL_Schaltplan.pdf).

## 2. Das Programm
Hier mit MicroPython geschrieben.

## 3. MQTT Broker
iobroker hat sich als eine gute L????sung hier ergeben.


## 4. Infrastruktur zur Auswertung
Eine popul????re, einfache und zugleich beeindruckende L????sung bietet sich hier Grafana an.


# LongTermEnvLogger
