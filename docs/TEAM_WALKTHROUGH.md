# Team Walkthrough and Beginner Guide
### Adaptive Thermal Comfort AC Controller for Campus Hostels

**Target Audience:** Teammates preparing for tomorrow's project review — even if you have zero prior experience with IoT, servers, or Python.  
**Goal:** Read this once from top to bottom (about 8 minutes). By the end, you will understand how the physical hardware, the math formula, and every single Python file fit together, plus have exact word-for-word scripts for what to say to the examiner.

> **Tip for reading the code:** Every single Python file now has plain-English comment lines starting with `#` that explain each section in simple language. Read the comments first — the code itself will make sense right after.

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

  ```text
  Comfortable Indoor Temp = 17.8 + (0.31 * Outdoor Temp)
  ```

  For example, when Katpadi is **34.0°C** outside, the formula gives `17.8 + (0.31 * 34.0) = 28.3°C` as the natural baseline, or residents can slide their own **Preferred Target Temperature (`16.0°C to 32.0°C`)** on the dashboard.

* **Why do we add `+1.0°C` at night (10:00 PM – 7:00 AM)?**  
  When you sleep, your body's heat production (metabolic rate) drops by 30% (from `1.0 met` awake to `0.7 met` sleeping), and you sleep under a blanket (`1.2 to 1.5 clo` insulation). Adding `+1.0°C` overnight prevents you from waking up freezing.

* **What is Hysteresis (`±1.5°C` Deadband)?**  
  If the target is **25.0°C**, we create a comfort buffer from **23.5°C to 26.5°C**:
  - When the room cools down to **23.5°C or below** → Turn AC **OFF (`0°`)**.
  - When the room warms up to **26.5°C or above** → Turn AC **ON (`90°`)**.
  - Anywhere in between (**23.5°C to 26.5°C**) → **Keep the current state!** This prevents the motor from clicking back and forth every 10 seconds ("switch chatter").

---

## 4. File-by-File Guide (Every File Explained Simply)

We wrote the entire Python project using **only basic first-year Python** (`def` functions, `{}` dictionaries, `[]` lists, `()` tuples, `if/elif/else`, `try/except`, and `with open` for CSV files — **zero classes or OOP**).

### File 1: `config.py` (The Settings File)
**One job:** Store all fixed numbers in one place so nothing is hardcoded across the project.
* `CAMPUS_LATITUDE = 12.9692`, `CAMPUS_LONGITUDE = 79.1559` (Katpadi, Vellore)
* `ASHRAE_INTERCEPT = 17.8`, `ASHRAE_SLOPE = 0.31`
* `NIGHT_START_HOUR = 22` (10 PM), `NIGHT_END_HOUR = 7` (7 AM), `NIGHT_COMFORT_OFFSET = 1.0`
* `SERVO_OFF_ANGLE = 0`, `SERVO_ON_ANGLE = 90`
* `DEFAULT_PREFERRED_TEMP = 25.0`
* `CSV_FILE_PATH = "data/hostel_telemetry.csv"`

### File 2: `weather_service.py` (Live Outdoor Weather)
**One job:** Fetch the real-time outdoor temperature and humidity for Katpadi, Vellore and return it as a Python dictionary.
* **Primary API:** Queries the live Katpadi weather station (`wttr.in/Katpadi,Vellore?format=j1`, which matches Google Weather) using `requests.get()`.
* **Fallback API:** Uses `Open-Meteo` GPS coordinates if the primary link is busy.
* **5-Minute Cache:** Saves the last weather reading in memory for 300 seconds (`5 minutes`) so the dashboard refreshes instantly without spamming the internet.
* **Offline Backup (`try/except`):** If the mobile hotspot has no internet, it safely returns `34.0°C, 45% RH` so the program never crashes.

