"""
storage.py
================================================================================
Saves and reads sensor telemetry using Python's built-in CSV file support.

A CSV (Comma-Separated Values) file looks like a spreadsheet saved as plain text.
Each row is one sensor reading + control decision. Example row:
    2026-10-13 22:15:00,HOSTEL_D_312,27.4,63.0,25.0,23.5,26.5,ON,90,...

How file writing works in Python:
    We use the 'with open(...)' pattern (context manager). This guarantees the
    file is always closed properly even if an error occurs, which prevents data
    corruption.

        mode="w"  means "write" (creates a new file, overwrites if it exists)
        mode="a"  means "append" (adds to the END of the file without deleting it)

Why append and not write?
    Each time a new reading arrives we want to ADD a row, not erase old data.
    So every call to save_telemetry() uses mode="a".
================================================================================
"""

import os      # os.makedirs lets us create folders; os.path.exists checks if a file exists
import csv     # Python's built-in csv module handles reading/writing comma-separated files
import pandas as pd   # pandas is a library for working with tabular data (like a spreadsheet)
import config  # for CSV_FILE_PATH


# The fixed column order for every row saved to the CSV file.
# Must stay consistent — dashboard and graphs depend on these exact names.
CSV_HEADERS = [
    "timestamp",        # date and time of the reading
    "room_id",          # room identifier (e.g. "HOSTEL_D_312")
    "current_temp",     # room temperature from DHT11 in Celsius
    "current_humidity", # relative humidity from DHT11 in percent
    "target_optimal",   # ASHRAE or preferred target temperature
    "comfort_min",      # lower edge of comfort band (target - 1.5°C)
    "comfort_max",      # upper edge of comfort band (target + 1.5°C)
    "ac_state",         # "ON" or "OFF"
    "servo_angle",      # servo position in degrees (0 or 90)
    "explanation"       # plain-English reason for the AC decision
]


def ensure_csv_exists():
    """
    Creates the 'data/' folder and the CSV file (with a header row) if they
    do not already exist. Called automatically before every read or write.

    os.makedirs("data", exist_ok=True):
        Creates the folder. exist_ok=True means no error if it already exists.

    with open(..., mode="w") as file:
        Creates a brand-new file and writes the header row once.
        mode="w" overwrites, but we only reach this branch when the file is new.
    """
    os.makedirs("data", exist_ok=True)   # create the 'data/' folder if missing
    if not os.path.exists(config.CSV_FILE_PATH):
        with open(config.CSV_FILE_PATH, mode="w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(CSV_HEADERS)   # write column names as the first row


def save_telemetry(record_dict):
    """
    Appends one telemetry reading + control decision as a new row in the CSV.

    Parameters:
        record_dict (dict): A dictionary with keys matching CSV_HEADERS.
                            Missing keys are filled with safe defaults.

    Returns:
        bool: True if the write succeeded, False if an error occurred.

    dict.get(key, default):
        Safely reads a key from the dict. If the key does not exist, it returns
        the default value instead of crashing with a KeyError.

    mode="a" (append):
        Adds a new row at the END of the file. Existing rows are never touched.
    """
    ensure_csv_exists()
    try:
        with open(config.CSV_FILE_PATH, mode="a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            # Write one row — the order matches CSV_HEADERS exactly
            writer.writerow([
                record_dict.get("timestamp",        ""),
                record_dict.get("room_id",          "HOSTEL_D_312"),
                record_dict.get("current_temp",     0.0),
                record_dict.get("current_humidity", 0.0),
                record_dict.get("target_optimal",   0.0),
                record_dict.get("comfort_min",      0.0),
                record_dict.get("comfort_max",      0.0),
                record_dict.get("ac_state",         "OFF"),
                record_dict.get("servo_angle",      0),
                record_dict.get("explanation",      "")
            ])
        return True
    except Exception as error:
        # If writing fails (disk full, permission error, etc.) print the error and
        # return False so the caller can handle it gracefully.
        print(f"[Storage Error] Could not write to CSV: {error}")
        return False


def read_telemetry_history(limit=100):
    """
    Reads the most recent 'limit' rows from the CSV file and returns them as
    a pandas DataFrame (think of it as a Python object that looks like a table).

    Parameters:
        limit (int): How many of the most recent rows to return. Default 100.

    Returns:
        pd.DataFrame: The rows as a table, or an empty DataFrame if no data.

    What is a DataFrame?
        pandas.DataFrame is like a Python list of dicts but optimised for maths,
        filtering, and plotting. Each column is a list of values; each row is
        one reading. The dashboard uses it directly with st.dataframe() and
        Plotly charts.

    pd.to_datetime(..., errors="coerce"):
        Converts timestamp strings like "2026-10-13 22:15:00" into real datetime
        objects that pandas can sort and plot on a time axis.
        errors="coerce" turns any unparseable value into NaT (Not a Time) instead
        of crashing.

    df.dropna(subset=["timestamp"]):
        Removes rows where the timestamp could not be parsed (NaT values).

    df.tail(limit):
        Returns the last 'limit' rows (the most recent ones).
    """
    ensure_csv_exists()
    try:
        df = pd.read_csv(config.CSV_FILE_PATH)   # read the whole CSV into a DataFrame
        if df.empty:
            return pd.DataFrame()   # return an empty DataFrame if the file has no rows

        if "timestamp" in df.columns:
            # Convert the timestamp column from plain text to datetime objects for sorting/plotting
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
            df = df.dropna(subset=["timestamp"]).sort_values("timestamp")

        return df.tail(limit).reset_index(drop=True)   # return the newest 'limit' rows
    except Exception as error:
        print(f"[Storage Error] Could not read CSV: {error}")
        return pd.DataFrame()   # return empty table on any error so the dashboard doesn't crash
