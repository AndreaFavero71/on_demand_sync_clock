"""
On-demand Sync Clock (OSC)
A digital clock with on-request NTP syncing, via a push button

Class managing the time related calculations


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



# modules for the DS3231SN - AT24C32 board
from ds3231_driver import DS3231

# standard modules
from utime import gmtime, mktime, ticks_diff, sleep_ms
from machine import SoftI2C, Pin
import uasyncio as asyncio
import ujson as json


SDA_PIN = 2
SCL_PIN = 1
DS3231_PWR_PIN = 3


class TimeManager:
    def __init__(self, config):
        
        self.config = config
        self.dst_rules = self._load_dst_rules()
        self.region = getattr(config, "DST_REGION", "EU")
        self.is_dst_enabled = getattr(config, "DST", True)
        self.UTC_TZ = getattr(config, "UTC_TZ", 0)
        self.degrees = config.TEMP_DEGREES
        
        # initialize the ds3231_pwr pin
        self.ds3231_pwr = Pin(DS3231_PWR_PIN, Pin.OUT)
        self.ds3231_pwr.value(0)
        
        # initialize the i2c
        i2c = SoftI2C(scl=Pin(SCL_PIN), sda=Pin(SDA_PIN), freq=400_000)

        # instance of RTC module
        self.ds = DS3231(i2c)
    
    
    
    async def update_rtc(self, epoch_s, pwr_up_time_ms = 5):
        if epoch_s is None:
            return False
        
        time_tuple_utc = self.epoch_to_timetuple(epoch_s)
        if time_tuple_utc is None:
            return False
        
        try:
            # writes time_tuple_utc to DS3231 flash memory
            self.ds3231_pwr.value(1)
            sleep_ms(pwr_up_time_ms)
            self.ds.datetime(time_tuple_utc)
            self.ds3231_pwr.value(0)
            return True
        except:
            return False
    
    
    
    async def get_DS3231_time(self, pwr_up_time_ms = 5):
        try:
            self.ds3231_pwr.value(1)
            sleep_ms(pwr_up_time_ms)
            
            # reads time_tuple from DS3231 flash memory
            time_tuple = self.ds.datetime()
            self.ds3231_pwr.value(0)
            return time_tuple
        except:
            return None
    
    
    
    async def get_DS3231_temperature(self, pwr_up_time_ms = 5):
        try:
            self.ds3231_pwr.value(1)
            sleep_ms(pwr_up_time_ms)
            
            # reads ds3231 temperature from DS3231 flash memory
            ds3231_temp = self.ds.read_temperature()
            self.ds3231_pwr.value(0)
            
            if self.degrees == 'C':
                return ds3231_temp
            elif self.degrees == 'F':
                return 32 + 9/5 * ds3231_temp
            else:
                print("[ERROR]   TEMP_DEGREES at config.py must be 'C'or 'F'")
                raise
        
        except:
            return None
    
    
    
    async def read_DS3231_aging(self, pwr_up_time_ms = 5):
        try:
            self.ds3231_pwr.value(1)
            sleep_ms(pwr_up_time_ms)
            
            # reads ds3231 aging from DS3231 flash memory
            ds3231_aging = self.ds.read_aging()
            self.ds3231_pwr.value(0)
            return ds3231_aging
        except:
            return None
    
    
    
    async def write_DS3231_aging(self, value, pwr_up_time_ms = 5):
        try:
            self.ds3231_pwr.value(1)
            sleep_ms(pwr_up_time_ms)
            
            # reads ds3231 aging from DS3231 flash memory
            ds3231_aging = self.ds.write_aging(value = value)
            self.ds3231_pwr.value(0)
            return True
        except:
            return False
    
    
    
    def epoch_to_timetuple(self, epoch_s):
        utc_tz_dst = self.get_UTC_TZ(epoch_s)         # DST CALCULATION
        local_epoch_s = epoch_s + 3600 * utc_tz_dst   # local epoch in secs
        return gmtime(local_epoch_s)                  # local time tuple
    
    
    
    def get_UTC_TZ(self, utc_epoch_time):
        """
        Calculates current UTC offset including DST, based on region rules.
        Returns offset in hours.
        """
        if not self.is_dst_enabled:
            return self.UTC_TZ

        rule = self.dst_rules.get(self.region, self.dst_rules.get("NONE", {}))
        if not rule or not rule.get("start") or not rule.get("end"):
            return self.UTC_TZ

        t = gmtime(utc_epoch_time)
        year, month, day, hour = t[0], t[1], t[2], t[3]

        start_m, start_w, start_d, start_h = rule["start"]
        end_m, end_w, end_d, end_h = rule["end"]

        start_day = self._get_rule_day(year, start_m, start_w, start_d)
        end_day = self._get_rule_day(year, end_m, end_w, end_d)

        months = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,
                  "JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}

        sm = months[start_m]
        em = months[end_m]

        in_dst = False
        if sm < em:  # northern hemisphere (e.g. EU, US)
            if (month > sm and month < em) or \
               (month == sm and (day > start_day or (day == start_day and hour >= start_h))) or \
               (month == em and (day < end_day or (day == end_day and hour < end_h))):
                in_dst = True
        else:  # southern hemisphere (e.g. AU)
            if not ((month > em and month < sm) or \
                    (month == em and (day > end_day or (day == end_day and hour >= end_h))) or \
                    (month == sm and (day < start_day or (day == start_day and hour < start_h)))):
                in_dst = True

        offset_hr = (rule.get("offset", 3600) // 3600) if in_dst else 0
        
        return self.UTC_TZ + offset_hr

    
    
    
    def _load_dst_rules(self):
        """Loads DST rules from dst_rules.json (once at init)."""
        try:
            with open("lib/config/dst_rules.json") as f:
                return json.load(f)
        except Exception as e:
            print("[DST] Warning: could not load dst_rules.json:", e)
            # fallback: only EU and NONE
            return {
                "EU": {
                    "start": ["MAR", "last", "sun", 2],
                    "end": ["OCT", "last", "sun", 3],
                    "offset": 3600
                },
                "NONE": {
                    "start": None,
                    "end": None,
                    "offset": 0
                }
            }

    
    
    def _get_rule_day(self, year, month_abbr, which, weekday_abbr):
        """Return the day number for nth/last weekday of a month."""
        months = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,
                  "JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}
        weekdays = {"mon":0,"tue":1,"wed":2,"thu":3,"fri":4,"sat":5,"sun":6}

        month = months[month_abbr.upper()]
        target_wday = weekdays[weekday_abbr.lower()]

        # simple month length
        if month in [1,3,5,7,8,10,12]:
            last_day = 31
        elif month == 2:
            last_day = 29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 28
        else:
            last_day = 30

        # find target weekday
        if which == "last":
            for d in range(last_day, last_day - 7, -1):
                if gmtime(mktime((year, month, d, 12, 0, 0, 0, 0)))[6] == target_wday:
                    return d
        else:
            nth = {"1st":0,"2nd":1,"3rd":2,"4th":3}.get(which,0)
            for d in range(1, 8):
                if gmtime(mktime((year, month, d, 12, 0, 0, 0, 0)))[6] == target_wday:
                    return d + nth * 7

        return 1  # fallback
    
    
    
    def ms_to_hms(self, ms):
        seconds = ms // 1000
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return "{:02d}:{:02d}:{:02d}".format(h, m, s)
    
    
    
    def get_dt_from_epoch(self, epoch_s):
        time_tuple_utc = self.epoch_to_timetuple(epoch_s)
        dd, day, d_string = self.get_date(time_tuple_utc)
        time = self.get_time(time_tuple_utc)
        return f"{d_string}  {time}"
    
    
    
    def get_time(self, time_tuple):
        HH = "{:02d}".format(time_tuple[3])
        MM = "{:02d}".format(time_tuple[4])
        SS = "{:02d}".format(time_tuple[5])
        return f"{HH}:{MM}:{SS}"
    
    
    
    def get_time_digits(self, time_tuple, am=True):
        """
        Returns the individual hours and minutes digits in string format.
        Hours and minutes are 0 padded.
        Converts to 12-hour format is that is set True at config.py
        Anti-meridian flag is always returned
        """
        HH = time_tuple[3]
        if self.config.HOUR_12_FORMAT:  # case of 12-Hour format
            if HH == 0:
                HH = 12
            elif HH >= 12:
                am = False
                if HH > 12:
                    HH -= 12
        
        HH = "{:02d}".format(HH)
        MM = "{:02d}".format(time_tuple[4])
        return HH[0], HH[1], MM[0], MM[1], am
    
    
    
    def get_date(self, time_tuple):
        yyyy = time_tuple[0]
        mm   = time_tuple[1]
        dd   = time_tuple[2]
        day  = self.config.DAYS[time_tuple[6]]
        
        YYYY = "{:04d}".format(yyyy)
        M    = "{:02d}".format(mm)
        D    = "{:02d}".format(dd)
        
        if self.config.DATE_FORMAT == "DMY":
            d_string = f"{D}-{M}-{YYYY}"
        elif self.config.DATE_FORMAT == "MDY":
            d_string = f"{M}-{D}-{YYYY}"
        elif self.config.DATE_FORMAT == "YMD":
            d_string = f"{YYYY}-{M}-{D}"
        else:
            d_string = f"{D}-{M}-{YYYY}"
        
        return dd, day, d_string