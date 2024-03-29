EESchema Schematic File Version 5
EELAYER 36 0
EELAYER END
$Descr A4 11693 8268
encoding utf-8
Sheet 1 1
Title "Long Term Environment Logger (LTEL)"
Date "2020-03-26"
Rev "1.2"
Comp "HCG Berlin"
Comment1 "Thomas Stolt"
Comment2 ""
Comment3 ""
Comment4 ""
Comment5 ""
Comment6 ""
Comment7 ""
Comment8 ""
Comment9 ""
$EndDescr
Connection ~ 4400 3900
Connection ~ 4400 4000
Connection ~ 4400 4600
Connection ~ 5050 3700
Connection ~ 5050 4000
Connection ~ 5050 4600
Connection ~ 6450 3600
Connection ~ 6550 3400
Connection ~ 8600 3600
Connection ~ 9150 3200
NoConn ~ 1750 3700
NoConn ~ 1750 4200
NoConn ~ 6650 3500
NoConn ~ 6650 3800
NoConn ~ 6650 3900
NoConn ~ 6650 4000
NoConn ~ 7300 4600
NoConn ~ 7400 4600
NoConn ~ 7500 4600
NoConn ~ 7600 4600
NoConn ~ 7700 4600
NoConn ~ 7800 4600
NoConn ~ 8450 3700
NoConn ~ 8450 3900
NoConn ~ 12400 7300
Wire Wire Line
	3250 3800 2950 3800
Wire Wire Line
	3250 4100 2950 4100
Wire Wire Line
	3600 3100 3600 3250
Wire Wire Line
	3600 3550 3600 3700
Wire Wire Line
	3600 3700 2950 3700
Wire Wire Line
	3600 4200 2950 4200
Wire Wire Line
	3600 4800 3600 4200
Wire Wire Line
	3950 3100 3950 4150
Wire Wire Line
	3950 4450 3950 4800
Wire Wire Line
	4400 3100 4400 3300
Wire Wire Line
	4400 3600 4400 3900
Wire Wire Line
	4400 3900 4400 4000
Wire Wire Line
	4400 4000 4500 4000
Wire Wire Line
	4400 4600 4500 4600
Wire Wire Line
	4400 4800 4400 4600
Wire Wire Line
	5050 3100 5050 3300
Wire Wire Line
	5050 3600 5050 3700
Wire Wire Line
	5050 3700 5050 4000
Wire Wire Line
	5050 4000 5150 4000
Wire Wire Line
	5050 4600 5150 4600
Wire Wire Line
	5050 4800 5050 4600
Wire Wire Line
	5200 3700 5050 3700
Wire Wire Line
	5600 3700 5500 3700
Wire Wire Line
	5600 4700 5600 3700
Wire Wire Line
	5600 4700 8500 4700
Wire Wire Line
	5800 3400 5800 3900
Wire Wire Line
	5800 3900 4400 3900
Wire Wire Line
	6450 3100 6450 3600
Wire Wire Line
	6450 3600 6450 4100
Wire Wire Line
	6450 4100 6650 4100
Wire Wire Line
	6550 3400 5800 3400
Wire Wire Line
	6550 3400 6550 3700
Wire Wire Line
	6550 3700 6650 3700
Wire Wire Line
	6650 3400 6550 3400
Wire Wire Line
	6650 3600 6450 3600
Wire Wire Line
	8450 2550 8750 2550
Wire Wire Line
	8450 3400 8450 2550
Wire Wire Line
	8450 3500 8500 3500
Wire Wire Line
	8450 3600 8600 3600
Wire Wire Line
	8450 3800 8500 3800
Wire Wire Line
	8450 4100 8600 4100
Wire Wire Line
	8500 2650 8750 2650
Wire Wire Line
	8500 3500 8500 2650
Wire Wire Line
	8500 3800 8500 4700
Wire Wire Line
	8600 3500 8600 3600
Wire Wire Line
	8600 3600 8850 3600
Wire Wire Line
	8600 4100 8600 4800
Wire Wire Line
	8850 4000 8450 4000
Wire Wire Line
	8850 4300 8850 4000
Wire Wire Line
	8850 4800 8850 4600
Wire Wire Line
	9150 3100 9150 3200
Wire Wire Line
	9150 3200 8600 3200
Wire Wire Line
	9150 3200 9150 3300
Wire Wire Line
	9150 4800 9150 3900
Wire Wire Line
	9400 2750 9400 4800
Wire Wire Line
	9450 2550 9050 2550
Wire Wire Line
	9450 2650 9050 2650
