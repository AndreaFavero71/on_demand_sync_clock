"""
On-demand Sync Clock (OSC)
A digital clock with on-request NTP syncing, via a push button.

More info at:
  https://github.com/AndreaFavero71/on_demand_sync_clock
  https://www.instructables.com/On-Demand-sync-Clock/
"""

###################################################################################################
# System controls #########################################################################

# features
QUICK_CHECK    = True#False               # set True only for code debugging
OPEN_NETWORKS  = True                # set True if open wify are an option
BATTERY        = True                # set True if battery operated
WDT_ENABLED    = True                # set True always (allows reboot is any code freezing)

# Notes:
# When QUICK_CHECK then:
# 1) LIGHTSLEEP_USAGE gets set False, to prevent serial communication dropping
# 2) DEBUG sets set True



###################################################################################################
# Constants #######################################################################################

NTP_SERVERS = ['pool.ntp.org', 'nl.pool.ntp.org', 'europe.pool.ntp.org', 
               'time.nist.gov', 'time.google.com', 'time.windows.com']

# regional settings
UTC_TZ = 1                           # timezone UTC (1 is the one for Amsterdam, in The Netherland)
DST = True                           # True if the Country uses DST (Day Saving Time), like The Netherlands does
DST_REGION   = 'EU'                  # or 'US'or 'AU', only needed if DST=True, see dst.json file for rules
TEMP_DEGREES = 'C'                   # 'C' for Celsius, 'F' for Farenheit
DATE_FORMAT  = 'DMY'                 # date format, options are DMY, MDY and YMD
HOUR_12_FORMAT = False               # set True for 12-hour format of time
AM_PM_LABEL = True                   # set False to remove AM / PM label from 12-hour time format

LANGUAGE = "EN"                      # set the language for the week's days

_DAYS = {"EN": ('MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY'),              # English
         "ES": ('LUNES', 'MARTES', 'MIERCOLES', 'JUEVES', 'VIERNES', 'SABADO', 'DOMINGO'),                  # Spanish
         "FR": ('LUNDI', 'MARDI', 'MERCREDI', 'JEUDI', 'VENDREDI', 'SAMEDI', 'DIMANCHE'),                   # French
         "DE": ('MONTAG', 'DIENSTAG', 'MITTWOCH', 'DONNERSTAG', 'FREITAG', 'SAMSTAG', 'SONNTAG'),           # German
         "IT": ('LUNEDI', 'MARTEDI', 'MERCOLEDI', 'GIOVEDI', 'VENERDI', 'SABATO', 'DOMENICA'),              # Italian
         "PT": ('SEGUNDA', 'TERCA', 'QUARTA', 'QUINTA', 'SEXTA', 'SABADO', 'DOMINGO'),                      # Portuguese
         "RU": ('PONEDELNIK', 'VTORNIK', 'SREDA', 'CHETVERG', 'PYATNITSA', 'SUBBOTA', 'VOSKRESENYE'),       # Russian (transliterated)
         "ZH": ('XINGQIYI', 'XINGQIER', 'XINGQISAN', 'XINGQISI', 'XINGQIWU', 'XINGQILIU', 'XINGQIRI'),      # Chinese (Pinyin)
         "HI": ('SOMAVAAR', 'MANGALAVAAR', 'BUDHAVAAR', 'GURUVAAR', 'SHUKRAVAAR', 'SHANIVAAR', 'RAVIVAAR'), # Hindi   (transliterated)
         "AR": ('AL-ITHNAYN', 'ATH-THULATHA', 'AL-ARBAA', 'AL-KHAMIS', 'AL-JUMAA', 'AS-SABT', 'AL-AHAD'),   # Arabic  (transliterated)
         }

DAYS = _DAYS[LANGUAGE]               # days of the week with the selected language


# EPD display update period (in ms)
DISPLAY_REFRESH_MS    =     60_000   # 60 secs is the smaller acceptable period


# NTP related settings
NTP_SERVER_ATTEMPTS   =          5   # number of times each NTP server will be querried
MAX_NTP_OFFSET_MS     =       1000   # max time offset from NTP to reset internal RTC


# Temperature shift
TEMPERATURE_SHIFT = 1.2              # value added to the temperature retrieved from DS3231


# Minimum period (in hours) to enable auto-calibration (aging factor) of the DS3231 chip
# This is the time from the boot, or since the last NTP sync. A longer period reduces
# the error due to low resolution (1 sec) of this clock.
# Note 1 sec error in in 14 days means 0.83ppm (26 secs error / year)
MIN_TIME_AUTO_CAL_H = 14 * 24        # 14 days


# case the clock is battery operated, a a low voltage warning is applicable
if BATTERY:
    BATTERY_WARNING = 3.4            # min battery voltage to plot a warning


# Files names for diagnostic and study relate
if WDT_ENABLED:
    WDT_LOG_FILE   = "log/wdt_log.txt"
RESET_FILE_NAME    = "log/reset_reason.txt"


# time delta in secs from 01/01/2000 (MicroPython system for ESP32)
NTP_DELTA = 3155673600

# fractional coefficient from Celsius to Fahrenheit conversion
C_TO_F_COEFF = 9/5



###################################################################################################
# Conditional settings ############################################################################

# NTP related settings
if QUICK_CHECK:                         # when quick test
    LIGHTSLEEP_USAGE = False            # disable lightsleep
    DEBUG = True                        # enable DEBUG (verbose printing)
else:                                   # when normal operation
    LIGHTSLEEP_USAGE = True             # enables lightsleep
    DEBUG = False                       # disable DEBUG


# WDT settings
if WDT_ENABLED:
    wdt_warn_fraction = 0.8
    wdt_timeout_ms = int(2.5 * DISPLAY_REFRESH_MS)
