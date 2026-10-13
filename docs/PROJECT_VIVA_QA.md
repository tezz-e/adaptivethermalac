# Project Review & Viva Q&A Guide
### Adaptive Thermal Comfort AC Controller for Campus Hostels

**Target Audience:** Teammates preparing for examiner questions during tomorrow's project review.  
All answers are written in **simple, direct English** with **no broken math symbols or confusing diagram code**.

---

## 1. Software Architecture & Python Syllabus Design

### Q1. Why did you use basic Functions, Dictionaries, and Lists instead of Object-Oriented Programming (Classes/OOP)?

**Answer:**
Our course focuses on mastering foundational Python concepts first:
* **Functions (`def`):** Used for modular, reusable logic in `comfort_model.py`, `weather_service.py`, and `storage.py`.
* **Dictionaries (`{}`):** Used to store structured data like `hostel_room_state`, comfort bands, and JSON payloads.
* **Tuples (`()`):** Used to return multiple values cleanly from a function, such as `(ac_state, servo_angle, reason)`.
* **Lists (`[]`):** Used for CSV row headers and history tables.

Using simple functions and dictionaries makes the data flow completely transparent and easy for every teammate to trace without unnecessary class boilerplate (`__init__`, `self`, inheritance).

**How Data Flows Through Our Python Functions:**
1. **`weather_service.fetch_live_weather()`** → Returns a dictionary with Katpadi's outdoor temperature (`34.0°C`) and humidity.
2. **`comfort_model.calculate_ashrae_comfort(outdoor_temp)`** → Calculates the base comfort temperature using the ASHRAE formula.
3. **`comfort_model.get_hostel_comfort_band(outdoor_temp, current_hour, preferred_temp)`** → Adds `+1.0°C` at night (`22:00–07:00`) and builds the `±1.5°C` comfort band dictionary (`min_temp`, `optimal_temp`, `max_temp`).
4. **`comfort_model.evaluate_hostel_ac_decision(room_temp, min_temp, max_temp, last_ac_state)`** → Compares the DHT11 room temperature against the comfort band and returns a 3-item tuple: `("ON" or "OFF", servo_angle, explanation)`.
5. **`storage.save_telemetry(record_dict)`** → Appends the reading and decision as a new row in `data/hostel_telemetry.csv`.

---

### Q2. Why did you use both Flask (`app.py`) and Streamlit (`dashboard.py`)?

**Answer:**
Each tool does the job it was designed for:
1. **Flask (`app.py` on Port 5000 — Hardware Server):**
   - The physical ESP32-S3 board needs a fast, lightweight URL (`POST /api/hostel/telemetry`) where it can send sensor JSON and get back a tiny JSON reply (`{"ac_state": "ON", "servo_angle": 90}`) in a few milliseconds.
2. **Streamlit (`dashboard.py` on Port 8501 — Human Web Interface):**
   - Humans need sliders, radio buttons, metric cards, and a live temperature graph in a web browser.
   - Our `run_system.py` script launches both servers together with a single command (`py run_system.py`).

---

## 2. Scope Justification: Why Hostels Over Classrooms?

### Q3. Why did you focus on hostel room ACs instead of campus classrooms? (Examiner Favorite!)

**Answer:**
This was a deliberate engineering decision based on what can actually be measured and controlled accurately:
1. **Classrooms Have Unmeasured Variables:**
   - Campus classrooms use large centralized chillers. Calculating energy waste there requires knowing compressor tonnage (TR), airflow (CFM), solar heat gain, and live student headcounts — industrial sensors that students do not have access to. Guessing those numbers would be fake engineering.
2. **Hostel Rooms Have a Physical Binary Switch:**
   - Hostel ACs are controlled by a simple ON/OFF rocker switch on the wall with no thermostat. Left ON at night, they overcool the room down to `19°C`.
3. **Safe, Closed-Loop Hardware Solution:**
   - By placing a `DHT11` temperature sensor (`GPIO 4`) and an `SG90` servo motor (`GPIO 18`) at the hostel wall switch, our ₹813 prototype physically turns the switch **OFF (`0°`)** when the room is cool and **ON (`90°`)** when it warms up — without touching dangerous 230V mains wires.

---

## 3. Thermal Physics & ASHRAE Standard 55

