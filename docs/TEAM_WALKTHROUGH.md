# Team Walkthrough and Beginner Guide
### Adaptive Thermal Comfort AC Controller for Campus Hostels

**Target Audience:** Teammates preparing for tomorrow's project review — even if you have zero prior experience with IoT, servers, or Python.  
**Goal:** Read this once from top to bottom (about 10 minutes). By the end, you will understand how the physical hardware, the math formula, and every single Python file fit together, plus have exact word-for-word scripts for what to say to the examiner.

> **Tip for reading the code:** Every single Python file and the `.ino` firmware now has plain-English comment lines starting with `#` that explain each section in simple language. Read the comments first — the code itself will make sense right after.

---

## 1. The Big Picture: What Problem Are We Actually Solving?

Before we look at any code, think about what happens every night in a campus hostel room:
1. The hostel air conditioner has only a simple plastic **ON/OFF rocker switch** on the wall. It has **no remote control** and **no thermostat**.
2. When you go to sleep at 11:00 PM, the room is warm, so you flip the wall switch **ON**.
3. Because there is no thermostat, the AC blows cold air non-stop all night. By 3:00 AM, the room plunges to **19°C**.
4. You wake up shivering under two blankets while the AC wastes hours of cooling until morning.

### Why Hostels Instead of Classrooms? (Examiner Favorite Question!)
If an examiner asks *"Why didn't you do this for campus classrooms?"*, here is the exact engineering reason:
* Classrooms are connected to massive central chiller plants. Calculating energy there requires knowing chiller tonnage (TR), airflow (CFM), and real-time student headcounts — sensors we do not have. Guessing those numbers would be fake engineering.
* In a hostel room, we have a **physical binary switch** right on the wall. By mounting a tiny temperature sensor and a small motorized arm (servo) next to that switch, our device physically turns the AC **OFF** when the room is cool enough and **ON** when it gets warm!

---

## 2. Our Physical Hardware (Total Cost: ₹813)

Think of our hardware box like a tiny robot assistant sitting next to the wall switch:

| Part | Pin on ESP32-S3 | What It Does in Plain English |
| :--- | :---: | :--- |
| **ESP32-S3 DevKitC-1** | USB-C (`COM12`) | **The Brain:** A small WiFi + USB microcontroller board that reads the sensors and controls the motor. |
| **DHT11 Sensor** | **`GPIO 4`** | **The Thermometer:** Reads real-time room temperature (°C) and humidity (%) every 2.5 seconds. |
| **TTP223 Touch Button** | **`GPIO 10`** | **Manual Touch Button:** Tap it with your finger at any time to manually flip the AC ON or OFF. |
| **SG90 Micro Servo** | **`GPIO 18`** | **The Mechanical Finger:** Moves to **`0°`** to push the AC switch **OFF**, or **`90°`** to push the AC switch **ON**. Powered by an external 5V adapter (with shared ground) so it has strong torque. |
| **1.3" SH1106 OLED** | **`GPIO 8` (SDA), `GPIO 9` (SCL)** | **The Mini Screen:** Shows live room temperature, target temperature, `DHT:LIVE`, and `SRV:RDY` / `SRV:ON`. |

---

## 3. What is ASHRAE Standard 55, and Why Do We Use It?

* **What does ASHRAE stand for?**  
  **A**merican **S**ociety of **H**eating, **R**efrigerating and **A**ir-Conditioning **E**ngineers. They are the global scientific body that writes the official indoor comfort rules (`ASHRAE Standard 55`) for buildings worldwide.
* **The Adaptive Comfort Formula:**  
  Instead of picking a random fixed number like 22°C, ASHRAE proved that the comfortable indoor temperature depends on how hot it is outside:
  $$\text{Comfortable Indoor Temp} = 17.8 + (0.31 \times \text{Outdoor Temp})$$
  For example, when Katpadi is **34.0°C** outside, the formula gives $17.8 + (0.31 \times 34.0) = 28.3^\circ\text{C}$ as the natural baseline, or residents can slide their own **Preferred Target Temperature (`16.0°C – 32.0°C`)** on the dashboard.
