# Team Walkthrough and Beginner Guide
### Adaptive Thermal Comfort AC Controller for Campus Hostels

**Target Audience:** Teammates preparing for tomorrow's project review — even if you have zero prior experience with IoT, servers, or Python.  
**Goal:** Read this once from top to bottom (about 8 minutes). By the end, you will understand how the physical hardware, the math formula, and every single Python file fit together, plus have exact word-for-word scripts for what to say to the examiner.

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

### File 1: `config.py` (The Settings File — 38 lines)
Stores all fixed numbers in one place so nothing is hardcoded across the project:
* `CAMPUS_LATITUDE = 12.9692`, `CAMPUS_LONGITUDE = 79.1559` (Katpadi, Vellore)
* `ASHRAE_INTERCEPT = 17.8`, `ASHRAE_SLOPE = 0.31`
* `NIGHT_START_HOUR = 22` (10 PM), `NIGHT_END_HOUR = 7` (7 AM), `NIGHT_COMFORT_OFFSET = 1.0`
* `SERVO_OFF_ANGLE = 0`, `SERVO_ON_ANGLE = 90`
* `CSV_FILE_PATH = "data/hostel_telemetry.csv"`

### File 2: `weather_service.py` (Live Outdoor Weather — 68 lines)
Fetches the real-time outdoor temperature and humidity for **Katpadi, Vellore** using `requests.get()`:
* Queries the live Katpadi weather station (`wttr.in/Katpadi,Vellore?format=j1`, matching Google Weather) with automatic fallback to `Open-Meteo`.
* **5-Minute Cache:** Saves the weather in memory for 300 seconds so we don't spam the internet every 2.5 seconds.
* **Offline Failsafe (`try...except`):** If the mobile hotspot loses internet, it safely returns backup values (`34.0°C, 45% RH`) so the system never crashes.

### File 3: `comfort_model.py` (The Math & Decision Brain — 98 lines)
Contains 4 pure functions:
1. `calculate_ashrae_comfort(outdoor_temp)`: Runs `17.8 + (0.31 * outdoor_temp)`.
2. `get_hostel_comfort_band(outdoor_temp, current_hour, preferred_temp)`: Adds `+1.0°C` if it is nighttime (`22:00–07:00`) and returns a dictionary with `optimal_temp`, `min_temp` (`-1.5°C`), and `max_temp` (`+1.5°C`).
3. `evaluate_hostel_ac_decision(room_temp, min_temp, max_temp, last_ac_state)`: Runs the `if / elif / else` hysteresis check and returns a 3-item tuple: `(ac_state, servo_angle, explanation)`.
4. `calculate_runtime_reduction(hours_ac_off)`: Calculates the percentage of overnight cooling time saved (e.g., 4 hours off out of 8 hours sleep = **50% run-time reduction**) and degree-hours of overcooling prevented.

### File 4: `storage.py` (CSV File Handling — 74 lines)
Demonstrates Python file handling:
* `save_telemetry(record_dict)`: Uses `with open("data/hostel_telemetry.csv", mode="a")` and `csv.writer` to safely append each sensor reading as a new row in the CSV spreadsheet.
* `read_telemetry_history(limit)`: Reads the CSV file using `pandas.read_csv()` so the dashboard can plot the graph and let you download the CSV.

### File 5: `app.py` (The Flask Communication Server — Port 5000)
Acts as the bridge between the physical ESP32-S3 board and the Python comfort model:
* **Dual Hardware Link (WiFi HTTP + USB Serial):** Accepts live readings from the ESP32 over WiFi (`POST /api/hostel/telemetry`) **and** automatically listens on USB Serial (`COM12`) if the board is plugged into the laptop.
* **UDP Auto-Discovery (`Port 5001`):** Even if your mobile hotspot changes the laptop's IP address, `app.py` replies to the ESP32's UDP broadcast so the board finds the laptop automatically without reflashing!
* **Immediate Dashboard Control (`/api/hostel/preference` & `/api/hostel/override`):** When you move the temperature slider or click Manual Override on the dashboard, `app.py` immediately updates the AC decision and commands the servo.

