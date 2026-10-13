"""
comfort_model.py
================================================================================
Mathematical and decision-making logic for the Hostel AC Controller:
1. Calculates the ASHRAE Standard 55 adaptive comfort temperature.
2. Applies the nighttime sleep offset (+1.0°C for blankets & lower 0.7 met).
3. Evaluates thermostat hysteresis logic (±1.5°C deadband) to decide whether
   the physical AC switch should be ON (90°) or OFF (0°).
4. Calculates overnight active cooling run-time reduction and overcooling avoided.
================================================================================
"""

import config


def calculate_ashrae_comfort(outdoor_temp):
    """
    Calculates indoor comfortable temperature using the ASHRAE 55 linear equation:
        Comfortable Temp = 17.8 + (0.31 * Outdoor Temp)
    """
    clamped_temp = max(10.0, min(35.0, outdoor_temp))
    comfortable_temp = config.ASHRAE_INTERCEPT + (config.ASHRAE_SLOPE * clamped_temp)
    return round(comfortable_temp, 2)


def get_hostel_comfort_band(outdoor_temp, current_hour, preferred_temp=None):
    """
    Returns the target setpoint and ±1.5°C comfort band for the hostel room.
    Adds +1.0°C overnight (22:00 to 07:00) to account for blankets and sleep metabolism.
    """
    if preferred_temp is not None:
        base_target = float(preferred_temp)
        profile_source = f"Resident Preferred ({preferred_temp:.1f}°C)"
    else:
        base_target = calculate_ashrae_comfort(outdoor_temp)
        profile_source = "ASHRAE Weather-Adaptive"

    is_night = (current_hour >= config.NIGHT_START_HOUR) or (current_hour < config.NIGHT_END_HOUR)

    if is_night:
        optimal_temp = round(base_target + config.NIGHT_COMFORT_OFFSET, 2)
        reason = f"{profile_source} + Night Mode (+{config.NIGHT_COMFORT_OFFSET}°C sleep offset)."
    else:
        optimal_temp = round(base_target, 2)
        reason = f"{profile_source} daytime profile."

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
    Hysteresis (Deadband) Controller:
    - Room cools to <= min_temp -> Turn AC OFF (Servo 0°)
    - Room warms to >= max_temp -> Turn AC ON (Servo 90°)
    - Inside [min_temp, max_temp] -> Keep previous state to prevent rapid toggling.
    """
    if room_temp <= min_temp:
        return (
            "OFF",
            config.SERVO_OFF_ANGLE,
            f"Room temp ({room_temp:.1f}°C) reached lower limit ({min_temp:.1f}°C). AC switched OFF."
        )
    elif room_temp >= max_temp:
        return (
            "ON",
            config.SERVO_ON_ANGLE,
            f"Room temp ({room_temp:.1f}°C) reached upper limit ({max_temp:.1f}°C). AC switched ON."
        )
    else:
        angle = config.SERVO_ON_ANGLE if last_ac_state == "ON" else config.SERVO_OFF_ANGLE
        return (
            last_ac_state,
            angle,
            f"Room temp ({room_temp:.1f}°C) is inside comfort band [{min_temp:.1f} – {max_temp:.1f}°C]. AC stays {last_ac_state}."
        )


def calculate_runtime_reduction(hours_ac_off=4.0, total_sleep_hours=config.OVERNIGHT_SLEEP_HOURS):
    """
    Calculates active cooling run-time reduction (%) and degree-hours of overcooling avoided.
    """
    clamped_hours = max(0.0, min(total_sleep_hours, hours_ac_off))
    reduction_pct = round((clamped_hours / total_sleep_hours) * 100, 1)
    degree_hours_avoided = round(clamped_hours * 4.0, 1)

    return {
        "hours_cooling_off": clamped_hours,
        "total_sleep_hours": total_sleep_hours,
        "runtime_reduction_pct": reduction_pct,
        "degree_hours_avoided": degree_hours_avoided
    }