* **Why do we add $+1.0^\circ\text{C}$ at night (10:00 PM – 7:00 AM)?**  
  When you sleep, your body's heat production (metabolic rate) drops by 30% (from `1.0 met` to `0.7 met`), and you sleep under a blanket (`1.2–1.5 clo` insulation). Adding $+1.0^\circ\text{C}$ overnight prevents you from waking up freezing.
* **What is Hysteresis ($\pm 1.5^\circ\text{C}$ Deadband)?**  
  If the target is **25.0°C**, we create a comfort buffer from **23.5°C to 26.5°C**:
  - When the room cools down to **$\le 23.5^\circ\text{C}$** $\rightarrow$ Turn AC **OFF (`0°`)**.
  - When the room warms up to **$\ge 26.5^\circ\text{C}$** $\rightarrow$ Turn AC **ON (`90°`)**.
  - Anywhere in between (`23.5°C – 26.5°C`) $\rightarrow$ **Keep the current state!** This prevents the motor from clicking back and forth every 10 seconds ("switch chatter").

---

## 4. File-by-File Guide (Every File Explained Simply)

We wrote the entire Python project using **only basic first-year Python** (`def` functions, `{}` dictionaries, `if/elif/else`, `try/except`, and `with open` for CSV files — **zero classes or OOP**).

> Every file has detailed `#` comments explaining each line. Open the file and read the comments alongside this guide.

---

### File 1: `config.py` (The Settings File)

**One job:** Store all the "magic numbers" in one place so nothing is hardcoded across the project. If you want to change a pin or temperature range, you only edit this file.

Key constants and what they mean:
* `CAMPUS_LATITUDE = 12.9692`, `CAMPUS_LONGITUDE = 79.1559` — GPS location of Katpadi, Vellore (used to fetch outdoor weather)
* `ASHRAE_INTERCEPT = 17.8`, `ASHRAE_SLOPE = 0.31` — the two numbers in the ASHRAE formula
* `NIGHT_START_HOUR = 22`, `NIGHT_END_HOUR = 7`, `NIGHT_COMFORT_OFFSET = 1.0` — night mode triggers between 10 PM and 7 AM, raising target by 1°C
* `SERVO_OFF_ANGLE = 0`, `SERVO_ON_ANGLE = 90` — the servo rotates to these angles to push the physical switch
* `DEFAULT_PREFERRED_TEMP = 25.0` — the slider starting value on the dashboard
* `CSV_FILE_PATH = "data/hostel_telemetry.csv"` — where all sensor readings are saved

**Python concept demonstrated:** Module-level constants (variables defined at the top of a file that other files can import and use).

---

### File 2: `weather_service.py` (Live Outdoor Weather)

**One job:** Fetch the real-time outdoor temperature and humidity for Katpadi, Vellore and return it as a Python dict.

How it works:
1. **Primary API:** `wttr.in/Katpadi,Vellore` — the same local weather station data Google Weather uses. `requests.get(url)` works exactly like typing a URL into a browser.
2. **Fallback API:** Open-Meteo using GPS coordinates from `config.py` — used if `wttr.in` is down.
3. **Offline backup:** Returns `34.0°C, 45% RH` if both APIs fail (e.g., hotspot has no internet).
4. **5-minute cache:** Saves the last result in a module-level variable (`cached_weather`). The next call within 5 minutes returns the cached value instantly without making a new network request. The `global` keyword tells Python we want to modify the module-level variable, not create a local one.

**Python concepts demonstrated:** `requests` library, `try/except` error handling, `global` variables, module-level variables as a simple cache.

---

### File 3: `comfort_model.py` (The Math and Decision Brain)

**One job:** Four pure functions that do all the temperature maths and the ON/OFF control decision.

The four functions:

**`calculate_ashrae_comfort(outdoor_temp)`**
Runs `17.8 + (0.31 * outdoor_temp)`.
The input is "clamped" to the range 10–35°C using `max(10, min(35, x))` — a Python idiom that prevents the formula from giving nonsense results for extreme temperatures outside ASHRAE's studied range.

