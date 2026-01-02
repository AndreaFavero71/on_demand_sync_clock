"""
Self-learning clock project
Class managing the e-paper display



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


from lib.lib_display import helvetica110b_digits, helvetica28b_subset, helvetica17b_subset
from lib.lib_display.battery_icons import BatteryIcons
from lib.lib_display.writer import Writer
from lib.lib_display.epd4in2_V2 import EPD

from machine import lightsleep
from utime import sleep_ms
import framebuf, gc



class Display():
    def __init__(self, wdt_manager, lightsleep_active, battery, degrees, debug=False, logo_time_ms=0):

        self.wdt_manager = wdt_manager
        self.lightsleep_active = lightsleep_active
        self.battery = battery
        self.debug = debug
        self.degrees = degrees
        
        self.sleeping = False
        self.bg = True
        self.reset_variables()
        
        self.epd = EPD()
        self.epd_reset()
        
        self.wri_110 = Writer(self.epd, helvetica110b_digits, verbose=False)
        self.wri_28  = Writer(self.epd, helvetica28b_subset, verbose=False)
        self.wri_17  = Writer(self.epd, helvetica17b_subset, verbose=False)
        
        # coordinates for labels and fields at the EPD
        self.date_x, self.date_y                =  12,  20
        self.ds3231_temp_x, self.ds3231_temp_y  = 150, 220  #160, 220  #12, 220
        self.free_txt_x, self.free_txt_y        =  26, 266
        self.wifi_x, self.wifi_y                =   2, 283
        self.ntp_x, self.ntp_y                  = 127, 283
        self.lastsync_x, self.lastsync_y        = 254, 283
        
        # get xy coordinates for HH:MM time characters (m1,m2 are minutes, s1,s2 are seconds, c is colon or battery icon)
        self.digits_coordinates(ref_x=11, ref_y=75)
        
        # force garbage collection
        gc.collect()
        
        with open("lib/lib_display/SLC_logo_328x208.bin", "rb") as f:  # opens the binary file with welcome bmp image
            slc_logo_image = bytearray(f.read())           # makes a bytearray from the image
        
        with open("lib/lib_display/SLC_text_280x64.bin", "rb") as f:   # opens the binary file with welcome bmp image
            slc_logo_text = bytearray(f.read())            # makes a bytearray from the image
        
        # cover the images from bytearray to framebuffer type
        self.slc_logo = framebuf.FrameBuffer(slc_logo_image, 328, 208, framebuf.MONO_HLSB)
        self.slc_text = framebuf.FrameBuffer(slc_logo_text, 280, 64, framebuf.MONO_HLSB)
        
        # delete the bytearray made for then binary images
        del slc_logo_image, slc_logo_text
        
        # force garbage collection
        gc.collect()
        
        # case the logo_time_ms (visualization time in ms) is bigger than zero
        if logo_time_ms > 0:
            # plot the SLC logo with its text
            self.plot_slc(text=True, plot=True, show_ms=logo_time_ms, lightsleep_req=False)
        
        # call the functiona managing the EPD deep sleep
        self.epd_sleep()     # prevents display damages on the long run (command takes ca 100ms)

    
    
    def feed_wdt(self, label=""):
        """Use the WDT manager instead of global WDT"""
        self.wdt_manager.feed(label)
    
    
    def epd_reset(self):
        self.epd.reset()
        self.sleeping = False
        
        
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
        
        
    def plot_slc(self, text=False, plot=False, show_ms=10000, lightsleep_req=True):
        """
        Plots the Self learning Clock logo, and optionally its text
        Blitting the two images takes ca 50ms
        """
        if self.debug:
            print(f"[DISPLAY]  Plotting the SLC logo")
        if self.sleeping:
            self.epd_wakeup()

        self.epd.fill(0xff)                  # fills the framebuffer with 1 (0 inverted)
        self.epd.blit(self.slc_logo, 36, 6)  # plots the Self learning Clock icon
        
        if text:
            self.epd.blit(self.slc_text, 60, 230) # plots the Self learning Clock text
        
        if plot:
            self.epd.partialDisplay()        # epd partial update 
            self.epd_sleep()                 # prevents display damages on the long run (command takes ca 100ms)
        
        self.show_time(show_ms, lightsleep_req)
        self.bg = True                       # activates the background plot request
    
    
    
    
    
    def show_time(self, show_ms, lightsleep_req=True):
        if self.lightsleep_active and lightsleep_req:
            if self.debug:
                print(f"[DISPLAY]  Going to lightsleep for {show_ms} ms")
            
            # HERE
#             lightsleep(show_ms)
            sleep_ms(show_ms)
        else:
            if self.debug:
                print(f"[DISPLAY]  Going to sleep for {show_ms} ms")
            sleep_ms(show_ms)



    
    def text_on_logo(self, text, x, y, show_time_ms=5000, lighsleep=True):
        """ Plot the Self Learning Clock logo and add a text message on the bottom."""
        
        if self.debug:
            print(f"[DISPLAY]  Plotting text on logo: {text}")
        
        self.plot_slc(text=False, plot=False, show_ms=0)   # add the logo to the framebuffer
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
        
        self.epd.fill_rect(0, self.free_txt_y - 16, 399, 52, 0) # add a black bandwhith
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
        
        # coordinates for the battery icon
        if self.battery:
            self.c_x,  self.c_y  = x + 176 , y + 20
        
        # coordinates for the colon placement
        else:
            # use colon character insted of battery symbol
            self.c_x  = x + 162
            self.c_y  = y -14 if y >= 12 else 0
        


    def reset_variables(self):
        self.last_ntp_datetime_str = -1
        self.last_batt_level = -1
        self.last_dd = -1
        self.last_H1, self.last_H2, self.last_M1, self.last_M2, self.last_dd = -1, -1, -1, -1, -1
        self.last_wifi_bool = -1
        self.last_ntp_bool = -1
        self.last_ds3231_temp = -1
    
    
    
    def background(self, battery_low=False, full_refresh=False):        
        
        if full_refresh:
            self.epd.init_Fast()   # wakes the EPD from eventual deeep sleep and enable full refresh
            self.epd.fill(0xff)    # fills the buffer with 1 (0 inverted...)
            self.epd.display()     # full edp refresh
        else:
            self.epd.fill(0xff)
        
        if not self.battery:
            # uses the colon as hours to minutes separator
            Writer.set_textpos(self.epd, self.c_y, self.c_x) # y, x order
            self.wri_110.printstring(":", invert=True)       # colon to separate HH and MM
        
        if not battery_low:
            self.epd.fill_rect(  0, 276, 399,  2, 0)         # add a black horizzontal line
            self.epd.fill_rect(119, 278,   2, 30, 0)         # add a black vertical line, to separate fields
            self.epd.fill_rect(246, 278,   2, 30, 0)         # add a black vertical line, to separate fields

            Writer.set_textpos(self.epd, self.wifi_y, self.wifi_x) 
            self.wri_17.printstring(f"WIFI:", invert=True)   # WIFI lable

            Writer.set_textpos(self.epd, self.ntp_y, self.ntp_x)
            self.wri_17.printstring(f"NTP:", invert=True)    # NPT lable

            
        self.reset_variables()
        
        self.bg = False
        



    def show_data(self, H1, H2, M1, M2, dd, day, d_string, ntp_datetime_str, ds3231_temp,
                  batt_level, wifi_bool, ntp_bool, battery_low=False, plot_all=True):
        """
        Plots the data to the framebuffer and shows it on the display.
        The function also manages partial update for the fields/digits that changes since
        the previous update.
        """

        if plot_all or self.bg:
            self.background(battery_low=battery_low, full_refresh=True)
             
        if self.sleeping:
            self.epd_wakeup()
        
        update_epd = False
        
        if self.battery and batt_level != self.last_batt_level:
            self.epd.blit(BatteryIcons.battery_icon[batt_level], self.c_x, self.c_y) # plots the Self learning Clock text
            self.last_batt_level = batt_level
            update_epd = True
        
        if dd != self.last_dd:
            Writer.set_textpos(self.epd, self.date_y, self.date_x)       # y, x order
            self.wri_28.printstring(day, invert=True)                    # day of the week 
            Writer.set_textpos(self.epd, self.date_y, self.date_x+223)   # y, x order
            self.wri_28.printstring(d_string, invert=True)               # date in date_format
            update_epd = True
            self.last_dd = dd
        
        if ds3231_temp != self.last_ds3231_temp:
            self.epd.fill_rect(self.ds3231_temp_x, self.ds3231_temp_y, 120, 28, 1)  # add a white rect to erase old text
            Writer.set_textpos(self.epd, self.ds3231_temp_y, self.ds3231_temp_x)
            self.wri_28.printstring(f"{round(ds3231_temp,1)} °{self.degrees}", invert=True)
            self.last_ds3231_temp = ds3231_temp
            update_epd = True
        
        if H1 != self.last_H1:
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

        
        if battery_low:
            self.text("BATTERY  LOW ...", -1, -1)
        
        else:
            if wifi_bool != self.last_wifi_bool:
                self.epd.fill_rect(self.wifi_x+45, self.wifi_y, 71, 19, 1)  # add a white rect to erase old text
                Writer.set_textpos(self.epd, self.wifi_y, self.wifi_x+45)
                txt = "OK" if wifi_bool else "NOT OK"
                self.wri_17.printstring(txt, invert=True)
                self.last_wifi_bool = wifi_bool
                update_epd = True
                
            if ntp_bool != self.last_ntp_bool:
                self.epd.fill_rect(self.ntp_x+45, self.ntp_y, 71, 19, 1)  # add a white rect to erase old text
                Writer.set_textpos(self.epd, self.ntp_y, self.ntp_x+45)
                txt = "OK" if ntp_bool else "NOT OK"
                self.wri_17.printstring(txt, invert=True)
                self.last_ntp_bool = ntp_bool
                update_epd = True
            
            if ntp_datetime_str != self.last_ntp_datetime_str:
                
                self.epd.fill_rect(self.lastsync_x, self.lastsync_y, 58, 19, 1)  # add a white rect to erase old text
                Writer.set_textpos(self.epd, self.lastsync_y, self.lastsync_x)
                
                self.wri_17.printstring(ntp_datetime_str, invert=True)
                self.last_ntp_datetime_str = ntp_datetime_str
                update_epd = True
                
        
        
        if update_epd:
            self.epd_partial_update()
            
        


