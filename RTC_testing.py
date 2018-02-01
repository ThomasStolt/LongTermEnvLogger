import machine, time
rtc = machine.RTC()

rtcmem = machine.


rtc.datetime((2016, 10, 17, 3, 43, 00, 0, 0))
print(rtc.datetime())
print(time.localtime())
