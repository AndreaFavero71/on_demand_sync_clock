"""
Andrea Favero 20260103

On-demand Sync Clock (OSC)
A digital clock with on-request NTP syncing, via the push of a button.

The NTP sync is used to adjust the RTC of DS3231SN; If enough time has passed from
boot, or from the previous sync, the DS3231SN aging factor gets automatically calibrated.



The clock is based on
- LiLyGO TTGO T8-S3 board (v1.2)      [https://tinyurl.com/3tyy9sea]
- DS3231SN module                     [https://tinyurl.com/3vp7n53h]
- WaveShare 4.2 inches epaper display [https://www.waveshare.com/wiki/Pico-ePaper-4.2]

More info at:
  https://github.com/AndreaFavero71/on_demand_sync_clock
  https://www.instructables.com/On-Demand-sync-Clock/



MIT License

Copyright (c) 2026 Andrea Favero

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

__version__ = "0.0.1"

# import standard modules
from utime import ticks_ms, sleep_ms, ticks_diff, mktime
from machine import Pin, freq, lightsleep
import uasyncio as asyncio
from esp32 import NVS, wake_on_ext0, WAKEUP_ANY_HIGH
import sys, gc

# import OSC custom modules
from network_manager import NetworkManager
from time_manager import TimeManager
from display_manager import Display
from battery_manager import Battery
from wdt_manager import WDTManager
from lib.config import config

# pin used to energize the DS3231ZN module
NTP_SYNC_PIN = 21


class SelfLearningClock:
    def __init__(self, logo_time_ms):
        
        print()
        print("#" * 41)
        print("#  Clock started. Press Ctrl+C to stop  #")
        print("#" * 41)
        print()
        
        # lower ESP32-S3 frequency to reduce power consumption (80MHz is the minimum for wlan operation)
        freq = 80_000_000
        
        # check / make a folder for the log related files
        self._make_folder("log")
        
        # initialize the ntp_sync_pin imput pin to start a NTP Sync
        self.ntp_sync_pin = Pin(NTP_SYNC_PIN, Pin.IN, Pin.PULL_DOWN)
        
        # enable the GPIO as a wake source from lightsleep
        wake_on_ext0(pin=self.ntp_sync_pin, level=WAKEUP_ANY_HIGH)
        
        # initialize the module for time management
        self.time_mgr = TimeManager(config)
        
        # initialize WDT manager, before the modules where it is passed
        self.wdt_manager = WDTManager()
        
        # initialize display module, by also passing the WDT manager
        self.display = Display(wdt_manager = self.wdt_manager,
                               lightsleep_active = config.LIGHTSLEEP_USAGE,
                               battery = config.BATTERY,
                               degrees = config.TEMP_DEGREES,
                               hour12 = config.HOUR_12_FORMAT,
                               am_pm_label = config.AM_PM_LABEL,
                               debug = config.DEBUG,
                               logo_time_ms = logo_time_ms
                               )
        
        self.display.plot_osc(text=False, show_ms=0, lightsleep_req=False)
        
        # initialize the network manager module, by also passing the WDT manager
        self.network_mgr = NetworkManager(self.wdt_manager, try_open_networks=config.OPEN_NETWORKS)

        # check if error from initializing the network manager
        if not self.network_mgr.secrets:
            self.display.text_on_logo("ERROR: SECRETS.JSON", x=-1, y=-1, show_time_ms=2_000)
            sys.exit(1)
            
        # initialize the battery manager module, if set at config file
        if config.BATTERY:
            self.battery = Battery(debug=config.DEBUG)
        
        # initialize WDT after all components are initialized
        self.wdt_manager.initialize() 
        
        # initialize global variables: EPD refresh time is at least 60 secs (nominal)
        self.display_interval_ms = max(60_000, config.DISPLAY_REFRESH_MS)

        # state variables
        self.forced_cycle = True        # it serves as first cycle and for forced cycles (i.e. on-demand NTP sync)
        self.upload_files = False       # flag to book the file uploading task to be executed at the convenient moment
        self.enable_cal = False         # disables the self calibration until config.MIN_TIME_AUTO_CAL_H time has elapsed
        self.cycle_counter = 0          # more for fun than needed, it counts all the cycles (525600 cycles a year)
        self.display_update_count = 0   # counter to limit partial epd refreshes in between full refreshes
        
        # unit variables
        self.degrees = config.TEMP_DEGREES
        
        # aging (calibration) variable is instantiated as zero
        # It gets overruled by the aging values from esp32.NVS or DS3231
        self.aging = 0

        # arbitrary initial temperature value
        self.ds3231_temp = -999
    
    
    
    
    def get_reset_reason(self):
        """Checks the reason for the MCU boot"""
        from machine import reset_cause, PWRON_RESET, HARD_RESET, WDT_RESET, DEEPSLEEP_RESET, SOFT_RESET
        
        reset_reason, reset_message = None, None
        reset_reason = reset_cause()
        reset_message = {
            PWRON_RESET: "POWER-ON RESET",
            HARD_RESET: "HARD RESET",
            WDT_RESET: "WATCHDOG RESET",
            DEEPSLEEP_RESET: "DEEPSLEEP WAKE",
            SOFT_RESET: "SOFT RESET"
        }.get(reset_reason, f"???: {reset_reason}")
        
        del reset_cause, PWRON_RESET, HARD_RESET, WDT_RESET, DEEPSLEEP_RESET, SOFT_RESET
        return reset_reason, reset_message
    
    
    
    
    def log_reset_reason(self, reset_reason, reset_msg):
        """Writes the reset reason to a text file."""
           
        # refresh the wdt
        self.network_mgr.feed_wdt(label="write_rst_reason")
            
        try:
            datetime = await self.time_mgr.get_DS3231_time()
            
            # measure the battery voltage and related level 
            batt_voltage, batt_level = self.battery.check_battery()
            
            if datetime is None:
                datetime = ('time not known')
            
            with open(config.RESET_FILE_NAME, "a") as file:
                file.write(f"Time: {datetime},  RST_reason: {str(reset_reason)},  RST_msg: {str(reset_msg)},  Batt_volt: {str(round(batt_voltage,3))}\n")

        except OSError as e:
            print(f"[ERROR]   Failed to write reset reason: {e}")
    
    
    
    
    def get_aging_nvs(self, key=1):
        """Read aging factor from NVS"""
        try:
            nvs = NVS("storage")
            buffer = bytearray(8)
            nvs.get_blob(str(key), buffer)
            value = buffer.decode().strip('\x00') 
            if config.DEBUG:
                print(f"[DEBUG]    An aging_factor was available: {value}")
            return int(self._convert_to_number(value))
        
        except Exception as e:
            if config.DEBUG:
                if e.errno == -0x1102:
                    print("[DEBUG]    Variable 'aging_factor' not found in esp32.NVS")
                else:
                    print(f"[ERROR]    Issue on reading from esp32.NVS: {e}")
            return None
    
    
    
    
    def save_aging_nvs(self, aging_factor, key=1):
        """Save aging factor to NVS"""
        try:
            nvs = NVS("storage")
            nvs.set_blob(str(key), str(aging_factor).encode())
            nvs.commit()
            return True
        except Exception as e:
            if config.DEBUG:
                print(f"[ERROR]   Issue on saving to esp32.NVS: {e}")
            raise
    
    
    
    
    def get_tz_dst_nvs(self, text="DEBUG", key=2):
        """Read tz_dst (Time Zone and DST correction) from NVS"""
        try:
            nvs = NVS("storage")
            buffer = bytearray(8)
            nvs.get_blob(str(key), buffer)
            value = buffer.decode().strip('\x00') 
            if config.DEBUG:
                print(f"[{text}]    A tz_dst (Time Zone and DST correction) was available, value: {value}")
            return self._convert_to_number(value)
        
        except Exception as e:
            if config.DEBUG:
                if e.errno == -0x1102:
                    print("[DEBUG]    Variable 'tz_dst' not found in esp32.NVS")
                else:
                    print(f"[ERROR]    Issue on reading from esp32.NVS: {e}")
            return None
    
    
    
    
    def save_tz_dst_nvs(self, tz_dst, key=2):
        """Save tz_dst (Time Zone and DST correction) to NVS"""
        try:
            nvs = NVS("storage")
            nvs.set_blob(str(key), str(tz_dst).encode())
            nvs.commit()
        except Exception as e:
            if config.DEBUG:
                print(f"[ERROR]   Issue on saving to esp32.NVS: {e}")
            raise
    
    
    
    
    def goto_sleep(self, total_sleep_ms):
        """Function handling the needed steps to enter lightsleep"""
        
        # refresh the wdt
        self.network_mgr.feed_wdt(label="goto_sleep_1")

        # ensures the sleep time being positive
        total_sleep_ms = max(0, total_sleep_ms)
        
        # case lightsleep is set False
        if not config.LIGHTSLEEP_USAGE:
            # The normal sleeping function is used, instead of the light sleep
            # The sleep is done in chunk, to check the NTP button as per lighsleep
 
            if config.DEBUG:
                print(f"[DEBUG]    MCU awake for {ticks_diff(ticks_ms(), self.t_out_sleep)} ms")
                print(f"[DEBUG]    Going to sleep for {total_sleep_ms} ms")

            sleep_chunk_ms = 10
            t_ref_ms = ticks_ms()
            wake_triggered = False
            while ticks_diff(ticks_ms(), t_ref_ms) < total_sleep_ms:
                sleep_ms(sleep_chunk_ms)
                if self.ntp_sync_pin.value():
                    t_ref2_ms = ticks_ms()
                    while self.ntp_sync_pin.value():
                        if ticks_diff(ticks_ms(), t_ref2_ms) > 250:
                            print("[DEBUG]    GPIO interrupt simulated — break sleep!")
                            wake_triggered = True
                            break
                        sleep_ms(10)
                if wake_triggered:
                    break
        
        # case lightsleep is set True
        elif config.LIGHTSLEEP_USAGE:
            
            # disables the wifi, otherwise the light sleep does not start
            if self.network_mgr.wlan.active() or self.network_mgr.wlan.isconnected():
                wlan_disabling_t_ms = self.network_mgr.disable_wifi()
                if total_sleep_ms > wlan_disabling_t_ms:
                    total_sleep_ms -= wlan_disabling_t_ms
                else:
                    total_sleep_ms = 0
            
            # refresh the wdt
            self.network_mgr.feed_wdt(label="goto_sleep_2")
            

            if config.DEBUG:
                # MCU awake time (in ms)
                print(f"[DEBUG]    MCU awake for {ticks_diff(ticks_ms(), self.t_out_sleep)} ms")
                
                # MCU lighsleep time to wake up jsut in time for the minute change
                print(f"[DEBUG]    Entering lightsleep for {total_sleep_ms} ms")   
            
            # call the light sleep function, passing the sleeping time in mS
            lightsleep(total_sleep_ms)
            
            #######################################################################
            ###### DBEBUG #########################################################
            #
            # This is only for debug the lightsleep part without lighsleep function
            # It prevents the serial communication from dropping.
            # Note the display_manager.py uses lightsleep function too.
            #
            # comment out lightsleep(total_sleep_ms) above
            # uncomment command below
#             sleep_ms(total_sleep_ms)
            #
            #######################################################################
            #######################################################################
            
            if config.DEBUG:
                print(f"[DEBUG]    Quitting lightsleep")
        
        # refresh the wdt
        self.network_mgr.feed_wdt(label="goto_sleep_3")
    
    
    
    
    async def run(self):
        """Main clock execution"""
        
        # retieve the reset reason
        reset_reason, reset_msg = self.get_reset_reason()
        print(f"\n[INFO]     Last reset reason: {reset_msg}\n")
        
        # writes the reset reason in a text file for later reference
        await self.log_reset_reason(reset_reason, reset_msg)
        
        # plot the OSC logo with the OSC code version
        self.display.text_on_logo(f"OSC  VERSION:  {__version__}", x=-1, y=-1, show_time_ms=5000)
        
        # check the aging factor at the DS3231SN and at ESP32 NVS
        self.aging = await self._check_aging_factor()   
        
        # plot the OSC logo with a custom text underneath
        self.display.text_on_logo("WIFI  CONNECTION  ...", x=-1, y=-1, show_time_ms=2_000)
        
        # force garbage collection
        gc.collect()
        
        # refresh the wdt
        self.network_mgr.feed_wdt(label="before making 1st wlan")
        
        # initialize WiFi
        self.network_mgr.connect_to_wifi(blocking=True)
        
        # check if error due to wifi connection
        if not self.network_mgr.wifi_bool:
            self.display.text_on_logo("ERROR: WIFI NETWORKS", x=-1, y=-1, show_time_ms=2_000)
            sys.exit(1)
        
        # check if the wifi has internet connection
        ret = await self.network_mgr.is_internet_available(blocking=True)
        
        # check if error due to internet access
        if not ret:
            self.display.text_on_logo("ERROR: NO INTERNET", x=-1, y=-1, show_time_ms=2_000)
            sys.exit(1)
        
        # refresh the wdt
        self.network_mgr.feed_wdt(label="after making 1st wlan")
        
        # check the IP addresses of the NTP server(s)
        ntp_servers_ip = await self.network_mgr.get_ntp_servers_ip(repeats=5)
        
        # check if error ar resolving the NTP servers addresses
        if len(ntp_servers_ip) == 0:
            self.display.text_on_logo("ERROR: NTP DNS", x=-1, y=-1, show_time_ms=0)
            sys.exit(1)
        
        # get the first tick, in ms (time from the board powering moment)
        tick = ticks_ms()
        
        # assign the tick to a instance variable
        self.last_display_update_ticks = tick

        # organize for the first NTP sync
        print("\n[INFO]     Performing first NTP sync ...")

        # plot the OSC logo with a custom text underneath
        self.display.text_on_logo("NTP  SYNCING ...", x=-1, y=-1, show_time_ms=500)
        
        # make the first NTP syncing, being also blocking
        ntp_epoch_s, epoch_fract_ms, sync_ticks_ms = await self.network_mgr.get_ntp_time(ntp_servers_ip, blocking=True)

        # case the real first NTP sync fails
        if ntp_epoch_s is None:
            # code is stopped
            raise Exception('First NTP synchronization failed. Halting.')
        
        # set the ntp_epoch_s to the ds3231 rtc module
        await self._set_DS3231_rtc(ntp_epoch_s, epoch_fract_ms, sync_ticks_ms)
        
        # assign ntp_epoch_s to self.last_ntp_epoch_s for later calibration purpose
        self.last_ntp_epoch_s = ntp_epoch_s
        
        # convert ntp_epoch_s in a string of date and time
        self.ntp_datetime_str = self.time_mgr.get_dt_from_epoch(ntp_epoch_s)

        # get temperature from the DS3231 module
        self.ds3231_temp = await self._get_DS3231_temperature()

        # case battery is set True
        if config.BATTERY:
            # check the battery voltage
            self.batt_voltage, self.batt_level = self.battery.check_battery()

        # conditional main loop variables
        if config.DEBUG:
            self.t_out_sleep = 0
        
        # main loop variables
        last_halfour_check_ms = tick
        last_hourly_check_ms = tick
        epd_refreshing_ms = 0
        sleep_time_ms = 0
        
        # instance counter for the period (hours) determining the calibration disabled / enabled
        self.hourly_counter = 0



        ########################################
        # infinite loop of the main clock code #
        ########################################
        
        print()
        print("#" * 44)
        print("#  Clock is working. Press Ctrl+C to stop  #")
        print("#" * 44)
        print()

        
        while True:

            # refresh the wdt
            self.network_mgr.feed_wdt(label="Infinite loop start")
            
            # tick (in ms) passed to most of the time-related funtions (all of those being time critical)
            current_ticks_ms = ticks_ms()
            

            # check if request for NTP sync (on-demand NTP sync, via an input pin)
            if  self.ntp_sync_pin.value():
                # time reference for contact debounce purpose
                t_ref_ms = ticks_ms()
                
                # iterates as long as the pin is active
                while self.ntp_sync_pin.value():
                    
                    # case the pin is active for at least 250 ms (debounce of 250ms)
                    if ticks_diff(ticks_ms(), t_ref_ms) > 250:
                        print("\n"*3)
                        if config.DEBUG:
                            print("[DEBUG]    ##############################################     on-demand NTP sync")
                        
                        # call the supporting function
                        await self._handle_ntp_sync(current_ticks_ms, ntp_servers_ip, ntp_epoch_s)
                        
                        # set the instance variable to force a display update
                        self.forced_cycle = True
                        
                        # interrupts the while loop
                        break
            
            
            # half-hour checks
            if ticks_diff(current_ticks_ms, last_halfour_check_ms) > 1_800_000:
                
                # assign the current ticks to the quarter check time
                last_halfour_check_ms = current_ticks_ms
                
                # refresh the wdt    
                self.network_mgr.feed_wdt(label="Half-hour checks")
                
                # call the supporting function to get the time from DS3231
                self.ds3231_temp = await self._get_DS3231_temperature()
                
               
                # hourly checks
                if ticks_diff(current_ticks_ms, last_hourly_check_ms) > 3_600_000:
                    
                    # increase the hourly counter by one
                    self.hourly_counter += 1
                    
                    # assign the current ticks to the hourly check time
                    last_hourly_check_ms = current_ticks_ms
                    
                    # refresh the wdt
                    self.network_mgr.feed_wdt(label="Hourly checks")
                    
                    # case the battery is set True
                    if config.BATTERY:
                        # measure the battery voltage and related level 
                        batt_voltage, batt_level = self.battery.check_battery()
                        
                        # case the current battery values differ from the previous ones
                        if batt_voltage != self.batt_voltage or batt_level != self.batt_level:
                            self.batt_voltage = batt_voltage
                            self.batt_level = batt_level
                    
                    # check if calibration can be enabled
                    if self.hourly_counter >= config.MIN_TIME_AUTO_CAL_H:
                        
                        # enables the option for self-calibration the DS3231 by forcing a NTP sunc
                        self.enable_cal = True
                        
                        # decrease the hourly counter by one when surely above config.MIN_TIME_AUTO_CAL_H
                        if self.hourly_counter >= 2 + config.MIN_TIME_AUTO_CAL_H:
                            self.hourly_counter -= 1
                        
                    
            
            # case it is time for display refresh
            if self.forced_cycle or ticks_diff(current_ticks_ms, self.last_display_update_ticks) >= self.display_interval_ms:
                
                self.last_display_update_ticks = current_ticks_ms
                
                # call the supporting function to get the time from DS3231
                self.time_tuple = await self._get_DS3231_time()

                # calls the support function to update the display
                epd_refreshing_ms = await self._display_update(current_ticks_ms)
                
                # eventually adapts the sleep time to get the display synchronized with minute change
                sleep_time_ms = self._epd_sync(current_ticks_ms, epd_refreshing_ms, sleep_time_ms )
                
                # call the supporting function for sleep or lighsleep
                self.goto_sleep(sleep_time_ms)
                
                # get the tick (in ms) right after waking up
                if config.DEBUG:
                    self.t_out_sleep = ticks_ms()
                
                # increases the cycle counter
                self.cycle_counter += 1
    
    
    
    
    async def _handle_ntp_sync(self, current_ticks_ms, ntp_servers_ip, ntp_epoch_s) -> int:
        """
        Support function handling NTP synchronization.
        It automatically adjusts 
        """
        
        # force garbage collection
        gc.collect()
        
        # refresh the wdt
        self.network_mgr.feed_wdt(label="Start of NTP IP refresh")
        
        # plot the OSC logo with a custom text underneath
        self.display.text_on_logo("GET SERVERS IP ...", x=-1, y=-1, show_time_ms=500)
        
        # force garbage collection
        gc.collect()
        
        # update NTP servers IP addresses
        ntp_servers_ip, _ = await self.network_mgr.refresh_ntp_ip(current_ticks_ms, ntp_servers_ip, blocking=False)
        
        if ntp_servers_ip is None:
            # plot the OSC logo with a custom text underneath
            self.display.text_on_logo("NTP  SYNC  FAILED ...", x=-1, y=-1, show_time_ms=5_000)
            self.display.text_on_logo("CHECK WIFI NETWORKS", x=-1, y=-1, show_time_ms=5_000)
            
            # the function gets interrupted
            return
            
        # force garbage collection
        gc.collect()
        
        # refresh the wdt
        self.network_mgr.feed_wdt(label="Start of synchronizing the display")
    
        # plot the OSC logo with a custom text underneath
        self.display.text_on_logo("NTP  SYNCING ...", x=-1, y=-1, show_time_ms=500)
        
        # perform NTP sync
        ntp_epoch_s, epoch_fract_ms, sync_ticks_ms = await self.network_mgr.get_ntp_time(ntp_servers_ip, blocking=False)
        
        # case the NTP sync fails
        if ntp_epoch_s is None or epoch_fract_ms is None or sync_ticks_ms is None:
            # plot the OSC logo with a custom text underneath
            self.display.text_on_logo("NTP  SYNC  FAILED ...", x=-1, y=-1, show_time_ms=5_000)
            self.display.text_on_logo("CHECK WIFI NETWORKS", x=-1, y=-1, show_time_ms=5_000)
            
            # the function gets interrupted
            return
        
        # force garbage collection
        gc.collect()
        
        # set the ntp_epoch_s to the ds3231 rtc module
        await self._set_DS3231_rtc(ntp_epoch_s, epoch_fract_ms, sync_ticks_ms)
        
        # call the supporting function to get the time back from DS3231, in time_tuple format
        time_tuple = await self._get_DS3231_time()
        
        # case self calibration is not enabled (config.MIN_TIME_AUTO_CAL_H time has not elapsed)
        if not self.enable_cal:
            # plot the OSC logo with a custom text underneath
            self.display.text_on_logo("ADJUSTED TIME, NO CAL", x=-1, y=-1, show_time_ms=5_000)
            
        # call the aging calibration function
        self.aging = await self._calibrate(ntp_epoch_s, epoch_fract_ms, sync_ticks_ms, time_tuple)
        
        # force garbage collection
        gc.collect()
        
        # assign ntp_epoch_s to self.last_ntp_epoch_s for later calibration purpose
        self.last_ntp_epoch_s = ntp_epoch_s

        # convert ntp_epoch_s in a string of date and time
        self.ntp_datetime_str = self.time_mgr.get_dt_from_epoch(ntp_epoch_s)
        
        # reset the counter that forces a minimum period to enable the calibration
        self.hourly_counter = 0
    
    
    
    
    async def _calibrate(self, ntp_epoch_s, epoch_fract_ms, sync_ticks_ms, time_tuple):
        """
        Determines the clock drift (in ppm)
        When self.calibration flag is:
        - enabled, it adjusts the clock and sets the DS3231 aging factor based on the measured drift.
        - disabled, it adjust the clock and in case of a long button pressing it
          resets the DS3231 aging factor to zero.
        """
        
        if config.DEBUG:
            print()
            
        # aging is initially set to None
        aging = None
        
        # set the done variable to False, used later to break to for loops
        done = False
        
        # set the reset_aging to False
        reset_aging = False
        
        # get the TZ and DST correction to NVS
        utc_tz_dst = self.get_tz_dst_nvs(text = "CALIB")
        
        # check NTP sync result
        if ntp_epoch_s is not None and time_tuple is not None and utc_tz_dst is not None:
            
            # elapsed time (in s) according to the latest two NTP syncs
            elapsed_ntp_time_s = ntp_epoch_s - self.last_ntp_epoch_s

            # elapsed time (in s) according to the DS3231SN RTC timer
            elapsed_ds3231_time_s = mktime(time_tuple) - int(utc_tz_dst * 3_600) - self.last_ntp_epoch_s
            
            # drift time (in s) of DS3231SN RTC timer vs NTP sysnc
            drift_ds3231_s = elapsed_ds3231_time_s - elapsed_ntp_time_s
            
            # preventing division by zero (and unrealistic negative time)
            if elapsed_ntp_time_s <= 0:
                if config.DEBUG:
                    print("[ERROR]    Elapsed time based on NTP sync is zero, how come ?")
                return
            
            # drift time (in pp) of DS3231SN RTC timer vs NTP sysnc
            drift_ds3231_ppm = 1_000_000 * drift_ds3231_s / elapsed_ntp_time_s
            
            if config.DEBUG:
                print(f"[CALIB]    Elapsed time based on NTP sync : {elapsed_ntp_time_s} s")
                print(f"[CALIB]    Elapsed time based on DS3231   : {elapsed_ds3231_time_s} s")
                print(f"[CALIB]    DS3231 drift  : {drift_ds3231_s} s")
                print(f"[CALIB]    DS3231 drift  : {round(drift_ds3231_ppm, 2)} ppm")
            
            # case the calibration is enabled
            if self.enable_cal:
                # shift the aging by the drift in ppm (sign of drift is already ok).
                # Every units should compensate 1ppm, using a factor 0.9 to prevent over-correction
                new_aging = int(round(min(127, max(-127, self.aging + 0.9 * drift_ds3231_ppm)),0))
                
                if config.DEBUG:
                    print(f"[CALIB]    New aging factor: {new_aging}")
                
                # set 3 attempts for aging factor calibration
                attempts = 3
            
            # case the calibration is disabled
            elif not self.enable_cal:
                # set one attempt for aging factor reset
                attempts = 1
            
             
            # iteration over the attempts
            for attempt in range(attempts):
                
                # variable 'done' is used to break the for loop in case of success before all attempts
                if done:
                    break
                
                # measure the delay (in ms) of the code execution from NTP sync till here
                delay_ms = ticks_diff(ticks_ms(), sync_ticks_ms)
                
                # check if the push button is still pressed
                if self.ntp_sync_pin.value() and not done:
                    
                    # case self calibration is enabled (config.MIN_TIME_AUTO_CAL_H time has elapsed)
                    if self.enable_cal:
                        self.display.text_on_logo("RELEASE FOR CALIB,", x=-1, y=-1, show_time_ms=300)
                        if not self.ntp_sync_pin.value():
                            break
                    
                    self.display.text_on_logo("KEEP FOR RESET", x=-1, y=-1, show_time_ms=300)
                    if not self.ntp_sync_pin.value():
                        break
                
                # delay to ensure the button signal is still intentionally high or it has dropped down
                sleep_ms(500)
                
                # evaluate the button signal again
                # case the button is still pressed
                if self.ntp_sync_pin.value():
                    # reset the DS3231 chip to aging factor = 0
                    ret = await self.time_mgr.write_DS3231_aging(value = 0)
                    reset_aging = True
                    if config.DEBUG:
                        print("[CALIB]    Going to reset the aging factor")
                
                # case the button has been released
                elif not self.ntp_sync_pin.value():
                    # set the ret variable False, in case write_DS3231_aging is not executed 
                    ret = False
                    
                    # case self calibration is enabled (config.MIN_TIME_AUTO_CAL_H time has elapsed)
                    if self.enable_cal:
                        
                        # write the new aging factor to the DS3231 chip
                        ret = await self.time_mgr.write_DS3231_aging(value = new_aging)
                        reset_aging = False
                        if config.DEBUG:
                            print("[CALIB]    Going to modify the aging factor")
                
                # small delay to ensure DS3231 writing is completed
                sleep_ms(250)
                
                # read the aging factor from the DS3231 chip
                aging_ds3231 = await self.time_mgr.read_DS3231_aging()
                
                # small delay after DS3231 reading
                sleep_ms(250)
                
                if config.DEBUG:
                    if ret:
                        print("[CALIB]    Writing to DS3231 without errors")
                    print(f"[CALIB]    Retrieved aging value from DS3231: {aging_ds3231}")
                
                # case writing to and reading from DS3231 are successfull
                if aging_ds3231 is not None:
                        
                    # case the choice is to reset and aging factor at the DS3231 is zero
                    if reset_aging and aging_ds3231 == 0:
                        
                        # the reset  aging value at the DS3131 is assigned to the variable aging
                        aging = 0
                        
                        if config.DEBUG:
                            print("[CALIB]    Aging factor reset to zero at DS3231 chip")
                        
                        # plot the OSC logo with a custom text underneath
                        self.display.text_on_logo("RESET CALIBRATION", x=-1, y=-1, show_time_ms=5_000)
                        
                        # set the done variable to False to interrupt the for loops
                        done = True # for loop is interrupted

                    # case the calibration is enabled and the choice is to modify the aging factor
                    # and the aging factor at the DS3231 equals the new_aging
                    if self.enable_cal and aging_ds3231 == new_aging:
                        
                        # the just saved aging value at the DS3131 is assigned to the variable aging
                        aging = aging_ds3231
                    
                        if config.DEBUG:
                            print("[CALIB]    New aging factor has been written to the DS3231 chip")
                        
                        # plot the OSC logo with a custom text underneath
                        self.display.text_on_logo(" CALIBRATED  CLOCK", x=-1, y=-1, show_time_ms=5_000)
                        
                        # set the done variable to False to interrupt the for loops
                        done = True # for loop is interrupted
                
                # reset the enable calibration flag
                self.enable_cal = False
                
                # case the variabe done isi set True
                if done:
                    break  # for loop is interrupted
        
        if config.DEBUG:
            print()
        
        if self.enable_cal:
            return aging
        else:
            return aging_ds3231
    
    
    
    
    async def _display_update(self, current_ticks_ms):
        """Support function handling display update"""
        
        t_edp_ref_ms = ticks_ms()
        
        if config.DEBUG:
            print(f"{'\n'*3}[DEBUG]    {'#'*46}     cycle_counter: {self.cycle_counter}")
            if not self.forced_cycle:
                print(f"[DEBUG]    From quitting sleep (or lightleep) and ticking",
                      f"display_interval_ms: {ticks_diff(ticks_ms(), self.t_out_sleep)} ms")

        if self.forced_cycle:
            self.forced_cycle = False
        
        try:
            
            # case self.time_tuple is not None
            if self.time_tuple is not None:
                # retrieve the single digits for hour and minute
                H1, H2, M1, M2, am = self.time_mgr.get_time_digits(self.time_tuple)
                
                # retrieve the date fields
                dd, day, d_string = self.time_mgr.get_date(self.time_tuple)
            
            # case self.time_tuple is None
            else:
                H1, H2, M1, M2, am =  0, 0, 0, 0, True
                dd, day, d_string = 1, 0, "  -  -  "
            
            # forced garbage collection
            gc.collect()
            
            # set the battery_low flag as False
            battery_low = False
            
            # if battery presence and its voltage below threshold
            if config.BATTERY and self.batt_voltage < config.BATTERY_WARNING:
                # set the battery_low flag as True
                battery_low = True
            
            # determines how to refresh the display (full or partial update)
            if self.time_tuple[4] == 0:  # case minutes = 0 (round hour)
                epd_clear = True         # display full refresh (prevent ghosting)
            else:                        # case minutes != 0 (minutes 1 to 59)
                epd_clear = False        # display partial update (saves energy)
            
            # send the updated info to the display Class
            self.display.show_data(H1, H2, M1, M2, dd, day, d_string, self.ntp_datetime_str,
                                   self.ds3231_temp, self.batt_level, self.network_mgr.wifi_bool,
                                   self.network_mgr.ntp_bool, self.aging, self.enable_cal,
                                   battery_low=battery_low, plot_all=epd_clear)
            
            # refresh the wdt
            self.network_mgr.feed_wdt(label="update_display_2")

        except Exception as e:
            print(f"[ERROR]   Display error: {e}")
            raise

        # print interpreted time and drift
        if config.DEBUG:
            print(f"[DEBUG]    Time from DS3231 module {self.time_tuple}, DS3231_Temp: {self.ds3231_temp:.2f}°{self.degrees}")
        else:
            print(f"[INFO]     Display: {self.time_tuple[3]}:{self.time_tuple[4]} \t"
                  f"DS3231_Temp: {self.ds3231_temp:.2f}°{self.degrees} \tBattery: {self.batt_level} %")
        
        self.last_display_update_ticks = current_ticks_ms
        self.display_update_count += 1
        epd_refreshing_ms = ticks_diff(ticks_ms(), t_edp_ref_ms)
        
        return epd_refreshing_ms
    
    
    
    
    def _epd_sync(self, current_ticks_ms, epd_refreshing_ms, sleep_time_ms):
        """
        Synchronizing the display refreshing moment right after a minute change.
        Essentially this function adjusts the sllep time in between display
        updates in order to have a very good sinchronization of the display
        with the real word time.
        The objectine is to refresh the display right after a new minute kicks in.
        
        When the display updates the minute, then it suggests the seconds were
        roughly between 0 and 10: This means the minute on the display is 'correct'
        for 50 to 60 seconds each minute.
        
        Namings
        remainder_ms --> time in ms exceeding display_interval_ms (like the ms from minute change)
        target_ms    --> it the target remainder to get the display updating (i.e. the ms from minute change)
        shift_ms     --> period to add or remove at the next cycle to anticipate of postpone the edp update
        
        Note: the shift_ms acts on both the display time reference and the sleeping time
        """
        
        target_ms = 4_000             # target 4000 ms means 4 secs after the minute change
        shift_ms = target_ms - 2_000  # when target 4000 ms the applied correction (shift_ms) is 2 secs
        
        # calculate the remainder (i.e. exceeding milliseconds from minute change)
        remainder_ms = (self.time_tuple[5] * 1_000) % self.display_interval_ms
        
        # case remainder_ms <= target_ms, it means the display refreshed too early: Need longer sleep_time_ms 
        if remainder_ms <= target_ms:  
            
            # last_display_update_ticks (time when display got updated last time) last gets postponed
            self.last_display_update_ticks += (shift_ms - remainder_ms)
            
            # calculate the cycle time, necessary for precise calculation of the lighsleep time
            cycle_time_ms = ticks_diff(ticks_ms(), current_ticks_ms)
            
            # sleep time adjustment (sleep as long as possible, yet in time for next display refresh)
            sleep_time_ms = self.display_interval_ms - cycle_time_ms - remainder_ms + shift_ms
            
            if config.DEBUG:
                if shift_ms - remainder_ms == 0:
                    print(f"[DEBUG]    Display refreshed at seconds {self.time_tuple[5]} --> OK ")
                else:
                    print(f"[DEBUG]    Display refreshed at seconds {self.time_tuple[5]} --> OK "   
                          f"(tuning sleep: {remainder_ms + shift_ms} and last_display_update_ticks: {shift_ms - remainder_ms})")
        
        # case remainder_ms >= target_ms, it means display refreshed too late: Need shorter sleep_time_ms
        else:
            
            # last_display_update_ticks (time when display got updated last time) last gets anticipate
            self.last_display_update_ticks -= (self.display_interval_ms - sleep_time_ms)
            
            # sleep time adjustment (sleep as long as possible, yet in time for next display refresh)
            sleep_time_ms = self.display_interval_ms - epd_refreshing_ms - remainder_ms + shift_ms
            if config.DEBUG:
                print(f"[DEBUG]    Display refreshed at seconds {self.time_tuple[5]} --> adapting the sleeping time")
        
        return sleep_time_ms
    
    
    
    
    async def _set_DS3231_rtc(self, ntp_epoch_s, epoch_fract_ms, sync_ticks_ms):   
        """
        Write the epoch_s to the ds3231 rtc module.
        Write to NVS the TZ and DST correction applied to the rtc
        """
        
        if config.DEBUG:
            t_ref_ms = ticks_ms()
        
        ret = False
        

        # compensation for code delay, in case exceeding 0.5 seconds
        delay_ms = epoch_fract_ms + ticks_diff(ticks_ms(), sync_ticks_ms)
        delay_s = int(round(delay_ms / 1_000, 0))
        
        # sets the time to the ds3231 module
        ret = await self.time_mgr.update_rtc(ntp_epoch_s + delay_s)
        
        # check the time has been correctly saved to the DS3231SN RTC
        time_tuple = await self._get_DS3231_time()
        
        # retrieve the TZ and DST correction applied when saving the epoch_s to DS3231 RTC
        utc_tz_dst = self.time_mgr.get_UTC_TZ(ntp_epoch_s)   # utc_tz_dst units is hours
        

        # Note: When writing the RTC, the TZ and DST is saved to the NVS; Tthis allows to correctly calculate the period in between
        # latest NTP syncs, also in case a DST adjustment has happened in the meanwhile.
        # The TZ and DST correction is then used to calculate the UTC epoch_s from DS3231 RTC and the seconds elapsed (at DS3231 rtc)
        # since the last time the RTC got written

        # save the TZ and DST correction to NVS
        self.save_tz_dst_nvs(utc_tz_dst)

        # check the DS3231 return
        if ret:
            if config.DEBUG:
                print(f"[DEBUG]    Set RTC to DS3231 module in {ticks_diff(ticks_ms(), t_ref_ms)} ms")
            return ret
        
        else:
            for i in range(5):
                ret = await self.time_mgr.update_rtc(ntp_epoch_s + delay_s, pwr_up_time_ms = (i+1)*10)
                if ret:
                    if config.DEBUG:
                        print("[DEBUG]    Set RTC to DS3231 module at attempt {i+2] out 5")
                    return ret
                
                if not ret:
                    # plot the OSC logo with a custom text underneath
                    self.display.text_on_logo("REPLACE  ML2032  BATT.", x=10, y=-1, show_time_ms=60000)
                    return ret
    
    
    
    
    async def _get_DS3231_time(self):
        if config.DEBUG:
            t_ref_ms = ticks_ms()
        
        ret = None
        
        # retrieves the time from the ds3231 module
        ret = await self.time_mgr.get_DS3231_time()
        
        # check the DS3231 return
        if ret is not None:
            if config.DEBUG:
                print(f"[DEBUG]    DS3231 module returned time in {ticks_diff(ticks_ms(), t_ref_ms)} ms")
            return ret
        
        else:
            for i in range(5):
                ret = await self.time_mgr.get_DS3231_time(pwr_up_time_ms = (i+1)*10)
                if ret is not None:
                    if config.DEBUG:
                        print("[DEBUG]    DS3231 module replied at attempt {i+2] out 5")
                    return ret
                
                elif ret is None:
                    # plot the OSC logo with a custom text underneath
                    self.display.text_on_logo("REPLACE  ML2032  BATT.", x=10, y=-1, show_time_ms=60000)
                    return ret
    
    
    
    
    async def _get_DS3231_temperature(self):
        if config.DEBUG:
            t_ref_ms = ticks_ms()
        
        ret = None
        
        # retrieves the temperature from the ds3231 module
        ret = await self.time_mgr.get_DS3231_temperature()
        
        # check the DS3231 return
        if ret is not None:
            if config.DEBUG:
                print(f"[DEBUG]    DS3231 module returned temperature in {ticks_diff(ticks_ms(), t_ref_ms)} ms")
            return ret + config.TEMPERATURE_SHIFT
        
        else:
            for i in range(5):
                ret = await self.time_mgr.get_DS3231_temperature(pwr_up_time_ms = (i+1)*10)
                if ret is not None:
                    if config.DEBUG:
                        print("[DEBUG]    DS3231 module replied at attempt {i+2] out 5")
                    return ret + config.TEMPERATURE_SHIFT
                
                elif ret is None:
                    # plot the OSC logo with a custom text underneath
                    self.display.text_on_logo("REPLACE  ML2032  BATT.", x=10, y=-1, show_time_ms=60000)
                    return ret + config.TEMPERATURE_SHIFT
    
    
    
    
    def _check_aging_factor(self):
        """
        Check the aging factor at DS3231SN and the one stored at ESP32 NVS.
        In case an aging factor is zero at at DS3231SN, and ESP32 NVS holds a different value,
        then the DS3231SN gets updated with the value from ESP32 NVS. This choice because
        the aging factor at DS3231SN is not retained in case of power loss (battery died).
        """
        
        aging = None
        
        # read aging factor from DS3232SN
        aging_factor_ds3231sn = await self.time_mgr.read_DS3231_aging()
        if config.DEBUG and aging_factor_ds3231sn is not None:
            print(f"[DEBUG]    Aging factor at DS3231SN flash memory: {aging_factor_ds3231sn}")
        
        # load aging factor from NVS
        aging_factor_nvs = self.get_aging_nvs()
        if config.DEBUG:
            if aging_factor_nvs is not None:
                print(f"[DEBUG]    Aging factor at NVS memory: {aging_factor_nvs}")
            else:
                print("[DEBUG]    Aging factor at NVS memory is None")
        
        # case the esp32.nsv is still None while the DS3231 aging is 0 or different value
        if aging_factor_nvs is None and aging_factor_ds3231sn is not None:
            ret = self.save_aging_nvs(int(aging_factor_ds3231sn), key=1)
        
        # case aging_factor_ds3231sn is zero and aging_factor_nvs differs from zero
        if aging_factor_nvs is not None and aging_factor_ds3231sn is not None:
            if aging_factor_ds3231sn == 0 and aging_factor_nvs != 0 :
                # the value at ESP32 NVS get written to the DS3231SN memory
                ret = await self.time_mgr.write_DS3231_aging(value = aging_factor_nvs)
                if config.DEBUG:
                    if ret:
                        print(f"[DEBUG]    Aging factor at ESP32 NVS {aging_factor_ds3231sn} is now written at DS3231SN flash memory") 
                    else:
                        print(f"[DEBUG]    Error in writing the aging factor {aging_factor_ds3231sn} to DS3231SN flash memory")
        
        # case aging_factor_ds3231sn differs from zero and aging_factor_nvs in None
        # this is the case when the aging_factor_ds3231sn is manually written in development phase
        # this IF case must remain at the end of the other IF cases
        if aging_factor_ds3231sn is not None and aging_factor_nvs is None:
            ret = self.save_aging_nvs(aging_factor_ds3231sn)
            if config.DEBUG:
                if ret:
                    print(f"[DEBUG]    Aging factor at DS3231SN flash memory ({aging_factor_ds3231sn}) is now written to ESP32 NVS") 
                else:
                    print(f"[DEBUG]    Error in writing the aging factor {aging_factor_ds3231sn} to ESP32 NVS")
        
        # load aging factor from NVS, eventually updated
        aging_factor_nvs = self.get_aging_nvs()
        return aging_factor_nvs
    
    
    
    
    def _convert_to_number(self, num_text):
        """Convert text to number"""
        if isinstance(num_text, (int, float)):
            return num_text
        
        try:
            return float(num_text)
        except ValueError as e:
            print(f"[ERROR]   The value {num_text} is not a number: {e}")
            return None
    
    
    
    
    def _c_to_f(self, temp_c):
        """Function to convert Celsius to Fahrenheit"""
        return temp_c * config.C_TO_F_COEFF + 32
    
    
    
    
    def _make_folder(self, folder):
        """Create folder if it doesn't exist."""
        from os import mkdir
        try:
            mkdir(folder)
        except OSError:
            pass        # if folder already exists, ignore
        del mkdir
    
    
    
    
    def _file_exists(self, path):
        """Checks if the file (path) exists."""
        from os import stat
        try:
            stat(path)
            return True
        except OSError:
            return False





async def main(logo_time_ms=0):
    """Main entry point"""
    clock = SelfLearningClock(logo_time_ms=logo_time_ms)
    await clock.run()



if __name__ == "__main__":
    print(f"\nOSC version = {__version__}")
    asyncio.run(main(logo_time_ms=5_000))
