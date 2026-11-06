#!/usr/bin/env bash
# ==============================================================================
# Sortyx 2.0 — All-In-One Automated Setup & Run for Raspberry Pi
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=========================================================="
echo " Setting up Sortyx 2.0 on Raspberry Pi..."
echo " Directory: ${SCRIPT_DIR}"
echo "=========================================================="

# 1. Install system prerequisites
echo "[1/5] Installing system packages..."
sudo apt update
sudo apt install -y python3-venv python3-pip nodejs npm i2c-tools python3-smbus curl

# 2. Enable I2C interface for PCA9685 servos
echo "[2/5] Enabling I2C bus..."
sudo raspi-config nonint do_i2c 0 2>/dev/null || true

# 3. Setup Python Backend Virtual Environment
echo "[3/5] Setting up Python backend..."
cd "${SCRIPT_DIR}/backend"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-rpi.txt

# Ensure SIMULATION_MODE=false for physical hardware
if [ -f ".env" ]; then
    sed -i 's/SIMULATION_MODE=true/SIMULATION_MODE=false/g' .env
fi

# 4. Setup Frontend Packages
echo "[4/5] Setting up Frontend..."
cd "${SCRIPT_DIR}/frontend"
npm install

# 5. Launch Application
echo "[5/5] Launching Sortyx 2.0 (Backend, Frontend, and Kiosk Video)..."
cd "${SCRIPT_DIR}"
chmod +x start_sortyx.sh
./start_sortyx.sh
