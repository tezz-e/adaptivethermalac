"""
run_system.py
================================================================================
One-command launcher that starts BOTH servers with a single terminal command:
    py run_system.py

What it starts:
    1. Flask Backend (app.py) on port 5000  — receives data from the ESP32
    2. Streamlit Dashboard (dashboard.py) on port 8501 — the browser UI

Why two separate processes instead of one?
    Flask and Streamlit are two different web frameworks that each want to run
    their own blocking event loop. Running them in separate OS processes
    (using subprocess.Popen) is the cleanest way to let both run in parallel.

What is subprocess.Popen?
    subprocess.Popen() starts a new, independent process — like opening a second
    terminal window and running a command in it. The main script keeps running
    in its own loop (while True: time.sleep(1)) and both child processes keep
    running alongside it.

    When you press Ctrl+C, the KeyboardInterrupt exception is caught and
    proc.terminate() is called on each child to shut them down cleanly.
================================================================================
"""

import sys        # sys.executable gives the path to the current Python interpreter
import time       # time.sleep(1) pauses the loop for 1 second between checks
import subprocess # subprocess.Popen starts child processes (Flask + Streamlit)

# Use the same Python interpreter that is running this script.
# This ensures the correct virtual environment / installed packages are used.
PYTHON_EXE = sys.executable


def main():
    print("\n============================================================")
    print("  HOSTEL ADAPTIVE THERMAL COMFORT AC CONTROLLER")
    print("============================================================\n")

    processes = []   # keep a list of started processes so we can stop them all on Ctrl+C

    try:
        # --- Start Flask backend (app.py) ---
        # Popen() is non-blocking: it starts the process and immediately returns.
        # The Flask server keeps running in the background as a child process.
        print("[1/2] Starting Flask API Server (Port 5000)...")
        p_backend = subprocess.Popen([PYTHON_EXE, "app.py"])
        processes.append(p_backend)

        # Wait 1.5 seconds to give Flask time to bind to port 5000 before
        # Streamlit tries to connect to it (avoids "connection refused" on startup)
        time.sleep(1.5)

        # --- Start Streamlit dashboard (dashboard.py) ---
        # "python -m streamlit run dashboard.py" is equivalent to "streamlit run dashboard.py"
        # The extra flags set the port, disable the browser auto-open, and enforce dark theme.
        print("[2/2] Starting Streamlit Dashboard (Port 8501)...")
        p_dashboard = subprocess.Popen([
            PYTHON_EXE, "-m", "streamlit", "run", "dashboard.py",
            "--server.port",      "8501",
            "--server.headless",  "true",     # don't auto-open a browser tab
            "--client.toolbarMode", "minimal",
            "--theme.base",       "dark"
        ])
        processes.append(p_dashboard)

        print("\n------------------------------------------------------------")
        print("  Live Dashboard:   http://localhost:8501")
        print("  Flask API Server: http://127.0.0.1:5000")
        print("------------------------------------------------------------")
        print("Press Ctrl+C to stop both servers.\n")

        # Keep the launcher alive so child processes keep running.
        # time.sleep(1) prevents this loop from burning 100% CPU while waiting.
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        # Ctrl+C was pressed — shut down both child processes gracefully
        print("\nStopping servers...")
        for proc in processes:
            proc.terminate()   # sends SIGTERM to the child process
        print("Stopped.")


# Standard Python entry-point guard:
# This block only runs when you execute "py run_system.py" directly.
# If another file imports run_system, main() will NOT be called automatically.
if __name__ == "__main__":
    main()
