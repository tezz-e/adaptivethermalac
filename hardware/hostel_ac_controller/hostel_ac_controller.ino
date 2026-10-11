/*
 * ======================================================================================
 * Project: Adaptive Thermal Comfort Advisory & Control System for Campus Hostels
 * Component: ESP32 Firmware for Hostel AC Physical Control Unit
 * 
 * Hardware Setup:
 * - ESP32 NodeMCU / DevKit V1
 * - DHT11 Temperature & Humidity Sensor (Data pin -> GPIO 4)
 * - SG90 Micro Servo Motor (Signal pin -> GPIO 18)
 * - Display: 0.96" I2C OLED (SSD1306) or 16x2 I2C LCD (SDA -> GPIO 21, SCL -> GPIO 22)
 *
 * Required Arduino IDE Libraries (Install via Sketch -> Include Library -> Manage Libraries):
 * 1. "DHT sensor library" by Adafruit
 * 2. "Adafruit Unified Sensor" by Adafruit
 * 3. "ESP32Servo" by Kevin Harrington
 * 4. "ArduinoJson" by Benoit Blanchon (version 6.x or 7.x)
 * 5. If using OLED: "Adafruit SSD1306" and "Adafruit GFX Library"
 * 6. If using LCD: "LiquidCrystal I2C" by Frank de Brabander
 * ======================================================================================
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <ESP32Servo.h>
#include <DHT.h>
#include <ArduinoJson.h>

// --------------------------------------------------------------------------------------
// 1. CONFIGURATION & PIN ASSIGNMENTS
// --------------------------------------------------------------------------------------

// WiFi Credentials (Replace with your hotspot / campus WiFi)
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// Flask Backend API URL (Use your laptop's local IP on the same WiFi network, e.g., 192.168.1.5)
const char* SERVER_URL    = "http://192.168.1.5:5000/api/hostel/telemetry";

// Hardware Pins
#define DHTPIN        4       // DHT11 Sensor Data Pin
#define DHTTYPE       DHT11   // Sensor type
#define SERVO_PIN     18      // Servo PWM Signal Pin
#define STATUS_LED    2       // ESP32 Onboard Blue LED

// Display Selection: Set to 1 for OLED (SSD1306 128x64), or 0 for 16x2 I2C LCD
#define USE_OLED_DISPLAY  1

#if USE_OLED_DISPLAY
  #include <Wire.h>
  #include <Adafruit_GFX.h>
  #include <Adafruit_SSD1306.h>
  #define SCREEN_WIDTH  128
  #define SCREEN_HEIGHT 64
  #define OLED_RESET    -1
  #define SCREEN_ADDRESS 0x3C
  Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);
#else
  #include <Wire.h>
  #include <LiquidCrystal_I2C.h>
  LiquidCrystal_I2C lcd(0x27, 16, 2); // Common I2C address is 0x27 or 0x3F
#endif

// Timing & Intervals
const unsigned long TELEMETRY_INTERVAL_MS = 5000; // Send telemetry every 5 seconds
unsigned long lastTelemetryTime = 0;

// Servo Angles for Physical AC Switch Actuation
const int ANGLE_OFF = 0;   // Physical switch OFF position (0 degrees)
const int ANGLE_ON  = 90;  // Physical switch ON position (90 degrees)

// Autonomous Offline Fallback Thresholds (used if WiFi drops)
const float FALLBACK_OFF_TEMP = 24.0; // If temp <= 24.0°C, AC OFF
const float FALLBACK_ON_TEMP  = 26.5; // If temp >= 26.5°C, AC ON

// --------------------------------------------------------------------------------------
// 2. GLOBAL OBJECTS & STATE
// --------------------------------------------------------------------------------------
DHT dht(DHTPIN, DHTTYPE);
Servo acServo;

String currentAcState = "OFF";
int currentServoAngle = ANGLE_OFF;
float currentTemp = 25.0;
float currentHum = 50.0;
float targetOptimal = 25.5;
bool isServerConnected = false;

// --------------------------------------------------------------------------------------
// 3. DISPLAY HELPER FUNCTIONS
// --------------------------------------------------------------------------------------
void setupDisplay() {
#if USE_OLED_DISPLAY
  Wire.begin(21, 22); // ESP32 default I2C pins: SDA=21, SCL=22
  if (!display.begin(SSD1306_SWITCHCAPVCC, SCREEN_ADDRESS)) {
    Serial.println("[Display] OLED allocation failed. Continuing without display...");
  } else {
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(1);
    display.setCursor(10, 10);
    display.println("ADAPTIVE COMFORT");
    display.setCursor(10, 26);
    display.println("Hostel AC Unit");
    display.setCursor(10, 42);
    display.println("Initializing...");
    display.display();
    delay(1000);
  }
#else
  Wire.begin(21, 22);
  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("Adaptive Comfort");
  lcd.setCursor(0, 1);
  lcd.print("Initializing...");
  delay(1000);
#endif
}

void updateDisplay(float temp, float hum, String acState, bool online) {
#if USE_OLED_DISPLAY
  display.clearDisplay();
  
  // Header Bar
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.print("HOSTEL D-312");
  display.setCursor(85, 0);
  display.print(online ? "[LIVE]" : "[OFFL]");
  
  display.drawLine(0, 10, 128, 10, SSD1306_WHITE);
  
  // Temperature & Humidity
  display.setTextSize(2);
  display.setCursor(0, 16);
  display.print(temp, 1);
  display.setTextSize(1);
  display.print(" C  ");
  display.setTextSize(2);
  display.print((int)hum);
  display.setTextSize(1);
  display.print(" %");

  // AC State Box
  display.drawLine(0, 36, 128, 36, SSD1306_WHITE);
  display.setCursor(0, 44);
  display.setTextSize(1);
  display.print("AC STATE: ");
  display.setTextSize(2);
  if (acState == "ON") {
    display.print("ON ");
  } else {
    display.print("OFF");
  }

  display.display();
#else
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("T:" + String(temp, 1) + "C H:" + String((int)hum) + "%");
  lcd.setCursor(0, 1);
  lcd.print("AC:" + acState + " " + (online ? "Srv:OK" : "Offline"));
#endif
}

// --------------------------------------------------------------------------------------
// 4. SERVO ACTUATION FUNCTION
// --------------------------------------------------------------------------------------
void setAcSwitch(int targetAngle, String newState) {
  if (currentServoAngle != targetAngle) {
    Serial.printf("[Servo] Actuating AC switch from %d deg to %d deg (AC -> %s)\n",
                  currentServoAngle, targetAngle, newState.c_str());
    acServo.write(targetAngle);
    currentServoAngle = targetAngle;
    currentAcState = newState;
    
    // Blink onboard LED to indicate mechanical actuation
    digitalWrite(STATUS_LED, HIGH);
    delay(200);
    digitalWrite(STATUS_LED, LOW);
  }
}

// --------------------------------------------------------------------------------------
// 5. LOCAL AUTONOMOUS FALLBACK (FAILSAFE)
// --------------------------------------------------------------------------------------
void executeOfflineFailsafe(float temp) {
  // If temp is cold enough, switch AC off
  if (temp <= FALLBACK_OFF_TEMP && currentAcState == "ON") {
    Serial.println("[Failsafe] Room cold (< 24.0°C). Switching AC OFF.");
    setAcSwitch(ANGLE_OFF, "OFF");
  } 
  // If temp is too hot, switch AC on
  else if (temp >= FALLBACK_ON_TEMP && currentAcState == "OFF") {
    Serial.println("[Failsafe] Room warm (> 26.5°C). Switching AC ON.");
    setAcSwitch(ANGLE_ON, "ON");
  }
}

// --------------------------------------------------------------------------------------
// 6. SETUP ROUTINE
// --------------------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n========================================================");
  Serial.println("  Adaptive Thermal Comfort - Hostel AC Controller v1.0");
  Serial.println("========================================================");

  pinMode(STATUS_LED, OUTPUT);
  digitalWrite(STATUS_LED, LOW);

  // Initialize DHT Sensor
  dht.begin();
  Serial.println("[Hardware] DHT11 sensor initialized on GPIO 4.");

  // Initialize Servo Motor
  ESP32PWM::allocateTimer(0);
  acServo.setPeriodHertz(50); // Standard 50Hz servo
  acServo.attach(SERVO_PIN, 500, 2400); // Standard micro servo pulse width
  acServo.write(ANGLE_OFF);
  currentServoAngle = ANGLE_OFF;
  Serial.println("[Hardware] SG90 Servo attached on GPIO 18 (Initialized to OFF: 0°).");

  // Initialize Display
  setupDisplay();

  // Connect to WiFi
  Serial.printf("[WiFi] Connecting to %s ", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int wifiAttempts = 0;
  while (WiFi.status() != WL_CONNECTED && wifiAttempts < 15) {
    delay(500);
    Serial.print(".");
    wifiAttempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WiFi] Connected successfully!");
    Serial.print("[WiFi] IP Address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\n[WiFi] Connection timed out. Operating in Autonomous Failsafe Mode.");
  }
}

// --------------------------------------------------------------------------------------
// 7. MAIN LOOP
// --------------------------------------------------------------------------------------
void loop() {
  unsigned long now = millis();

  if (now - lastTelemetryTime >= TELEMETRY_INTERVAL_MS) {
    lastTelemetryTime = now;

    // Read sensor data
    float t = dht.readTemperature();
    float h = dht.readHumidity();

    if (isnan(t) || isnan(h)) {
      Serial.println("[Sensor Error] Failed to read from DHT11 sensor! Checking connections...");
      return;
    }

    currentTemp = t;
    currentHum = h;
    Serial.printf("\n[Reading] DHT11 -> Temp: %.1f °C, Humidity: %.1f %%\n", t, h);

    // Communicate with backend if WiFi is connected
    if (WiFi.status() == WL_CONNECTED) {
      HTTPClient http;
      http.begin(SERVER_URL);
      http.addHeader("Content-Type", "application/json");

      // Prepare JSON payload
      StaticJsonDocument<128> reqDoc;
      reqDoc["temperature"] = t;
      reqDoc["humidity"] = h;
      String requestBody;
      serializeJson(reqDoc, requestBody);

      int httpResponseCode = http.POST(requestBody);

      if (httpResponseCode == 200) {
        isServerConnected = true;
        String response = http.getString();
        Serial.printf("[Backend] Response (%d): %s\n", httpResponseCode, response.c_str());

        // Parse JSON response from Flask
        StaticJsonDocument<512> resDoc;
        DeserializationError error = deserializeJson(resDoc, response);

        if (!error) {
          String backendAcState = resDoc["ac_state"].as<String>();
          int targetAngle = resDoc["servo_angle"].as<int>();
          targetOptimal = resDoc["target_optimal"].as<float>();
          const char* explanation = resDoc["explanation"];

          Serial.printf("[Comfort Decision] AC State: %s | Servo: %d deg | Note: %s\n",
                        backendAcState.c_str(), targetAngle, explanation);

          // Actuate physical switch
          setAcSwitch(targetAngle, backendAcState);
        } else {
          Serial.printf("[JSON] Deserialization error: %s\n", error.c_str());
        }
      } else {
        isServerConnected = false;
        Serial.printf("[Backend] HTTP POST error code: %d. Using fallback logic.\n", httpResponseCode);
        executeOfflineFailsafe(t);
      }

      http.end();
    } else {
      isServerConnected = false;
      Serial.println("[WiFi] Offline. Using local autonomous comfort thresholds.");
      executeOfflineFailsafe(t);
    }

    // Update on-device screen
    updateDisplay(currentTemp, currentHum, currentAcState, isServerConnected);
  }
}
