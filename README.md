# on_demand_sync_clock
On-Demand Sync Clock (OSC), a DIY smart table clock that calibrates itself with one touch of a button.

<br><br>
![title image](/images/slc_picture_small.jpg)![title image](/images/osc_picture_small.jpg)


The distinctive feature of this clock is its effortless adjustment: Simply press the push-button while an open network (Wi-Fi without password) is available, for instance, a smartphone hotspot.



Timekeeping is handled by a DS3231SN Real-Time Clock (RTC) module, which features a temperature-compensated crystal oscillator. According to the datasheet, its accuracy is within ±2 ppm (approximately ±1 minute per year).

When the button is pressed, the clock synchronizes with NTP servers. If at least 14 days have passed since the previous sync, it also calculates the drift and automatically adjusts the DS3231SN’s internal aging factorto improve long-term accuracy.

This automatic calibration is particularly handy, as many DS3231 chips on the market (in all versions, SN included) are clones with lower precision.



In short, the On-demand Sync Clock (OSC) is a DIY smart table clock that synchronizes with NTP servers on-demand via a button press, calibrates its RTC drift automatically, and runs for months on a battery.

This makes the OSC a practical option for any location without permanent internet access.


<br><br>
## Repo content
- all the Micropython files
- the Gerber files to make the Connections board


<br><br>
## For more information
More detailed informations at my [Instructables page](https://www.instructables.com/On-demand-Sync-Clock-OSC/)

