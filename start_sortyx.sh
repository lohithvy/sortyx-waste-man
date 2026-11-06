#!/usr/bin/env bash
# ==============================================================================
# Sortyx 2.0 — Raspberry Pi Kiosk Auto-Start Launcher
# ==============================================================================
# This script starts the Sortyx 2.0 backend, frontend, and opens the fullscreen
# dashboard with the ad video screensaver on Raspberry Pi boot.
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${SCRIPT_DIR}/backend"
FRONTEND_DIR="${SCRIPT_DIR}/frontend"

echo "=========================================================="
echo " Starting Sortyx 2.0 Smart Waste Management System"
echo " Working directory: ${SCRIPT_DIR}"
echo "=========================================================="

# Prevent display sleep / screensaver on Raspberry Pi OS
xset s off 2>/dev/null || true
xset -dpms 2>/dev/null || true
xset s noblank 2>/dev/null || true

# 1. Start Python Backend
echo "[1/3] Starting Sortyx 2.0 FastAPI Backend..."
cd "${BACKEND_DIR}"

if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
elif [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
echo "Backend started (PID: ${BACKEND_PID})"

# Wait for backend to be ready
echo "Waiting for backend API on port 8000..."
MAX_WAIT=20
WAIT_COUNT=0
until curl -s http://localhost:8000/api/status >/dev/null 2>&1 || [ ${WAIT_COUNT} -eq ${MAX_WAIT} ]; do
    sleep 1
    WAIT_COUNT=$((WAIT_COUNT+1))
done

if [ ${WAIT_COUNT} -eq ${MAX_WAIT} ]; then
    echo "Warning: Backend took longer than expected, proceeding..."
else
    echo "Backend is live and responding."
fi

# 2. Start Frontend Dev Server
echo "[2/3] Starting Frontend Server on port 5173..."
cd "${FRONTEND_DIR}"
npx vite --host 0.0.0.0 --port 5173 &
FRONTEND_PID=$!
echo "Frontend started (PID: ${FRONTEND_PID})"

sleep 3

# 3. Launch Chromium in Fullscreen Kiosk Mode
echo "[3/3] Opening Chromium Fullscreen Kiosk..."

CHROME_BIN=""
for b in chromium-browser chromium google-chrome; do
    if command -v $b >/dev/null 2>&1; then
        CHROME_BIN=$b
        break
    fi
done

if [ -n "${CHROME_BIN}" ]; then
    ${CHROME_BIN} \
        --kiosk \
        --start-fullscreen \
        --noerrdialogs \
        --disable-infobars \
        --disable-session-crashed-bubble \
        --disable-restore-session-state \
        --check-for-update-interval=31536000 \
        --autoplay-policy=no-user-gesture-required \
        --overscroll-history-navigation=0 \
        --disable-pinch \
        "http://localhost:5173"
else
    echo "Chromium not found in PATH. Please open http://localhost:5173 in your browser."
fi

# Cleanup on exit
trap "kill ${BACKEND_PID} ${FRONTEND_PID} 2>/dev/null || true" EXIT

