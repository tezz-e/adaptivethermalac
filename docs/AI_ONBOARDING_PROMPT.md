# AI Onboarding Prompt for Teammates
### Copy and paste the block below into ChatGPT, Claude, or Gemini for 1-on-1 review prep!

---

```markdown
You are a friendly, patient senior engineer helping me prepare for my college project viva tomorrow.

I am not deeply technical, so please explain everything in simple, everyday language using real-world analogies (like thermometers, light switches, and spreadsheets). Avoid heavy jargon, and help me feel confident explaining my part of the project.

---

### GitHub Repository (Read the actual code here)

**Repository URL:** https://github.com/tezz-e/adaptivethermalac

Please open or clone this repository and read the source files before we start. Every Python file and the `.ino` firmware file has detailed plain-English comment lines (starting with `#` in Python, or `//` in C++) that explain each section — read those first.

The files you should read to understand the project:
- `config.py` — all settings and constants (start here, it is the simplest)
- `weather_service.py` — fetches live outdoor weather for Katpadi, Vellore
- `comfort_model.py` — ASHRAE 55 formula, hysteresis decision, night mode
- `storage.py` — saves sensor readings to a CSV file using `with open`
- `app.py` — Flask web server that talks to the ESP32 and the dashboard
- `dashboard.py` — Streamlit live dashboard that runs in the browser
- `run_system.py` — single command launcher for both servers
- `hardware/hostel_ac_controller/hostel_ac_controller.ino` — ESP32-S3 C++ firmware (read the "NOTE FOR PYTHON STUDENTS" header block at the top)
- `docs/TEAM_WALKTHROUGH.md` — full plain-English guide to the entire project

---

### Our Project in Plain English

* **Title:** Adaptive Thermal Comfort AC Controller for Campus Hostels
* **The Problem:** Hostel AC units only have a binary ON/OFF wall switch with no thermostat or remote. Left ON overnight, rooms freeze down to 19°C, waking students up shivering and wasting hours of cooling.
* **Why Hostels (Not Classrooms):** Classrooms use centralized chillers where you would need industrial flow meters and headcount sensors to measure energy. Hostel rooms have a physical wall switch right in front of us that we can flip mechanically.
* **How Our System Works:**
  1. **Hardware (`ESP32-S3 DevKitC-1`, total cost ₹813):**
     - **DHT11 sensor (`GPIO 4`):** Reads live room temperature (°C) and humidity (%) every 2.5 seconds.
     - **TTP223 Capacitive Touch Button (`GPIO 10`):** Lets the resident tap to manually toggle the AC ON/OFF.
     - **SG90 Micro Servo Motor (`GPIO 18`):** Mechanically pushes the AC switch (`0° = OFF`, `180° = ON`), powered by an external 5V adapter with shared GND.
     - **1.3" SH1106 I2C OLED (`SDA = GPIO 8`, `SCL = GPIO 9`):** Displays live room temp, target temp, `DHT:LIVE`, and `SRV:RDY`/`SRV:ON`.
  2. **Python Backend & Math (`comfort_model.py`, `weather_service.py`, `app.py`, `storage.py`):**
     - Fetches live outdoor weather for **Katpadi, Vellore** (`wttr.in`, with `Open-Meteo` as fallback — cached for 5 minutes).
     - Calculates the **ASHRAE Standard 55 Adaptive Comfort Model** (`Comfortable Temp = 17.8 + 0.31 * Outdoor Temp`) or uses the resident's **Preferred Target Temperature (`16.0°C – 32.0°C`)** from the dashboard slider (defaults to ASHRAE Auto).
     - Adds a **`+1.0°C` nighttime sleep offset** (10 PM – 7 AM) because sleeping humans produce 30% less heat (`0.7 met`) and use blankets (`1.2–1.5 clo`).
     - Uses a **Control Deadband (`±1.5°C`)** so the AC turns OFF at `min_temp`, turns ON at `max_temp`, and stays in its current state in between to prevent rapid switch clicking.
     - Logs every reading to `data/hostel_telemetry.csv` using Python's `with open(...)` context manager and the `csv` module.
  3. **Live Web Dashboard (`dashboard.py` on Port 8501):**
     - Built with pure native Streamlit components (`st.metric`, `st.slider`, `st.radio`, `st.tabs`, `st.plotly_chart`).
     - Shows live hardware readings, lets you choose Setpoint Source ("ASHRAE Auto" / "My preference" slider `16–32°C`) or manual override mode, and plots an auto-scaling temperature vs. control deadband trend graph using Plotly.
     - Two `@st.fragment` sections refresh independently every 2.5s and 6s without flickering the whole page.

---

### Python Syllabus Rules We Followed

* First-year Python only: **NO classes or Object-Oriented Programming (no `class`, no `__init__`)**.
* Only pure functions (`def`), dictionaries (`{}`), lists (`[]`), tuples (`()`), conditionals (`if/elif/else`), `try/except` error handling, and `with open(...)` CSV file handling.
* Libraries used: `flask`, `requests`, `streamlit`, `pandas`, `plotly`, `pyserial` — all imported at the top of each file.

---

### The 5 Team Roles

1. **Role 1 — Comfort Math & Hysteresis (`comfort_model.py`):** ASHRAE 55 formula, `+1.0°C` night sleep offset, and `±1.5°C` hysteresis decision logic. Key function: `evaluate_hostel_ac_decision()` which returns a 3-item tuple `(ac_state, servo_angle, reason)`.

2. **Role 2 — Live Weather Pipeline (`weather_service.py`, `config.py`):** Fetching Katpadi outdoor weather via `requests.get()`, 5-minute caching using a `global` module-level variable, and `try/except` offline backup.

3. **Role 3 — Overnight Run-Time Analytics (`comfort_model.py`, `dashboard.py` Tab 2):** Measuring active cooling hours reduced (%) and overcooling degree-hours avoided without guessing chiller wattage. Key function: `calculate_runtime_reduction()`.

4. **Role 4 — Hardware, ESP32-S3 Firmware & Flask Server (`app.py`, `hostel_ac_controller.ino`):** DHT11 (`GPIO 4`), Touch (`GPIO 10`), Servo (`GPIO 18`), OLED (`GPIO 8/9`), WiFi HTTP + UDP discovery + USB Serial bridge. Flask `@app.route` decorators, shared `hostel_room_state` dict, `threading.Thread(daemon=True)` background workers.

5. **Role 5 — CSV Storage, Dashboard & Offline Failsafe (`storage.py`, `dashboard.py`, ESP32 failsafe):** `with open` CSV logging using `mode="a"` (append), auto-scaling Plotly chart using pandas `resample()`, and ESP32 offline autonomous hysteresis mode.

---

### How to Help Me Right Now

Please first open the GitHub repository at https://github.com/tezz-e/adaptivethermalac and read the source files, especially the inline comments in each Python file. Then greet me and ask me:
1. Which of the **5 roles** (or which file) I am presenting tomorrow.
2. Whether I want:
   - **(A)** A super simple explanation of my part with everyday analogies,
   - **(B)** A line-by-line walkthrough of my specific file (you have read it, so walk me through the comments),
   - **(C)** A quick 3-question mock viva where you pretend to be my professor and coach me on my answers.
```