Wire Wire Line
	9450 2750 9400 2750
Text Notes 1650 4000 0    60   ~ 0
USB
Text Label 9300 2550 0    60   ~ 0
TxD
Text Label 9300 2650 0    60   ~ 0
RxD
Text Label 9300 2750 0    60   ~ 0
GND
$Comp
L ltl-rescue:+3.3V-power #PWR01
U 1 1 59EE392B
P 3600 3100
F 0 "#PWR01" H 3600 2950 50  0001 C CNN
F 1 "+3.3V" H 3600 3240 50  0000 C CNN
F 2 "" H 3600 3100 50  0001 C CNN
F 3 "" H 3600 3100 50  0001 C CNN
	1    3600 3100
	1    0    0    -1  
$EndComp
$Comp
L ltl-rescue:+3.3V-power #PWR03
U 1 1 59EE3A01
P 3950 3100
F 0 "#PWR03" H 3950 2950 50  0001 C CNN
F 1 "+3.3V" H 3950 3240 50  0000 C CNN
F 2 "" H 3950 3100 50  0001 C CNN
F 3 "" H 3950 3100 50  0001 C CNN
	1    3950 3100
	1    0    0    -1  
$EndComp
$Comp
L ltl-rescue:+3.3V-power #PWR05
U 1 1 59EE3A18
P 4400 3100
F 0 "#PWR05" H 4400 2950 50  0001 C CNN
F 1 "+3.3V" H 4400 3240 50  0000 C CNN
F 2 "" H 4400 3100 50  0001 C CNN
F 3 "" H 4400 3100 50  0001 C CNN
	1    4400 3100
	1    0    0    -1  
$EndComp
$Comp
L ltl-rescue:+3.3V-power #PWR07
U 1 1 59EE3A2F
P 5050 3100
F 0 "#PWR07" H 5050 2950 50  0001 C CNN
F 1 "+3.3V" H 5050 3240 50  0000 C CNN
F 2 "" H 5050 3100 50  0001 C CNN
F 3 "" H 5050 3100 50  0001 C CNN
	1    5050 3100
	1    0    0    -1  
$EndComp
$Comp
L ltl-rescue:+3.3V-power #PWR09
U 1 1 59EE354C
P 6450 3100
F 0 "#PWR09" H 6450 2950 50  0001 C CNN
F 1 "+3.3V" H 6450 3240 50  0000 C CNN
F 2 "" H 6450 3100 50  0001 C CNN
F 3 "" H 6450 3100 50  0001 C CNN
	1    6450 3100
	1    0    0    -1  
$EndComp
$Comp
L ltl-rescue:+3.3V-power #PWR012
U 1 1 59EF6E6A
P 9150 3100
F 0 "#PWR012" H 9150 2950 50  0001 C CNN
F 1 "+3.3V" H 9150 3240 50  0000 C CNN
F 2 "" H 9150 3100 50  0001 C CNN
F 3 "" H 9150 3100 50  0001 C CNN
	1    9150 3100
	1    0    0    -1  
$EndComp
$Comp
L power:GND #PWR02
U 1 1 59EE3907
P 3600 4800
F 0 "#PWR02" H 3600 4550 50  0001 C CNN
F 1 "GND" H 3600 4650 50  0000 C CNN
F 2 "" H 3600 4800 50  0001 C CNN
F 3 "" H 3600 4800 50  0001 C CNN
	1    3600 4800
	1    0    0    -1  
$EndComp
$Comp
L power:GND #PWR04
U 1 1 59EE39B5
P 3950 4800
F 0 "#PWR04" H 3950 4550 50  0001 C CNN
F 1 "GND" H 3950 4650 50  0000 C CNN
F 2 "" H 3950 4800 50  0001 C CNN
F 3 "" H 3950 4800 50  0001 C CNN
	1    3950 4800
	1    0    0    -1  
$EndComp
$Comp
L power:GND #PWR06
U 1 1 59EE39D3
P 4400 4800
F 0 "#PWR06" H 4400 4550 50  0001 C CNN
F 1 "GND" H 4400 4650 50  0000 C CNN
F 2 "" H 4400 4800 50  0001 C CNN
F 3 "" H 4400 4800 50  0001 C CNN
	1    4400 4800
	1    0    0    -1  
$EndComp
$Comp
L power:GND #PWR08
U 1 1 59EE39EA
P 5050 4800
F 0 "#PWR08" H 5050 4550 50  0001 C CNN
F 1 "GND" H 5050 4650 50  0000 C CNN
F 2 "" H 5050 4800 50  0001 C CNN
F 3 "" H 5050 4800 50  0001 C CNN
	1    5050 4800
	1    0    0    -1  
