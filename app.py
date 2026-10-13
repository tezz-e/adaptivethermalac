"""
app.py
================================================================================
Flask REST API Server for the Hostel Adaptive Thermal Comfort AC Controller.
1. Receives DHT11 temperature & humidity from the ESP32-S3 over WiFi or USB Serial.
2. Evaluates the ASHRAE 55 comfort band and hysteresis decision logic.
3. Returns JSON commands to actuate the SG90 servo motor (0° OFF / 90° ON).
4. Responds to UDP broadcast discovery on port 5001 so the ESP32 finds the laptop IP.
================================================================================
"""

import json
import socket
import threading
import time
from flask import Flask, request, jsonify

import config
import weather_service
import comfort_model
import storage

app = Flask(__name__)

# Shared state dictionary tracking live hardware telemetry and control mode
hostel_room_state = {
    "room_id": "HOSTEL_D_312",
    "current_temp": 25.0,
    "current_humidity": 50.0,
    "sensor_source": "SIMULATED",
    "servo_status": "READY",
    "touch_override": False,
    "connection_mode": "STANDBY",
    "preferred_temp": config.DEFAULT_PREFERRED_TEMP,
    "ac_state": "OFF",
    "servo_angle": 0,
    "manual_override": False,
    "override_state": None,
    "last_ping": None
}

_workers_started = False
_last_csv_log_time = 0.0


def process_incoming_reading(room_temp, room_humidity, sensor_source="LIVE_DHT11",
                             servo_status="READY", touch_override=False,
                             esp_ac_state=None, esp_servo_angle=None,
                             connection_mode="WIFI_HTTP"):
    """Updates shared room state, evaluates ASHRAE control decision, and logs to CSV."""
    global _last_csv_log_time
    weather = weather_service.fetch_live_weather()
    current_hour = time.localtime().tm_hour
    preferred = hostel_room_state.get("preferred_temp", config.DEFAULT_PREFERRED_TEMP)
    band = comfort_model.get_hostel_comfort_band(weather["temperature_c"], current_hour, preferred_temp=preferred)

    prev_ac_state = hostel_room_state.get("ac_state", "OFF")

    if touch_override and esp_ac_state in ("ON", "OFF"):
        ac_state = esp_ac_state
        servo_angle = int(esp_servo_angle) if esp_servo_angle is not None else (90 if ac_state == "ON" else 0)
        reason = f"Capacitive touch button override on GPIO 10 ({ac_state})."
    elif hostel_room_state["manual_override"] and hostel_room_state["override_state"] in ("ON", "OFF"):
        ac_state = hostel_room_state["override_state"]
        servo_angle = config.SERVO_ON_ANGLE if ac_state == "ON" else config.SERVO_OFF_ANGLE
        reason = f"Manual override active ({ac_state})."
    else:
        ac_state, servo_angle, reason = comfort_model.evaluate_hostel_ac_decision(
            room_temp=room_temp,
            min_temp=band["min_temp"],
            max_temp=band["max_temp"],
            last_ac_state=prev_ac_state
        )

    hostel_room_state["current_temp"] = round(float(room_temp), 1)
    hostel_room_state["current_humidity"] = round(float(room_humidity), 1)
    hostel_room_state["sensor_source"] = str(sensor_source)
    hostel_room_state["servo_status"] = str(servo_status)
    hostel_room_state["touch_override"] = bool(touch_override)
    hostel_room_state["connection_mode"] = str(connection_mode)
    hostel_room_state["ac_state"] = ac_state
    hostel_room_state["servo_angle"] = servo_angle
    hostel_room_state["last_ping"] = time.strftime("%Y-%m-%d %H:%M:%S")

    now_ts = time.time()
    if (now_ts - _last_csv_log_time) >= 2.0 or ac_state != prev_ac_state:
        _last_csv_log_time = now_ts
        storage.save_telemetry({
            "timestamp": hostel_room_state["last_ping"],
            "room_id": hostel_room_state["room_id"],
            "current_temp": hostel_room_state["current_temp"],
            "current_humidity": hostel_room_state["current_humidity"],
            "target_optimal": band["optimal_temp"],
            "comfort_min": band["min_temp"],
            "comfort_max": band["max_temp"],
            "ac_state": ac_state,
            "servo_angle": servo_angle,
            "explanation": reason
        })
    return band, ac_state, servo_angle, reason


