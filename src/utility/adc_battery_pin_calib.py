"""
Andrea Favero 20260103

On-demand Sync Clock (OSC)
A digital clock with on-request NTP syncing, via a push button.


Function to monitor the GPIO input voltage for ADC calibration purpose


MIT License

Copyright (c) 2025 Andrea Favero

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

from utime import time, gmtime, sleep_ms, ticks_ms, ticks_diff
from machine import Pin, ADC
import gc

from lib.lib_display import helvetica110b_digits, helvetica28b_subset
from lib.lib_display.epd4in2_V2 import EPD
from lib.lib_display.writer import Writer


EPD_WIDTH = 400
EPD_HEIGHT = 300


BATTERY_CHECK_INTERVAL_S = 1        # period (in secs) in between battery level check

# settings for battery voltage check
ADC_IN = Pin(4)                     # GPIO1 reads battery voltage
adc_bat = ADC(ADC_IN)               # adc object
adc_bat.atten(ADC.ATTN_11DB)        # 11dB attenuation (input range up to ~3.3V)
V_REF = 3.3                         # ADC reference voltage (assuming ESP32 powered at 3.3V)
DIVIDER_RATIO = 2                   # voltage divider ratio:  (R2 + R41) / R41 = (100 + 100) / 100
VBAT_READINGS = 20                  # number of readings for averaging
CORRECTION = 1.0004 # default 1.0   # correction of adc reading slope vs measured (multimeter)
SHIFT = 0.23        # default 0.0   # correction of adc reading shift vs measured (multimeter)    
HYSTERESIS_V = 0.03                 # 30 mV hysteresys from battery_level change


# battery voltage initial variabile
battery_voltage_list = []           # initialize list holdist the last voltage measurements
battery_voltage = 0                 # initialize variable holding the battery voltage
battery_level = 0                   # initialize variable holding the battery level
last_battery_level = None           # track the last battery_level
last_battery_check_time = 0         # initialize variable holding the last battery check time


def read_battery_voltage(adc_avg=0, bat_voltage=0):
    """Monitor the battery voltage"""
    try:
        adc_avg = adc_bat.read()       # first ADC reading
        sleep_ms(5)                    # Short sleep time

        for _ in range(VBAT_READINGS): # iterating VBAT_READINGS times
            adc_avg += adc_bat.read()  # adds raw ADC value (0-4095) for VBAT_READINGS times
            sleep_ms(10)               # short sleep time
        
        adc_avg /= (VBAT_READINGS + 1) # average the VBAT_READINGS readings
        
         # convertion to batt voltage and correction
        bat_voltage = SHIFT + CORRECTION * (adc_avg / 4095) * V_REF * DIVIDER_RATIO
        return bat_voltage             # returns the measured battery voltag

    except Exception as e:
        print(f"Error reading battery voltage: {e}")
        return None



def get_battery_percentage(voltage):
    """
    Returns the battery percentage corresponding to the closest voltage level.
    Args:
        voltage (float): The measured battery voltage.
    Returns:
        int: The battery percentage that best matches the voltage.
    """
    voltage_levels = [4.1, 3.93, 3.82, 3.75, 3.7, 3.65, 3.6]
    percent_levels = [100, 80,   60,   40,   20,  10,   0]

    # find the index of the voltage level closest to the measured voltage
    closest_index = min(range(len(voltage_levels)), key=lambda i: abs(voltage - voltage_levels[i]))
    new_level = percent_levels[closest_index]
    
    # if this is the first measurement, return directly
    if last_battery_level is None:
        return new_level

    # find index of the last level
    try:
        last_index = percent_levels.index(last_level)
    except ValueError:
        last_index = closest_index

    # hysteresis logic
    if new_level > last_level:
        # only go up if voltage exceeds next threshold + hysteresis
        next_up_v = voltage_levels[last_index - 1] if last_index > 0 else voltage_levels[0]
        if voltage >= next_up_v + HYSTERESIS_V:
            return new_level
        else:
            return last_level

    elif new_level < last_level:
        # only go down if voltage goes below next threshold - hysteresis
        next_down_v = voltage_levels[last_index + 1] if last_index < len(voltage_levels) - 1 else voltage_levels[-1]
        if voltage <= next_down_v - HYSTERESIS_V:
            return new_level
        else:
            return last_level

    else:
        return last_level



def check_battery(now, battery_voltage, battery_voltage_list, battery_level, last_battery_check_time,
                  BATTERY_CHECK_INTERVAL_S, first_time = False):

    if first_time or now > last_battery_check_time + BATTERY_CHECK_INTERVAL_S:
        battery_voltage = round(read_battery_voltage(),3) # battery voltage is measured   
        battery_voltage_list.append(battery_voltage)
        
        if len(battery_voltage_list) > 1:
            battery_voltage = sum(battery_voltage_list) / len(battery_voltage_list)
        
        if len(battery_voltage_list) > 10:
            battery_voltage_list.pop(0)
            
        battery_level = get_battery_percentage(battery_voltage)
        last_battery_level = battery_level
        
        last_battery_check_time = time()
    
    return battery_voltage, battery_voltage_list, battery_level, last_battery_check_time


def show_data(volt, batt_level, run, partial=True):
    
    # corrdinates to organize the fields on the screen
    ref_x = 110
    ref_y = 90
    y_shift = 30
    
    # add a white rect to erase old day text
    epd.fill_rect(0, 0, 399, 299, 1)                 
    
    # measurement counter
    Writer.set_textpos(epd, 270, 10)
    wri_28.printstring(f"MEASURE: {run}", invert=True)
    
    # measured voltage at GPIO input pin
    Writer.set_textpos(epd, ref_y, ref_x)
    wri_28.printstring(f"{round(volt,3):.3f} VOLT", invert=True)
    
    # interpreted battery level
    Writer.set_textpos(epd, ref_y + 2*y_shift, ref_x)
    wri_28.printstring(f"{batt_level} %", invert=True)

    # intermittent line separation to substantiate
    if run % 2 == 0:
        Writer.set_textpos(epd, ref_y+y_shift, ref_x)
        wri_28.printstring("----------------", invert=True)


def print_info():
    print()
    print("#" *87)
    print("#                                                                                     #")
    print("#  Shows the averaged voltage supplied at GPIO pin for the battery (and level %).     #")
    print("#                                                                                     #")
    print("#  Recall to detach the battery first !                                               #")
    print("#                                                                                     #")
    print("#  Connect an adjustable power supply voltage to the wiring, normally used by the     #")
    print("#  battery to energize the T8 board.                                                  #")
    print("#                                                                                     #")
    print("#  Vary the power supply voltage from ca 3.0 Volts to max 4.2 Volts.                  #")
    print("#  After every variation, wait until the value on the screen gets stable (averaging)  #")
    print("#  Make a table with the supply voltage, and the voltage measured by the ESP32.       #")
    print("#                                                                                     #")
    print("#  Calculate the correction factor for the slope and the one for the shift:           #")
    print("#  The correction of adc reading vs measured (multimeter / power supply voltage)      #")
    print("#  - for the slope should be > 1 when intepreted value is smaller than real.          #")
    print("#  - for the shift should be > 0 when intepreted value is smaller than real.          #")
    print("#                                                                                     #")
    print("#  Adjust the battery_manager.py accordingly:                                         #")
    print("#  - constant CORRECTION  (default = 1.0 --> Adapt it according to your case)         #")
    print("#  - constant SHIFT       (default = 0.0 --> Adapt it according to your case)         #")
    print("#                                                                                     #")
    print("#" *87)
    print()
    
    
    
print_info()
epd = EPD()
epd.init()
gc.collect()
wri_110 = Writer(epd, helvetica110b_digits, verbose=False)
wri_28 = Writer(epd, helvetica28b_subset, verbose=False)
gc.collect()
epd.reset()   # wake the epd up from deep sleep


full_refresh_cycles = 60
update_epd = False
run = 0
while True:
    
    epd.reset()   # wake the epd up from deep sleep
    
    if run >= full_refresh_cycles:
        epd.reset()
        epd.display()
        run = 0
    
    now = time()
    
    # first check of the battery voltage and related level 
    battery_voltage, battery_voltage_list, battery_level, last_battery_check_time = check_battery(now,
                                                                                                  battery_voltage,
                                                                                                  battery_voltage_list,
                                                                                                  battery_level,
                                                                                                  last_battery_check_time,
                                                                                                  BATTERY_CHECK_INTERVAL_S)
    
    show_data(battery_voltage, battery_level, run, partial=True)
    epd.partialDisplay()
    epd.sleep()               # prevents display damages on the long run (command takes ca 100ms)
    run += 1
    
    print(f"Avg batt = {battery_voltage:.3f}V \t Batt level = {battery_level}% \t Raw data = {battery_voltage_list}",  end='\r')
    
    sleep_ms(1000)
