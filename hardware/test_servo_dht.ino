/*
 * Standalone Hardware Test Sketch
 * Use this to verify your DHT11 sensor and SG90 servo motor without WiFi or Flask.
 * 
 * Pins:
 * - DHT11 Data Pin: GPIO 4
 * - Servo Signal Pin: GPIO 18
 */

#include <DHT.h>
#include <ESP32Servo.h>

#define DHTPIN 4
#define DHTTYPE DHT11
#define SERVO_PIN 18

DHT dht(DHTPIN, DHTTYPE);
Servo testServo;

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n--- HARDWARE DIAGNOSTIC TEST ---");
  
  dht.begin();
  
  ESP32PWM::allocateTimer(0);
  testServo.setPeriodHertz(50);
  testServo.attach(SERVO_PIN, 500, 2400);

  Serial.println("Testing Servo sweep: moving to 0° (AC OFF)...");
  testServo.write(0);
  delay(1500);

  Serial.println("Testing Servo sweep: moving to 90° (AC ON)...");
  testServo.write(90);
  delay(1500);

  Serial.println("Returning to 0°...");
  testServo.write(0);
  delay(1000);

  Serial.println("Setup completed. Beginning continuous DHT11 readings...\n");
}

void loop() {
  float temp = dht.readTemperature();
  float hum = dht.readHumidity();

  if (isnan(temp) || isnan(hum)) {
    Serial.println("[ERROR] Failed to read from DHT11 sensor! Check VCC, GND, and GPIO 4 wiring.");
  } else {
    Serial.printf("[DIAGNOSTIC] Temperature: %.1f °C | Humidity: %.1f %%\n", temp, hum);
    
    // Quick test: if finger warms sensor > 28°C, sweep servo to 90°
    if (temp >= 28.0) {
      Serial.println(" -> High temp detected: Actuating servo to ON (90°)");
      testServo.write(90);
    } else {
      Serial.println(" -> Normal temp: Keeping servo at OFF (0°)");
      testServo.write(0);
    }
  }

  delay(2000);
}