### File 3: `comfort_model.py` (The Math and Decision Brain)
**One job:** Four simple functions that do all the temperature math and the ON/OFF decision:
1. `calculate_ashrae_comfort(outdoor_temp)`: Runs `17.8 + (0.31 * outdoor_temp)`.
2. `get_hostel_comfort_band(outdoor_temp, current_hour, preferred_temp)`: Adds `+1.0°C` if it is nighttime (`22:00 to 07:00`) and returns a dictionary with `optimal_temp`, `min_temp` (`-1.5°C`), and `max_temp` (`+1.5°C`).
3. `evaluate_hostel_ac_decision(room_temp, min_temp, max_temp, last_ac_state)`: Runs the `if / elif / else` hysteresis check and returns a 3-item tuple: `(ac_state, servo_angle, explanation)`.
4. `calculate_runtime_reduction(hours_ac_off)`: Calculates the percentage of overnight cooling time saved (`(hours_off / 8.0) * 100`) and degree-hours of overcooling prevented.

### File 4: `storage.py` (CSV File Handling)
**One job:** Save each sensor reading as a new row in a CSV spreadsheet, and read that spreadsheet back for the graph and download button.
* `save_telemetry(record_dict)`: Uses `with open("data/hostel_telemetry.csv", mode="a")` and `csv.writer` to append each reading to the end of the file without erasing old rows.
* `read_telemetry_history(limit)`: Reads the CSV file using `pandas.read_csv()` so the dashboard can plot the temperature graph and let you download the CSV file.

### File 5: `app.py` (The Flask Communication Server — Port 5000)
**One job:** Act as the middleman between the ESP32 hardware and the Streamlit dashboard.
* **What is Flask?** A lightweight Python web server that listens for incoming messages on port `5000`.
* **4 Simple Routes:**
  1. `POST /api/hostel/telemetry` — ESP32 sends live DHT11 temperature & humidity here every 2.5 seconds; `app.py` runs `comfort_model.py` and replies with `{"ac_state": "ON", "servo_angle": 90}`.
  2. `GET /api/hostel/status` — Dashboard reads the current room state from here every 2.5 seconds.
  3. `POST /api/hostel/preference` — Dashboard sends the slider temperature (`16°C–32°C`) here.
  4. `POST /api/hostel/override` — Dashboard sends the operating mode (`AUTO`, `ON`, or `OFF`) here.
* **Dual Hardware Link:** Works over **WiFi HTTP** (with automatic UDP discovery on port `5001` so the ESP32 finds the laptop IP automatically) and also listens on **USB Serial (`COM12`)** if the board is plugged into the laptop.

### File 6: `dashboard.py` (The Live Streamlit Web Dashboard — Port 8501)
**One job:** Display a clean, live web page using native Streamlit components (`st.metric`, `st.slider`, `st.radio`, `st.tabs`, `st.plotly_chart`, `st.table`):
* **Tab 1 (`Hostel AC Unit`):** Target temperature slider (`16.0°C – 32.0°C`), operating mode selector (`Automatic`, `Manual Override ON`, `Manual Override OFF`), 4 live metric boxes refreshing every 2.5 seconds, and an auto-scaling Plotly graph refreshing every 6 seconds without page flicker.
* **Tab 2 (`Overnight Run-Time Analytics`):** Interactive slider showing `% Run-Time Reduction` and `Degree-Hours Avoided`.
* **Tab 3 (`Sleep Biology & Weather`):** Live Katpadi weather and the ASHRAE 55 + sleep metabolism explanation.
* **Tab 4 (`Telemetry Logs`):** Live CSV table + one-click CSV download button.
* **Tab 5 (`Hardware & Architecture`):** Complete ₹813 Bill of Materials and First-Year Python syllabus mapping table.

### File 7: `run_system.py` (The One-Command Launcher)
**One job:** Start both `app.py` (Flask) and `dashboard.py` (Streamlit) at the same time when you run `py run_system.py`.

### File 8: `hardware/hostel_ac_controller/hostel_ac_controller.ino` (ESP32-S3 Firmware)
**One job:** Code flashed directly onto the ESP32-S3 chip using the Arduino IDE.
* Written in Arduino C++ (has a plain-English header at the top explaining how it works for Python students).
* `setup()` runs once when powered on to start the OLED screen, DHT11 sensor, touch button, servo motor, and WiFi.
* `loop()` runs forever: checks the touch button on `GPIO 10`, reads DHT11 temp/humidity on `GPIO 4` every 2.5 seconds, sends it to the laptop, moves the servo on `GPIO 18` (`0°` or `90°`), and updates the OLED screen.

