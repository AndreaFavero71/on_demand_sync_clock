"""
On-demand Sync Clock (OSC)
A digital clock with on-request NTP syncing, via a push button.

Class managing the e-paper display


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

# specific modules for the OSC clock
from lib.lib_display import helvetica110b_digits, helvetica32b_subset, helvetica28b_subset, helvetica17b_subset
from lib.lib_display.battery_icons import BatteryIcons
from lib.lib_display.epd4in2_V2 import EPD
from lib.lib_display.writer import Writer

# standard modules
from machine import lightsleep
from utime import sleep_ms
import framebuf, gc



class Display():
    def __init__(self, wdt_manager, lightsleep_active, battery, degrees, hour12, am_pm_label, debug=False, logo_time_ms=0):

        self.wdt_manager = wdt_manager
        self.lightsleep_active = lightsleep_active
        self.battery = battery
        self.degrees = degrees
        self.hour12 = hour12
        self.am_pm_label = am_pm_label
        self.debug = debug
        
        self.sleeping = False
        self.bg = True
        self.reset_variables()
        
        self.epd = EPD()
        self.epd_wakeup()
        
        self.wri_110 = Writer(self.epd, helvetica110b_digits, verbose=False)        
        self.wri_32  = Writer(self.epd, helvetica32b_subset, verbose=False)
        self.wri_28  = Writer(self.epd, helvetica28b_subset, verbose=False)
        self.wri_17  = Writer(self.epd, helvetica17b_subset, verbose=False)
        
        # coordinates for fields at the EPD        X ,  Y
        self.date_x, self.date_y                =  12,  12
        self.am_x, self.am_y                    =  12,  52
        self.ds3231_temp_x, self.ds3231_temp_y  =  16, 202
        self.batt_x, self.batt_y                = 242, 202
        self.free_txt_x, self.free_txt_y        =  26, 268
        self.wifi_x, self.wifi_y                =   4, 266
        self.ntp_x, self.ntp_y                  = 119, 266
        self.lastsync_x, self.lastsync_y        = 234, 266
        self.cal_enabled_x, self.cal_enabled_y  =   4, 283
        self.aging_x, self.aging_y              = 234, 283
        
        # get xy coordinates for HH:MM time characters, based on one unique reference (ref_x, ref_y)
        # m1,m2 are minutes, s1,s2 are seconds, c is colon or battery icon
        ref_x, ref_y = 11, 64
        if self.hour12 and self.am_pm_label:
            ref_y              += 8
            self.ds3231_temp_y += 8
            self.batt_y        += 8

        self.digits_coordinates(ref_x=ref_x, ref_y=ref_y)
        
        # force garbage collection
        gc.collect()
        
        with open("lib/lib_display/OSC_logo_328x208.bin", "rb") as f:  # opens the binary file with welcome bmp image
            osc_logo_image = bytearray(f.read())           # makes a bytearray from the image
        
        with open("lib/lib_display/OSC_text_304x64.bin", "rb") as f:   # opens the binary file with welcome bmp image
            osc_logo_text = bytearray(f.read())            # makes a bytearray from the image
        
        # cover the images from bytearray to framebuffer type
        self.osc_logo = framebuf.FrameBuffer(osc_logo_image, 328, 208, framebuf.MONO_HLSB)
        self.osc_text = framebuf.FrameBuffer(osc_logo_text, 304, 64, framebuf.MONO_HLSB)
        
        
        # delete the bytearray made for then binary images
        del osc_logo_image, osc_logo_text
        
        # force garbage collection
        gc.collect()
        
        # case the logo_time_ms (visualization time in ms) is bigger than zero
        if logo_time_ms > 0:
            # plot the OSC logo with its text
            self.plot_osc(text=True, plot=True, show_ms=logo_time_ms, lightsleep_req=False)
        
        # call the functiona managing the EPD deep sleep
        self.epd_sleep()     # prevents display damages on the long run (command takes ca 100ms)

    
    
    def feed_wdt(self, label=""):
        """Use the WDT manager instead of global WDT"""
        self.wdt_manager.feed(label)
        
        
    def epd_wakeup(self):
        self.epd.reset()            # wakes up the display from sleeping, and enables partial refresh
        self.sleeping = False

    
    def epd_sleep(self):
        self.sleeping = True
        self.epd.sleep()            # prevents display damages on the long run
    
    
    def epd_partial_update(self):
        self.epd.partialDisplay()   # plots the buffer to the display (takes ca 0.6 secs)
        if not self.sleeping:
            self.epd_sleep()
        
        
    def plot_osc(self, text=False, plot=False, show_ms=10000, lightsleep_req=True):
        """
        Plots the On-demand Sync Clock logo, and optionally its text
        Blitting the two images takes ca 50ms
        """
        
        if self.debug:
            if text:
                print(f"[DISPLAY]  Plotting the OSC logo with OSC text")
            else:
                print(f"[DISPLAY]  Plotting the OSC logo without OSC text")
        
        if self.sleeping:
            self.epd_wakeup()

        self.epd.fill(0xff)                  # fills the framebuffer with 1 (0 inverted)
        self.epd.blit(self.osc_logo, 34, 14) # plots the OSC icon
        
        if text:
            self.epd.blit(self.osc_text, 50, 222) # plots the OSC logo with custom text
        
        if plot:
            self.epd.partialDisplay()        # epd partial update 
            self.epd_sleep()                 # prevents display damages on the long run (command takes ca 100ms)
        
        self.show_time(show_ms, lightsleep_req)
        self.bg = True                       # activates the background plot request
    
    
    
    
    
    def show_time(self, show_ms, lightsleep_req=True):
        """Sleep or lightsleep time to allow display reading time."""
        if self.lightsleep_active and lightsleep_req:
            lightsleep(show_ms)
            
            #######################################################################
            ###### DBEBUG #########################################################
            #
            # This is only for debug the lightsleep part without lighsleep function
            # It prevents the serial communication from dropping.
            # Note osc.py uses lightsleep function too.
            #
            # comment out lightsleep(show_ms)
            # uncomment command below
#             sleep_ms(show_ms)
            #
            #######################################################################
            #######################################################################
            
        else:
            if self.debug and show_ms > 0:
                print(f"[DISPLAY]  Going to sleep for {show_ms} ms")
            sleep_ms(show_ms)



    
    def text_on_logo(self, text, x, y, show_time_ms=5000, lighsleep=True):
        """ Plot the OSC logo and add a text message on the bottom."""
        
        if self.debug:
            print(f"[DISPLAY]  Plotting text on logo: {text}")
        
        self.plot_osc(text=False, plot=False, show_ms=0)   # add the logo to the framebuffer
        self.text(text, x, y)                              # add the text to the framebuffer
        self.epd.partialDisplay()                          # partial update of the display
        self.show_time(show_time_ms)                       # sleep time to read the message
        self.bg = True                                     # activates the background plot request
        
    
    
    def text(self, text, x, y):
        """ Add a text message to the framebuffer."""
        
        if x < 0:
            x = self.free_txt_x
        if y < 0:
            y = self.free_txt_y
        
        self.epd.fill_rect(0, self.free_txt_y - 10, 399, 40, 0) # add a black bandwhith
        Writer.set_textpos(self.epd, y, x)                 # set the text location (y, x order)
        self.wri_28.printstring(text, invert=False)        # add the white text 
         
        

    def digits_coordinates(self, ref_x=0, ref_y=0):
        """
        Returns the coordinates for HH:MM characters, from the reference xy coordinates.
        Returned values are based on helvetica110b_digits font.
        This for perfect overlapping of single digit over the multi-digits previously plotted.
        """
        # (top-left starting) coordinate of HH:SS string placement on the EDP
        x, y = ref_x, ref_y
        
        # coordinates for the individual digits placement
        self.m1_x, self.m1_y = x       , y
        self.m2_x, self.m2_y = x + 82  , y
        self.s1_x, self.s1_y = x + 214 , y
        self.s2_x, self.s2_y = x + 296 , y
        self.c_x  = x + 162
        self.c_y  = y -14 if y >= 12 else 0
        


    def reset_variables(self):
        """Assign an unrealistic value to all fields."""
        
        defaults = {
            'last_ntp_datetime_str': -1,
            'last_batt_level': -1,
            'last_dd': -1,
            'last_H1': -1,
            'last_H2': -1,
            'last_M1': -1,
            'last_M2': -1,
            'last_ds3231_temp': -1,
            'prev_battery_low': -1,
        }

        if self.am_pm_label:
            defaults['last_am_pm'] = -1

        for k, v in defaults.items():
            setattr(self, k, v)
    
    
    
    def background(self, wifi_bool, ntp_bool, ntp_datetime_str, aging, cal_bool=False, battery_low=False, full_refresh=False):        
        
        if full_refresh:
            self.epd.init_Fast()   # wakes the EPD from eventual deeep sleep and enable full refresh
            self.epd.fill(0xff)    # fills the buffer with 1 (0 inverted...)
            self.epd.display()     # full edp refresh
        else:
            self.epd.fill(0xff)
        
        # colon character separating HH and MM
        Writer.set_textpos(self.epd, self.c_y, self.c_x)     # y, x order
        self.wri_110.printstring(":", invert=True)           # colon to separate HH and MM
            
        if not battery_low:
            Writer.set_textpos(self.epd, self.wifi_y, self.wifi_x) 
            txt = "WIFI OK" if wifi_bool else "WIFI NOT OK"
            self.wri_17.printstring(txt, invert=True)

            Writer.set_textpos(self.epd, self.ntp_y, self.ntp_x)
            txt = "NTP OK" if ntp_bool else "NTP NOT OK"
            self.wri_17.printstring(txt, invert=True)
            
            # date time of the last NTP sync
            Writer.set_textpos(self.epd, self.lastsync_y, self.lastsync_x)
            self.wri_17.printstring(ntp_datetime_str, invert=True)
            
            # aging factor
            Writer.set_textpos(self.epd, self.aging_y, self.aging_x)
            self.wri_17.printstring(f"AGING FACT:  {aging}", invert=True)
            
            # calibration enabled / disabled
            Writer.set_textpos(self.epd, self.cal_enabled_y, self.cal_enabled_x)
            txt = "CALIBRATION  ENABLED" if cal_bool else "CALIBRATION  DISABLED"
            self.wri_17.printstring(txt, invert=True)
            
            # a set of lines are plot, to separate the fields and increase readability.
            # Lines are plot after plotting the text, as overlapping with part of the 'white' characters'part
            # Target is to compress as mush as possible on the y axis this text part, while keeping readability
            self.epd.fill_rect(  0, 263, 399,  1, 0)         # add a 1st black horizzontal line
            self.epd.fill_rect(  0, 281, 399,  1, 0)         # add a 2nd black horizzontal line
            self.epd.fill_rect(  0, 299, 399,  1, 0)         # add a 3nd black horizzontal line
            self.epd.fill_rect(113, 264,   1, 17, 0)         # add a 1st black vertical line, to separate fields
            self.epd.fill_rect(228, 264,   1, 35, 0)         # add a 2nd and longer black vertical line, to separate fields

            
        self.reset_variables()
        
        self.bg = False
        



    def show_data(self, H1, H2, M1, M2, dd, day, d_string, ntp_datetime_str, ds3231_temp, batt_level,
                  wifi_bool, ntp_bool, aging, cal_bool, am=False, battery_low=False, plot_all=True):
        """
        Plots the data to the framebuffer and shows it on the display.
        The function also manages partial update for the fields/digits that changes since
        the previous update.
        """
        
        # cases requiring background update
        if plot_all or self.bg or (not battery_low and self.prev_battery_low):
            self.background(wifi_bool, ntp_bool, ntp_datetime_str, aging, cal_bool, battery_low=battery_low, full_refresh=True)
             
        if self.sleeping:
            self.epd_wakeup()
        
        update_epd = False
        
        if self.battery and batt_level != self.last_batt_level:
            self.epd.blit(BatteryIcons.battery_icon[batt_level], self.batt_x, self.batt_y) # plots the OSC logo with custom text
            self.last_batt_level = batt_level
            update_epd = True
        
        if dd != self.last_dd:
            # day of the week
            self.epd.fill_rect(self.date_x, self.date_y, 210, 27, 1)     # add a white rect to erase old text
            Writer.set_textpos(self.epd, self.date_y, self.date_x)       # y, x order
            self.wri_28.printstring(day, invert=True)                    # day of the week 
            
            # full date
            Writer.set_textpos(self.epd, self.date_y, self.date_x+223)   # y, x order
            self.wri_28.printstring(d_string, invert=True)               # date in date_format
            update_epd = True
            self.last_dd = dd
        
        if ds3231_temp != self.last_ds3231_temp:
            self.epd.fill_rect(self.ds3231_temp_x, self.ds3231_temp_y, 210, 33, 1)  # add a white rect to erase old text
            Writer.set_textpos(self.epd, self.ds3231_temp_y, self.ds3231_temp_x)
            self.wri_32.printstring(f"{round(ds3231_temp,1)} °{self.degrees}", invert=True)
            self.last_ds3231_temp = ds3231_temp
            update_epd = True
        
        if H1 != self.last_H1:
            if self.hour12 and H1 == '0':
                if self.last_H1 == '1' or self.last_H1 == -1:
                    self.epd.fill_rect(self.m1_x, self.m1_y, 82, 110, 1)  # add a white rect to erase old text
                t_string = f"{H2}"
                Writer.set_textpos(self.epd, self.m1_y, self.m1_x+82)
            else:
                t_string = f"{H1+H2}"
                Writer.set_textpos(self.epd, self.m1_y, self.m1_x)
            self.wri_110.printstring(t_string, invert=True)
            
            t_string = f"{M1+M2}"
            Writer.set_textpos(self.epd, self.s1_y, self.s1_x)
            self.wri_110.printstring(t_string, invert=True)

            self.last_H1 = H1
            self.last_H2 = H2
            self.last_M1 = M1
            self.last_M2 = M2
            update_epd = True
        
        elif H2 != self.last_H2:
            t_string = f"{H2}"
            Writer.set_textpos(self.epd, self.m2_y, self.m2_x)
            self.wri_110.printstring(t_string, invert=True)
            t_string = f"{M1+M2}"
            Writer.set_textpos(self.epd, self.s1_y, self.s1_x)
            self.wri_110.printstring(t_string, invert=True)
            self.last_H2 = H2
            self.last_M1 = M1
            self.last_M2 = M2
            update_epd = True
            
        elif M1 != self.last_M1:
            t_string = f"{M1+M2}"
            Writer.set_textpos(self.epd, self.s1_y, self.s1_x)
            self.wri_110.printstring(t_string, invert=True)
            self.last_M1 = M1
            self.last_M2 = M2
            update_epd = True
        
        elif M2 != self.last_M2:
            Writer.set_textpos(self.epd, self.s2_y, self.s2_x)
            self.wri_110.printstring(M2, invert=True)
            self.last_M2 = M2
            update_epd = True

        if self.am_pm_label and self.hour12:
            if am != self.last_am_pm:
                if am:
                    Writer.set_textpos(self.epd, self.am_y, self.am_x)
                    self.wri_17.printstring('AM', invert=True)
                else:
                    Writer.set_textpos(self.epd, self.am_y, self.am_x)
                    self.wri_17.printstring('PM', invert=True)
                    
        if battery_low:
            if not self.prev_battery_low:
                self.text("BATTERY  LOW ...", -1, -1)
                self.prev_battery_low = battery_low
        else:
            if self.prev_battery_low:
                self.prev_battery_low = battery_low

        if update_epd:
            self.epd_partial_update()
            
        


if __name__ == "__main__":
    """
    The __main__ function has the purpose to visualize the display layout, by
    plotting random values.
    Modules like config.py and time_manager are used.
    """
    
    from lib.config import config
    from lib.time_manager import TimeManager
    from utime import localtime
    from random import randint
    
    print("\nDisplay test, with random values\n")
    
    print("battery     :", config.BATTERY)
    print("degrees     :", config.TEMP_DEGREES)
    print("hour12      :", config.HOUR_12_FORMAT)
    print("am_pm_label :", config.AM_PM_LABEL)
    print()

    
    def get_time_tuple_from_epoch(epoch_s):
        return localtime(epoch_s)
    
    def get_datetime_from_time_tuple(time_tuple):
        year          = time_tuple[0]
        month         = time_tuple[1]
        mday          = time_tuple[2]
        hour          = time_tuple[3]
        minute        = time_tuple[4]
        second        = time_tuple[5]
        weekday       = time_tuple[6]
        yearday       = time_tuple[7]
        return year, month, mday, hour, minute, second, weekday, yearday
    
    
    def get_ntp_datetime_str(epoch_s):
        # get the time tuple calculated as one year earlier than the passed epoch
        time_tuple = get_time_tuple_from_epoch(epoch_s - 31536000)
        year, month, mday, hour, minute, second, weekday, yearday = get_datetime_from_time_tuple(time_tuple)

        # assign fields according to date format
        if config.DATE_FORMAT == 'DMY':
            field_1, field_2, field_3 = mday, month, year
        elif config.DATE_FORMAT == 'MDY':
            field_1, field_2, field_3 = month, mday, year
        elif config.DATE_FORMAT == 'YMD':
            field_1, field_2, field_3 = year, month, mday
        else:
            field_1, field_2, field_3 = year, month, mday

        # prepare formatted date with correct width for year
        def fmt_field(value, is_year=False):
            if is_year:
                return "{:04d}".format(value)
            return "{:02d}".format(value)

        # build formatted date string with 4-digit year
        date_str = "{}-{}-{}".format(
            fmt_field(field_1, field_1 == year),
            fmt_field(field_2, field_2 == year),
            fmt_field(field_3, field_3 == year)
            )

        # format time (12h or 24h)
        if not config.HOUR_12_FORMAT:
            return "{} {:02d}:{:02d}".format(date_str, hour, minute)
        else:
            am_pm = 'AM'
            if hour == 0:
                hour = 12
            elif hour >= 12:
                am_pm = 'PM'
                if hour > 12:
                    hour -= 12
            if config.AM_PM_LABEL:
                return "{} {:02d}:{:02d} {}".format(date_str, hour, minute, am_pm)
            else:
                return "{} {:02d}:{:02d}".format(date_str, hour, minute)

    
    
    # initialize the display
    display = Display(wdt_manager = None,
                      lightsleep_active = config.LIGHTSLEEP_USAGE,
                      battery = config.BATTERY,
                      degrees = config.TEMP_DEGREES,
                      hour12 = config.HOUR_12_FORMAT,
                      am_pm_label = config.AM_PM_LABEL,
                      debug = config.DEBUG,
                      logo_time_ms = 1000
                      )
    
    # initialize the time_manager
    time_mgr = TimeManager(config)
    
    print("\n"*2)
    run = -1
    
    while True:
        
        # generate random epoch between 20251212 and 20301212
        epoch_s = 818856732 + randint(0, 5*365*86_400)
        
        # get the time tuple from the random epoch
        time_tuple = get_time_tuple_from_epoch(epoch_s)
        
        # get the datetime elements from the random time_tuple
        year, month, mday, hour, minute, second, weekday, yearday = get_datetime_from_time_tuple(time_tuple)

        # retrieve date and time strings
        dd, day, d_string = time_mgr.get_date(time_tuple)
        H1, H2, M1, M2, am = time_mgr.get_time_digits(time_tuple)
        ntp_datetime_str = get_ntp_datetime_str(epoch_s)
        
        # other fields
        temp          = randint(0, 500)/10
        ntp_bool      = (True, False)[randint(0,1)]
        wifi_bool     = (True, False)[randint(0,1)]
        cal_bool      = (True, False)[randint(0,1)]
        aging         = randint(-127, 127)
        batt_level    = (0, 10, 20, 40, 60, 80, 100)[randint(0,6)]
        
        # The transition from True to False of battery_low forces a full refresh of the display
        # For this reason its occurrence gets limited
        battery_low   = True if run % 10 == 0 else False    

        # define whether the EPD shoyld partial update or full refresh
        if run < 0 or run >= 3: #60:
            run = 0
            plot_all = True
        else:
            plot_all = False
        
        # printing to the shell
        if config.HOUR_12_FORMAT:
            time24 = "{:02d}".format(hour) + ":" + "{:02d}".format(minute)
            print(f"Date: {d_string} \t Time24 {time24} \t Time12 {H1}{H2}:{M1}{M2} {'AM' if am else 'PM'} \t Last NTP sync: {ntp_datetime_str}")
        elif not config.HOUR_12_FORMAT:
            print(f"Date: {d_string} \t Time: {H1}{H2}:{M1}{M2} \t Last NTP sync: {ntp_datetime_str}")
        
        # call the display 
        display.show_data(H1, H2, M1, M2, dd, day, d_string, ntp_datetime_str, temp, batt_level,
                          wifi_bool, ntp_bool, aging, cal_bool, am, battery_low=battery_low, plot_all=plot_all)
            
        run += 1
        sleep_ms(5000)