### Q4. What is ASHRAE Standard 55, and why use it instead of a fixed 22°C?

**Answer:**
1. **What ASHRAE Stands For:**
   - **A**merican **S**ociety of **H**eating, **R**efrigerating and **A**ir-Conditioning **E**ngineers — the global organization that sets indoor comfort standards for buildings.
2. **Why Not a Fixed 22°C?**
   - In hot climates like Katpadi, Vellore (where outdoor temperatures reach `34°C–38°C`), our bodies naturally adapt to warmer weather and we wear lighter clothes. Walking from `34°C` outside into a `20°C` room causes thermal shock and shivering, whereas `25°C–27°C` feels comfortable and saves energy.
3. **The ASHRAE 55 Adaptive Comfort Equation:**
   ```text
   Comfortable Indoor Temp = 17.8 + (0.31 * Outdoor Temp)
   ```
   **Example Values:**
   | Outdoor Temp (°C) | ASHRAE Optimal Target (°C) | ±1.5°C Comfort Band (°C) |
   | :---: | :---: | :---: |
   | `20.0°C` | `24.0°C` | `22.5°C – 25.5°C` |
   | `25.0°C` | `25.6°C` | `24.1°C – 27.1°C` |
   | `30.0°C` | `27.1°C` | `25.6°C – 28.6°C` |
   | `34.0°C` (Katpadi) | `28.3°C` | `26.8°C – 29.8°C` |

---

### Q5. Why does your code add `+1.0°C` to the target temperature at night (10:00 PM to 7:00 AM)?

**Answer:**
When a person goes to sleep at night, two biological changes happen:
1. **Metabolic Rate Drops by 30%:** A sleeping human produces less internal body heat (`0.7 met` while sleeping vs. `1.0 met` while sitting awake).
2. **Blanket Insulation Increases:** Sleeping under a blanket or quilt increases thermal insulation from `0.5 clo` (daytime clothes) to `1.2–1.5 clo`.

Because of blankets and lower metabolism, `get_hostel_comfort_band()` automatically adds **`+1.0°C`** between `22:00` and `07:00` so the AC shuts off earlier and prevents the room from freezing at 3:00 AM.

---

### Q6. How do you measure savings when you don't know the hostel chiller's electrical wattage?

**Answer:**
Instead of guessing fake kilowatt (kW) numbers without a power meter, `calculate_runtime_reduction()` measures two direct physical quantities:
1. **Active Cooling Run-Time Reduction (%):**
   ```text
   Run-Time Reduction (%) = (Hours AC Switched OFF / 8.0 Sleep Hours) * 100
   ```
   If our controller turns the AC off for `4 hours` out of an `8-hour` night, it reduces active cooling run-time by **50%**.
2. **Overcooling Degree-Hours Avoided (°C·hr):**
   Measures how much excess chilling was prevented (`Hours OFF * 4.0°C = 16.0 °C·hr` for a 4-hour shutoff).

---

### Q7. What if a student wants a colder or warmer room than the formula suggests?

**Answer:**
Thermal comfort varies from person to person, so the dashboard includes a **Preferred Target Temperature Slider (`16.0°C to 32.0°C`)** plus an **Operating Mode selector**:
* **Preferred Slider (`16.0°C – 32.0°C`):** Centers the `±1.5°C` comfort band around whatever temperature the student chooses (for example, `24.0°C` gives a band of `22.5°C – 25.5°C`).
* **Dashboard Manual Override:** Lets the student force the switch **ON (`90°`)** or **OFF (`0°`)** from their laptop browser.
* **Physical Touch Button (`GPIO 10`):** Lets the student tap the capacitive touch sensor on the wall unit to toggle the AC switch immediately without opening a laptop.

---

## 4. Control Systems & Hysteresis Logic

### Q8. What is Hysteresis (Deadband), and why is it necessary for a motorized switch?

**Answer:**
If our target temperature is `25.0°C` and we had no deadband buffer, the servo motor would wear out:
* At `25.1°C` → AC turns ON.
* 20 seconds later at `24.9°C` → AC turns OFF.
* 20 seconds later at `25.1°C` → AC turns ON again.

This rapid clicking is called **switch chatter / hunting**.

