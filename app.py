"""
app.py
================================================================================
Flask REST API Server for the Hostel AC Adaptive Thermal Comfort System.
Acts as the communication bridge between the physical ESP32 and our Python model:
1. Receives DHT11 temperature & humidity from ESP32 over WiFi.
2. Evaluates ASHRAE comfort model and thermostat hysteresis.
3. Returns JSON command to actuate the SG90 servo motor (0° OFF / 90° ON).
================================================================================
"""

import time
from flask import Flask, request, jsonify
import config
import weather_service
import comfort_model
import storage

app = Flask(__name__)

# State dictionary tracking current hostel unit state
hostel_room_state = {
    "room_id": "HOSTEL_D_312",
    "name": "Hostel D - Room 312",
    "current_temp": 25.0,
    "current_humidity": 50.0,
    "preferred_temp": config.DEFAULT_PREFERRED_TEMP,
    "ac_state": "OFF",
    "servo_angle": 0,
    "manual_override": False,
    "override_state": None,
    "last_ping": None
}


@app.route("/", methods=["GET"])
def home():
    """Root endpoint confirming API is running."""
    return jsonify({
        "project": "Hostel Adaptive Thermal Comfort AC Control System",
        "status": "Online and operational",
        "campus": config.CAMPUS_NAME
    })


@app.route("/api/health", methods=["GET"])
def health_check():
    """Health check endpoint for connection verification."""
    return jsonify({
        "status": "ok",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    })


@app.route("/api/hostel/telemetry", methods=["POST"])
def receive_hostel_telemetry():
    """
    Main communication endpoint for the ESP32 microcontroller.
    Receives JSON: {"temperature": 23.4, "humidity": 55.0}
    Returns JSON: {"ac_state": "OFF", "servo_angle": 0, ...}
    """
    try:
        incoming_data = request.get_json(force=True, silent=True)
        if not incoming_data:
            return jsonify({"status": "error", "message": "No JSON data received"}), 400

        room_temp = float(incoming_data.get("temperature", 25.0))
        room_humidity = float(incoming_data.get("humidity", 50.0))

        # 1. Fetch live outdoor weather and hour
        weather = weather_service.fetch_live_weather()
        current_hour = time.localtime().tm_hour

        # 2. Compute adaptive comfort band with resident preferred setpoint & sleep offset
        preferred = hostel_room_state.get("preferred_temp", config.DEFAULT_PREFERRED_TEMP)
        band = comfort_model.get_hostel_comfort_band(weather["temperature_c"], current_hour, preferred_temp=preferred)

        # 3. Determine AC state and servo angle
        if hostel_room_state["manual_override"] and hostel_room_state["override_state"] in ("ON", "OFF"):
            ac_state = hostel_room_state["override_state"]
            servo_angle = config.SERVO_ON_ANGLE if ac_state == "ON" else config.SERVO_OFF_ANGLE
            reason = f"Manual override active ({ac_state})."
        else:
            ac_state, servo_angle, reason = comfort_model.evaluate_hostel_ac_decision(
                room_temp=room_temp,
                min_temp=band["min_temp"],
                max_temp=band["max_temp"],
                last_ac_state=hostel_room_state["ac_state"]
            )

        # 4. Update in-memory state dictionary
        hostel_room_state["current_temp"] = room_temp
        hostel_room_state["current_humidity"] = room_humidity
        hostel_room_state["ac_state"] = ac_state
        hostel_room_state["servo_angle"] = servo_angle
        hostel_room_state["last_ping"] = time.strftime("%Y-%m-%d %H:%M:%S")

        # 5. Append entry to CSV telemetry file
        log_record = {
            "timestamp": hostel_room_state["last_ping"],
            "room_id": hostel_room_state["room_id"],
            "current_temp": room_temp,
            "current_humidity": room_humidity,
            "target_optimal": band["optimal_temp"],
            "comfort_min": band["min_temp"],
            "comfort_max": band["max_temp"],
            "ac_state": ac_state,
            "servo_angle": servo_angle,
            "explanation": reason
        }
        storage.save_telemetry(log_record)

        # 6. Respond to ESP32
        return jsonify({
            "status": "success",
            "ac_state": ac_state,
            "servo_angle": servo_angle,
            "current_temp": room_temp,
            "comfort_min": band["min_temp"],
            "comfort_max": band["max_temp"],
            "target_optimal": band["optimal_temp"],
            "is_night_mode": band["is_night_mode"],
            "explanation": reason,
            "timestamp": hostel_room_state["last_ping"]
        }), 200

    except Exception as error:
        return jsonify({"status": "error", "message": str(error)}), 500


@app.route("/api/weather", methods=["GET"])
def get_weather():
    """Returns live campus weather dictionary."""
    weather = weather_service.fetch_live_weather()
    return jsonify(weather)


@app.route("/api/hostel/status", methods=["GET"])
def get_hostel_status():
    """Returns current hostel room status and comfort band."""
    weather = weather_service.fetch_live_weather()
    current_hour = time.localtime().tm_hour
    preferred = hostel_room_state.get("preferred_temp", config.DEFAULT_PREFERRED_TEMP)
    band = comfort_model.get_hostel_comfort_band(weather["temperature_c"], current_hour, preferred_temp=preferred)

    return jsonify({
        "room": hostel_room_state,
        "comfort_band": band,
        "outdoor_weather": weather
    })


@app.route("/api/hostel/preference", methods=["POST"])
def post_hostel_preference():
    """Allows resident to set their preferred target temperature."""
    data = request.get_json(force=True, silent=True) or {}
    try:
        new_temp = float(data.get("preferred_temp", 25.0))
        hostel_room_state["preferred_temp"] = round(new_temp, 1)
        return jsonify({
            "status": "success",
            "message": f"Resident preferred temperature set to {new_temp:.1f}°C",
            "preferred_temp": hostel_room_state["preferred_temp"]
        }), 200
    except (ValueError, TypeError) as error:
        return jsonify({"status": "error", "message": str(error)}), 400


@app.route("/api/hostel/override", methods=["POST"])
def post_hostel_override():
    """Sets manual override ('ON', 'OFF', or 'AUTO')."""
    data = request.get_json(force=True, silent=True) or {}
    mode = data.get("mode", "AUTO").upper()

    if mode in ("ON", "OFF"):
        hostel_room_state["manual_override"] = True
        hostel_room_state["override_state"] = mode
        hostel_room_state["ac_state"] = mode
        hostel_room_state["servo_angle"] = config.SERVO_ON_ANGLE if mode == "ON" else config.SERVO_OFF_ANGLE
        msg = f"Manual override set to {mode}"
    else:
        hostel_room_state["manual_override"] = False
        hostel_room_state["override_state"] = None
        msg = "Returned to Automatic ASHRAE Comfort Control"

    return jsonify({
        "status": "success",
        "message": msg,
        "override_active": hostel_room_state["manual_override"]
    })


@app.route("/api/history", methods=["GET"])
def get_history():
    """Returns recent telemetry entries from CSV."""
    df = storage.read_telemetry_history(limit=50)
    return jsonify(df.to_dict(orient="records"))


@app.route("/api/savings", methods=["GET"])
def get_savings():
    """Returns estimated overnight run-time reduction and degree-hours prevented."""
    stats = comfort_model.calculate_runtime_reduction(hours_ac_off=4.0)
    return jsonify(stats)


if __name__ == "__main__":
    print(f"Starting Hostel AC API Server on http://127.0.0.1:{config.FLASK_PORT}...")
    app.run(host="0.0.0.0", port=config.FLASK_PORT, debug=True)