def udp_discovery_worker():
    """Listens on UDP port 5001 so the ESP32 can auto-discover the laptop IP on the hotspot."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", 5001))
        while True:
            try:
                data, addr = sock.recvfrom(256)
                if "DISCOVER_HOSTEL_BACKEND" in data.decode("utf-8", errors="ignore"):
                    sock.sendto(b"HOSTEL_BACKEND_OK", addr)
            except Exception:
                time.sleep(0.5)
    except Exception:
        pass


def usb_serial_bridge_worker():
    """Reads [TELEMETRY_JSON] from the ESP32-S3 over USB Serial if plugged into the laptop."""
    while True:
        try:
            import serial
            import serial.tools.list_ports
            esp_port = None
            for p in serial.tools.list_ports.comports():
                desc = (p.description or "").upper()
                if getattr(p, "vid", None) == 0x303A or p.device == "COM12" or "CP210" in desc or "CH34" in desc:
                    esp_port = p.device
                    break

            if esp_port:
                ser = serial.Serial()
                ser.port = esp_port
                ser.baudrate = 115200
                ser.timeout = 2.0
                ser.dtr = False
                ser.rts = False
                ser.open()
                try:
                    while True:
                        raw_line = ser.readline().decode("utf-8", errors="ignore").strip()
                        if "[TELEMETRY_JSON]" in raw_line:
                            payload = json.loads(raw_line.split("[TELEMETRY_JSON]", 1)[1].strip())
                            process_incoming_reading(
                                room_temp=float(payload.get("temperature", 25.0)),
                                room_humidity=float(payload.get("humidity", 50.0)),
                                sensor_source=str(payload.get("sensor_source", "LIVE_DHT11")),
                                servo_status=str(payload.get("servo_status", "READY")),
                                touch_override=bool(payload.get("touch_override", False)),
                                esp_ac_state=str(payload.get("ac_state", "OFF")),
                                esp_servo_angle=int(payload.get("servo_angle", 0)),
                                connection_mode=f"USB_SERIAL ({esp_port})"
                            )
                finally:
                    ser.close()
            else:
                time.sleep(2.5)
        except Exception:
            time.sleep(2.5)


def start_background_workers():
    """Starts the UDP discovery and USB serial bridge background threads once."""
    global _workers_started
    if not _workers_started:
        _workers_started = True
        threading.Thread(target=udp_discovery_worker, daemon=True).start()
        threading.Thread(target=usb_serial_bridge_worker, daemon=True).start()


start_background_workers()


@app.route("/", methods=["GET"])
def home():
    """Health check endpoint."""
    return jsonify({"status": "online", "project": "Hostel AC Controller"})


@app.route("/api/hostel/telemetry", methods=["POST"])
def receive_hostel_telemetry():
    """Receives ESP32 DHT11 readings and returns target AC state and servo angle."""
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({"status": "error", "message": "No JSON payload"}), 400

        band, ac_state, servo_angle, reason = process_incoming_reading(
            room_temp=float(data.get("temperature", 25.0)),
            room_humidity=float(data.get("humidity", 50.0)),
            sensor_source=str(data.get("sensor_source", "LIVE_DHT11")),
            servo_status=str(data.get("servo_status", "READY")),
            touch_override=bool(data.get("touch_override", False)),
            esp_ac_state=data.get("ac_state"),
            esp_servo_angle=data.get("servo_angle"),
            connection_mode=str(data.get("connection_mode", "WIFI_HTTP"))
        )

        return jsonify({
            "status": "success",
            "ac_state": ac_state,
            "servo_angle": servo_angle,
            "comfort_min": band["min_temp"],
            "comfort_max": band["max_temp"],
            "target_optimal": band["optimal_temp"],
            "explanation": reason
        }), 200
    except Exception as error:
        return jsonify({"status": "error", "message": str(error)}), 500


@app.route("/api/hostel/status", methods=["GET"])
def get_hostel_status():
    """Returns current hardware state and comfort band for the Streamlit dashboard."""
    weather = weather_service.fetch_live_weather()
    current_hour = time.localtime().tm_hour
    band = comfort_model.get_hostel_comfort_band(
        weather["temperature_c"], current_hour, preferred_temp=hostel_room_state["preferred_temp"]
    )
    return jsonify({
        "room": hostel_room_state,
        "comfort_band": band,
        "outdoor_weather": weather
    })


@app.route("/api/hostel/preference", methods=["POST"])
def post_hostel_preference():
    """Updates resident preferred target temperature and immediately re-evaluates AC state."""
    data = request.get_json(force=True, silent=True) or {}
    try:
        hostel_room_state["preferred_temp"] = round(float(data.get("preferred_temp", 25.0)), 1)
        hostel_room_state["touch_override"] = False

        weather = weather_service.fetch_live_weather()
        band = comfort_model.get_hostel_comfort_band(
            weather["temperature_c"], time.localtime().tm_hour, preferred_temp=hostel_room_state["preferred_temp"]
        )
        if not hostel_room_state["manual_override"]:
            ac_state, servo_angle, _ = comfort_model.evaluate_hostel_ac_decision(
                room_temp=hostel_room_state["current_temp"],
                min_temp=band["min_temp"],
                max_temp=band["max_temp"],
                last_ac_state=hostel_room_state["ac_state"]
            )
            hostel_room_state["ac_state"] = ac_state
            hostel_room_state["servo_angle"] = servo_angle

        return jsonify({
            "status": "success",
            "preferred_temp": hostel_room_state["preferred_temp"],
            "ac_state": hostel_room_state["ac_state"],
            "servo_angle": hostel_room_state["servo_angle"]
        }), 200
    except (ValueError, TypeError) as error:
        return jsonify({"status": "error", "message": str(error)}), 400


@app.route("/api/hostel/override", methods=["POST"])
def post_hostel_override():
    """Sets operating mode ('ON', 'OFF', or 'AUTO') and immediately updates servo target."""
    data = request.get_json(force=True, silent=True) or {}
    mode = str(data.get("mode", "AUTO")).upper()
    hostel_room_state["touch_override"] = False

    if mode in ("ON", "OFF"):
        hostel_room_state["manual_override"] = True
        hostel_room_state["override_state"] = mode
        hostel_room_state["ac_state"] = mode
        hostel_room_state["servo_angle"] = config.SERVO_ON_ANGLE if mode == "ON" else config.SERVO_OFF_ANGLE
    else:
        hostel_room_state["manual_override"] = False
        hostel_room_state["override_state"] = None
        weather = weather_service.fetch_live_weather()
        band = comfort_model.get_hostel_comfort_band(
            weather["temperature_c"], time.localtime().tm_hour, preferred_temp=hostel_room_state["preferred_temp"]
        )
        ac_state, servo_angle, _ = comfort_model.evaluate_hostel_ac_decision(
            room_temp=hostel_room_state["current_temp"],
            min_temp=band["min_temp"],
            max_temp=band["max_temp"],
            last_ac_state=hostel_room_state["ac_state"]
        )
        hostel_room_state["ac_state"] = ac_state
        hostel_room_state["servo_angle"] = servo_angle

    return jsonify({
        "status": "success",
        "override_active": hostel_room_state["manual_override"],
        "ac_state": hostel_room_state["ac_state"],
        "servo_angle": hostel_room_state["servo_angle"]
    })


if __name__ == "__main__":
    print(f"Starting Hostel AC API Server on http://0.0.0.0:{config.FLASK_PORT}...")
    app.run(host="0.0.0.0", port=config.FLASK_PORT, debug=False, use_reloader=False)
