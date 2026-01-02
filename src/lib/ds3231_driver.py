#! /usr/bin/env micropython

# Micropython driver for the DS3231 RTC Module


# Based on the works of Conrad Storz, Willem Peters and Mike Causer, below their ref.

# In this version:
# - Modified the workday for direct compatibility with MicroPython (DS3231 1-7, MP 0-6)
# - Moved the temperature reading to the 'original' driver.
# - Added the methods to read and write the aging factor.


# Based on:
# - Conrad Storz, who extended the work of Willem Peterse: https://github.com/conradstorz/micropython-DS3231-AT24C32
# - Willem Peterse driver ds3231.py: https://github.com/pangopi/micropython-DS3231-AT24C32, who based on
# - Mike Causer (mcauser) work for the DS1307: https://github.com/mcauser/micropython-tinyrtc-i2c/blob/master/ds1307.py



# The MIT License (MIT)
#
# Copyright (c) 2020 Willem Peterse
# Copyright (c) 2025 by Conrad Storz
# Copyright (c) 2025 by Andrea Favero
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

from micropython import const


DS3231_I2C_ADDRESS = 0x68


# -------------------------------------------------------------------------------
# Register address constants (using const for memory efficiency in MicroPython)
# -------------------------------------------------------------------------------
DATETIME_REG    = const(0)  # Starting register for time/date data (7 bytes total)
ALARM1_REG      = const(7)  # Starting register for Alarm 1 settings (5 bytes total)
ALARM2_REG      = const(11) # Starting register for Alarm 2 settings (4 bytes total)
CONTROL_REG     = const(14) # Control register for square-wave, interrupts, etc.
STATUS_REG      = const(15) # Status register for flags (e.g., OSF, busy)
AGING_REG       = const(16) # Aging offset register (tuning TCXO frequency)
TEMPERATURE_REG = const(17) # Temperature register (2 bytes: MSB, LSB)

# ------------------------------------------------------------------------------
# Helper functions to convert between decimal and Binary Coded Decimal (BCD)
# ------------------------------------------------------------------------------
def dectobcd(decimal):
    """Convert a base-10 integer (0-99) into BCD format (0x00-0x99).
    
    BCD packs two decimal digits into one byte: high nibble = tens, low nibble = ones.
    Example: 45 → (4 << 4) | 5 = 0x45.
    """
    tens = decimal // 10            # extract tens digit
    ones = decimal % 10             # extract ones digit
    return (tens << 4) | ones       # combine into one BCD byte


def bcdtodec(bcd):
    """Convert a BCD-encoded byte into a base-10 integer.
    
    BCD format: high nibble = tens, low nibble = ones.
    Example: 0x37 → (3 * 10) + 7 = 37.
    """
    tens = (bcd >> 4) & 0x0F        # high nibble
    ones = bcd & 0x0F               # low nibble
    return tens * 10 + ones         # compute decimal value


