"""
weather_service.py
================================================================================
Fetches real-time outdoor temperature and humidity for Katpadi, Vellore
(12.9692°N, 79.1559°E).
Uses wttr.in local station data first (matching Google Weather for Katpadi),
falls back to Open-Meteo, and uses a safe offline backup if internet is down.
================================================================================
"""

import time
import requests
import config

cached_weather = None
last_fetch_timestamp = 0


def fetch_live_weather(force_refresh=False):
    """
    Fetches live outdoor temperature and humidity for Katpadi, Vellore.
    Caches the reading for 5 minutes (300 seconds) so dashboard refreshes stay instant.
    """
    global cached_weather, last_fetch_timestamp

    current_time = time.time()
    if not force_refresh and cached_weather is not None and (current_time - last_fetch_timestamp) < 300:
        return cached_weather

    # 1. Primary: wttr.in local weather station for Katpadi, Vellore (matches Google Weather)
    try:
        resp = requests.get("https://wttr.in/Katpadi,Vellore?format=j1", timeout=4)
        if resp.status_code == 200:
            current_cond = resp.json()["current_condition"][0]
            cached_weather = {
                "temperature_c": round(float(current_cond["temp_C"]), 1),
                "humidity_pct": round(float(current_cond["humidity"]), 1),
                "source": "Katpadi Weather Station (Live API)"
            }
            last_fetch_timestamp = current_time
            return cached_weather
    except Exception:
        pass

    # 2. Secondary: Open-Meteo coordinate grid API
    try:
        api_url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={config.CAMPUS_LATITUDE}&longitude={config.CAMPUS_LONGITUDE}"
            f"&current=temperature_2m,relative_humidity_2m"
        )
        resp = requests.get(api_url, timeout=4)
        if resp.status_code == 200:
            current_data = resp.json()["current"]
            cached_weather = {
                "temperature_c": round(float(current_data["temperature_2m"]), 1),
                "humidity_pct": round(float(current_data["relative_humidity_2m"]), 1),
                "source": "Open-Meteo Live API"
            }
            last_fetch_timestamp = current_time
            return cached_weather
    except Exception:
        pass

    # 3. Offline fallback if hotspot has no internet access
    if cached_weather is not None:
        return cached_weather
    return {
        "temperature_c": 34.0,
        "humidity_pct": 45.0,
        "source": "Katpadi Offline Backup"
    }
