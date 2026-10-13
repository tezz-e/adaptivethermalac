---
name: flash-esp32-firmware
description: >-
  Builds, compiles, and flashes C++ Arduino firmware onto the ESP32-S3 microcontroller board using PlatformIO.
  Use this skill whenever the user asks to build, compile, flash, or upload firmware to the ESP32 / ESP32-S3,
  or when firmware changes need to be deployed to the physical hardware.
---

# Flash ESP32-S3 Firmware

Runbook for compiling and uploading firmware to the physical **ESP32-S3 DevKitC-1 N16R8** board via PlatformIO over USB Serial (`COM12`).

## Quick Execution Helper

You can execute the automated helper script to stop port-locking processes and flash in one step:

```powershell
powershell -ExecutionPolicy Bypass -File .agents/skills/flash-esp32-firmware/scripts/flash.ps1
```

---

## Step-by-Step Procedure

### 1. Release the Serial Port (`COM12`)
The background Flask server (`app.py`), started by `run_system.py`, runs a `usb_serial_bridge_worker` thread that holds `COM12` open with `pyserial`. If this is running, flashing will immediately fail with:
`PermissionError(13, 'Access is denied.') / Could not open COM12, the port is busy`.

**Action:** Stop any running Python instances holding the port before flashing:
```powershell
Get-Process | Where-Object { $_.ProcessName -match "python" } | Stop-Process -Force -ErrorAction SilentlyContinue
```

### 2. Verify Port Availability
Check that the ESP32-S3 (USB VID `303A`) is plugged in and detected:
```powershell
Get-PnpDevice -PresentOnly | Where-Object { $_.Class -eq "Ports" -and $_.FriendlyName -match "COM12" }
```

### 3. Build & Upload Firmware
The PlatformIO Core CLI is installed at:
`C:\Users\manee\.platformio\penv\Scripts\pio.exe`

**To build & upload to ESP32-S3:**
```powershell
& "C:\Users\manee\.platformio\penv\Scripts\pio.exe" run -t upload
```

*(Note: Run with `WaitMsBeforeAsync: 10000` or handle background task completion notification).*

**To verify / compile only (without flashing):**
```powershell
& "C:\Users\manee\.platformio\penv\Scripts\pio.exe" run
```

### 4. Verify Flash Output
Ensure the upload output concludes with:
- `Hash of data verified.`
- `Leaving... Hard resetting via RTS pin...`
- `========================= [SUCCESS] =========================`

### 5. Restart System Services
After the ESP32 reboot, start the Flask backend and Streamlit dashboard back up:
```powershell
py run_system.py
```
*(Run as daemon: `IsDaemon: true`).*

Confirm via logs that `POST /api/hostel/telemetry` receives `200 OK` responses from the ESP32.