**How Our `±1.5°C` Hysteresis Deadband Solves It (for a `25.0°C` target):**
* **Lower Limit (`23.5°C`):** Room has cooled down enough → Turn AC **OFF (`0°`)**.
* **Upper Limit (`26.5°C`):** Room has warmed up enough → Turn AC **ON (`90°`)**.
* **Inside the Band (`23.5°C to 26.5°C`):** **Keep the previous state!** If the AC was ON, it stays ON until the room reaches `23.5°C`. If it was OFF, it stays OFF until the room warms back up to `26.5°C`.

---

## 5. Hardware, ESP32-S3 & IoT Engineering

### Q9. Why use an SG90 Servo motor to flip the wall switch instead of an electrical relay?

**Answer:**
1. **Complete Electrical Safety:** Hostel students are not allowed to open 230V AC wall switchboards or cut mains wires. A servo motor works from the outside by mechanically pushing the plastic switch like a finger.
2. **Easy to Remove:** It mounts next to the switch plate and can be removed in seconds without leaving any wiring changes.
3. **External 5V Power Supply:** We power the SG90 servo from an external 5V adapter (with its ground wire connected to the ESP32's `GND` pin for a common ground reference) so the motor has strong, reliable torque without causing the ESP32-S3 to brown out.

---

### Q10. What happens if the mobile hotspot disconnects or the laptop shuts down while students are sleeping?

**Answer:**
The ESP32-S3 firmware (`hostel_ac_controller.ino`) has a built-in **Local Autonomous Hysteresis Failsafe**:
* Every time the ESP32 talks to the Flask server, it saves the latest `comfortMin` and `comfortMax` limits in its own memory (defaulting to `23.5°C – 26.5°C`).
* If WiFi disconnects or the laptop is turned off, the ESP32 automatically switches to its internal `evaluateLocalHysteresis()` function.
* It keeps reading the `DHT11` sensor on `GPIO 4` every 2.5 seconds and turns the servo **OFF (`0°`)** if the room drops to `comfortMin` and **ON (`90°`)** if it rises to `comfortMax`. The student is never left freezing!

---

## 6. First-Year Python Syllabus Mapping

### Q11. Where is each Python syllabus concept used in your code?

**Answer:**

| Python Syllabus Topic | File & Function | How We Used It |
| :--- | :--- | :--- |
| **Variables & Constants** | `config.py` | Stores coordinates, ASHRAE constants (`17.8`, `0.31`), and pin angles in one file. |
| **Functions (`def`)** | `comfort_model.py` | 4 modular functions (`calculate_ashrae_comfort`, `get_hostel_comfort_band`, `evaluate_hostel_ac_decision`, `calculate_runtime_reduction`). |
| **Conditionals (`if/elif/else`)** | `comfort_model.py` | 3-branch hysteresis check (`<= min_temp`, `>= max_temp`, `else` keep state) and night mode check. |
| **Dictionaries (`{}`) & Tuples (`()`)** | `app.py`, `comfort_model.py` | `hostel_room_state` dictionary and `(ac_state, servo_angle, reason)` return tuple. |
| **File Handling (`with open`, CSV)** | `storage.py` | Appends sensor logs to `data/hostel_telemetry.csv` using `mode="a"` and `csv.writer`. |
| **Exception Handling (`try/except`)** | `weather_service.py`, `app.py`, `storage.py` | Prevents crashes when WiFi drops, weather APIs time out, or files are busy. |
| **External Libraries (`requests`, `pandas`, `flask`, `streamlit`)** | `weather_service.py`, `app.py`, `dashboard.py` | Fetches live weather, runs the HTTP server, processes CSV tables, and plots interactive graphs. |

---

## 7. Limitations & Future Scope

### Q12. What are the limitations of this prototype, and how could you improve it in the future?

**Answer:**
1. **Sensor Precision:** The `DHT11` sensor has a `±2.0°C` accuracy tolerance. Upgrading to a `BME280` or `DHT22` sensor (`±0.5°C` accuracy) would make temperature switching even more precise.
2. **Future Upgrade — Infrared (IR) LED Transmitter:** For hostel rooms that have split ACs with remote controls, we could add a ₹15 IR LED to the ESP32 to send infrared remote signals directly instead of moving a mechanical servo arm.
