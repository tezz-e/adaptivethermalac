"""
storage.py
================================================================================
What is this file?
This module handles saving sensor data to a CSV file and reading it back.

Why do we import 'csv'?
'csv' is Python's built-in module for reading and writing Comma-Separated Values (CSV)
files (like spreadsheets in Excel).

Why do we import 'pandas'?
'pandas' is a data analysis library that reads CSV files into clean tables (DataFrames)
which our Streamlit dashboard can plot as graphs.

Why do we use 'with open(...)'?
'with open(...)' is a Python context manager. It safely opens the file, writes the
data, and automatically closes the file when done so no files get corrupted.
================================================================================
"""

import os
import csv
import pandas as pd
import config


def ensure_csv_exists():
    """Checks if the data folder and CSV file exist. If not, creates them with headers."""
    # Create the 'data' directory if it doesn't already exist
    os.makedirs("data", exist_ok=True)

    # If the CSV file does not exist yet, write the header row
    if not os.path.exists(config.CSV_FILE_PATH):
        with open(config.CSV_FILE_PATH, mode="w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow([
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
            ])


def save_telemetry(record_dict):
    """
    Appends a new reading and decision record into the CSV file.
    
    Args:
        record_dict: A dictionary containing temperature, humidity, AC state, etc.
    """
    ensure_csv_exists()

    try:
        # 'a' mode stands for 'append' (adds a new line at the end without erasing old data)
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


def read_telemetry_history(limit=50):
    """
    Reads the last 'limit' records from the CSV file into a pandas DataFrame.
    Filters test records and sorts chronologically by timestamp.
    Returns an empty DataFrame if no data is found.
    """
    ensure_csv_exists()

    try:
        df = pd.read_csv(config.CSV_FILE_PATH)
        if df.empty:
            return pd.DataFrame()
        # Filter out test records if present
        if "room_id" in df.columns:
            df = df[df["room_id"] != "TEST_ROOM"]
        # Parse timestamps and sort chronologically
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.sort_values("timestamp")
        # Return only the most recent rows
        return df.tail(limit).reset_index(drop=True)
    except Exception as error:
        print(f"[Storage Error] Could not read CSV: {error}")
        return pd.DataFrame()
