# Automated build, flash, and restart script for ESP32-S3 firmware
$ErrorActionPreference = "Stop"

Write-Host "==> [1/4] Stopping processes holding serial port (COM12)..." -ForegroundColor Cyan
Get-Process | Where-Object { $_.ProcessName -match "python" } | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

Write-Host "==> [2/4] Verifying COM12 connection..." -ForegroundColor Cyan
$portAvailable = [System.IO.Ports.SerialPort]::GetPortNames() -contains "COM12"
if (-not $portAvailable) {
    Write-Warning "COM12 was not found in SerialPort list! Proceeding anyway in case OS enumerates on access."
}

$pioPath = "C:\Users\manee\.platformio\penv\Scripts\pio.exe"
if (-not (Test-Path $pioPath)) {
    $pioCmd = Get-Command "pio" -ErrorAction SilentlyContinue
    if ($pioCmd) {
        $pioPath = $pioCmd.Source
    } else {
        Write-Error "PlatformIO executable not found at $pioPath"
        exit 1
    }
}

Write-Host "==> [3/4] Compiling and uploading firmware with PlatformIO..." -ForegroundColor Cyan
& $pioPath run -t upload
if ($LASTEXITCODE -ne 0) {
    Write-Error "PlatformIO upload failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

Write-Host "==> [4/4] Firmware flashed successfully!" -ForegroundColor Green
Write-Host "To restart host services, run: py run_system.py"