**`get_hostel_comfort_band(outdoor_temp, current_hour, preferred_temp)`**
Wraps the ASHRAE result into a ±1.5°C band. If it is nighttime (`current_hour >= 22 or current_hour < 7`), it adds +1.0°C. Returns a dict with `optimal_temp`, `min_temp`, `max_temp`, `is_night_mode`, and `reason`.

**`evaluate_hostel_ac_decision(room_temp, min_temp, max_temp, last_ac_state)`**
The hysteresis controller. Uses `if / elif / else`:
- `room_temp <= min_temp` → return `("OFF", 0, "explanation...")`
- `room_temp >= max_temp` → return `("ON", 90, "explanation...")`
- Otherwise → return `(last_ac_state, angle, "explanation...")`

Notice the **3-item tuple** return — this is a key Python concept. The caller unpacks it with `ac_state, servo_angle, reason = evaluate_hostel_ac_decision(...)`.

**`calculate_runtime_reduction(hours_ac_off)`**
Simple percentage calculation for Tab 2 of the dashboard: `(hours_off / 8.0) * 100`.

**Python concepts demonstrated:** Pure functions, tuples as multi-value returns, dict return values, `max/min` clamping, boolean expressions for time-of-day check.

---

### File 4: `storage.py` (CSV File Handling)

**One job:** Save each sensor reading as a new row in a CSV spreadsheet, and read that spreadsheet back for the graph and download button.

Key points:
- `ensure_csv_exists()` — creates the `data/` folder and writes the column header row the first time. Uses `os.makedirs("data", exist_ok=True)` so it does not crash if the folder already exists.
- `save_telemetry(record_dict)` — opens the CSV in `mode="a"` (append — adds to the end without deleting). Uses `dict.get(key, default)` to safely read values from the dict without crashing if a key is missing.
- `read_telemetry_history(limit)` — reads the CSV with `pandas.read_csv()` and returns a DataFrame (think of it as a Python object that looks like a spreadsheet). `pd.to_datetime()` converts timestamp strings into real datetime objects for plotting.

**Python concepts demonstrated:** `with open(...)` context manager, `mode="a"` vs `mode="w"`, `csv.writer`, `dict.get(key, default)`, `try/except` for file errors.

---

### File 5: `app.py` (The Flask Communication Server — Port 5000)

**One job:** Be the middleman between the ESP32 hardware and the Streamlit dashboard. Receives sensor data, runs the comfort model, commands the servo, and stores logs.

**What is Flask?** Flask is a Python library that creates a simple web server in a few lines. A web server listens for incoming HTTP requests (like a phone waiting for calls) and sends back replies.

The server has 4 endpoints (URLs it listens on):

| URL | Method | Who calls it | What it does |
|-----|--------|-------------|--------------|
| `/api/hostel/telemetry` | POST | ESP32 (every 2.5s) | Receives temp/humidity, runs ASHRAE model, returns `{"ac_state": "ON", "servo_angle": 90}` |
| `/api/hostel/status` | GET | Dashboard (every 2.5s) | Returns current room state for the metric cards |
| `/api/hostel/preference` | POST | Dashboard slider | Updates preferred target temp, re-evaluates AC |
| `/api/hostel/override` | POST | Dashboard radio | Forces ON / OFF / AUTO mode |

The `@app.route("/api/hostel/telemetry", methods=["POST"])` decorator above each function "registers" that URL with Flask. When a request arrives, Flask automatically calls that function.

**`hostel_room_state` dict** — a module-level (global) dict that all functions share. It is the "live memory" of the system — the most recent temperature, AC state, servo angle, etc. It is global because Flask processes each HTTP request in a separate function call, so without a shared top-level dict, each request would know nothing about the previous one.

**Two background threads** (run in parallel using `threading.Thread(daemon=True)`):
- `udp_discovery_worker` — listens on UDP port 5001 for the ESP32's broadcast, replies with the laptop IP so the board finds the server even if the hotspot changes the laptop's IP
- `usb_serial_bridge_worker` — reads USB Serial if the ESP32 is plugged in by cable; parses `[TELEMETRY_JSON]` lines printed by the firmware and feeds them into the same `process_incoming_reading()` function as WiFi

