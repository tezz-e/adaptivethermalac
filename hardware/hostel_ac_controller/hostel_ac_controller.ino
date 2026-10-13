/*
 * ======================================================================================
 * Project: Adaptive Thermal Comfort Advisory & Control System for Campus Hostels
 * Component: ESP32-S3 Firmware for Hostel AC Physical Control Unit
 *
 * --------------------------------------------------------------------------------------
 * NOTE FOR PYTHON STUDENTS: This file is NOT Python.
 * --------------------------------------------------------------------------------------
 * This file is written in C++ and uses the Arduino framework. It runs directly ON the
 * ESP32-S3 microcontroller chip — not on a laptop. You upload it using the Arduino IDE
 * or PlatformIO, not by running "python" in a terminal.
 *
 * Key differences from Python you will notice:
 *   - Every statement ends with a semicolon ;
 *   - Variable types must be declared (e.g. "int", "float", "bool", "String")
 *     unlike Python where you just write  x = 5
 *   - Comments use  // for single-line  and  /* ... * /  for multi-line blocks
 *   - There are no classes in our Python code, but C++ uses them everywhere
 *
 * How an Arduino/ESP32 program is structured (always two mandatory functions):
 *
 *   void setup()  — runs ONCE when the chip is powered on or reset.
 *                   Used to initialise hardware: serial port, WiFi, sensors, servo.
 *                   Think of it like the code at the top of a Python script before
 *                   any loop.
 *
 *   void loop()   — runs FOREVER in an infinite loop after setup() finishes.
 *                   This is called automatically by the Arduino framework ~60 times
 *                   per second. It is equivalent to:
 *                       while True:
 *                           check_touch_button()
 *                           read_dht11()
 *                           send_to_flask()
 *                           update_oled()
 *
 * What each #include library does (like Python's "import"):
 *   Arduino.h    — core Arduino functions: pinMode, digitalWrite, delay, millis
 *   Wire.h       — I2C communication protocol (used to talk to the OLED display)
 *   WiFi.h       — connects the ESP32 to a WiFi network (our mobile hotspot)
 *   WiFiUdp.h    — UDP networking (used for auto-discovery broadcast to find laptop IP)
 *   HTTPClient.h — sends HTTP POST requests to the Flask server (like requests.post in Python)
 *   DHT.h        — reads temperature and humidity from the DHT11 sensor on GPIO 4
 *   ArduinoJson.h — parses and builds JSON strings (like Python's json.loads / json.dumps)
 *   U8g2lib.h    — draws text and graphics on the 1.3" SH1106 OLED display
 *
 * Hardware Setup (ESP32-S3-DevKitC-1 N16R8):
 *   - Microcontroller : ESP32-S3-DevKitC-1 (16MB Flash, 8MB PSRAM)
 *   - OLED Display    : 1.3" SH1106 128x64 (SDA -> GPIO 8, SCL -> GPIO 9)
 *   - DHT11 Sensor    : Data pin -> GPIO 4, VCC -> 3.3V, GND -> GND
 *   - SG90 Servo      : Signal -> GPIO 18, VCC -> 5V (external adapter), GND -> shared GND
 *   - Touch Button    : SIG -> GPIO 10, VCC -> 3.3V, GND -> GND
 * ======================================================================================
 */

#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <HTTPClient.h>
#include <DHT.h>
#include <ArduinoJson.h>
#include <U8g2lib.h>

// --------------------------------------------------------------------------------------
// 1. CONFIGURATION & PIN ASSIGNMENTS
// --------------------------------------------------------------------------------------

// WiFi Credentials (Hotspot)
const char* WIFI_SSID     = "eeeeee";
const char* WIFI_PASSWORD = "vv202526";

// Flask Backend API URL (Laptop local IPv4 on the hotspot + UDP auto-discovery)
String serverUrl          = "http://10.93.146.96:5000/api/hostel/telemetry";
WiFiUDP udpClient;

// Hardware Pins (Matched to ESP32-S3 setup)
#define OLED_SDA        8       // I2C SDA Pin for SH1106 OLED
#define OLED_SCL        9       // I2C SCL Pin for SH1106 OLED
#define DHTPIN          4       // DHT11 Sensor Data Pin (Connect DATA/OUT here)
#define DHTTYPE         DHT11   // Sensor type
#define SERVO_PIN       18      // SG90 Servo PWM Signal Pin (Orange/Yellow wire)
#define TOUCH_BTN_PIN   10      // Capacitive Touch Button Pin (GPIO 10)
#define STATUS_LED      2       // Status indicator GPIO

