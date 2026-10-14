"""
config.py
================================================================================
All the "magic numbers" and settings for the system live here in one place.
If you want to change a pin number, temperature range, or file path, you only
need to edit this file — nothing else.

Why one central config file?
    Instead of scattering numbers like 17.8 or 0.31 across multiple files, we
    define them once here and import this file wherever needed. That means if
    your hardware changes, you only update one line.
================================================================================
"""

# ---------------------------------------------------------------------------
# Campus Location (used to fetch outdoor weather from Open-Meteo / wttr.in)
# ---------------------------------------------------------------------------
CAMPUS_NAME      = "Campus Hostels"
CAMPUS_LATITUDE  = 12.9692   # Latitude of Katpadi, Vellore (degrees North)
CAMPUS_LONGITUDE = 79.1559   # Longitude of Katpadi, Vellore (degrees East)

# ---------------------------------------------------------------------------
# Flask Server Port
# The ESP32 sends its sensor data to http://<laptop-ip>:5000/api/hostel/telemetry
# The dashboard reads the latest state from the same server on the same port.
# ---------------------------------------------------------------------------
FLASK_PORT = 5000

# ---------------------------------------------------------------------------
# ASHRAE Standard 55 Adaptive Comfort Equation Constants
# Formula: Comfortable Indoor Temp = 17.8 + (0.31 x Outdoor Temp)
# Example: If outdoor temp is 34°C  →  17.8 + (0.31 x 34) = 28.34°C target
# Source: ASHRAE 55 adaptive model for naturally conditioned spaces, simplified:
# uses current outdoor temp instead of the prevailing mean outdoor temp
# ---------------------------------------------------------------------------
ASHRAE_INTERCEPT = 17.8   # The "base" indoor temp when outdoor temp is 0°C
ASHRAE_SLOPE     = 0.31   # How much the target rises for each 1°C outdoor rise

# ---------------------------------------------------------------------------
# Control Deadband (Hysteresis)
# Half-width around optimal temperature. Our design choice (prevents servo chatter).
# ---------------------------------------------------------------------------
COMFORT_BAND_HALF_WIDTH = 1.5   # ±1.5°C control deadband

# ---------------------------------------------------------------------------
# Overnight Sleep Mode Settings
# Between 22:00 and 07:00 the target is shifted up by NIGHT_COMFORT_OFFSET.
# Reason: sleeping humans generate less body heat (0.7 MET vs 1.0 MET awake)
# and are under blankets (~1.3 clo insulation), so the room can be warmer.
# ---------------------------------------------------------------------------
NIGHT_START_HOUR    = 22    # 10:00 PM — night mode switches ON
NIGHT_END_HOUR      = 7     # 07:00 AM — night mode switches OFF
NIGHT_COMFORT_OFFSET = 1.0  # Shift the target +1.0°C warmer during sleep

# ---------------------------------------------------------------------------
# SG90 Servo Motor Angles (GPIO 18)
# The servo arm physically presses the wall AC switch:
#   0 degrees   = arm retracted  = switch OFF
#   180 degrees = arm extended   = switch ON
# ---------------------------------------------------------------------------
SERVO_OFF_ANGLE = 0    # Servo angle that pushes AC switch to OFF position
SERVO_ON_ANGLE  = 180  # Servo angle that pushes AC switch to ON position (full 180° throw)

# ---------------------------------------------------------------------------
# Default Resident Temperature Preference
# None = use ASHRAE auto calculation by default.
# If set to a float (e.g. 25.0), overrides ASHRAE with user preference.
# ---------------------------------------------------------------------------
DEFAULT_PREFERRED_TEMP = None   # None = use ASHRAE auto

# ---------------------------------------------------------------------------
# Overnight Sleep Duration & Overcooling Estimate (Illustrative Scenario)
# Baseline assumes an on/off wall-switch AC would otherwise run all 8 hours.
# ---------------------------------------------------------------------------
OVERNIGHT_SLEEP_HOURS   = 8.0   # hours per night
OVERCOOL_DEG_PER_HOUR   = 4.0   # estimated overcooling rate (°C per hour) without control

# ---------------------------------------------------------------------------
# CSV Log File Path (relative to the project root folder)
# All sensor readings and AC decisions are appended here.
# The "data/" folder is created automatically if it does not exist.
# ---------------------------------------------------------------------------
CSV_FILE_PATH = "data/hostel_telemetry.csv"
