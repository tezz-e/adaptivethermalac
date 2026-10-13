"""
weather_service.py
================================================================================
Fetches real-time outdoor temperature and humidity for Katpadi, Vellore.

How it works:
    1. We call a free weather API (wttr.in) and ask for current conditions
       at "Katpadi, Vellore" — the same data Google Weather uses locally.
    2. If that API fails (no internet on the hotspot), we try a second API
       (Open-Meteo) using GPS coordinates.
    3. If both fail, we return a safe offline backup value (34°C).

Why cache the weather?
    The dashboard refreshes every 2.5 seconds. If we called the weather API
    on every refresh, we would get rate-limited and slow down the dashboard.
    Instead, we store (cache) the last result and only re-fetch every 5 minutes.
================================================================================
"""

import time       # time.time() gives us the current time as a number (seconds since 1970)
import requests   # the 'requests' library lets Python fetch data from a URL, like a browser would
import config     # our central settings file (campus coordinates, etc.)

# ---------------------------------------------------------------------------
# Module-level cache variables
# These live at the top level of this file (outside any function) so they
# persist between function calls — Python keeps them alive for the whole run.
# ---------------------------------------------------------------------------
cached_weather     = None   # stores the last successful weather dict (or None if never fetched)
last_fetch_timestamp = 0    # stores the time() value when we last fetched (starts at 0 = never)


def fetch_live_weather(force_refresh=False):
    """
    Returns a dict with current outdoor weather for Katpadi, Vellore:
        {
            "temperature_c": 34.1,
            "humidity_pct": 42.0,
            "source": "Katpadi Weather Station (Live API)"
        }

    Parameters:
        force_refresh (bool): If True, bypass the 5-minute cache and fetch
                              fresh data immediately. Default is False.

    The cache means this function only makes a real network request once
    every 5 minutes (300 seconds), even if called every 2.5 seconds.
    """
    # 'global' tells Python we want to modify the module-level variables,
    # not create new local ones inside this function.
    global cached_weather, last_fetch_timestamp

    current_time = time.time()   # get the current time in seconds

    # If we already have a cached result and it is less than 5 minutes old,
    # return it immediately without making any network request.
    if not force_refresh and cached_weather is not None and (current_time - last_fetch_timestamp) < 300:
        return cached_weather

    # -----------------------------------------------------------------------
    # Attempt 1: wttr.in local weather station for Katpadi, Vellore
    # This matches what Google Weather shows for our campus location.
    # requests.get() sends an HTTP GET request (like opening a URL in a browser)
    # timeout=4 means "give up after 4 seconds if the server doesn't respond"
    # -----------------------------------------------------------------------
    try:
        resp = requests.get("https://wttr.in/Katpadi,Vellore?format=j1", timeout=4)
        if resp.status_code == 200:   # 200 means "OK, the server replied successfully"
            current_cond = resp.json()["current_condition"][0]   # parse the JSON response
            cached_weather = {
                "temperature_c": round(float(current_cond["temp_C"]), 1),
                "humidity_pct":  round(float(current_cond["humidity"]), 1),
                "source": "Katpadi Weather Station (Live API)"
            }
            last_fetch_timestamp = current_time   # record when this successful fetch happened
            return cached_weather
    except Exception:
        pass   # if anything went wrong (no internet, timeout, etc.), try the next source

    # -----------------------------------------------------------------------
    # Attempt 2: Open-Meteo coordinate-based grid API (fallback)
    # We build the URL from our campus latitude/longitude in config.py.
    # f-strings (f"...") let us insert variable values directly into strings.
    # -----------------------------------------------------------------------
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
                "humidity_pct":  round(float(current_data["relative_humidity_2m"]), 1),
                "source": "Open-Meteo Live API"
            }
            last_fetch_timestamp = current_time
            return cached_weather
    except Exception:
        pass   # both APIs failed — fall through to the offline backup

    # -----------------------------------------------------------------------
    # Attempt 3: Offline backup
    # If we still have a stale cached value from a previous successful fetch,
    # return it rather than a hardcoded number.
    # If this is the very first run and we have never fetched anything, return
    # a hardcoded offline backup (34°C is the typical Katpadi summer average).
    # -----------------------------------------------------------------------
    if cached_weather is not None:
        return cached_weather
    return {
        "temperature_c": 34.0,
        "humidity_pct":  45.0,
        "source": "Katpadi Offline Backup"
    }