$EndComp
$Comp
L power:GND #PWR010
U 1 1 59EF6848
P 8600 4800
F 0 "#PWR010" H 8600 4550 50  0001 C CNN
F 1 "GND" H 8600 4650 50  0000 C CNN
F 2 "" H 8600 4800 50  0001 C CNN
F 3 "" H 8600 4800 50  0001 C CNN
	1    8600 4800
	1    0    0    -1  
$EndComp
$Comp
L power:GND #PWR011
U 1 1 59EF69A1
P 8850 4800
F 0 "#PWR011" H 8850 4550 50  0001 C CNN
F 1 "GND" H 8850 4650 50  0000 C CNN
F 2 "" H 8850 4800 50  0001 C CNN
F 3 "" H 8850 4800 50  0001 C CNN
	1    8850 4800
	1    0    0    -1  
$EndComp
$Comp
L power:GND #PWR013
U 1 1 59EF6E0B
P 9150 4800
F 0 "#PWR013" H 9150 4550 50  0001 C CNN
F 1 "GND" H 9150 4650 50  0000 C CNN
F 2 "" H 9150 4800 50  0001 C CNN
F 3 "" H 9150 4800 50  0001 C CNN
	1    9150 4800
	1    0    0    -1  
$EndComp
$Comp
L power:GND #PWR014
U 1 1 59EF7331
P 9400 4800
F 0 "#PWR014" H 9400 4550 50  0001 C CNN
F 1 "GND" H 9400 4650 50  0000 C CNN
F 2 "" H 9400 4800 50  0001 C CNN
F 3 "" H 9400 4800 50  0001 C CNN
	1    9400 4800
	1    0    0    -1  
$EndComp
$Comp
L ltl-rescue:R R1
U 1 1 59EE3A60
P 4400 3450
F 0 "R1" V 4480 3450 50  0000 C CNN
F 1 "2,2k" V 4400 3450 50  0000 C CNN
F 2 "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal" V 4330 3450 50  0001 C CNN
F 3 "" H 4400 3450 50  0001 C CNN
	1    4400 3450
	1    0    0    -1  
$EndComp
$Comp
L ltl-rescue:R R2
U 1 1 59EE3AD1
P 5050 3450
F 0 "R2" V 5130 3450 50  0000 C CNN
F 1 "2,2k" V 5050 3450 50  0000 C CNN
F 2 "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal" V 4980 3450 50  0001 C CNN
F 3 "" H 5050 3450 50  0001 C CNN
	1    5050 3450
	1    0    0    -1  
$EndComp
$Comp
L ltl-rescue:R R3
U 1 1 59EE3B0F
P 5350 3700
F 0 "R3" V 5430 3700 50  0000 C CNN
F 1 "2,2k" V 5350 3700 50  0000 C CNN
F 2 "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal" V 5280 3700 50  0001 C CNN
F 3 "" H 5350 3700 50  0001 C CNN
	1    5350 3700
	0    1    1    0   
$EndComp
$Comp
L ltl-rescue:R R4
U 1 1 59EF6E96
P 8600 3350
F 0 "R4" V 8680 3350 50  0000 C CNN
F 1 "4,7k" V 8600 3350 50  0000 C CNN
F 2 "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal" V 8530 3350 50  0001 C CNN
F 3 "" H 8600 3350 50  0001 C CNN
	1    8600 3350
	1    0    0    -1  
$EndComp
$Comp
L ltl-rescue:R R5
U 1 1 59EF68EB
P 8850 4450
F 0 "R5" V 8930 4450 50  0000 C CNN
F 1 "2,2k" V 8850 4450 50  0000 C CNN
F 2 "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal" V 8780 4450 50  0001 C CNN
F 3 "" H 8850 4450 50  0001 C CNN
	1    8850 4450
	-1   0    0    1   
$EndComp
$Comp
L Device:R R6
U 1 1 5E719AF2
P 8900 2550
F 0 "R6" V 8800 2550 50  0000 C CNN
F 1 "1k" V 8900 2550 50  0000 C CNN
F 2 "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal" V 8830 2550 50  0001 C CNN
F 3 "~" H 8900 2550 50  0001 C CNN
	1    8900 2550
	0    1    1    0   
$EndComp
$Comp
L Device:R R7
U 1 1 5E71AD9E
P 8900 2650
F 0 "R7" V 9000 2650 50  0000 C CNN
F 1 "1k" V 8900 2650 50  0000 C CNN
F 2 "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal" V 8830 2650 50  0001 C CNN
F 3 "~" H 8900 2650 50  0001 C CNN
	1    8900 2650
	0    1    1    0   