### File 6: `dashboard.py` (The Live Streamlit Web Dashboard — Port 8501)
Built using **pure native Streamlit components** (`st.metric`, `st.slider`, `st.radio`, `st.tabs`, `st.plotly_chart`, `st.table`):
* **Tab 1 (`Hostel AC Unit`):**
  - **Preferred Target Temperature Slider (`16.0°C – 32.0°C`)** and **Operating Mode Radio** (`Automatic (ASHRAE)`, `Manual Override ON (90°)`, `Manual Override OFF (0°)`).
  - **4 Live Hardware Metrics (refreshing every 2.5s):** Room Temperature & Humidity (`DHT11 LIVE`), AC Switch State (`ON`/`OFF`), Servo Position (`0°`/`90°`), and Target Comfort Band (`±1.5°C`).
  - **Adaptive Time-Scale Graph:** Starts by plotting raw 2.5-second readings during the first 1.5 minutes, then automatically scales its time window to `10s`, `30s`, and `2m` intervals as the session runs longer.
* **Tab 2 (`Overnight Run-Time Analytics`):** Interactive slider showing `% Run-Time Reduction` and `Degree-Hours Avoided`.
* **Tab 3 (`Sleep Biology & Weather`):** Live Katpadi weather and the ASHRAE 55 + sleep metabolism formulas.
* **Tab 4 (`Telemetry Logs`):** Live CSV table + one-click CSV download button.
* **Tab 5 (`Hardware & Architecture`):** Complete ₹813 Bill of Materials and First-Year Python syllabus mapping table.

---

## 5. Word-for-Word Speaking Scripts for Tomorrow's Review

Split these 5 roles among your team so everyone has a clear 45-second explanation ready:

### Speaker 1: Problem Statement & Comfort Math (`comfort_model.py`)
> *"Our project solves overnight overcooling in hostel rooms, where ACs only have a binary ON/OFF wall switch and no thermostat. In `comfort_model.py`, I implemented the ASHRAE Standard 55 Adaptive Comfort formula (`17.8 + 0.31 * outdoor_temp`), a `+1.0°C` nighttime sleep offset for blanket insulation and lower sleep metabolism (`0.7 met`), and a `±1.5°C` hysteresis deadband so the servo motor only flips the switch when crossing the lower or upper comfort limits."*

### Speaker 2: Live Weather Pipeline & Error Handling (`weather_service.py` & `config.py`)
> *"I built `weather_service.py` and `config.py`. Using Python's `requests` library, our code fetches live outdoor temperature and humidity for Katpadi, Vellore. Because outdoor weather changes slowly, we cache the reading in memory for 5 minutes so the server responds in milliseconds. We also wrapped the network call in a `try...except` block so if the hotspot loses internet, it seamlessly uses backup values without crashing."*

### Speaker 3: Overnight Run-Time Analytics (`comfort_model.py` & `dashboard.py`)
> *"I worked on the thermal run-time analytics. Because hostel cooling comes from a centralized plant where chiller wattage isn't accessible to students, we don't guess fake kW numbers. Instead, we measure indoor temperature and time directly: turning the switch off for 4 out of 8 sleep hours cuts active cooling run-time by 50% and prevents 16 degree-hours of freezing overcooling overnight."*

### Speaker 4: Hardware, ESP32-S3 Firmware & Flask Server (`app.py` & `hostel_ac_controller.ino`)
> *"I integrated the physical ESP32-S3 hardware with our Flask server (`app.py`). Our ESP32-S3 reads live room temperature from a DHT11 sensor on GPIO 4, displays status on a 1.3-inch OLED on GPIO 8 and 9, supports manual touch toggling on GPIO 10, and drives an SG90 servo motor on GPIO 18 between 0 degrees (OFF) and 90 degrees (ON). It streams telemetry every 2.5 seconds over both WiFi HTTP and USB Serial."*

### Speaker 5: CSV Storage, Dashboard & Offline Failsafe (`storage.py` & `dashboard.py`)
> *"I built the CSV storage module (`storage.py`) using Python's `with open` context manager to log every reading to `hostel_telemetry.csv`, and the Streamlit dashboard (`dashboard.py`) with an auto-scaling Plotly comfort graph. I also verified the ESP32's offline failsafe: if WiFi disconnects while residents are asleep, the board automatically switches to internal safety limits (`24.0°C – 26.5°C`) so the room never freezes."*
