#!/usr/bin/env bash
# =============================================================================
# Sortyx 2.0 — Raspberry Pi 5 Automated Deployment & Installation Script
# Target OS: Raspberry Pi OS 64-bit (Debian Bookworm)
# Target Hardware: Raspberry Pi 5 (RP1 I/O Southbridge)
# =============================================================================

set -e

echo "================================================================="
echo "   SORTYX 2.0 — RASPBERRY PI 5 AUTOMATED SYSTEM SETUP"
echo "================================================================="

# 1. Require non-root user with sudo privileges
if [ "$(id -u)" -eq 0 ]; then
    echo "ERROR: Do not run this script as root directly."
    echo "Run as user 'pi' (or your regular user) with: bash scripts/install_pi.sh"
    exit 1
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo ">> Project Directory: $PROJECT_ROOT"

# 2. Update package repositories & install system dependencies
echo ">> [1/6] Installing Linux system dependencies and libraries..."
sudo apt-get update
sudo apt-get install -y \
    python3-venv \
    python3-pip \
    python3-dev \
    i2c-tools \
    libcamera-apps \
    libcamera-dev \
    libgl1 \
    libglib2.0-0 \
    libatlas-base-dev \
    curl \
    git

# 3. Enable hardware interfaces via raspi-config
echo ">> [2/6] Enabling Raspberry Pi I2C and Camera hardware interfaces..."
if command -v raspi-config >/dev/null 2>&1; then
    sudo raspi-config nonint do_i2c 0
    sudo raspi-config nonint do_camera 0
    echo "✓ I2C and Camera enabled in kernel device-tree."
else
    echo "ℹ raspi-config not found (skipping non-interactive hardware flags)."
fi

# 4. User group permissions for non-root hardware access
echo ">> [3/6] Granting user '$(whoami)' hardware permissions (i2c, gpio, video)..."
sudo usermod -aG i2c,gpio,video "$USER" || true

# 5. Backend Python virtual environment and dependencies
echo ">> [4/6] Setting up Python virtual environment and dependencies..."
cd "$PROJECT_ROOT/backend"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

# Install Raspberry Pi 5 hardware drivers (adafruit-circuitpython-servokit, rpi-lgpio, smbus2)
echo ">> Installing hardware drivers (adafruit-circuitpython-servokit, rpi-lgpio, smbus2)..."
pip install adafruit-circuitpython-servokit rpi-lgpio smbus2

# 6. Frontend installation & production build
echo ">> [5/6] Building frontend kiosk dashboard..."
cd "$PROJECT_ROOT/frontend"
if command -v npm >/dev/null 2>&1; then
    npm install
    npm run build
    echo "✓ Frontend built successfully to frontend/dist/."
else
    echo "⚠️ Node.js / npm not detected. To install Node 22: curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt install -y nodejs"
fi

# 7. Hardware config template setup
echo ">> [6/6] Verifying hardware configuration file..."
cd "$PROJECT_ROOT"
if [ ! -f "config/hardware.yaml" ]; then
    cp config/hardware.example.yaml config/hardware.yaml
    echo "✓ Created config/hardware.yaml template."
    echo "  ⚠️ IMPORTANT: Edit config/hardware.yaml to enter actual PCA9685 channels and GPIO pins."
fi

if [ ! -f "backend/.env" ]; then
    cp backend/.env.example backend/.env
    echo "✓ Created backend/.env template. Update with your Gemini API key and Supabase credentials."
fi

echo "================================================================="
echo "   SORTYX 2.0 INSTALLATION COMPLETE!"
echo "================================================================="
echo "Next Steps:"
echo "1. Run hardware diagnostics:"
echo "   python3 scripts/diagnose_hardware.py"
echo "2. Wire your hardware following docs/HARDWARE_WIRING.md"
echo "3. Calibrate your servos and ultrasonic sensors:"
echo "   python3 scripts/test_hardware_cli.py"
echo "4. Set up autostart kiosk service:"
echo "   sudo bash scripts/setup_service.sh"
echo "5. Please log out and back in (or reboot) for group permissions to take effect:"
echo "   sudo reboot"
echo "================================================================="