// Hardware LEDC PWM Settings for SG90 Servo (50Hz, 12-bit resolution on ESP32-S3)
#define SERVO_LEDC_CH   0
#define SERVO_FREQ_HZ   50
#define SERVO_RES_BITS  12      // 4096 ticks per 20,000 us period
#define SERVO_MIN_US    500     // 0 degrees pulse width in microseconds
#define SERVO_MAX_US    2400    // 180 degrees pulse width in microseconds

// Timing & Intervals
const unsigned long TELEMETRY_INTERVAL_MS = 2500; // Poll DHT11 & update every 2.5 seconds
unsigned long lastTelemetryTime = 0;

// Servo Angles for Physical AC Switch Actuation
const int ANGLE_OFF = 0;   // Physical switch OFF position (0 degrees)
const int ANGLE_ON  = 90;  // Physical switch ON position (90 degrees)

// Autonomous ASHRAE Comfort Thresholds
float targetOptimal = 25.0;
float comfortMin    = 23.5; // If temp <= 23.5 C, switch AC OFF
float comfortMax    = 26.5; // If temp >= 26.5 C, switch AC ON

// --------------------------------------------------------------------------------------
// 2. GLOBAL OBJECTS & STATE
// --------------------------------------------------------------------------------------
U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, /* reset=*/ U8X8_PIN_NONE);
DHT dht(DHTPIN, DHTTYPE);

String currentAcState       = "OFF";
int currentServoAngle       = ANGLE_OFF;
float currentTemp           = 25.0;
float currentHum            = 55.0;
bool isServerConnected      = false;
bool isDhtLive              = false; // True ONLY when real DHT11 data is read from GPIO 4
bool isServoInitialized     = false; // True when 50Hz hardware PWM on GPIO 18 is active
bool hasSimulatedOverride   = false;
bool manualTouchOverride    = false; // True when user toggles AC via GPIO 10 capacitive button

// Capacitive Button State (Supports 3-pin TTP223 active-HIGH, active-LOW, and bare touch pad)
int touchMode               = 0;     // 0 = Active-HIGH (TTP223), 1 = Active-LOW, 2 = Native TouchRead
bool lastTouchActive        = false;
unsigned long lastTouchTime = 0;
uint32_t touchBaseline      = 0;
int servoProbePullup        = 1;
int touchProbePullup        = 0;

// --------------------------------------------------------------------------------------
// 3. HARDWARE SERVO PWM FUNCTIONS (DIRECT PULSE TRAIN + ESP32-S3 LEDC HOLD)
// --------------------------------------------------------------------------------------
void holdServoAngleLedc(int angle) {
  if (angle < 0) angle = 0;
  if (angle > 180) angle = 180;
  uint32_t pulseUs = map(angle, 0, 180, SERVO_MIN_US, SERVO_MAX_US);
  uint32_t dutyTicks = (pulseUs * ((1UL << SERVO_RES_BITS) - 1)) / 20000UL;
  ledcWrite(SERVO_LEDC_CH, dutyTicks);
}

void writeServoAngle(int angle, int pulseCount = 22) {
  if (angle < 0) angle = 0;
  if (angle > 180) angle = 180;

  uint32_t pulseUs = map(angle, 0, 180, SERVO_MIN_US, SERVO_MAX_US);
  uint32_t lowUs = 20000UL - pulseUs;

  // Detach LEDC briefly and drive direct hardware-timed 50Hz pulses on GPIO 18
  // Guarantees 100% physical actuation regardless of timer/LEDC state
  ledcDetachPin(SERVO_PIN);
  pinMode(SERVO_PIN, OUTPUT);
  for (int i = 0; i < pulseCount; i++) {
    digitalWrite(SERVO_PIN, HIGH);
    delayMicroseconds(pulseUs);
    digitalWrite(SERVO_PIN, LOW);
    delayMicroseconds(lowUs);
  }

  // Re-attach hardware LEDC 50Hz PWM to maintain holding torque continuously
  ledcAttachPin(SERVO_PIN, SERVO_LEDC_CH);
  holdServoAngleLedc(angle);
}

