# This file is executed on every boot (including wake-boot from deepsleep)


##################################################################
# To get the code starting at the boot, uncomment the below code #
# Before doing so, ensures the code is running without errors    #
##################################################################

# from utime import sleep_ms
# 
# print(f"\n\n15 seconds sleep time to delay the WDT")
# print("This time should suffice to interrupt the code via CTRL + C (preventing automatic script execution)\n")
# sleep_ms(10_000)
# 
# import asyncio
# import osc
# asyncio.run(osc.main(logo_time_ms=10_000))



##################################################################
# To calibrate the GPIO input pin for battery voltage            #
##################################################################
# import utility.adc_battery_pin_calib
