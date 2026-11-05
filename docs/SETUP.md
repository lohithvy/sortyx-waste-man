# Sortyx 2.0 — Setup Guide

## Development Setup (Laptop)

### Prerequisites

- Python 3.11+ (3.13 works for laptop development)
- Node.js 18+ (22.x recommended)
- npm 10+
- Git

### 1. Clone the Project

```bash
git clone <repository-url>
cd Sortyx2
```

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (Linux/macOS)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create environment file
cp .env.example .env
# Edit .env with your actual API keys
```

**Required environment variables in `backend/.env`:**

| Variable | Where to Get |
|----------|-------------|
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/apikey) |
| `SUPABASE_URL` | Supabase dashboard → Settings → API |
| `SUPABASE_SECRET_KEY` | Supabase dashboard → Settings → API → service_role |
| `DEVICE_API_SECRET` | Generate: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |

**Start the backend:**

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start dev server
npm run dev
```

Open `http://localhost:5173` in your browser.

### 4. Development Configuration

For laptop development, use these settings in `backend/.env`:

```env
CAMERA_SOURCE=WEBCAM
CAMERA_INDEX=0
SIMULATION_MODE=true
LOG_LEVEL=DEBUG
```

This enables:
- Webcam via OpenCV (index 0)
- Simulated servo and ultrasonic hardware
- Debug-level logging

---

## Raspberry Pi 4 Deployment

### Prerequisites

- Raspberry Pi 4 Model B (4GB or 8GB recommended)
- Raspberry Pi OS (64-bit Bookworm or Bullseye)
- MicroSD card (32GB+ Class 10 / A2)
- Official Raspberry Pi USB-C 5V/3A power supply (for the Pi)
- External Regulated 5V/4-6A DC power supply (for the PCA9685 servos)
- Display (HDMI monitor or official DSI touch screen)

---

### Step 1: Automated Installation

Clone the repository and run the automated installation script:

```bash
cd /home/pi
git clone <repository-url> Sortyx2
cd Sortyx2

# Run automated deployment script (installs dependencies, sets permissions, builds frontend)
bash scripts/install_pi.sh
```

---

### Step 2: Configure Environment & Hardware

1. **Configure Credentials (`backend/.env`)**:
   ```bash
   cp backend/.env.example backend/.env
   chmod 600 backend/.env
   nano backend/.env
   ```
   Set:
   - `GEMINI_API_KEY`: Google Gemini API key
   - `SUPABASE_URL`: Supabase project URL
   - `SUPABASE_SECRET_KEY`: Supabase service_role secret
   - `CAMERA_SOURCE`: `RASPBERRY_PI` (for Ribbon Camera) or `WEBCAM` (for USB webcam)
   - `SIMULATION_MODE`: `true` (keep `true` until wiring is verified)

2. **Configure Pinout & Channels (`config/hardware.yaml`)**:
   Fill in your actual PCA9685 servo channels (0-15) and BCM GPIO pins for ultrasonic sensors.

---

### Step 3: Hardware Diagnostics

Run the non-destructive connection diagnostic tool to verify all hardware interfaces:

```bash
python3 scripts/diagnose_hardware.py
```

Expected output confirms:
- Host architecture & Raspberry Pi hardware model
- I2C bus active at `/dev/i2c-1` and PCA9685 responding at `0x40`
- GPIO memory access active
- Camera interface detected

---

### Step 4: Sensor & Servo Interactive Calibration

Use the safety-guarded interactive CLI to test each lid and calibrate ultrasonic fill levels:

```bash
python3 scripts/test_hardware_cli.py
```

- **Option 1**: Test Bio, Organic, and Non-Bio servos individually (requires explicit confirmation).
- **Option 2**: Calibrate Empty and Full bin distances for each bin using live 10-sample median filtering.
- **Option 3**: Emergency stop (instantly commands all lids closed).

---

### Step 5: Autostart Background Service

Install the systemd unit to start the Sortyx backend on boot:

```bash
sudo bash scripts/setup_service.sh

# Verify live status
sudo systemctl status sortyx
```

---

### Step 6: Fullscreen Kiosk Mode Display

To automatically launch Chromium in fullscreen kiosk mode on boot:

```bash
bash scripts/run_kiosk.sh
```

Or add to your desktop autostart configuration (`~/.config/autostart/sortyx-kiosk.desktop`):
```ini
[Desktop Entry]
Type=Application
Name=Sortyx 2.0 Kiosk
Exec=/home/pi/Sortyx2/scripts/run_kiosk.sh
```

---

## Running Automated Tests

```bash
cd backend
source .venv/bin/activate
pytest tests/ -v
```

---

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues and solutions.

