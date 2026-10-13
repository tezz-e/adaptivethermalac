"""
app.py
================================================================================
Flask REST API Server — the "middleman" between the ESP32 hardware and the
Streamlit dashboard.

What is Flask?
    Flask is a Python library that lets you create a simple web server in a few
    lines of code. A "server" is just a program that listens for incoming
    requests (like a phone waiting for calls) and sends back replies.

What is a REST API?
    REST API (Application Programming Interface) is a standard way for programs
    to talk to each other over a network using URLs. Each URL is called an
    "endpoint". Our server has 4 endpoints:

        POST /api/hostel/telemetry  <- ESP32 sends sensor data HERE every 2.5 s
        GET  /api/hostel/status     <- Dashboard READS current state from HERE
        POST /api/hostel/preference <- Dashboard sends slider value to HERE
        POST /api/hostel/override   <- Dashboard sends ON/OFF/AUTO mode to HERE

    POST = "I am sending you data"
    GET  = "Please give me data"

Data flow on each ESP32 reading:
    ESP32 --(WiFi HTTP POST)--> /api/hostel/telemetry
    --> process_incoming_reading() evaluates ASHRAE comfort model
    --> returns JSON {"ac_state": "ON", "servo_angle": 90, ...}
    --> ESP32 moves servo to the commanded angle

Two background threads (always running in parallel with the server):
    1. udp_discovery_worker   — helps ESP32 auto-find the laptop IP on the hotspot
    2. usb_serial_bridge_worker — reads USB Serial data if ESP32 is plugged in by cable

================================================================================
"""

import json       # json.loads() parses a JSON string into a Python dict
import socket     # socket lets Python send/receive low-level network packets (UDP)
import threading  # threading.Thread lets Python run two functions at the same time
import time       # time.time() and time.strftime() for timestamps
from flask import Flask, request, jsonify
# Flask     - the web framework class (creates the server app)
# request   - gives access to the data sent in an incoming HTTP request
# jsonify   - converts a Python dict into a properly formatted JSON HTTP response

import config
import weather_service
import comfort_model
import storage

# Create the Flask application object. __name__ tells Flask the name of this file.
app = Flask(__name__)

# ---------------------------------------------------------------------------
# Shared state dictionary
# ---------------------------------------------------------------------------
# This dict is the "live memory" of the system — it holds the most recent
# sensor reading, AC decision, and control settings. It is a module-level
# (global) variable so that ALL functions in this file can read and update it.
#
# Why global? Because Flask processes each HTTP request in its own function
# call. Without a shared dict at the top level, each request would start with
# a blank slate and know nothing about the previous reading.
#
# Think of it like a shared whiteboard in a room that everyone can read/write.
# ---------------------------------------------------------------------------
hostel_room_state = {
    "room_id":         "HOSTEL_D_312",
    "current_temp":    25.0,      # last known room temperature from DHT11
    "current_humidity": 50.0,     # last known humidity from DHT11
    "sensor_source":   "SIMULATED",  # "LIVE_DHT11" when real data is flowing
    "servo_status":    "READY",
    "touch_override":  False,     # True when the physical touch button was pressed
    "connection_mode": "STANDBY", # "WIFI_HTTP" or "USB_SERIAL (COM12)"
    "preferred_temp":  config.DEFAULT_PREFERRED_TEMP,
    "ac_state":        "OFF",     # "ON" or "OFF" — what the servo is currently doing
    "servo_angle":     0,         # 0 = switch OFF, 90 = switch ON
    "manual_override": False,     # True when the dashboard radio button forced ON/OFF
    "override_state":  None,      # "ON", "OFF", or None (AUTO)
    "last_ping":       None       # timestamp string of the last received ESP32 reading
}

# Guard flag: ensures background threads are only started once, not on every reload
_workers_started = False

# CSV write throttle: only save to CSV at most every 2 seconds (prevents duplicate
# rows when USB Serial and WiFi HTTP both arrive almost simultaneously)
_last_csv_log_time = 0.0


# ---------------------------------------------------------------------------
# Core processing function — called by every incoming telemetry source
# ---------------------------------------------------------------------------