bool initServoHardware() {
  // Digital-only check (NEVER call analogReadMilliVolts on GPIO 18 as it locks RTC analog mux!)
  pinMode(SERVO_PIN, INPUT_PULLUP);
  delay(10);
  servoProbePullup = digitalRead(SERVO_PIN);

  pinMode(SERVO_PIN, OUTPUT);
  digitalWrite(SERVO_PIN, LOW);

  uint32_t configuredFreq = ledcSetup(SERVO_LEDC_CH, SERVO_FREQ_HZ, SERVO_RES_BITS);
  if (configuredFreq == 0) {
    Serial.println("[Servo ERROR] Failed to configure 50Hz LEDC timer on ESP32-S3!");
    isServoInitialized = false;
    return false;
  }
  ledcAttachPin(SERVO_PIN, SERVO_LEDC_CH);
  isServoInitialized = true;
  Serial.printf("[Servo INIT] 50Hz PWM initialized on GPIO %d (Freq: %u Hz, PullupProbe: %d)\n",
                SERVO_PIN, configuredFreq, servoProbePullup);
  return true;
}

// --------------------------------------------------------------------------------------
// 4. DISPLAY HELPER FUNCTIONS (U8G2 SH1106 128x64)
// --------------------------------------------------------------------------------------
void setupDisplay() {
  Wire.begin(OLED_SDA, OLED_SCL, 400000);
  u8g2.begin();
  u8g2.setBusClock(400000);

  u8g2.clearBuffer();
  u8g2.drawFrame(0, 0, 128, 64);
  u8g2.drawFrame(2, 2, 124, 60);
  u8g2.setFont(u8g2_font_helvB08_tr);
  u8g2.drawStr(12, 20, "ADAPTIVE COMFORT");
  u8g2.drawHLine(12, 24, 104);
  u8g2.setFont(u8g2_font_6x10_tf);
  u8g2.drawStr(10, 38, "DHT:GPIO4  SRV:GPIO18");
  u8g2.drawStr(10, 52, "TOUCH BTN: GPIO10");
  u8g2.sendBuffer();
  delay(900);
}

void updateDisplay(float temp, float hum, String acState, int servoAngle, bool online, bool dhtReal, bool srvOk) {
  u8g2.clearBuffer();

  // 1. Top Header Bar: Room ID + DHT Badge + Servo Badge
  u8g2.setFont(u8g2_font_6x10_tf);
  u8g2.drawStr(1, 10, "D312");

  // DHT Sensor Indicator (Middle-Left)
  if (dhtReal) {
    u8g2.drawBox(30, 0, 48, 12);
    u8g2.setDrawColor(0);
    u8g2.drawStr(32, 9, "DHT:LIVE");
    u8g2.setDrawColor(1);
  } else {
    u8g2.drawStr(31, 10, "DHT:SIM");
  }

  // Servo Status Indicator (Top-Right)
  if (srvOk) {
    if (acState == "ON") {
      u8g2.drawBox(81, 0, 47, 12);
      u8g2.setDrawColor(0);
      u8g2.drawStr(85, 9, "SRV:ON");
      u8g2.setDrawColor(1);
    } else {
      u8g2.drawFrame(81, 0, 47, 12);
      u8g2.drawStr(83, 9, "SRV:RDY");
    }
  } else {
    u8g2.drawStr(81, 10, "SRV:ERR");
  }
  u8g2.drawHLine(0, 13, 128);

  // 2. Main Temperature & Humidity Readout
  char tempBuf[16];
  snprintf(tempBuf, sizeof(tempBuf), "%.1f C", temp);
  u8g2.setFont(u8g2_font_helvB14_tr);
  u8g2.drawStr(4, 32, tempBuf);

  char humBuf[16];
  snprintf(humBuf, sizeof(humBuf), "RH:%d%%", (int)hum);
  u8g2.setFont(u8g2_font_helvB08_tr);
  u8g2.drawStr(82, 25, humBuf);

  char setBuf[16];
  snprintf(setBuf, sizeof(setBuf), "Set:%.1fC", targetOptimal);
  u8g2.setFont(u8g2_font_6x10_tf);
  u8g2.drawStr(74, 36, setBuf);

  // 3. Sensor Status / Touch Override / Comfort Band Subtitle
  u8g2.setFont(u8g2_font_6x10_tf);
  if (manualTouchOverride) {
    char touchBuf[32];
    snprintf(touchBuf, sizeof(touchBuf), "Touch GPIO10: AC %s", acState.c_str());
    u8g2.drawStr(4, 44, touchBuf);
  } else if (dhtReal) {
    char bandBuf[32];
    snprintf(bandBuf, sizeof(bandBuf), "Band: %.1f - %.1f C", comfortMin, comfortMax);
    u8g2.drawStr(4, 44, bandBuf);
  } else {
    u8g2.drawStr(4, 44, "No DHT on GPIO4 (Sim)");
  }

  // 4. Bottom Status Bar (AC Switch & Servo Angle)
  u8g2.drawHLine(0, 47, 128);
  u8g2.setFont(u8g2_font_helvB08_tr);

  char acBuf[20];
  snprintf(acBuf, sizeof(acBuf), "AC: %s", acState.c_str());
  u8g2.drawStr(4, 60, acBuf);

  char srvBuf[20];
  snprintf(srvBuf, sizeof(srvBuf), "SERVO: %d deg", servoAngle);
  u8g2.drawStr(56, 60, srvBuf);

  u8g2.sendBuffer();
}

