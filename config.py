"""
config.py
================================================================================
Central configuration settings for the Hostel Adaptive Thermal Comfort System.
Stores geographic location, comfort thresholds, hardware settings, and file paths.
================================================================================
"""

# Campus Geographic Coordinates
CAMPUS_NAME = "Campus Hostels"
CAMPUS_LATITUDE = 12.9692
CAMPUS_LONGITUDE = 79.1559

# Flask Server Port (ESP32 communicates here)
FLASK_PORT = 5000

# ASHRAE Standard 55 Linear Regression Constants
# Formula: Comfortable Temp = 17.8 + (0.31 * Outdoor Temp)
ASHRAE_INTERCEPT = 17.8
ASHRAE_SLOPE = 0.31

# Hostel Overnight Sleep Profile Settings
NIGHT_START_HOUR = 22      # 10:00 PM (night mode begins)
NIGHT_END_HOUR = 7         # 07:00 AM (night mode ends)
NIGHT_COMFORT_OFFSET = 1.0 # +1.0°C higher target during sleep (blankets + 0.7 met)

# SG90 Micro Servo Motor Angles (Physical Rocker Switch)
SERVO_OFF_ANGLE = 0   # 0 degrees = Switch pushed OFF
SERVO_ON_ANGLE = 90   # 90 degrees = Switch pushed ON

# Default Resident Preferred Temperature (°C)
DEFAULT_PREFERRED_TEMP = 25.0

# Typical Overnight Sleep Duration (hours)
OVERNIGHT_SLEEP_HOURS = 8.0

# CSV Telemetry File Path
CSV_FILE_PATH = "data/hostel_telemetry.csv"
