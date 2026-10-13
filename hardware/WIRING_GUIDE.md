# ESP32-S3 Hardware Wiring Guide

This guide details the exact pin connections for the **Hostel AC Physical Control Unit** running on the **ESP32-S3 DevKitC-1 N16R8** (Total BOM: ₹813).

---

## 1. Complete Pinout Table

| Component | Module Pin | ESP32-S3 Pin | Notes |
| :--- | :--- | :--- | :--- |
| **DHT11 Sensor** | `VCC (+)` | `3V3` | 3.3V power |
| | `DATA (out)` | **`GPIO 4`** | Digital temperature & humidity signal |
| | `GND (-)` | `GND` | Ground |
| **TTP223 Capacitive Touch Button** | `VCC` | `3V3` | 3.3V power |
| | `I/O (SIG)` | **`GPIO 10`** | Active-HIGH touch signal (instantly toggles servo `0°` / `180°`) |
| | `GND` | `GND` | Ground |
| **1.3" SH1106 I2C OLED Display** | `VCC` | `3V3` | 3.3V power |
| | `GND` | `GND` | Ground |
| | `SDA` | **`GPIO 8`** | Hardware I2C Data |
| | `SCL` | **`GPIO 9`** | Hardware I2C Clock |
| **SG90 Micro Servo Motor** | `Orange / Yellow (PWM)` | **`GPIO 18`** | 50Hz PWM control signal (`0°` = OFF, `180°` = ON) |
| | `Red (VCC +5V)` | **External 5V `+`** | External 5V adapter provides clean torque current |
| | `Brown / Black (GND)` | **External `GND` + ESP32 `GND`** | **IMPORTANT:** Tie external adapter `GND` and ESP32 `GND` together! |

---

## 2. On-Screen OLED Status Badges

The 1.3" SH1106 OLED screen shows live hardware diagnostics so you always know what the board is doing:
* **`DHT:LIVE`** — Reading real temperature & humidity from the physical DHT11 on `GPIO 4`. (`DHT:SIM` if sensor wire is loose).
* **`SRV:RDY` / `SRV:ON`** — Servo initialized on `GPIO 18` (`0°` when AC is OFF, `180°` when AC is ON).
* **`TCH`** — Appears on the middle row when you toggle the AC manually using the capacitive touch button on `GPIO 10`.
* **Bottom Row:** Displays WiFi connection status or `[OFFLINE AUTO]` if running on autonomous failsafe.
