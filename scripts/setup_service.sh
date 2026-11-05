#!/usr/bin/env bash
# =============================================================================
# Sortyx 2.0 — Raspberry Pi 5 Systemd Autostart & Safe Shutdown Configuration
# Automatically starts backend, hardware interfaces, webcam, ultrasonic monitoring,
# and React dashboard upon Raspberry Pi 5 boot.
# Enforces safe shutdown handlers (0° servo reset, camera release, GPIO cleanup).
# =============================================================================

set -e

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: Please run this script with sudo: sudo bash scripts/setup_service.sh"
    exit 1
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_USER="${SUDO_USER:-pi}"

echo "================================================================="
echo "   SORTYX 2.0 — SYSTEMD SERVICE INSTALLER (RASPBERRY PI 5)"
echo "================================================================="
echo "Configuring services for user: '$SERVICE_USER'"
echo "Project root directory:       '$PROJECT_ROOT'"

# 1. Backend Service (FastAPI + Camera + PCA9685 Servos + HC-SR04 Sensors)
echo ">> [1/2] Installing /etc/systemd/system/sortyx-backend.service..."
cat <<EOF > /etc/systemd/system/sortyx-backend.service
[Unit]
Description=Sortyx 2.0 Smart Waste Segregation Backend (Raspberry Pi 5)
Documentation=https://github.com/Sortyx/Sortyx2
After=network-online.target time-sync.target
Wants=network-online.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$PROJECT_ROOT/backend
Environment=PYTHONUNBUFFERED=1
ExecStartPre=/bin/sh -c 'fuser -k 8000/tcp || true'
ExecStart=$PROJECT_ROOT/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5
TimeoutStopSec=15
KillSignal=SIGTERM
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# 2. Frontend Service (React Dashboard)
echo ">> [2/2] Installing /etc/systemd/system/sortyx-frontend.service..."
cat <<EOF > /etc/systemd/system/sortyx-frontend.service
[Unit]
Description=Sortyx 2.0 Kiosk React Dashboard Service
Documentation=https://github.com/Sortyx/Sortyx2
After=sortyx-backend.service network.target
Wants=sortyx-backend.service
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$PROJECT_ROOT/frontend
ExecStartPre=/bin/sh -c 'fuser -k 5173/tcp || true'
ExecStart=/usr/bin/npm run preview -- --host 0.0.0.0 --port 5173
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Reload and enable
systemctl daemon-reload
systemctl enable sortyx-backend.service
systemctl enable sortyx-frontend.service

echo "================================================================="
echo "✓ Systemd services successfully configured and enabled on boot!"
echo "================================================================="
echo "Management Commands:"
echo "  sudo systemctl start sortyx-backend      # Start backend now"
echo "  sudo systemctl start sortyx-frontend     # Start frontend now"
echo "  sudo systemctl status sortyx-backend     # Check backend status"
echo "  sudo systemctl status sortyx-frontend    # Check frontend status"
echo "  sudo systemctl restart sortyx-backend    # Restart backend"
echo "  sudo systemctl stop sortyx-backend       # Stop backend (initiates safe hardware shutdown)"
echo "  sudo journalctl -u sortyx-backend -f     # Live log stream"
echo "  sudo journalctl -u sortyx-frontend -f    # Live frontend log stream"

