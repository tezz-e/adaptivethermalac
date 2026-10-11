"""
test_system.py
================================================================================
What is this file?
This is our verification test script. Running 'py test_system.py' automatically checks:
1. Does the weather service fetch temperature properly?
2. Does the ASHRAE math formula calculate the right numbers?
3. Does the night sleep offset work properly?
4. Does the AC hysteresis turn off when cold and on when warm?
5. Does the CSV file logging work?
6. Does the Flask API answer properly?
================================================================================
"""

import unittest
import weather_service
import comfort_model
import storage
from app import app


class TestThermalComfortSystem(unittest.TestCase):

    def test_01_weather_fetching(self):
        """Test if weather_service returns a valid dictionary."""
        data = weather_service.fetch_live_weather()
        print(f"\n[Test 1] Weather: {data['temperature_c']}°C, {data['humidity_pct']}% ({data['source']})")
        self.assertIn("temperature_c", data)
        self.assertGreater(data["temperature_c"], 0.0)

    def test_02_ashrae_math(self):
        """Test ASHRAE 55 formula: 17.8 + 0.31 * 30.0 = 27.1°C"""
        temp = comfort_model.calculate_ashrae_comfort(30.0)
        self.assertAlmostEqual(temp, 27.1, places=1)

        # Test night offset (+1.0°C)
        night_band = comfort_model.get_hostel_comfort_band(30.0, current_hour=23)
        day_band = comfort_model.get_hostel_comfort_band(30.0, current_hour=14)
        self.assertTrue(night_band["is_night_mode"])
        self.assertFalse(day_band["is_night_mode"])
        self.assertEqual(night_band["optimal_temp"], day_band["optimal_temp"] + 1.0)
        print(f"[Test 2] Day Optimal: {day_band['optimal_temp']}°C | Night Optimal: {night_band['optimal_temp']}°C")

    def test_03_hysteresis_decision(self):
        """Test AC decision: cold room -> OFF, warm room -> ON."""
        band = comfort_model.get_hostel_comfort_band(30.0, current_hour=2)

        # If room drops to 22.0°C (below min_temp), AC must turn OFF
        state, angle, reason = comfort_model.evaluate_hostel_ac_decision(
            room_temp=22.0, min_temp=band["min_temp"], max_temp=band["max_temp"], last_ac_state="ON"
        )
        self.assertEqual(state, "OFF")
        self.assertEqual(angle, 0)

        # If room warms to 32.0°C (above max_temp), AC must turn ON
        state, angle, reason = comfort_model.evaluate_hostel_ac_decision(
            room_temp=32.0, min_temp=band["min_temp"], max_temp=band["max_temp"], last_ac_state="OFF"
        )
        self.assertEqual(state, "ON")
        self.assertEqual(angle, 90)
        print(f"[Test 3] Hysteresis Logic Passed: Cold->OFF(0°), Warm->ON(90°)")

    def test_04_csv_storage(self):
        """Test saving and reading from CSV."""
        sample = {
            "timestamp": "2026-10-11 10:00:00",
            "room_id": "TEST_ROOM",
            "current_temp": 24.0,
            "current_humidity": 50.0,
            "target_optimal": 26.0,
            "comfort_min": 24.5,
            "comfort_max": 27.5,
            "ac_state": "OFF",
            "servo_angle": 0,
            "explanation": "Test write"
        }
        success = storage.save_telemetry(sample)
        self.assertTrue(success)
        df = storage.read_telemetry_history(limit=5)
        self.assertFalse(df.empty)
        print(f"[Test 4] CSV Storage Passed: {len(df)} rows read successfully")

    def test_05_flask_api_endpoint(self):
        """Test Flask API response using test client."""
        client = app.test_client()
        response = client.post("/api/hostel/telemetry", json={"temperature": 23.0, "humidity": 50.0})
        self.assertEqual(response.status_code, 200)
        json_data = response.get_json()
        self.assertEqual(json_data["status"], "success")
        self.assertIn("ac_state", json_data)
        print(f"[Test 5] Flask API Passed: Received AC={json_data['ac_state']}, Servo={json_data['servo_angle']}°")

    def test_06_runtime_reduction(self):
        """Test calculation of overnight run-time reduction."""
        stats = comfort_model.calculate_runtime_reduction(hours_ac_off=4.0, total_sleep_hours=8.0)
        self.assertEqual(stats["runtime_reduction_pct"], 50.0)
        self.assertEqual(stats["hours_cooling_off"], 4.0)
        self.assertEqual(stats["degree_hours_avoided"], 16.0)
    def test_07_resident_preference(self):
        """Test user preferred temperature override."""
        # Day: Preferred 24.0°C
        band_day = comfort_model.get_hostel_comfort_band(30.0, current_hour=14, preferred_temp=24.0)
        self.assertEqual(band_day["optimal_temp"], 24.0)
        self.assertEqual(band_day["min_temp"], 22.5)
        self.assertEqual(band_day["max_temp"], 25.5)

        # Night: Preferred 24.0°C + 1.0°C sleep offset = 25.0°C
        band_night = comfort_model.get_hostel_comfort_band(30.0, current_hour=23, preferred_temp=24.0)
        self.assertEqual(band_night["optimal_temp"], 25.0)
        print(f"[Test 7] Resident Preference Passed: Day Target={band_day['optimal_temp']}°C, Night Target={band_night['optimal_temp']}°C")


if __name__ == "__main__":
    unittest.main()