// --------------------------------------------------------------------------------------
// 5. SERVO ACTUATION FUNCTION
// --------------------------------------------------------------------------------------
void setAcSwitch(int targetAngle, String newState) {
  Serial.printf("[Servo] Actuating AC switch on GPIO %d -> %d deg (AC: %s)\n",
                SERVO_PIN, targetAngle, newState.c_str());
  writeServoAngle(targetAngle);
  currentServoAngle = targetAngle;
  currentAcState = newState;

  digitalWrite(STATUS_LED, HIGH);
  delay(80);
  digitalWrite(STATUS_LED, LOW);
}

// --------------------------------------------------------------------------------------
// 6. CAPACITIVE TOUCH BUTTON HANDLER (GPIO 10)
// --------------------------------------------------------------------------------------
void initTouchButton() {
  // Pure digital probe (do NOT call analogReadMilliVolts, which disables digital input buffer!)
  pinMode(TOUCH_BTN_PIN, INPUT_PULLUP);
  delay(15);
  int pu = digitalRead(TOUCH_BTN_PIN);
  touchProbePullup = pu;

  pinMode(TOUCH_BTN_PIN, INPUT_PULLDOWN);
  delay(15);
  int pd = digitalRead(TOUCH_BTN_PIN);

  Serial.printf("[Touch PROBE] GPIO 10 -> Pullup: %d, Pulldown: %d\n", pu, pd);

  if (pu == LOW && pd == LOW) {
    // 3-pin TTP223 module actively holds GPIO 10 LOW when untouched, goes HIGH when touched
    touchMode = 0;
    pinMode(TOUCH_BTN_PIN, INPUT_PULLDOWN);
    Serial.println("[Touch INIT] 3-pin TTP223 Capacitive Touch Module detected on GPIO 10 (Active-HIGH).");
  } else if (pu == HIGH && pd == HIGH) {
    // Active-LOW touch/button module
    touchMode = 1;
    pinMode(TOUCH_BTN_PIN, INPUT_PULLUP);
    Serial.println("[Touch INIT] Active-LOW Touch/Button Module detected on GPIO 10.");
  } else {
    // Floating pin when idle: could be bare capacitive touch pad or open button
    // Check if touchRead(10) gives a valid capacitive reading, otherwise use INPUT_PULLDOWN
    touchMode = 0;
    pinMode(TOUCH_BTN_PIN, INPUT_PULLDOWN);
    Serial.println("[Touch INIT] Configured GPIO 10 as Active-HIGH touch input.");
  }
}

void checkCapacitiveButton() {
  bool isTouched = false;
  if (touchMode == 0) {
    isTouched = (digitalRead(TOUCH_BTN_PIN) == HIGH);
  } else if (touchMode == 1) {
    isTouched = (digitalRead(TOUCH_BTN_PIN) == LOW);
  }

  // Rising edge detection with 280ms debounce
  if (isTouched && !lastTouchActive && (millis() - lastTouchTime > 280)) {
    lastTouchTime = millis();
    manualTouchOverride = true;

    if (currentAcState == "OFF") {
      setAcSwitch(ANGLE_ON, "ON");
    } else {
      setAcSwitch(ANGLE_OFF, "OFF");
    }

    Serial.printf("[Touch GPIO 10] Button touched! Toggled AC -> %s (Servo -> %d deg)\n",
                  currentAcState.c_str(), currentServoAngle);

    updateDisplay(currentTemp, currentHum, currentAcState, currentServoAngle,
                  isServerConnected, isDhtLive, isServoInitialized);
  }

  lastTouchActive = isTouched;
}