$EndComp
$Comp
L ltl-rescue:D D1
U 1 1 59EE385B
P 3600 3400
F 0 "D1" H 3600 3500 50  0000 C CNN
F 1 "1N4001" H 3600 3300 50  0000 C CNN
F 2 "Diode_THT:D_A-405_P7.62mm_Horizontal" H 3600 3400 50  0001 C CNN
F 3 "" H 3600 3400 50  0001 C CNN
	1    3600 3400
	0    1    1    0   
$EndComp
$Comp
L ltl-rescue:Battery_Cell BT1
U 1 1 59EE3594
P 3250 4000
F 0 "BT1" V 3350 4000 50  0000 L CNN
F 1 "18650" V 3150 3950 50  0000 L CNN
F 2 "18650:18650_small" V 3250 4060 50  0001 C CNN
F 3 "" V 3250 4060 50  0001 C CNN
	1    3250 4000
	1    0    0    -1  
$EndComp
$Comp
L ltl-rescue:CP C1
U 1 1 59EE3954
P 3950 4300
F 0 "C1" H 3975 4400 50  0000 L CNN
F 1 "1000uF" H 3975 4200 50  0000 L CNN
F 2 "Capacitor_THT:CP_Radial_D6.3mm_P2.50mm" H 3988 4150 50  0001 C CNN
F 3 "" H 3950 4300 50  0001 C CNN
	1    3950 4300
	1    0    0    -1  
$EndComp
$Comp
L ltl-rescue:CONN_01X03 J1
U 1 1 59EF7158
P 9650 2650
F 0 "J1" H 9650 2850 50  0000 C CNN
F 1 "CONN_01X03" V 9750 2650 50  0000 C CNN
F 2 "Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical" H 9650 2650 50  0001 C CNN
F 3 "" H 9650 2650 50  0001 C CNN
	1    9650 2650
	1    0    0    1   
$EndComp
$Comp
L LTL:SW_DIP_x02_LTL Reset1
U 1 1 5E7676F5
P 4450 4300
F 0 "Reset1" H 4200 4550 60  0000 L CNN
F 1 "Reset" H 4550 4550 60  0000 L CNN
F 2 "Button_Switch_THT:SW_PUSH_6mm" H 4450 4300 60  0001 C CNN
F 3 "" H 4450 4300 60  0001 C CNN
	1    4450 4300
	0    1    1    0   
$EndComp
$Comp
L LTL:SW_DIP_x02_LTL Flash1
U 1 1 5E769C54
P 5100 4300
F 0 "Flash1" H 4800 4550 60  0000 L CNN
F 1 "Flash" H 5150 4550 60  0000 L CNN
F 2 "Button_Switch_THT:SW_PUSH_6mm" H 5100 4300 60  0001 C CNN
F 3 "" H 5100 4300 60  0001 C CNN
	1    5100 4300
	0    1    1    0   
$EndComp
$Comp
L ltl-rescue:DS18B20 U3
U 1 1 59EF6A53
P 9150 3600
F 0 "U3" H 9000 3850 50  0000 C CNN
F 1 "DS18B20" H 9400 3850 50  0000 C CNN
F 2 "Package_TO_SOT_THT:TO-92" H 8150 3350 50  0001 C CNN
F 3 "" H 9000 3850 50  0001 C CNN
	1    9150 3600
	-1   0    0    -1  
$EndComp
$Comp
L LTL:TP4056 U1
U 1 1 5E7F3843
P 2350 3950
F 0 "U1" H 2350 4447 60  0000 C CNN
F 1 "TP4056" H 2350 4341 60  0000 C CNN
F 2 "TP4506:TP4056" H 2300 3850 60  0001 C CNN
F 3 "" H 2300 3850 60  0001 C CNN
	1    2350 3950
	1    0    0    -1  
$EndComp
$Comp
L ltl-rescue:ESP-12E-ESP8266 U2
U 1 1 5E6E4A20
P 7550 3700
F 0 "U2" H 7550 4465 50  0000 C CNN
F 1 "ESP-12E" H 7550 4374 50  0000 C CNN
F 2 "ESP8266:ESP-12E" H 7550 3700 50  0001 C CNN
F 3 "http://l0l.org.uk/2014/12/esp8266-modules-hardware-guide-gotta-catch-em-all/" H 7550 3700 50  0001 C CNN
	1    7550 3700
	1    0    0    -1  
$EndComp
$EndSCHEMATC
