#!/usr/bin/env bash
# ==============================================================================
# Sortyx 2.0 — Raspberry Pi Autostart Installer
# ==============================================================================
# Run this once on the Raspberry Pi:
#   chmod +x autostart/install_autostart.sh
#   bash autostart/install_autostart.sh
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AUTOSTART_DIR="${HOME}/.config/autostart"
DESKTOP_FILE="${AUTOSTART_DIR}/sortyx.desktop"
LAUNCHER="${SCRIPT_DIR}/start_sortyx.sh"

echo "=========================================================="
echo " Installing Sortyx 2.0 Autostart on Raspberry Pi"
echo " Project directory: ${SCRIPT_DIR}"
echo "=========================================================="

# Ensure launcher is executable
chmod +x "${LAUNCHER}"
echo "✓ Made start_sortyx.sh executable"

# Create autostart directory if not exists
mkdir -p "${AUTOSTART_DIR}"

# Generate desktop autostart entry with actual paths
cat << EOF > "${DESKTOP_FILE}"
[Desktop Entry]
Type=Application
Name=Sortyx 2.0 Kiosk
Comment=Start Sortyx 2.0 Smart Waste Management on Boot
Exec=/bin/bash -c "sleep 4 && ${LAUNCHER}"
Terminal=false
Categories=Utility;Application;
StartupNotify=false
X-GNOME-Autostart-enabled=true
EOF

chmod +x "${DESKTOP_FILE}"
echo "✓ Created autostart entry: ${DESKTOP_FILE}"

echo ""
echo "=========================================================="
echo " Autostart successfully installed!"
echo " When the Raspberry Pi boots, it will automatically:"
echo " 1. Start the Sortyx 2.0 backend & frontend."
echo " 2. Open Chromium fullscreen displaying the ad video."
echo " 3. Wake up the sorting dashboard when a hand is detected."
echo " 4. Resume the ad video when no hands are in view."
echo "=========================================================="