// --------------------------------------------------------------------------------------
// 7. LOCAL AUTONOMOUS HYSTERESIS (FAILSAFE / STANDALONE)
// --------------------------------------------------------------------------------------
void evaluateLocalHysteresis(float temp) {
  if (manualTouchOverride) {
    return; // Respect manual capacitive touch toggle unless reset to AUTO
  }
  if (temp <= comfortMin && currentAcState != "OFF") {
    Serial.printf("[Hysteresis] Room cool (%.1f C <= %.1f C). Switching AC OFF.\n", temp, comfortMin);
    setAcSwitch(ANGLE_OFF, "OFF");
  } else if (temp >= comfortMax && currentAcState != "ON") {
    Serial.printf("[Hysteresis] Room warm (%.1f C >= %.1f C). Switching AC ON.\n", temp, comfortMax);
    setAcSwitch(ANGLE_ON, "ON");
  }
}

// --------------------------------------------------------------------------------------
// 8. USB SERIAL COMMAND LISTENER (FOR LIVE DEMO / HARDWARE TESTING)
// --------------------------------------------------------------------------------------
void checkSerialCommands() {
  if (Serial.available() > 0) {
    String input = Serial.readStringUntil('\n');
    input.trim();
    if (input.length() == 0) return;

    if (input.startsWith("URL:")) {
      serverUrl = input.substring(4);
      serverUrl.trim();
      Serial.printf("[Serial Config] Updated Backend URL to: %s\n", serverUrl.c_str());
      return;
    }

    if (input.equalsIgnoreCase("AUTO")) {
      hasSimulatedOverride = false;
      manualTouchOverride = false;
      Serial.println("[Serial Override] Returned to AUTO mode (live DHT11 polling on GPIO 4).");
      return;
    }

    if (input.equalsIgnoreCase("TOGGLE")) {
      manualTouchOverride = true;
      if (currentAcState == "OFF") {
        setAcSwitch(ANGLE_ON, "ON");
      } else {
        setAcSwitch(ANGLE_OFF, "OFF");
      }
      updateDisplay(currentTemp, currentHum, currentAcState, currentServoAngle,
                    isServerConnected, isDhtLive, isServoInitialized);
      return;
    }

    // Allow sending temperature directly over Serial (e.g., "28.5" or "TEMP:28.5")
    if (input.startsWith("TEMP:")) {
      input = input.substring(5);
    }
    float val = input.toFloat();
    if (val >= 15.0 && val <= 40.0) {
      currentTemp = val;
      hasSimulatedOverride = true;
      manualTouchOverride = false;
      isDhtLive = false;
      Serial.printf("[Serial Override] Simulated Room Temp set to %.1f C (Source: SIMULATED)\n", currentTemp);
      evaluateLocalHysteresis(currentTemp);
      updateDisplay(currentTemp, currentHum, currentAcState, currentServoAngle,
                    isServerConnected, isDhtLive, isServoInitialized);
    }
  }
}

