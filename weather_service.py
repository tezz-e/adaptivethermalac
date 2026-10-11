"""
weather_service.py
================================================================================
What is this file?
This module fetches the real-time outdoor temperature and humidity for our campus
from the internet.

Why do we import 'requests'?
'requests' is a popular Python library used to download data from website APIs.
Think of it like Python's built-in web browser that can fetch information in code.

Why do we import 'config'?
'config' is our own config.py file right next to this one! We import it to get
the campus latitude (12.9692) and longitude (79.1559).
================================================================================
"""

import time
import requests
import config

# Simple memory variables to store the latest weather reading
# Outdoor weather changes slowly, so we reuse the reading for 5 minutes (300 seconds)
# to avoid spamming the free API and keep ESP32 responses instant!
cached_weather = None
last_fetch_timestamp = 0


def fetch_live_weather(force_refresh=False):
    """
    Fetches the current live temperature and humidity for the campus using Open-Meteo API.
    Open-Meteo is a free weather service that requires no API key or account signup.
    
    Returns:
        A dictionary containing:
        - 'temperature_c': float (outdoor temperature in °C)
        - 'humidity_pct': float (relative humidity in %)
        - 'source': str (where the data came from)
    """
    global cached_weather, last_fetch_timestamp

    # Check if we already have a recent reading from the last 5 minutes (300 seconds)
    current_time = time.time()
    if not force_refresh and cached_weather is not None and (current_time - last_fetch_timestamp) < 300:
        return cached_weather

    # Build the URL to ask Open-Meteo for the current temperature and humidity
    api_url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={config.CAMPUS_LATITUDE}&longitude={config.CAMPUS_LONGITUDE}"
        f"&current=temperature_2m,relative_humidity_2m"
    )

    # We use a try...except block to prevent our code from crashing if the internet drops
    try:
        # Step 1: Send the request over the internet (timeout=5 means wait max 5 seconds)
        response = requests.get(api_url, timeout=5)

        # Step 2: Convert the website's response into a Python dictionary
        data = response.json()

        # Step 3: Extract current numbers from the dictionary
        current_data = data["current"]
        temp = float(current_data["temperature_2m"])
        hum = float(current_data["relative_humidity_2m"])

        # Step 4: Save to memory and return clean dictionary
        cached_weather = {
            "temperature_c": round(temp, 1),
            "humidity_pct": round(hum, 1),
            "source": "Open-Meteo Live API"
        }
        last_fetch_timestamp = current_time
        return cached_weather

    except Exception as error:
        # If there is no internet, we print a warning and return safe backup numbers
        # so the rest of the project and demo continue working without stopping!
        print(f"[Warning] Could not reach weather API ({error}). Using offline backup values.")
        if cached_weather is not None:
            return cached_weather
        return {
            "temperature_c": 30.5,
            "humidity_pct": 55.0,
            "source": "Offline Backup Value"
        }
