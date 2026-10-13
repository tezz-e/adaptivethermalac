"""
comfort_model.py
================================================================================
The "brain" of the system — all the temperature maths and control decisions.

This file contains four functions. They are called in order by app.py each
time a new sensor reading arrives from the ESP32:

    1. calculate_ashrae_comfort(outdoor_temp)
       Converts outdoor temperature into a recommended indoor target using
       the official ASHRAE Standard 55 equation.

    2. get_hostel_comfort_band(outdoor_temp, current_hour, preferred_temp)
       Wraps the ASHRAE result into a ±1.5°C band and adds a nighttime offset.
       Returns a dict with the target, band limits, and a reason string.

    3. evaluate_hostel_ac_decision(room_temp, min_temp, max_temp, last_ac_state)
       Implements the hysteresis (deadband) controller that decides ON/OFF.
       Returns a 3-item tuple: (ac_state, servo_angle, explanation).

    4. calculate_runtime_reduction(hours_ac_off, total_sleep_hours)
       Computes how much active cooling time was saved overnight (used in Tab 2).

No classes, no objects — just plain functions and dicts.
================================================================================
"""

import config   # for ASHRAE constants, servo angles, night hours, sleep duration


# ---------------------------------------------------------------------------
# FUNCTION 1: ASHRAE Standard 55 comfort equation
# ---------------------------------------------------------------------------

def calculate_ashrae_comfort(outdoor_temp):
    """
    Calculates the recommended indoor "comfortable temperature" using the
    ASHRAE Standard 55 linear regression equation:

        Comfortable Temp = 17.8 + (0.31 x Outdoor Temp)

    Example: Outdoor = 34°C  -->  17.8 + (0.31 x 34) = 28.34°C

    Why "clamped_temp"?
        ASHRAE only studied buildings with outdoor temps between 10°C and 35°C.
        If outdoor temp is outside that range (e.g., 5°C or 40°C), the formula
        gives unreliable results. We clamp (clip) it to the studied range using
        min() and max() together: max(10, min(35, value)) is a Python idiom
        that forces a value to stay inside [10, 35].

    Parameters:
        outdoor_temp (float): Current outdoor temperature in Celsius.

    Returns:
        float: Recommended indoor temperature, rounded to 2 decimal places.
    """
    # Clamp outdoor_temp to the valid ASHRAE study range of 10°C – 35°C
    clamped_temp = max(10.0, min(35.0, outdoor_temp))

    # Apply the linear equation using constants from config.py
    comfortable_temp = config.ASHRAE_INTERCEPT + (config.ASHRAE_SLOPE * clamped_temp)

    return round(comfortable_temp, 2)


# ---------------------------------------------------------------------------
# FUNCTION 2: Full comfort band (target + ±1.5°C deadband + night offset)
# ---------------------------------------------------------------------------

def get_hostel_comfort_band(outdoor_temp, current_hour, preferred_temp=None):
    """
    Builds the full comfort band dict used by the thermostat controller.

    Two modes:
        - If the resident has set a preferred temp (via the slider), we use that.
        - Otherwise we calculate the ASHRAE adaptive target from outdoor weather.

    Night mode (22:00 – 07:00):
        Adds +1.0°C to the target because sleeping humans produce less body heat
        and are insulated by blankets, so they are comfortable at a slightly
        warmer room temperature.

    The ±1.5°C deadband (comfort band):
        Instead of targeting exactly 25.0°C, we accept the range 23.5 – 26.5°C.
        This prevents the servo from toggling rapidly on tiny 0.1°C DHT11 noise.

    Parameters:
        outdoor_temp   (float): Current outdoor temperature in Celsius.
        current_hour   (int):   Current hour of day (0-23), from time.localtime().
        preferred_temp (float): Resident's slider preference, or None for ASHRAE auto.

    Returns:
        dict with keys: optimal_temp, min_temp, max_temp, is_night_mode,
                        preferred_temp, reason
    """
    # Choose the base target: resident preference or ASHRAE calculation
    if preferred_temp is not None:
        base_target    = float(preferred_temp)
        profile_source = f"Resident Preferred ({preferred_temp:.1f}°C)"
    else:
        base_target    = calculate_ashrae_comfort(outdoor_temp)
        profile_source = "ASHRAE Weather-Adaptive"

    # Night mode check: True if time is 22:00-23:59 OR 00:00-06:59
    # The "or" covers midnight crossing: hour >= 22 covers 22,23 and hour < 7 covers 0-6.
    is_night = (current_hour >= config.NIGHT_START_HOUR) or (current_hour < config.NIGHT_END_HOUR)

    if is_night:
        optimal_temp = round(base_target + config.NIGHT_COMFORT_OFFSET, 2)
        reason = f"{profile_source} + Night Mode (+{config.NIGHT_COMFORT_OFFSET}°C sleep offset)."
    else:
        optimal_temp = round(base_target, 2)
        reason = f"{profile_source} daytime profile."

    # Comfort band: ±1.5°C around the target
    min_temp = round(optimal_temp - 1.5, 2)
    max_temp = round(optimal_temp + 1.5, 2)

    # Return everything as a dict so callers can access values by name, not by index
    return {
        "optimal_temp":   optimal_temp,
        "min_temp":       min_temp,
        "max_temp":       max_temp,
        "is_night_mode":  is_night,
        "preferred_temp": preferred_temp,
        "reason":         reason
    }