// --------------------------------------------------------------------------------------
// 9. SETUP ROUTINE
// --------------------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("\n========================================================");
  Serial.println("  Adaptive Thermal Comfort - Hostel AC Controller (S3)");
  Serial.println("========================================================");

  pinMode(STATUS_LED, OUTPUT);
  digitalWrite(STATUS_LED, LOW);

  // 1. Initialize SH1106 OLED Display on SDA=8, SCL=9
  setupDisplay();
  Serial.println("[Display] SH1106 128x64 OLED initialized on SDA=8, SCL=9.");

  // 2. Initialize DHT11 Sensor on GPIO 4
  dht.begin();
  Serial.println("[Hardware] DHT11 sensor initialized on GPIO 4.");

  // 3. Initialize Capacitive Touch Button on GPIO 10
  initTouchButton();

  // 4. Initialize SG90 Servo Motor on GPIO 18 with Active Self-Test Sweep (0 -> 90 -> 0)
  if (initServoHardware()) {
    u8g2.clearBuffer();
    u8g2.drawFrame(0, 0, 128, 64);
    u8g2.setFont(u8g2_font_helvB08_tr);
    u8g2.drawStr(10, 20, "SERVO SELF-TEST");
    u8g2.drawHLine(10, 24, 108);
    u8g2.setFont(u8g2_font_6x10_tf);
    u8g2.drawStr(10, 38, "Pin: GPIO 18 (50Hz)");
    u8g2.drawStr(10, 52, "Sweep: 0 -> 90 -> 0");
    u8g2.sendBuffer();

    writeServoAngle(ANGLE_OFF);
    delay(350);
    writeServoAngle(ANGLE_ON);
    delay(550);
    writeServoAngle(ANGLE_OFF);
    delay(350);
    currentServoAngle = ANGLE_OFF;
    currentAcState = "OFF";
    Serial.println("[Servo INIT] Self-test sweep (0 -> 90 -> 0 deg) completed on GPIO 18.");
  }

  // 5. Connect to WiFi Hotspot
  if (String(WIFI_SSID) != "YOUR_WIFI_SSID" && strlen(WIFI_SSID) > 0) {
    Serial.printf("[WiFi] Connecting to %s ", WIFI_SSID);
    u8g2.clearBuffer();
    u8g2.drawFrame(0, 0, 128, 64);
    u8g2.setFont(u8g2_font_helvB08_tr);
    u8g2.drawStr(10, 20, "CONNECTING WIFI");
    u8g2.drawHLine(10, 24, 108);
    u8g2.setFont(u8g2_font_6x10_tf);
    String ssidLine = "SSID: " + String(WIFI_SSID);
    u8g2.drawStr(10, 40, ssidLine.c_str());
    u8g2.sendBuffer();

    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    int wifiAttempts = 0;
    while (WiFi.status() != WL_CONNECTED && wifiAttempts < 14) {
      delay(400);
      Serial.print(".");
      wifiAttempts++;
    }

    if (WiFi.status() == WL_CONNECTED) {
      Serial.println("\n[WiFi] Connected successfully!");
      Serial.print("[WiFi] IP Address: ");
      Serial.println(WiFi.localIP());

      u8g2.clearBuffer();
      u8g2.drawFrame(0, 0, 128, 64);
      u8g2.setFont(u8g2_font_helvB08_tr);
      u8g2.drawStr(14, 22, "WIFI CONNECTED!");
      u8g2.setFont(u8g2_font_6x10_tf);
      String ipStr = "IP: " + WiFi.localIP().toString();
      u8g2.drawStr(10, 42, ipStr.c_str());
      u8g2.sendBuffer();
      delay(800);
    } else {
      Serial.println("\n[WiFi] Hotspot not in range yet. Operating in Autonomous Mode.");
      WiFi.reconnect();
    }
  }

  // Initial DHT11 check
  float initT = dht.readTemperature();
  float initH = dht.readHumidity();
  if (!isnan(initT) && !isnan(initH)) {
    currentTemp = initT;
    currentHum = initH;
    isDhtLive = true;
  } else {
    isDhtLive = false;
  }

  updateDisplay(currentTemp, currentHum, currentAcState, currentServoAngle,
                false, isDhtLive, isServoInitialized);
}

void discoverBackendViaUdp() {
  udpClient.begin(5002);
  udpClient.beginPacket(IPAddress(255, 255, 255, 255), 5001);
  udpClient.print("DISCOVER_HOSTEL_BACKEND");
  udpClient.endPacket();

  unsigned long startWait = millis();
  while (millis() - startWait < 350) {
    int pktSize = udpClient.parsePacket();
    if (pktSize > 0) {
      char buf[64];
      int len = udpClient.read(buf, sizeof(buf) - 1);
      buf[len > 0 ? len : 0] = '\0';
      if (String(buf).indexOf("HOSTEL_BACKEND_OK") >= 0) {
        IPAddress remoteIp = udpClient.remoteIP();
        serverUrl = "http://" + remoteIp.toString() + ":5000/api/hostel/telemetry";
        Serial.printf("[UDP Discovery] Found Flask server at %s\n", serverUrl.c_str());
        break;
      }
    }
    delay(10);
  }
  udpClient.stop();
}

