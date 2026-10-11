# ESP32 Hardware Wiring Guide

This guide details the complete hardware connections for the **Hostel AC Physical Control Unit** prototype (Total BOM: ₹813).

---

## 1. Component Pinout Connections

| Component | Pin Label | ESP32 Pin | Wire Color Recommendation | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **DHT11 Sensor** | VCC (+) | 3V3 / VIN | Red | Connect to 3.3V (or 5V if module has onboard regulator) |
| | GND (-) | GND | Black | Common Ground |
| | DATA (out) | GPIO 4 | Yellow / Blue | If 3-pin module, resistor is builtin. If 4-pin bare, add 10kΩ pullup to 3.3V |
| **SG90 Servo Motor** | VCC (Red) | VIN (5V) | Red | Servo needs 5V for mechanical torque |
| | GND (Brown) | GND | Black | Common Ground |
| | PWM (Orange/Yellow) | GPIO 18 | Orange | Connected to ESP32 PWM pin |
| **0.96" OLED Display (I2C)** | VCC | 3V3 | Red | Operates on 3.3V |
| | GND | GND | Black | Common Ground |
| | SDA | GPIO 21 | Green | ESP32 Hardware I2C SDA |
| | SCL | GPIO 22 | White / Blue | ESP32 Hardware I2C SCL |
| **(Alternative) 16x2 I2C LCD** | VCC | VIN (5V) | Red | 16x2 LCD backlight requires 5V |
| | GND | GND | Black | Common Ground |
| | SDA | GPIO 21 | Green | Shared I2C Bus |
| | SCL | GPIO 22 | White / Blue | Shared I2C Bus |

---

## 2. Servo Mechanical Mounting on Mock AC Switch

1. Take the single-arm horn that comes with the SG90 servo.
2. In the `test_servo_dht.ino` or with power disconnected, position the arm such that:
   - At **0°**, the arm rests away or in the switch OFF position.
   - At **90°**, the arm pivots against the toggle switch rocker, physically pressing it to the ON position.
3. Secure the servo bracket using double-sided mounting foam or a small 3D-printed/cardboard rig next to the switch.

---

## 3. Quick Troubleshooting Checklist

- **Sensor reads NaN (Not a Number)**:
  - Check that DHT11 data pin is seated firmly into GPIO 4.
  - Verify VCC is on 3.3V and GND is connected.
- **Servo jitters or ESP32 resets on servo movement**:
  - The servo draws sudden peak current (~200mA). Ensure ESP32 is powered from a decent 5V 1A+ USB port or phone charger (not an unpowered USB hub).
- **OLED screen is blank**:
  - Verify I2C address is `0x3C` (default for most 0.96" SSD1306 displays).
  - Ensure SDA is GPIO 21 and SCL is GPIO 22.