def process_incoming_reading(room_temp, room_humidity, sensor_source="LIVE_DHT11",
                             servo_status="READY", touch_override=False,
                             esp_ac_state=None, esp_servo_angle=None,
                             connection_mode="WIFI_HTTP"):
    """
    The central function that runs every time a new sensor reading arrives.

    Steps:
        1. Fetch outdoor weather (from 5-min cache or live API).
        2. Calculate the ASHRAE comfort band for the current hour and preference.
        3. Decide whether to turn AC ON or OFF (or keep current state).
        4. Update the shared hostel_room_state dict with the latest values.
        5. Append a row to the CSV log file (at most every 2 seconds).
        6. Return the band, decision, servo angle, and explanation to the caller.

    Override priority (highest to lowest):
        1. Physical capacitive touch button (GPIO 10) — always wins if pressed
        2. Dashboard manual override (ON/OFF radio button)
        3. Automatic ASHRAE hysteresis decision

    Parameters:
        room_temp       (float): Temperature reading from DHT11 in Celsius.
        room_humidity   (float): Humidity reading from DHT11 in percent.
        sensor_source   (str):   "LIVE_DHT11" or "SIMULATED".
        servo_status    (str):   "READY" or "ERR".
        touch_override  (bool):  True if the GPIO 10 button was pressed this cycle.
        esp_ac_state    (str):   AC state the ESP32 was using when touch was active.
        esp_servo_angle (int):   Servo angle the ESP32 was holding.
        connection_mode (str):   "WIFI_HTTP" or "USB_SERIAL (COM12)".

    Returns:
        tuple: (band_dict, ac_state_str, servo_angle_int, reason_str)
    """
    global _last_csv_log_time   # we will modify the module-level variable

    # Step 1: Get outdoor weather (uses 5-min cache in weather_service.py)
    weather = weather_service.fetch_live_weather()

    # Step 2: What hour is it locally right now? (0–23)
    current_hour = time.localtime().tm_hour

    # What is the resident's current preferred temperature?
    preferred = hostel_room_state.get("preferred_temp", config.DEFAULT_PREFERRED_TEMP)

    # Calculate the full comfort band dict from comfort_model.py
    band = comfort_model.get_hostel_comfort_band(weather["temperature_c"], current_hour, preferred_temp=preferred)

    # Remember what the previous AC state was, so hysteresis can "stay put" when inside the band
    prev_ac_state = hostel_room_state.get("ac_state", "OFF")

    # Step 3: Decide ON/OFF using the override priority chain
    if touch_override and esp_ac_state in ("ON", "OFF"):
        # Physical button was pressed — obey the ESP32's own toggle, don't override it
        ac_state    = esp_ac_state
        servo_angle = int(esp_servo_angle) if esp_servo_angle is not None else (90 if ac_state == "ON" else 0)
        reason      = f"Capacitive touch button override on GPIO 10 ({ac_state})."

    elif hostel_room_state["manual_override"] and hostel_room_state["override_state"] in ("ON", "OFF"):
        # Dashboard radio button is forcing a specific state
        ac_state    = hostel_room_state["override_state"]
        servo_angle = config.SERVO_ON_ANGLE if ac_state == "ON" else config.SERVO_OFF_ANGLE
        reason      = f"Manual override active ({ac_state})."

    else:
        # Automatic ASHRAE hysteresis — let the comfort model decide
        ac_state, servo_angle, reason = comfort_model.evaluate_hostel_ac_decision(
            room_temp=room_temp,
            min_temp=band["min_temp"],
            max_temp=band["max_temp"],
            last_ac_state=prev_ac_state
        )

    # Step 4: Update the shared state dict with the latest values
    # str(), float(), bool(), int() are explicit type conversions to prevent unexpected types
    hostel_room_state["current_temp"]    = round(float(room_temp), 1)
    hostel_room_state["current_humidity"] = round(float(room_humidity), 1)
    hostel_room_state["sensor_source"]   = str(sensor_source)
    hostel_room_state["servo_status"]    = str(servo_status)
    hostel_room_state["touch_override"]  = bool(touch_override)
    hostel_room_state["connection_mode"] = str(connection_mode)
    hostel_room_state["ac_state"]        = ac_state
    hostel_room_state["servo_angle"]     = servo_angle
    hostel_room_state["last_ping"]       = time.strftime("%Y-%m-%d %H:%M:%S")

    # Step 5: Write to CSV — but at most every 2.0 seconds to avoid duplicate rows.
    # Exception: always write immediately when the AC state changes (ON <-> OFF).
    now_ts = time.time()
    if (now_ts - _last_csv_log_time) >= 2.0 or ac_state != prev_ac_state:
        _last_csv_log_time = now_ts
        storage.save_telemetry({
            "timestamp":        hostel_room_state["last_ping"],
            "room_id":          hostel_room_state["room_id"],
            "current_temp":     hostel_room_state["current_temp"],
            "current_humidity": hostel_room_state["current_humidity"],
            "target_optimal":   band["optimal_temp"],
            "comfort_min":      band["min_temp"],
            "comfort_max":      band["max_temp"],
            "ac_state":         ac_state,
            "servo_angle":      servo_angle,
            "explanation":      reason
        })

    # Step 6: Return results to whichever endpoint called this function
    return band, ac_state, servo_angle, reason