// --------------------------------------------------------------------------------------
// 10. MAIN LOOP
// --------------------------------------------------------------------------------------
void loop() {
  // Poll capacitive touch button on GPIO 10 and USB serial commands immediately (~60Hz)
  checkCapacitiveButton();
  checkSerialCommands();

  unsigned long now = millis();
  if (now - lastTelemetryTime >= TELEMETRY_INTERVAL_MS) {
    lastTelemetryTime = now;

    // Always check physical DHT11 sensor on GPIO 4
    float t = dht.readTemperature();
    float h = dht.readHumidity();

    if (!isnan(t) && !isnan(h)) {
      if (!hasSimulatedOverride) {
        currentTemp = t;
        currentHum = h;
        isDhtLive = true;
      }
      Serial.printf("[Sensor: REAL DHT11] GPIO 4 -> Temp: %.1f C, Humidity: %.1f %%\n", t, h);
    } else {
      isDhtLive = false;
      Serial.printf("[Sensor: SIMULATED] No DHT11 on GPIO 4 -> Fallback: %.1f C, %.0f %%\n",
                    currentTemp, currentHum);
    }

    // Re-assert servo PWM angle every cycle to ensure servo holds position
    holdServoAngleLedc(currentServoAngle);

    // Emit structured JSON line over USB Serial for local bridge/monitoring
    Serial.printf("[TELEMETRY_JSON] {\"temperature\":%.1f,\"humidity\":%.1f,\"sensor_source\":\"%s\",\"servo_status\":\"%s\",\"servo_pullup\":%d,\"touch_pullup\":%d,\"touch_override\":%s,\"ac_state\":\"%s\",\"servo_angle\":%d}\n",
                  currentTemp, currentHum,
                  isDhtLive ? "LIVE_DHT11" : "SIMULATED",
                  isServoInitialized ? "READY" : "ERR",
                  servoProbePullup, touchProbePullup,
                  manualTouchOverride ? "true" : "false",
                  currentAcState.c_str(), currentServoAngle);

    // Communicate with Flask backend if WiFi is connected
    if (WiFi.status() == WL_CONNECTED) {
      JsonDocument reqDoc;
      reqDoc["temperature"]     = currentTemp;
      reqDoc["humidity"]        = currentHum;
      reqDoc["sensor_source"]   = isDhtLive ? "LIVE_DHT11" : "SIMULATED";
      reqDoc["servo_status"]    = isServoInitialized ? "READY" : "ERR";
      reqDoc["touch_override"]  = manualTouchOverride;
      reqDoc["ac_state"]        = currentAcState;
      reqDoc["servo_angle"]     = currentServoAngle;
      reqDoc["connection_mode"] = "WIFI_HTTP";
      String requestBody;
      serializeJson(reqDoc, requestBody);

      HTTPClient http;
      http.setConnectTimeout(900);
      http.setTimeout(900);
      http.begin(serverUrl);
      http.addHeader("Content-Type", "application/json");
      int httpResponseCode = http.POST(requestBody);

      if (httpResponseCode <= 0) {
        http.end();
        discoverBackendViaUdp();
        http.setConnectTimeout(900);
        http.setTimeout(900);
        http.begin(serverUrl);
        http.addHeader("Content-Type", "application/json");
        httpResponseCode = http.POST(requestBody);
      }

      if (httpResponseCode == 200) {
        isServerConnected = true;
        String response = http.getString();
        Serial.printf("[Backend] HTTP 200: %s\n", response.c_str());

        JsonDocument resDoc;
        DeserializationError error = deserializeJson(resDoc, response);

        if (!error) {
          String backendAcState = resDoc["ac_state"].as<String>();
          int targetAngle       = resDoc["servo_angle"].as<int>();
          targetOptimal         = resDoc["target_optimal"] | 25.0;
          comfortMin            = resDoc["comfort_min"] | 23.5;
          comfortMax            = resDoc["comfort_max"] | 26.5;

          if (!manualTouchOverride) {
            setAcSwitch(targetAngle, backendAcState);
          }
        }
      } else {
        isServerConnected = false;
        evaluateLocalHysteresis(currentTemp);
      }
      http.end();
    } else {
      isServerConnected = false;
      evaluateLocalHysteresis(currentTemp);
    }

    // Refresh SH1106 OLED screen with explicit DHT and Servo indicators
    updateDisplay(currentTemp, currentHum, currentAcState, currentServoAngle,
                  isServerConnected, isDhtLive, isServoInitialized);
  }

  delay(15);
}