---

## 5. How Everything Connects Step-by-Step

1. **Every 2.5 seconds**, the **DHT11 sensor (`GPIO 4`)** measures the hostel room temperature and humidity.
2. The **ESP32-S3** sends that reading to `app.py` on the laptop (over WiFi or USB cable).
3. `app.py` gets the outdoor temperature from `weather_service.py` and asks `comfort_model.py` if the AC should be `ON` or `OFF`.
4. `storage.py` saves the reading and decision as a new row in `data/hostel_telemetry.csv`.
5. `app.py` replies to the **ESP32-S3** with the target servo angle (`0°` for OFF, `90°` for ON), and the **SG90 servo (`GPIO 18`)** physically flips the wall switch.
6. Meanwhile, `dashboard.py` reads the latest status from `app.py` and updates the metrics and graph on your laptop screen.

---

## 6. Word-for-Word Speaking Scripts for Tomorrow's Review

Split these 5 roles among your team so everyone has a clear 45-second explanation ready:

### Speaker 1: Problem Statement & Comfort Math (`comfort_model.py`)
> *"Our project solves overnight overcooling in hostel rooms, where ACs only have a binary ON/OFF wall switch and no thermostat. In `comfort_model.py`, I implemented the ASHRAE Standard 55 Adaptive Comfort formula (`17.8 + 0.31 * outdoor_temp`), a `+1.0°C` nighttime sleep offset for blanket insulation and lower sleep metabolism (`0.7 met`), and a `±1.5°C` hysteresis deadband so the servo motor only flips the switch when crossing the lower or upper comfort limits."*

### Speaker 2: Live Weather Pipeline & Error Handling (`weather_service.py` & `config.py`)
> *"I built `weather_service.py` and `config.py`. Using Python's `requests` library, our code fetches live outdoor temperature and humidity for Katpadi, Vellore from the local weather station API — matching Google Weather. Because outdoor weather changes slowly, we cache the reading in memory for 5 minutes so the server responds in milliseconds. We also wrapped every network call in a `try/except` block so if the hotspot loses internet, it seamlessly uses backup values without crashing."*

### Speaker 3: Overnight Run-Time Analytics (`comfort_model.py` & `dashboard.py`)
> *"I worked on the thermal run-time analytics in `calculate_runtime_reduction()` and Tab 2 of the dashboard. Because hostel cooling comes from a centralized plant where chiller wattage isn't accessible to students, we don't guess fake kW numbers. Instead, we measure indoor temperature and time directly: turning the switch off for 4 out of 8 sleep hours cuts active cooling run-time by 50% and prevents 16 degree-hours of freezing overcooling overnight."*

### Speaker 4: Hardware, ESP32-S3 Firmware & Flask Server (`app.py` & `hostel_ac_controller.ino`)
> *"I integrated the physical ESP32-S3 hardware with our Flask server. The ESP32-S3 reads the DHT11 sensor on GPIO 4, drives the SG90 servo on GPIO 18 between 0 and 90 degrees, shows live status on the OLED on GPIO 8 and 9, and supports manual touch toggling on GPIO 10. It sends telemetry every 2.5 seconds over both WiFi HTTP and USB Serial. `app.py` receives this data, runs the comfort model, and replies with the servo command."*

### Speaker 5: CSV Storage, Dashboard & Offline Failsafe (`storage.py` & `dashboard.py`)
> *"I built the CSV storage module using Python's `with open` context manager to log every reading to `hostel_telemetry.csv`, and the Streamlit dashboard with an auto-scaling Plotly comfort graph. The graph automatically adjusts from raw 2.5-second readings to 10-second, 30-second, and 2-minute intervals as the session runs longer. I also verified the ESP32's offline failsafe: if WiFi disconnects while residents are asleep, the board automatically runs its own local hysteresis check so the room never freezes."*
