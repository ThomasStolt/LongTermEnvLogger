# Long Term Environment Logger Project

Das Ziel dieses Projektes ist es, die Temperatur und andere Umweltdaten in den Räumen eines Gebäudes über einen sehr langen Zeitraum (> 6 Monate) zu messen, speichern, auszuwerten und darzustellen. Dazu wird eine einfache Schaltung um den Mikroprozessor ESP8266 benutzt. Im Wesentlichen besteht diese Schaltung aus einem Lithium-Ionen Akku, einer Diode zur Spannungsabsenkung, einem oder mehreren Sensoren, einem Mikrocontroller, sowie einigen zusätzlichen mechanischen und elektronischen Bauteilen.

Dieses Projekt ist, wenn man es sich im Detail durchdenkt, nicht ganz so trivial, wie es zunächst den Anschein hat. Zu bedenken sind unter anderem:

* Wie kann man eine lange Laufzeit erreichen?
	* Hierzu kann der Energiesparmodus ("DeepSleep") des ESP8266 genutzt werden. Allderdings vergisst der ESP8266 alle seine Stati und Variablen. Das muss also bedacht werden.
* Wie kann man eine Updatefähigkeit gewährleisten ohne ständig an alle LTELs physisch ran zu müssen?
	* Updates "Over The Air"?
* Eine gute Energiequelle für diese Art von Projekten sind Li-Ionen-Akkus, insbesondere die Bauform 18650. Sie sind zum einen sehr preiswert, haben zum anderen aber eine hohe Kapazität. Da diese Akkus aber gegen Fehlbehandlung sehr empfindlich sind, gilt es allerdings Vorkehrungen zu treffen
	* Wie kann man sicherstellen, dass der LiIon Akku nicht tiefentladen werden kann? 
	* Wie kann man sicherstellen, dass der LiIon Akku nicht überladen werden kann?
	* Wie kann ich die Spannung der Stromversorung (des LiIo Akkus) überwachen um rechtzeitig den Akku auszutauschen oder zu laden?

Das Projekt besteht somit aus mehreren Teilprojekten:

1. Der Logger (Hardware)
2. Das Programm - hier benutze ich MicroPython
3. MQTT Broker
4. Infrastruktur zur Auswertung (schnelle Lösung: Node-RED)


## 1. Temperatur Logger
Bestehend aus:
1 x ESP8266 als Mikroprozessor
1 x Gehäuse / Schachtel
2 x Taster (Reset & Flash)
1 x LiIon 18650 Akku
1 x 1000µA Kondensator
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
Mosquitto


## 4. Infrastruktur zur Auswertung
Im Moment eine schnelle Lösung mit Node-RED. 





# LongTermEnvLogger
