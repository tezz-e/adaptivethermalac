"""
storage.py
================================================================================
Handles saving sensor telemetry to a CSV file and reading it back into pandas
using Python's 'with open(...)' context manager.
================================================================================
"""

import os
import csv
import pandas as pd
import config

CSV_HEADERS = [
    "timestamp",
    "room_id",
    "current_temp",
    "current_humidity",
    "target_optimal",
    "comfort_min",
    "comfort_max",
    "ac_state",
    "servo_angle",
    "explanation"
]


def ensure_csv_exists():
    """Creates the data folder and CSV header row if they do not exist yet."""
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(config.CSV_FILE_PATH):
        with open(config.CSV_FILE_PATH, mode="w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(CSV_HEADERS)


def save_telemetry(record_dict):
    """Appends a telemetry reading and control decision row to the CSV file."""
    ensure_csv_exists()
    try:
        with open(config.CSV_FILE_PATH, mode="a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow([
                record_dict.get("timestamp", ""),
                record_dict.get("room_id", "HOSTEL_D_312"),
                record_dict.get("current_temp", 0.0),
                record_dict.get("current_humidity", 0.0),
                record_dict.get("target_optimal", 0.0),
                record_dict.get("comfort_min", 0.0),
                record_dict.get("comfort_max", 0.0),
                record_dict.get("ac_state", "OFF"),
                record_dict.get("servo_angle", 0),
                record_dict.get("explanation", "")
            ])
        return True
    except Exception as error:
        print(f"[Storage Error] Could not write to CSV: {error}")
        return False


def read_telemetry_history(limit=100):
    """Reads the most recent 'limit' rows from the CSV file as a pandas DataFrame."""
    ensure_csv_exists()
    try:
        df = pd.read_csv(config.CSV_FILE_PATH)
        if df.empty:
            return pd.DataFrame()
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
            df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
        return df.tail(limit).reset_index(drop=True)
    except Exception as error:
        print(f"[Storage Error] Could not read CSV: {error}")
        return pd.DataFrame()
