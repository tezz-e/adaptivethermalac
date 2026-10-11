"""
Hardware Simulator for ESP32 & DHT11 Sensor.
Allows testing and demonstrating the full end-to-end system without physical hardware connected.
Sends real-time telemetry packets to the Flask backend API and displays responses.
Demonstrates: requests, time manipulation, simulation algorithms, exception handling.
"""

import sys
import time
import requests
import argparse

DEFAULT_API_URL = "http://127.0.0.1:5000/api/hostel/telemetry"


def run_interactive_mode(url: str):
    """Allows manual entry of temperature and humidity values."""
    print("\n=======================================================")
    print("   ESP32 HARDWARE SIMULATOR - INTERACTIVE MODE")
    print("=======================================================")
    print(f"Target Backend: {url}")
    print("Type a temperature (e.g. 23.5) and press Enter to send.")
    print("Type 'q' to quit.\n")

    while True:
        try:
            val = input("Enter Room Temperature (°C) [or 'q' to quit]: ").strip()
            if val.lower() == 'q':
                break
            temp = float(val)
            hum = 55.0

            payload = {"temperature": temp, "humidity": hum}
            resp = requests.post(url, json=payload, timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                print(f" -> [ESP32 RECEIVED] AC State: {data['ac_state']} | "
                      f"Servo: {data['servo_angle']}° | "
                      f"Comfort Band: [{data['comfort_min']}°C - {data['comfort_max']}°C]")
                print(f"    Reason: {data['explanation']}\n")
            else:
                print(f" -> [ERROR] Backend returned HTTP {resp.status_code}: {resp.text}\n")
        except ValueError:
            print("Please enter a valid numeric temperature.\n")
        except requests.RequestException as e:
            print(f" -> [NETWORK ERROR] Could not connect to {url}: {e}\n")


def run_automatic_mode(url: str, interval_sec: int = 4):
    """
    Simulates physical thermal dynamics:
    - Starts at 28.5°C.
    - If AC turns ON, room gradually cools down (-0.4°C per cycle).
    - Once AC turns OFF, room slowly warms up (+0.3°C per cycle).
    - Demonstrates natural hysteresis behavior!
    """
    print("\n=======================================================")
    print("   ESP32 HARDWARE SIMULATOR - AUTOMATED DEMO MODE")
    print("=======================================================")
    print(f"Target Backend: {url}")
    print("Simulating realistic room heating/cooling cycle...")
    print("Press Ctrl+C to stop.\n")

    current_temp = 28.0
    current_humidity = 58.0
    last_ac_state = "OFF"

    step = 1
    while True:
        try:
            payload = {
                "temperature": round(current_temp, 1),
                "humidity": round(current_humidity, 1)
            }
            
            resp = requests.post(url, json=payload, timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                last_ac_state = data.get("ac_state", "OFF")
                servo = data.get("servo_angle", 0)
                band_min = data.get("comfort_min", 24.5)
                band_max = data.get("comfort_max", 27.5)
                optimal = data.get("target_optimal", 26.0)
                note = data.get("explanation", "")

                print(f"[{step:03d}] Temp: {current_temp:.1f}°C | Hum: {current_humidity:.0f}% | "
                      f"AC: [{last_ac_state:3s}] (Servo: {servo:2d}°) | "
                      f"Target: {optimal:.1f}°C [{band_min:.1f} - {band_max:.1f}°C]")
                print(f"      {note}")

                # Simulate thermal physics:
                if last_ac_state == "ON":
                    # Cooling down
                    current_temp -= 0.4
                    current_humidity -= 0.2
                else:
                    # AC is OFF -> ambient room heat warms up room
                    current_temp += 0.3
                    current_humidity += 0.2

                # Keep in realistic physical bounds
                current_temp = max(21.0, min(31.0, current_temp))

            else:
                print(f"[{step:03d}] Server error {resp.status_code}")

            step += 1
            time.sleep(interval_sec)

        except requests.RequestException as e:
            print(f"[Offline] Backend not responding at {url}. Retrying in {interval_sec}s...")
            time.sleep(interval_sec)
        except KeyboardInterrupt:
            print("\nSimulator stopped by user.")
            break


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ESP32 Telemetry Simulator")
    parser.add_argument("--url", default=DEFAULT_API_URL, help="Backend API endpoint URL")
    parser.add_argument("--interactive", action="store_true", help="Run interactive prompt mode")
    parser.add_argument("--interval", type=int, default=4, help="Seconds between telemetry updates")

    args = parser.parse_args()

    if args.interactive:
        run_interactive_mode(args.url)
    else:
        run_automatic_mode(args.url, args.interval)