**Python concepts demonstrated:** Flask framework, `@app.route` decorator, `request.get_json()`, `jsonify()`, `global` dict as shared state, `threading.Thread(daemon=True)`, `socket` for UDP, `try/except` everywhere, `pyserial` for COM port reading.

---

### File 6: `dashboard.py` (The Streamlit Web Dashboard — Port 8501)

**One job:** Show a live browser dashboard that your team and the examiner can interact with.

**What is Streamlit?** Streamlit is a Python library that turns a regular Python script into a live web page. Every time you interact (drag a slider, click a radio button), Streamlit re-runs the script from top to bottom and updates the page. You do not write HTML — you call Python functions like `st.metric()`, `st.slider()`.

Structure:
- **`st.session_state`** — a dict that persists between re-runs in the same browser session. Used to remember the last slider value sent to Flask, so we don't spam the API on every re-run.
- **`sync_from_flask_backend()`** — called on each page load. Does a quick `requests.get` to Flask to refresh the room state. `timeout=0.35s` so it never blocks the page.
- **Two `@st.fragment` sections** — fragments refresh independently on a timer without re-running the whole page (prevents full-page flicker):
  - `render_live_metrics()` — refreshes every 2.5s (the 4 metric cards)
  - `render_live_chart()` — refreshes every 6s (the Plotly temperature graph)
- **Adaptive chart** — `prepare_adaptive_trend_dataframe()` auto-scales the chart: raw readings for the first 90 seconds, then 10s buckets, 30s buckets, 2m buckets as the session runs longer. Uses pandas `.resample()` to average readings into time buckets.

**Python concepts demonstrated:** Streamlit library, `st.session_state`, `@st.fragment`, `st.metric`, `st.slider`, `st.radio`, `st.tabs`, Plotly `go.Figure()` and `go.Scatter()`, `pd.to_datetime`, `df.resample()`.

---

### File 7: `run_system.py` (The One-Command Launcher)

**One job:** Start both Flask and Streamlit with a single command (`py run_system.py`).

Uses `subprocess.Popen()` to launch each server as a separate OS process — like opening two terminal windows simultaneously. `sys.executable` ensures the same Python interpreter (and virtual environment) is used for both. A `while True: time.sleep(1)` loop keeps the launcher alive. Pressing Ctrl+C triggers `KeyboardInterrupt`, which calls `proc.terminate()` on both child processes to shut them down cleanly.

**Python concepts demonstrated:** `subprocess.Popen`, `sys.executable`, `while True` loop, `KeyboardInterrupt` exception, list of processes.

---

### File 8: `hardware/hostel_ac_controller/hostel_ac_controller.ino` (The ESP32 Firmware)

> **Read the top of this file first** — there is a large comment block titled "NOTE FOR PYTHON STUDENTS" that explains everything below in plain English before you see any C++ code.

This file is **not Python**. It is C++ using the Arduino framework and runs directly **on the ESP32-S3 chip** — not on the laptop. You upload it using the Arduino IDE.

Key points explained in the file's header:
- Every C++ statement ends with a semicolon `;`
- Variable types must be declared: `int`, `float`, `bool`, `String`
- `void setup()` runs **once** on power-on (initialise WiFi, sensors, servo, OLED)
- `void loop()` runs **forever** in an infinite loop (~60 times per second) — equivalent to Python's `while True:`
- Each `#include <Library.h>` is like Python's `import` — `WiFi.h` for networking, `DHT.h` for the sensor, `ArduinoJson.h` like Python's `json`, `HTTPClient.h` like Python's `requests`

What the firmware does every 2.5 seconds in `loop()`:
1. Read DHT11 temperature and humidity from GPIO 4
2. Print a `[TELEMETRY_JSON]` line over USB Serial (picked up by `usb_serial_bridge_worker` in `app.py`)
3. POST the same data to Flask over WiFi HTTP
4. Receive `{"ac_state": "ON", "servo_angle": 90}` back from Flask
5. Move the servo to the commanded angle
6. Update the OLED display

---

## 5. How All the Files Connect (Data Flow)

