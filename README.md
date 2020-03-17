# Long Term Environment Logger Project

Das Ziel dieses Projektes ist es, die Temperatur in den Räumen eines Gebäudes über einen sehr langen Zeitraum (> 6 Monate) zu messen, speichern, auszuwerten und darzustellen. Dazu wird eine einfache Schaltung um den Mikroprozessor ESP8266 benutzt. Im Wesentlichen besteht diese Schaltung aus einem Lithium-Ionen Akku, einem Mikrocontroller, einer Diode zur Spannungsabsenkung, einem oder mehreren Sensoren, sowie einigen zusätzlichen mechanischen und elektronischen Bauteilen.

Als Mikrocontroller fällt die Wahl auf den ESP8266. Er ist vielseitig, sehr preisgünstig und Informationen sind leicht zu finden.

Dieses Projekt ist, wenn man es sich im Detail durchdenkt, nicht ganz so trivial, wie es zunächst den Anschein hat. Zu bedenken sind unter anderem:

* Laufzeit - Wie kann man eine lange Laufzeit erreichen?
	* Da die batteriebetriebenen Temperatursensoren in vielen Räumen in einem Gebäude verteilt werden sollen, möchte man eine möglichst lange Laufzeit der einzelnen Sensoren haben. Hierzu muss der Energiesparmodus ("DeepSleep") des Mikrocontrollers genutzt werden. Allderdings vergisst der ESP8266 alle seine Stati und Variablen. Das muss also bedacht werden.
* Update OTA
	* Ist es möglich, eine Updatefähigkeit gewährleisten ohne ständig an alle LTELs physisch ran zu müssen?
* Energieversorgung / Batterie
	* Eine gute Energiequelle für diese Art von Projekten sind Li-Ionen-Akkus, insbesondere die Bauform 18650. Sie sind zum einen sehr preiswert, haben zum anderen aber eine hohe Kapazität. Da diese Akkus aber gegen Fehlbehandlung sehr empfindlich sind, gilt es entsprechende Vorkehrungen zu treffen
	* Wie kann man sicherstellen, dass der LiIon Akku nicht tiefentladen werden kann? 
	* Wie kann man sicherstellen, dass der LiIon Akku nicht überladen werden kann?
	* Wie kann ich die Spannung der Stromversorung (des LiIo Akkus) überwachen um rechtzeitig den Akku auszutauschen oder zu laden?

## Überblick

Zunächst ein kurzes Schaubild für den Überblick:

![alt text](<https://github.com/ThomasStolt/LongTermEnvLogger/blob/master/Solution%20Architecture%2020200317.png>)

Das Projekt besteht somit aus mehreren Teilprojekten:

1. Der Logger (Hardware)
2. Das Programm - Micropython wäre hier ideal, leider gibt es schlechte Erfahrungen mit MQTT unter MicroPython
3. MQTT Broker
4. Logging in eine Datenbank (MariaDB)
4. Darstellung der Wert in einem Dashboard


## 1. Temperatur Logger
Bestehend aus:
1 x ESP8266 als Mikroprozessor
1 x Gehäuse / Schachtel
2 x Taster (Reset & Flash)
1 x LiIon 18650 Akku
1 x 100µA Kondensator
1 x Diode (zur Spannungsabsenkung)
1 x Temperatursensor DS18B20
diverse Widerstände
1 x Ladebuchse
1 x 3-Pin-Buchse für seriellen Port

1 x "Stop-Schalter" mit PullUp Widerstand

Die Schaltung findet sich [hier](https://github.com/Crayfish68/LongTermEnvLogger/blob/master/kicad/PDF/LTEL_Schaltplan.pdf).

## 2. Das Programm
Hier mit MicroPython geschrieben.

## 3. MQTT Broker
iobroker hat sich als eine gute Lösung hier ergeben.


## 4. Infrastruktur zur Auswertung
Eine populäre, einfache und zugleich beeindruckende Lösung bietet sich hier Grafana an.


# LongTermEnvLogger
