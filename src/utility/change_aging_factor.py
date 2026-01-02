
"""
Andrea Favero 20260103

On-demand Sync Clock (OSC)
A digital clock with on-request NTP syncing, via a push button.
The clock is based on a LiLyGO TTGO T8-S3 board and DS3231SN module


Utility function to set a new aging factor to the DS3231 chip.
The aging factor allows to speed up or slow down the timekeeper.
The aging factor ranges from -127 to 127.
Every unit affects about 1 ppm.

 - Negative sign indicates the clock runs slow (needs speeding up)
 + Positive sign means the clock runs runs fast (needs slowing down)

"""

SDA_PIN = 1
SCL_PIN = 2
DS3231_PWR_PIN = 3


# modules for the DS3231SN - AT24C32 board
from ds3231_driver import DS3231
from machine import SoftI2C, Pin
from utime import sleep_ms


def _convert_to_number(num_text):
    """Convert text to number"""
    if isinstance(num_text, (int, float)):
        return int(round(num_text,0))
    
    try:
        return int(num_text)
    except ValueError as e:
        return None


# initialize the ds3231_pwr pin
ds3231_pwr = Pin(DS3231_PWR_PIN, Pin.OUT)

# energize the sd3231
ds3231_pwr.value(1)
sleep_ms(100)

# initialize the i2c
i2c = SoftI2C(scl=Pin(SCL_PIN), sda=Pin(SDA_PIN), freq=400_000)
sleep_ms(250)
        
# instance of RTC module with EEPROM support
ds = DS3231(i2c)
sleep_ms(250)

# read aging
current_aging_factor = ds.read_aging()
sleep_ms(250)

if current_aging_factor is not None:
    full_line = "#" * 77
    separation_line = f"#{" " * 75}#"

    print()
    print(full_line)
    print(separation_line)
    print("#  Utility to apply an aging factor, to speed up or slow down the DS3231SN  #")
    print("#  The allowed range is from -127 to 127; Every unit corrects about 1 ppm   #")
    print(separation_line)
    print("#  - Negative sign indicates the clock runs slow (needs speeding up)        #")
    print("#  + Positive sign means the clock runs runs fast (needs slowing down)      #")
    print(separation_line)
    print(full_line)

    print(f"\nNOTE: The aging factor currently used by the DS3231 chip is: {current_aging_factor}")
    
    user_input = input("ENTER THE AGING FACTOR, AFTER THE COLON: ").strip()

    if user_input == "":
        print("\nNo value entered. The aging factor will remain unchanged.")
    else:
        aging_factor = _convert_to_number(user_input)
        
        if aging_factor is None:
            print("\nInvalid entry (non-numeric). The aging factor will remain unchanged.")
        else:
            print(f"\nThe entered aging factor of {aging_factor} is getting written to the DS3231 chip")

            # write the entered aging_factor to the DS3231 chip
            ds.write_aging(value = aging_factor)
            sleep_ms(250)
            
            # read aging_factor stored at the DS3231 chip
            new_aging_factor = ds.read_aging()
            
            # compared the aging_factor with the original one, and print out
            if new_aging_factor != current_aging_factor:
                print(f"INFO: The new aging factor stored at the DS3231 chip is: {new_aging_factor}\n")
            else:
                print(f"INFO: The aging factor stored at the DS3231 chip is: {new_aging_factor}\n")


# de-energize the sd3231
ds3231_pwr.value(0)


