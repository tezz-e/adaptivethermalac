"""
run_system.py
================================================================================
One-command launcher that starts both:
1. Flask Backend Server (app.py) on Port 5000 (communicates with ESP32-S3)
2. Streamlit Live Dashboard (dashboard.py) on Port 8501
================================================================================
"""

import sys
import time
import subprocess

PYTHON_EXE = sys.executable


def main():
    print("\n============================================================")
    print("  HOSTEL ADAPTIVE THERMAL COMFORT AC CONTROLLER")
    print("============================================================\n")

    processes = []
    try:
        print("[1/2] Starting Flask API Server (Port 5000)...")
        p_backend = subprocess.Popen([PYTHON_EXE, "app.py"])
        processes.append(p_backend)
        time.sleep(1.5)

        print("[2/2] Starting Streamlit Dashboard (Port 8501)...")
        p_dashboard = subprocess.Popen([
            PYTHON_EXE, "-m", "streamlit", "run", "dashboard.py",
            "--server.port", "8501",
            "--server.headless", "true",
            "--client.toolbarMode", "minimal",
            "--theme.base", "dark"
        ])
        processes.append(p_dashboard)

        print("\n------------------------------------------------------------")
        print("  Live Dashboard:   http://localhost:8501")
        print("  Flask API Server: http://127.0.0.1:5000")
        print("------------------------------------------------------------")
        print("Press Ctrl+C to stop both servers.\n")

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping servers...")
        for proc in processes:
            proc.terminate()
        print("Stopped.")


if __name__ == "__main__":
    main()
