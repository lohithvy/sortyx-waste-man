#!/usr/bin/env bash
# =============================================================================
# Sortyx 2.0 — Raspberry Pi Fullscreen Kiosk Launcher
# Launches Chromium in true fullscreen kiosk mode on the connected HDMI or DSI screen.
# =============================================================================

# Disable display power management and screen blanking
xset s noblank || true
xset s off || true
xset -dpms || true

# Hide mouse cursor when idle
unclutter -idle 0.5 -root &

# Wait for local FastAPI backend and Vite server to respond
echo "Waiting for Sortyx service to become available..."
until curl -s http://localhost:8000/api/health > /dev/null; do
    sleep 1
done

echo "Sortyx backend is ready. Launching kiosk interface..."

# Launch Chromium in dedicated kiosk mode
chromium-browser \
    --noerrdialogs \
    --disable-infobars \
    --kiosk \
    --check-for-update-interval=31536000 \
    --disable-pinch \
    --overscroll-history-navigation=0 \
    --disable-features=Translate \
    --app=http://localhost:8000