# ---------------------------------------------------------------------------
# FUNCTION 3: Hysteresis (deadband) controller
# ---------------------------------------------------------------------------

def evaluate_hostel_ac_decision(room_temp, min_temp, max_temp, last_ac_state="OFF"):
    """
    Decides whether to turn the AC ON or OFF based on room temperature and the
    comfort band. Uses hysteresis (deadband) logic to avoid rapid toggling.

    The three possible outcomes:
        1. Room is too cold (<= min_temp) --> Turn AC OFF (servo 0°)
        2. Room is too hot  (>= max_temp) --> Turn AC ON  (servo 90°)
        3. Room is inside the band        --> Keep previous state (no change)

    Why "keep previous state" inside the band?
        Without this rule, if the room is exactly at 25.0°C and the target is
        also 25.0°C, the AC would flip ON and OFF every 2.5 seconds as the
        DHT11 reads 24.9 then 25.1 due to sensor noise. The deadband prevents
        that "chattering" behaviour.

    Parameters:
        room_temp     (float): Current room temperature from DHT11.
        min_temp      (float): Lower edge of comfort band (target - 1.5°C).
        max_temp      (float): Upper edge of comfort band (target + 1.5°C).
        last_ac_state (str):   Previous AC state, "ON" or "OFF". Default "OFF".

    Returns:
        A 3-item tuple: (ac_state, servo_angle, explanation_string)
        Example: ("ON", 90, "Room temp (27.2°C) reached upper limit (26.5°C). AC switched ON.")
    """
    if room_temp <= min_temp:
        # Room has cooled down to the lower edge — switch AC OFF
        return (
            "OFF",
            config.SERVO_OFF_ANGLE,
            f"Room temp ({room_temp:.1f}°C) reached lower limit ({min_temp:.1f}°C). AC switched OFF."
        )
    elif room_temp >= max_temp:
        # Room has warmed up to the upper edge — switch AC ON
        return (
            "ON",
            config.SERVO_ON_ANGLE,
            f"Room temp ({room_temp:.1f}°C) reached upper limit ({max_temp:.1f}°C). AC switched ON."
        )
    else:
        # Room is inside the comfort band — hold previous state to avoid chattering
        angle = config.SERVO_ON_ANGLE if last_ac_state == "ON" else config.SERVO_OFF_ANGLE
        return (
            last_ac_state,
            angle,
            f"Room temp ({room_temp:.1f}°C) is inside comfort band [{min_temp:.1f} – {max_temp:.1f}°C]. AC stays {last_ac_state}."
        )


# ---------------------------------------------------------------------------
# FUNCTION 4: Overnight run-time reduction calculator (used in Tab 2)
# ---------------------------------------------------------------------------

def calculate_runtime_reduction(hours_ac_off=4.0, total_sleep_hours=config.OVERNIGHT_SLEEP_HOURS):
    """
    Calculates how much active cooling time was avoided overnight by using the
    adaptive comfort system (which turns the AC off when the room is already cool).

    Example:
        If the AC was off for 4 hours out of an 8-hour sleep period:
            Run-time reduction = (4 / 8) * 100 = 50%
            Degree-hours avoided = 4 hours * 4.0°C/hr = 16.0 °C·hr

    The "degree-hours avoided" is a measure of overcooling prevented:
        It assumes the AC would have overcooled the room by ~4°C during that time.
        This is a rough estimate used to illustrate energy savings for the viva.

    Parameters:
        hours_ac_off      (float): How many hours the AC was switched off overnight.
                                   The Tab 2 slider controls this value (1.0 to 7.0).
        total_sleep_hours (float): Total overnight sleep window (default 8.0 hrs).

    Returns:
        dict with keys: hours_cooling_off, total_sleep_hours,
                        runtime_reduction_pct, degree_hours_avoided
    """
    # Clamp hours_ac_off so it cannot exceed total_sleep_hours or go below 0
    clamped_hours = max(0.0, min(total_sleep_hours, hours_ac_off))

    # Percentage of the sleep window where AC was off
    reduction_pct = round((clamped_hours / total_sleep_hours) * 100, 1)

    # Degree-hours: rough estimate of overcooling avoided (4°C * hours off)
    degree_hours_avoided = round(clamped_hours * 4.0, 1)

    return {
        "hours_cooling_off":    clamped_hours,
        "total_sleep_hours":    total_sleep_hours,
        "runtime_reduction_pct": reduction_pct,
        "degree_hours_avoided": degree_hours_avoided
    }
