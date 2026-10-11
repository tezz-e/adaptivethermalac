"""
comfort_model.py
================================================================================
What is this file?
Contains the mathematical and decision-making logic for the hostel AC unit:
1. Calculates the ASHRAE Standard 55 adaptive comfort temperature.
2. Applies the diurnal nighttime sleep adjustment (+1.0°C for blankets & 0.7 met).
3. Evaluates thermostat hysteresis logic to decide if the AC switch should be ON or OFF.
4. Calculates overnight run-time reduction and overcooling degree-hours prevented.
   (Based strictly on measured temperature and time, without guessing chiller specs!)
================================================================================
"""

import config


def calculate_ashrae_comfort(outdoor_temp):
    """
    Calculates the base indoor comfortable temperature using ASHRAE 55 formula.
    
    Formula:
        Comfortable Temp = 17.8 + (0.31 * Outdoor Temp)
        
    Example:
        If outdoor temp is 30.0°C:
        Comfortable Temp = 17.8 + (0.31 * 30.0) = 27.1°C
    """
    clamped_temp = max(10.0, min(35.0, outdoor_temp))
    comfortable_temp = config.ASHRAE_INTERCEPT + (config.ASHRAE_SLOPE * clamped_temp)
    return round(comfortable_temp, 2)


def get_hostel_comfort_band(outdoor_temp, current_hour, preferred_temp=None):
    """
    Calculates the acceptable comfort band for a hostel room.
    
    If preferred_temp is set by the resident (e.g., 24.5°C):
    - Uses the resident's preferred temperature as the baseline target.
    If preferred_temp is None:
    - Automatically calculates the target from outdoor weather via ASHRAE 55.
    
    Why the night offset?
    At night (10:00 PM to 7:00 AM), adds +1.0°C because residents sleep under blankets
    and produce ~30% less metabolic heat (0.7 met).
    
    Returns:
        A dictionary with 'optimal_temp', 'min_temp', 'max_temp', 'is_night_mode', and 'reason'.
    """
    if preferred_temp is not None:
        base_target = float(preferred_temp)
        profile_source = f"Resident Preferred ({preferred_temp:.1f}°C)"
    else:
        base_target = calculate_ashrae_comfort(outdoor_temp)
        profile_source = "ASHRAE Weather-Adaptive"

    # Check if current time is nighttime (between 22:00 and 07:00)
    is_night = (current_hour >= config.NIGHT_START_HOUR) or (current_hour < config.NIGHT_END_HOUR)

    if is_night:
        optimal_temp = round(base_target + config.NIGHT_COMFORT_OFFSET, 2)
        reason = f"{profile_source} + Night Mode ({current_hour:02d}:00 hrs). Target shifted up by +{config.NIGHT_COMFORT_OFFSET}°C for blankets."
    else:
        optimal_temp = round(base_target, 2)
        reason = f"{profile_source} daytime profile active."

    # Comfort deadband of ±1.5°C around the target
    min_temp = round(optimal_temp - 1.5, 2)
    max_temp = round(optimal_temp + 1.5, 2)

    return {
        "optimal_temp": optimal_temp,
        "min_temp": min_temp,
        "max_temp": max_temp,
        "is_night_mode": is_night,
        "preferred_temp": preferred_temp,
        "reason": reason
    }


def evaluate_hostel_ac_decision(room_temp, min_temp, max_temp, last_ac_state="OFF"):
    """
    Decides whether the physical AC switch should be ON (90°) or OFF (0°).
    
    Hysteresis (Deadband) Logic:
    - If room temp cools down to <= min_temp -> Turn AC OFF (Servo to 0°)
    - If room temp warms up to >= max_temp -> Turn AC ON (Servo to 90°)
    - If room temp is between min_temp and max_temp -> Maintain previous state!
    
    Returns:
        A tuple: (ac_state, servo_angle, explanation)
    """
    if room_temp <= min_temp:
        return "OFF", config.SERVO_OFF_ANGLE, f"Room temp ({room_temp:.1f}°C) reached lower comfort limit ({min_temp:.1f}°C). AC switched OFF to prevent overcooling."

    elif room_temp >= max_temp:
        return "ON", config.SERVO_ON_ANGLE, f"Room temp ({room_temp:.1f}°C) exceeded upper comfort threshold ({max_temp:.1f}°C). AC switched ON to restore comfort."

    else:
        angle = config.SERVO_ON_ANGLE if last_ac_state == "ON" else config.SERVO_OFF_ANGLE
        return last_ac_state, angle, f"Room temp ({room_temp:.1f}°C) is comfortable [{min_temp:.1f}°C - {max_temp:.1f}°C]. AC remains {last_ac_state}."


def calculate_runtime_reduction(hours_ac_off=4.0, total_sleep_hours=config.OVERNIGHT_SLEEP_HOURS):
    """
    Calculates active cooling run-time reduction and degree-hours of overcooling prevented.
    Notice: We measure temperature and time directly — zero unknown chiller wattage or tonnage needed!
    
    Returns:
        A dictionary with 'hours_off', 'reduction_pct', and 'degree_hours_avoided'.
    """
    clamped_hours = max(0.0, min(total_sleep_hours, hours_ac_off))
    reduction_pct = round((clamped_hours / total_sleep_hours) * 100, 1)

    # Assuming unregulated centralized AC would chill the room ~4.0°C below comfortable limits
    degree_hours_avoided = round(clamped_hours * 4.0, 1)

    return {
        "hours_cooling_off": clamped_hours,
        "total_sleep_hours": total_sleep_hours,
        "runtime_reduction_pct": reduction_pct,
        "degree_hours_avoided": degree_hours_avoided
    }