```
DHT11 (GPIO 4) reads temp/humidity every 2.5s
         |
    ESP32-S3 firmware (hostel_ac_controller.ino)
         |
    Two parallel paths:
    |                           |
WiFi HTTP POST              USB Serial [TELEMETRY_JSON] line
to Flask port 5000          read by usb_serial_bridge_worker
         |                           |
         +---------> app.py: process_incoming_reading()
                          |
                  weather_service.py (outdoor temp, 5-min cache)
                          |
                  comfort_model.py (ASHRAE band + hysteresis)
                          |
                  storage.py (append row to CSV)
                          |
                  returns {"ac_state": "ON", "servo_angle": 90}
                          |
                    ESP32 moves servo arm
                          |
                 Physical AC switch flips ON/OFF

dashboard.py (port 8501)
  --> every 2.5s: GET /api/hostel/status from Flask
  --> renders st.metric cards, Plotly chart, slider, radio
  --> slider POST --> /api/hostel/preference --> app.py re-evaluates
  --> radio  POST --> /api/hostel/override   --> app.py forces ON/OFF/AUTO
```

---

## 6. Word-for-Word Speaking Scripts for Tomorrow's Review

Split these 5 roles among your team so everyone has a clear 45-second explanation ready:

### Speaker 1: Problem Statement & Comfort Math (`comfort_model.py`)
> *"Our project solves overnight overcooling in hostel rooms, where ACs only have a binary ON/OFF wall switch and no thermostat. In `comfort_model.py`, I implemented the ASHRAE Standard 55 Adaptive Comfort formula (`17.8 + 0.31 * outdoor_temp`), a `+1.0°C` nighttime sleep offset for blanket insulation and lower sleep metabolism (`0.7 met`), and a `±1.5°C` hysteresis deadband so the servo motor only flips the switch when crossing the lower or upper comfort limits."*

### Speaker 2: Live Weather Pipeline & Error Handling (`weather_service.py` & `config.py`)
> *"I built `weather_service.py` and `config.py`. Using Python's `requests` library, our code fetches live outdoor temperature and humidity for Katpadi, Vellore from the `wttr.in` local weather station — the same source Google Weather uses for our area. Because outdoor weather changes slowly, we cache the reading in memory for 5 minutes so the server responds in milliseconds. We also wrapped every network call in a `try/except` block so if the hotspot loses internet, it seamlessly uses backup values without crashing."*

### Speaker 3: Overnight Run-Time Analytics (`comfort_model.py` & `dashboard.py`)
> *"I worked on the thermal run-time analytics in `calculate_runtime_reduction()` and Tab 2 of the dashboard. Because hostel cooling comes from a centralized plant where chiller wattage isn't accessible to students, we don't guess fake kW numbers. Instead, we measure indoor temperature and time directly: turning the switch off for 4 out of 8 sleep hours cuts active cooling run-time by 50% and prevents 16 degree-hours of freezing overcooling overnight."*

### Speaker 4: Hardware, ESP32-S3 Firmware & Flask Server (`app.py` & `hostel_ac_controller.ino`)
> *"I integrated the physical ESP32-S3 hardware with our Flask server. The firmware in `hostel_ac_controller.ino` — written in C++, not Python — reads the DHT11 sensor on GPIO 4, drives the SG90 servo on GPIO 18 between 0 and 90 degrees, shows live status on the OLED on GPIO 8 and 9, and supports manual touch toggling on GPIO 10. It sends telemetry every 2.5 seconds over both WiFi HTTP and USB Serial. `app.py` receives this data, runs the comfort model, and replies with the servo command."*

### Speaker 5: CSV Storage, Dashboard & Offline Failsafe (`storage.py` & `dashboard.py`)
> *"I built the CSV storage module using Python's `with open` context manager to log every reading to `hostel_telemetry.csv`, and the Streamlit dashboard with an auto-scaling Plotly comfort graph. The graph automatically switches from raw 2.5-second readings to 10-second, 30-second, and 2-minute averages as the session runs longer — using pandas `resample()`. I also verified the ESP32's offline failsafe: if WiFi disconnects while residents are asleep, the board automatically runs its own local hysteresis loop using the last comfort band values received from Flask."*