# ------------------------------------------------------------------------------
# Main DS3231 driver class
# ------------------------------------------------------------------------------
class DS3231:
    """MicroPython driver for the DS3231 Real-Time Clock (RTC) chip.
    
    - Works only for years 2000-2099 (two-digit year storage).
    - Provides time/date read/write, square wave output, alarms, and status flags.
    """
    # --------------------------------------------------------------------------
    # Square-wave output frequency options (for control register)
    # --------------------------------------------------------------------------
    FREQ_1      = const(1)    # 1 Hz output
    FREQ_1024   = const(2)    # 1.024 kHz output
    FREQ_4096   = const(3)    # 4.096 kHz output
    FREQ_8192   = const(4)    # 8.192 kHz output
    SQW_32K     = const(1)    # Option to output 32 kHz on the SQW pin

    # --------------------------------------------------------------------------
    # Alarm 1 “match” modes (bit masks for register flags)
    # --------------------------------------------------------------------------
    AL1_EVERY_S     = const(15)  # Trigger every second
    AL1_MATCH_S     = const(14)  # Trigger when seconds match (once per minute)
    AL1_MATCH_MS    = const(12)  # Trigger when minutes & seconds match (once per hour)
    AL1_MATCH_HMS   = const(8)   # Trigger when hours, minutes & seconds match (once per day)
    AL1_MATCH_DHMS  = const(0)   # Trigger when date|weekday, hour, min, sec match

    # --------------------------------------------------------------------------
    # Alarm 2 “match” modes (bit masks for register flags)
    # --------------------------------------------------------------------------
    AL2_EVERY_M     = const(7)  # Trigger every minute at second 00
    AL2_MATCH_M     = const(6)  # Trigger when minutes match (once per hour)
    AL2_MATCH_HM    = const(4)  # Trigger when hours & minutes match (once per day)
    AL2_MATCH_DHM   = const(0)  # Trigger when date|weekday match

    
    
    def __init__(self, i2c, addr=DS3231_I2C_ADDRESS):
        """Initialize with an I2C bus object and the RTC's I2C address (default 0x68)."""
        self.i2c = i2c
        self.addr = addr
        # Pre-allocate reusable buffers to minimize memory churn on reads/writes:
        self._timebuf  = bytearray(7)  # buffer for reading/writing 7 time registers
        self._buf      = bytearray(1)  # single-byte buffer for control/status ops
        self._al1_buf  = bytearray(4)  # buffer for the first 4 bytes of Alarm 1
        self._al2buf   = bytearray(3)  # buffer for all bytes of Alarm 2
        
    
    
    def read_aging(self):
        """ Read aging setting from the DS3231 RTC.
        :return: Aging setting (from -127 to 127)
        """
        raw = self.i2c.readfrom_mem(self.addr, AGING_REG, 1)[0]
        
        # convert from unsigned byte to signed integer
        return raw - 256 if raw > 127 else raw
    
    
    
    def write_aging(self, value):
        """
        Write a new aging offset to the DS3231 RTC.
        :param value: Aging offset (-128 to +127)
        """
        if not -128 <= value <= 127:
            raise ValueError("Aging offset must be between -128 and +127")

        # Convert to unsigned 8-bit value (two's complement)
        raw = value & 0xFF

        self.i2c.writeto_mem(self.addr, AGING_REG, bytes([raw]))
    
    
    
    def read_temperature(self):
        """
        Read temperature from the DS3231 RTC and convert to Celsius.

        :return: Temperature in °C as a float
        """
        # read two bytes from the temperature register
        temp_bytes = self.i2c.readfrom_mem(
            self.addr, TEMPERATURE_REG, 2
        )

        # combine bytes into a single signed 16-bit integer
        raw_temp = (temp_bytes[0] << 8) | temp_bytes[1]
        # If negative, convert from two's complement
        if raw_temp & 0x8000:
            raw_temp -= 0x10000

        # DS3231 provides temperature in 1/256 °C increments
        celsius = raw_temp / 256.0
        return celsius

    
    
    def datetime(self, datetime=None):
        """Get or set the RTC's date/time.
        
        Without argument: reads 7 bytes starting at DATETIME_REG,
        decodes BCD to (year, month, day, weekday, hour, minute, second).
        
        With tuple argument: writes new date/time, resets Oscillator Stop Flag.
        Tuple format: (year, month, day, hour, minute, second, weekday)
        - Seconds and weekday are optional on set; missing fields default to 0.
        - Always uses 24-hour format on return.
        - Weekday are increased by one (only writing): DS3231 1-7, Micropython 0-6
        """
        if datetime is None:
            # ----------------------------
            # Read current time from chip
            # ----------------------------
            self.i2c.readfrom_mem_into(self.addr, DATETIME_REG, self._timebuf)
            # Byte layout in self._timebuf:
            # [0] = seconds (BCD)
            # [1] = minutes (BCD)
            # [2] = hour register (BCD + 12/24 & AM/PM bits)
            # [3] = weekday (BCD, 1-7)
            # [4] = day of month (BCD)
            # [5] = month (BCD + century flag in bit 7)
            # [6] = year (BCD, 00-99 → 2000-2099)

            # Convert each BCD field to decimal:
            seconds = bcdtodec(self._timebuf[0])
            minutes = bcdtodec(self._timebuf[1])

            # Hour decoding: test bit 6 → 12/24h mode
            hr_reg = self._timebuf[2]
            if (hr_reg & 0x40):  # if bit 6 set → 12-h mode
                # mask out format bits to get BCD hour, then add 12 if PM bit (5) set
                hour = bcdtodec(hr_reg & 0x1F)
                if (hr_reg & 0x20):  # PM indicator
                    hour += 12
            else:
                # 24-h mode: mask out only bit 6, decode BCD
                hour = bcdtodec(hr_reg & 0x3F)
                
            weekday = bcdtodec(self._timebuf[3])
            day     = bcdtodec(self._timebuf[4])
            month   = bcdtodec(self._timebuf[5] & 0x7F)   # mask out century bit
            year    = bcdtodec(self._timebuf[6]) + 2000   # base 2000
            
            weekday = (weekday -1 ) % 7  # from DS3121 1-7 to MicroPython 0-6

            # Warn if oscillator was stopped (power loss)
            if self.OSF():
                print("WARNING: Oscillator stop flag set. Time may not be accurate.")

            # Return full tuple plus dummy yearday (0) to match ESP32 RTC MicroPython API
            return (year, month, day, hour, minutes, seconds, weekday, 0)

        # A new datetime tuple was provided by the user to set the RTC.
        # Let's perform some basic validation:
        if not isinstance(datetime, tuple) or len(datetime) < 1 or len(datetime) > 8:
            raise ValueError("datetime must be a tuple with 1 to 7 elements: "
                             "(year, month, day, hour, minute, second, weekday, yearday)")
        
        year, month, day, hour, minute, second, weekday, yearday = (
            datetime[0],
            datetime[1],
            datetime[2],
            datetime[3],
            datetime[4],
            datetime[5] if len(datetime) > 5 else 0,
            datetime[6] if len(datetime) > 6 else 0,  # weekday is 0-6 in MicroPython
            datetime[7] if len(datetime) > 7 else 1   # yearday is 1-366
            )

        weekday = (weekday % 7) + 1  # from MicroPython 0-6 to DS3231 1-7

        if not (2000 <= year <= 2099):
            raise ValueError(f"Year {year} out of range (2000-2099)")
        if not (1 <= month <= 12):
            raise ValueError(f"Month {month} out of range (1-12)")
        if not (1 <= day <= 31):
            raise ValueError(f"Day {day} out of range (1-31)")
        if not (0 <= hour < 24):
            raise ValueError(f"Hour {hour} out of range (0-23)")
        if not (0 <= minute < 60):
            raise ValueError(f"Minute {minute} out of range (0-59)")
        if not (0 <= second < 60):
            raise ValueError(f"Second {second} out of range (0-59)")
        if not (1 <= weekday < 8):
            raise ValueError(f"Weekday {weekday} out of range (1-7) for DS3231")
        if not (1 <= yearday < 367):
            raise ValueError(f"Yearday {yearday} out of range (1-366)")
        
        # Validation passed, now prepare to set the new date/time.
        # ----------------------------
        # Set new date/time on chip
        # ----------------------------

        self._timebuf[0] = dectobcd(second)                     # Seconds
        self._timebuf[1] = dectobcd(minute)                     # Minutes
        self._timebuf[2] = dectobcd(hour)                       # Hours, assumes 24-h format
        self._timebuf[3] = dectobcd(weekday)                    # weekday 1-7
        self._timebuf[4] = dectobcd(day)                        # Day of the month
        self._timebuf[5] = dectobcd(month) & 0xFF               # Month, ignore century bit
        
        # Year: allow full YYYY or YY; take last two digits
        self._timebuf[6] = dectobcd(int(str(year)[-2:]))

        # Write all 7 bytes in one I²C transaction for accuracy
        self.i2c.writeto_mem(self.addr, DATETIME_REG, self._timebuf)
        
        # Clear any Oscillator Stop Flag now that time is freshly set
        self._OSF_reset()
        return True

    
    
    def square_wave(self, freq=None):
        """Enable/read square-wave output on SQW pin.
        
        - No argument: returns current CONTROL_REG value (which encodes freq).
        - freq=False: disable SQW (forces INTCN=1, ALIE1&2=0).
        - freq=1-4: enable 1 Hz, 1.024 kHz, 4.096 kHz, or 8.192 kHz output.
        """
        if freq is None:
            # Read one byte from CONTROL_REG
            return self.i2c.readfrom_mem(self.addr, CONTROL_REG, 1)[0]

        # Read current control byte into buffer
        self.i2c.readfrom_mem_into(self.addr, CONTROL_REG, self._buf)
        ctrl = self._buf[0]
        if not freq:
            # Disable SQW: set INTCN bit=1 (mask lower 3 bits → preserve top 5) then OR 0x04
            new = (ctrl & 0xF8) | 0x04
        else:
            # Enable SQW: clear INTCN=0 (mask bits 3-5), then OR desired freq<<3
            new = (ctrl & 0xE3) | ((freq - 1) << 3)
        # Write updated control byte
        self.i2c.writeto_mem(self.addr, CONTROL_REG, bytearray([new]))
        return True

    
    
    def output_32kHz(self, enable=True):
        """Toggle the 32.768 kHz output on the SQW pin (STATUS_REG bit 3)."""
        current = self.i2c.readfrom_mem(self.addr, STATUS_REG, 1)[0]
        if enable:
            new = current | (1 << 3)
        else:
            new = current & ~(1 << 3)
        self.i2c.writeto_mem(self.addr, STATUS_REG, bytearray([new]))

    
    
    def OSF(self):
        """Return the Oscillator Stop Flag (OSF, STATUS_REG bit 7).
        
        True if the timekeeping was halted (power loss) since last check.
        """
        return bool(self.i2c.readfrom_mem(self.addr, STATUS_REG, 1)[0] & 0x80)

    
    
    def _OSF_reset(self):
        """Clear the Oscillator Stop Flag (OSF) by writing 0 to STATUS_REG bit 7."""
        self.i2c.readfrom_mem_into(self.addr, STATUS_REG, self._buf)
        cleared = self._buf[0] & 0x7F
        self.i2c.writeto_mem(self.addr, STATUS_REG, bytearray([cleared]))

    
    
    def _is_busy(self):
        """Return True if the DS3231 is busy with TCXO frequency trimming (STATUS_REG bit 2)."""
        return bool(self.i2c.readfrom_mem(self.addr, STATUS_REG, 1)[0] & (1 << 2))