# ---------------------------------------------------------------------------
# Background Thread 1: UDP Discovery Worker
# ---------------------------------------------------------------------------

def udp_discovery_worker():
    """
    Listens on UDP port 5001 for a broadcast message from the ESP32.

    What is UDP? A connectionless, fire-and-forget network protocol.
    The ESP32 sends "DISCOVER_HOSTEL_BACKEND" as a broadcast to the whole hotspot.
    This server hears it and replies "HOSTEL_BACKEND_OK" with the laptop's IP.
    The ESP32 then builds the Flask URL automatically, even if the hotspot assigns
    the laptop a different IP address each time.

    socket.AF_INET   = IPv4 network (the standard internet address type)
    socket.SOCK_DGRAM = UDP socket (datagram — no handshake, just send/receive)
    sock.bind(("0.0.0.0", 5001)) = listen on all network interfaces, port 5001
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)   # allow port reuse on restart
        sock.bind(("0.0.0.0", 5001))
        while True:
            try:
                data, addr = sock.recvfrom(256)   # wait for up to 256 bytes from any sender
                if "DISCOVER_HOSTEL_BACKEND" in data.decode("utf-8", errors="ignore"):
                    sock.sendto(b"HOSTEL_BACKEND_OK", addr)   # reply to the ESP32's IP
            except Exception:
                time.sleep(0.5)
    except Exception:
        pass   # if port 5001 is already in use, silently do nothing


# ---------------------------------------------------------------------------
# Background Thread 2: USB Serial Bridge Worker
# ---------------------------------------------------------------------------

def usb_serial_bridge_worker():
    """
    Reads telemetry from the ESP32-S3 over the USB cable (if plugged in).

    Why do we need this alongside WiFi?
        Sometimes the hotspot is not available or the laptop IP changes. USB Serial
        gives a reliable wired fallback that always works when the cable is connected.

    How does it work?
        The ESP32 firmware prints a specially tagged line every 2.5 seconds:
            [TELEMETRY_JSON] {"temperature": 27.4, "humidity": 63.0, ...}
        This worker reads those lines, strips the tag, parses the JSON dict,
        and calls process_incoming_reading() — exactly the same as the WiFi path.

    The pyserial library (imported as 'serial') lets Python open COM ports.
        ser.dtr = False, ser.rts = False: prevents the ESP32 from resetting when
        Python opens the port (a common gotcha with ESP32 + pyserial on Windows).

    The inner try/finally guarantees ser.close() is always called, preventing
    the COM port from being locked even if an error occurs mid-read.
    """
    while True:
        try:
            import serial                    # pyserial: read/write to COM ports
            import serial.tools.list_ports  # helper to list connected serial devices

            esp_port = None
            # Scan all COM ports to find the ESP32-S3 (vendor ID 0x303A is Espressif)
            for p in serial.tools.list_ports.comports():
                desc = (p.description or "").upper()
                if getattr(p, "vid", None) == 0x303A or p.device == "COM12" or "CP210" in desc or "CH34" in desc:
                    esp_port = p.device
                    break

            if esp_port:
                # Build the Serial object step by step so we can set dtr/rts BEFORE opening
                ser = serial.Serial()
                ser.port     = esp_port
                ser.baudrate = 115200   # must match the ESP32 firmware's Serial.begin(115200)
                ser.timeout  = 2.0     # wait up to 2 seconds for each line
                ser.dtr      = False   # prevent ESP32 from resetting when port opens
                ser.rts      = False   # same as above (RTS = request to send)
                ser.open()
                try:
                    while True:
                        raw_line = ser.readline().decode("utf-8", errors="ignore").strip()
                        if "[TELEMETRY_JSON]" in raw_line:
                            # Split on the tag and parse everything after it as JSON
                            json_str = raw_line.split("[TELEMETRY_JSON]", 1)[1].strip()
                            payload  = json.loads(json_str)   # dict from JSON string
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
                    ser.close()   # always release the COM port even if an error occurred
            else:
                time.sleep(2.5)   # no ESP32 found — wait and try again
        except Exception:
            time.sleep(2.5)       # any error (import fail, port busy) — wait and retry


# ---------------------------------------------------------------------------
# Start background threads once at import time
# ---------------------------------------------------------------------------

def start_background_workers():
    """
    Starts the two background threads exactly once.

    threading.Thread(target=func, daemon=True):
        Creates a new thread that runs 'func' in parallel with the Flask server.
        daemon=True means the thread will be killed automatically when the main
        program exits — we don't need to manually stop it with Ctrl+C.

    The _workers_started guard flag prevents this function from creating
    duplicate threads if Flask somehow calls it more than once on startup.
    """
    global _workers_started
    if not _workers_started:
        _workers_started = True
        threading.Thread(target=udp_discovery_worker,  daemon=True).start()
        threading.Thread(target=usb_serial_bridge_worker, daemon=True).start()


# Start workers immediately when this file is imported by run_system.py
start_background_workers()


# ---------------------------------------------------------------------------
# Flask API Endpoints (Routes)
# ---------------------------------------------------------------------------
# Each @app.route(...) decorator "registers" a URL with the Flask server.
# When a request arrives at that URL, Flask automatically calls the function
# directly below the decorator.
# ---------------------------------------------------------------------------

@app.route("/", methods=["GET"])
def home():
    """Health-check endpoint — confirms the server is running."""
    return jsonify({"status": "online", "project": "Hostel AC Controller"})


@app.route("/api/hostel/telemetry", methods=["POST"])
def receive_hostel_telemetry():
    """
    Endpoint that the ESP32 POSTs to every 2.5 seconds.

    request.get_json(force=True, silent=True):
        Parses the HTTP request body as JSON, even if the Content-Type header
        is not set correctly (force=True). Returns None instead of crashing if
        parsing fails (silent=True).

    Returns JSON back to the ESP32 with the commanded AC state and servo angle.
    The ESP32 reads this response and physically moves the servo.
    """
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({"status": "error", "message": "No JSON payload"}), 400  # 400 = Bad Request

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

        # jsonify() converts the Python dict into a valid JSON HTTP response
        return jsonify({
            "status":         "success",
            "ac_state":       ac_state,
            "servo_angle":    servo_angle,
            "comfort_min":    band["min_temp"],
            "comfort_max":    band["max_temp"],
            "target_optimal": band["optimal_temp"],
            "explanation":    reason
        }), 200  # 200 = OK

    except Exception as error:
        return jsonify({"status": "error", "message": str(error)}), 500  # 500 = Internal Server Error


@app.route("/api/hostel/status", methods=["GET"])
def get_hostel_status():
    """
    Endpoint the Streamlit dashboard polls every 2.5 seconds to refresh metrics.
    Returns the current room state, comfort band, and outdoor weather as JSON.
    No data is written here — it is purely a read.
    """
    weather      = weather_service.fetch_live_weather()
    current_hour = time.localtime().tm_hour
    band = comfort_model.get_hostel_comfort_band(
        weather["temperature_c"], current_hour, preferred_temp=hostel_room_state["preferred_temp"]
    )
    return jsonify({
        "room":            hostel_room_state,
        "comfort_band":    band,
        "outdoor_weather": weather
    })


@app.route("/api/hostel/preference", methods=["POST"])
def post_hostel_preference():
    """
    Receives the resident's preferred temperature from the dashboard slider.
    Immediately re-evaluates the AC state so the servo responds right away.
    """
    data = request.get_json(force=True, silent=True) or {}
    try:
        # Store the new preference (clamp is not needed here; slider enforces 16–32)
        hostel_room_state["preferred_temp"] = round(float(data.get("preferred_temp", 25.0)), 1)
        hostel_room_state["touch_override"] = False   # a new preference clears touch override

        weather = weather_service.fetch_live_weather()
        band = comfort_model.get_hostel_comfort_band(
            weather["temperature_c"], time.localtime().tm_hour, preferred_temp=hostel_room_state["preferred_temp"]
        )
        # Re-evaluate AC only if not in manual override mode
        if not hostel_room_state["manual_override"]:
            ac_state, servo_angle, _ = comfort_model.evaluate_hostel_ac_decision(
                room_temp=hostel_room_state["current_temp"],
                min_temp=band["min_temp"],
                max_temp=band["max_temp"],
                last_ac_state=hostel_room_state["ac_state"]
            )
            hostel_room_state["ac_state"]    = ac_state
            hostel_room_state["servo_angle"] = servo_angle

        return jsonify({
            "status":        "success",
            "preferred_temp": hostel_room_state["preferred_temp"],
            "ac_state":      hostel_room_state["ac_state"],
            "servo_angle":   hostel_room_state["servo_angle"]
        }), 200

    except (ValueError, TypeError) as error:
        return jsonify({"status": "error", "message": str(error)}), 400


@app.route("/api/hostel/override", methods=["POST"])
def post_hostel_override():
    """
    Receives the operating mode from the dashboard radio button.
    Mode can be "ON" (force on), "OFF" (force off), or "AUTO" (return to ASHRAE).

    When AUTO is selected, the ASHRAE hysteresis logic immediately re-evaluates
    the current room temperature and updates the servo target.
    """
    data = request.get_json(force=True, silent=True) or {}
    mode = str(data.get("mode", "AUTO")).upper()
    hostel_room_state["touch_override"] = False   # dashboard override clears touch override

    if mode in ("ON", "OFF"):
        # Force a specific state immediately
        hostel_room_state["manual_override"] = True
        hostel_room_state["override_state"]  = mode
        hostel_room_state["ac_state"]        = mode
        hostel_room_state["servo_angle"]     = config.SERVO_ON_ANGLE if mode == "ON" else config.SERVO_OFF_ANGLE

    else:
        # Return to AUTO: clear the manual override and re-evaluate
        hostel_room_state["manual_override"] = False
        hostel_room_state["override_state"]  = None
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
        hostel_room_state["ac_state"]    = ac_state
        hostel_room_state["servo_angle"] = servo_angle

    return jsonify({
        "status":          "success",
        "override_active": hostel_room_state["manual_override"],
        "ac_state":        hostel_room_state["ac_state"],
        "servo_angle":     hostel_room_state["servo_angle"]
    })


# ---------------------------------------------------------------------------
# Entry point: only runs if you execute "python app.py" directly
# (run_system.py launches app.py as a subprocess, so this block is what
#  Flask uses to actually start listening for connections)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"Starting Hostel AC API Server on http://0.0.0.0:{config.FLASK_PORT}...")
    # debug=False and use_reloader=False are important in production:
    # debug=True would show internal errors to anyone on the network (security risk)
    # use_reloader=False prevents Flask from starting a second copy of the process
    app.run(host="0.0.0.0", port=config.FLASK_PORT, debug=False, use_reloader=False)
