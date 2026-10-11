"""
run_system.py
================================================================================
What is this file?
This is our one-click runner script. Running 'py run_system.py' starts BOTH:
1. The Flask API server (app.py) on Port 5000 (for the ESP32)
2. The Streamlit Dashboard (dashboard.py) on Port 8501 (in your web browser)

How does it work?
It uses Python's built-in 'subprocess' module to run both programs at the same time.
================================================================================
"""

import sys
import time
import subprocess
import argparse

PYTHON_EXE = sys.executable


def start_backend():
    """Starts the Flask server (app.py)."""
    return subprocess.Popen([PYTHON_EXE, "app.py"])


def start_dashboard():
    """Starts the Streamlit dashboard (dashboard.py)."""
    return subprocess.Popen([PYTHON_EXE, "-m", "streamlit", "run", "dashboard.py", "--server.port", "8501", "--server.headless", "true"])


def main():
    parser = argparse.ArgumentParser(description="Adaptive Thermal Comfort Launcher")
    parser.add_argument("--backend-only", action="store_true", help="Launch only Flask API backend")
    parser.add_argument("--dashboard-only", action="store_true", help="Launch only Streamlit dashboard")
    args = parser.parse_args()

    print("\n==================================================================")
    print("  ADAPTIVE THERMAL COMFORT ADVISORY & CONTROL SYSTEM")
    print("  BTech First Year Project - Campus Hostels")
    print("==================================================================\n")

    processes = []

    try:
        if args.backend_only:
            print("🚀 Launching Flask API Backend (Port 5000)...")
            p = start_backend()
            processes.append(p)
            print(" -> API active at: http://127.0.0.1:5000")
            p.wait()

        elif args.dashboard_only:
            print("🚀 Launching Streamlit Notion-Style Dashboard (Port 8501)...")
            p = start_dashboard()
            processes.append(p)
            print(" -> Dashboard active at: http://localhost:8501")
            p.wait()

        else:
            print("🚀 [1/2] Starting Flask API Backend (Port 5000)...")
            p_back = start_backend()
            processes.append(p_back)
            time.sleep(2)

            print("🚀 [2/2] Starting Streamlit Notion-Style Dashboard (Port 8501)...")
            p_dash = start_dashboard()
            processes.append(p_dash)

            print("\n------------------------------------------------------------------")
            print("✅ SYSTEM READY AND OPERATIONAL!")
            print("🌐 Web Dashboard:    http://localhost:8501")
            print("🔌 Flask API Server: http://127.0.0.1:5000")
            print("📡 ESP32 Endpoint:   http://<YOUR_IP>:5000/api/hostel/telemetry")
            print("------------------------------------------------------------------")
            print("Press Ctrl+C at any time in this window to stop both programs.\n")

            while True:
                time.sleep(1)

    except KeyboardInterrupt:
        print("\n🛑 Shutting down services safely...")
        for p in processes:
            p.terminate()
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                p.kill()
        print("Done. Goodbye!")


if __name__ == "__main__":
    main()
