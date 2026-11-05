# Sortyx 2.0 — AI-Powered Smart Waste Segregation System

<div align="center">

**Automated waste classification and sorting using AI, computer vision, and servo-controlled bins.**

</div>

---

## Overview

Sortyx 2.0 is a hardware-integrated waste segregation system that runs on a Raspberry Pi 4. It uses a camera with MediaPipe hand tracking to detect when someone presents waste, sends the image to Google Gemini for classification, and automatically opens the correct bin lid using PCA9685-controlled servo motors.

### Waste Categories

| Category | Examples | Bin Color |
|----------|----------|-----------|
| **Bio** | Paper, cardboard, untreated natural materials | Purple |
| **Organic** | Food waste, banana peels, vegetable scraps | Green |
| **Non-Bio** | Plastic, glass, metal | Blue |

### Key Features

- Real-time hand tracking and object detection
- AI-powered waste classification via Google Gemini
- Three independently controlled servo-driven bin lids
- Ultrasonic bin fill-level monitoring
- Live dashboard with system status
- Supabase cloud database for event logging
- Offline event queue for network resilience
- Hazardous material detection and safety alerts
- Configurable hardware — no hardcoded pin mappings
- Image privacy — no waste images are stored

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  React Frontend                  │
│        (Single-window kiosk dashboard)           │
└──────────────────┬──────────────────────────────┘
                   │ WebSocket + REST
┌──────────────────▼──────────────────────────────┐
│              FastAPI Backend (Python)             │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │  Camera   │ │  Gemini  │ │  State Machine   │ │
│  │  Service  │ │  Service │ │  (10 states)     │ │
│  └──────────┘ └──────────┘ └──────────────────┘ │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │  Servo   │ │Ultrasonic│ │  Supabase        │ │
│  │  Service │ │  Service │ │  Service         │ │
│  └────┬─────┘ └────┬─────┘ └───────┬──────────┘ │
└───────┼────────────┼───────────────┼────────────┘
        │            │               │
   ┌────▼────┐  ┌────▼────┐   ┌─────▼─────┐
   │ PCA9685 │  │ HC-SR04 │   │ Supabase  │
   │ + Servos│  │ Sensors │   │  Cloud    │
   └─────────┘  └─────────┘   └───────────┘
```

---

## Quick Start

### Prerequisites

- Python 3.11+ (3.12 recommended for Raspberry Pi)
- Node.js 18+
- Git

### 1. Clone and configure

```bash
cd Sortyx2

# Backend
cp backend/.env.example backend/.env
# Edit backend/.env with your actual API keys

# Hardware config (optional — for Pi deployment)
cp config/hardware.example.yaml config/hardware.yaml
cp config/application.example.yaml config/application.yaml
```

### 2. Backend setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 3. Frontend setup

```bash
cd frontend
npm install
npm run dev
```

### 4. Open the dashboard

Navigate to `http://localhost:5173` in your browser.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | Yes | Google Gemini API key |
| `GEMINI_MODEL` | Yes | Gemini model name |
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_SECRET_KEY` | Yes | Supabase service role key |
| `DEVICE_API_SECRET` | Yes | Device authentication secret |
| `CAMERA_SOURCE` | No | `WEBCAM` (default) or `RASPBERRY_PI` |
| `CAMERA_INDEX` | No | Webcam device index (default: 0) |
| `SIMULATION_MODE` | No | `true` for laptop testing (default) |
| `LOG_LEVEL` | No | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

> ⚠️ **Never commit `backend/.env` to version control.** See [SECURITY.md](SECURITY.md) for details.

---

## Project Structure

```
Sortyx2/
├── backend/           # Python FastAPI backend
│   ├── app/
│   │   ├── api/       # REST endpoints & WebSocket
│   │   ├── core/      # Config, logging, security
│   │   ├── models/    # Enums and data models
│   │   ├── schemas/   # Pydantic request/response schemas
│   │   ├── services/  # Business logic services
│   │   ├── hardware/  # Hardware abstraction layer
│   │   ├── state_machine/  # Sorting state machine
│   │   └── utils/     # Validators and helpers
│   └── tests/         # Pytest test suite
├── frontend/          # React TypeScript dashboard
│   └── src/
│       ├── components/  # UI components
│       ├── screens/     # Full-screen views
│       ├── services/    # API client
│       ├── hooks/       # Custom React hooks
│       ├── state/       # State management
│       ├── styles/      # CSS modules
│       └── assets/      # Branding images
├── config/            # Hardware & app configuration
├── docs/              # Documentation
├── scripts/           # Utility scripts
└── supabase/          # Edge functions
```

---

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Hardware Wiring](docs/HARDWARE_WIRING.md)
- [Database Schema](docs/DATABASE.md)
- [Security](docs/SECURITY.md)
- [Setup Guide](docs/SETUP.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)

---

## Security

See [SECURITY.md](SECURITY.md) for the complete security policy.

**Critical rules:**
- API keys are stored only in `backend/.env`
- No secrets in frontend code, browser storage, or Git
- Backend binds to localhost only
- All cloud communication uses HTTPS
- Device authentication via HMAC-signed requests
- No waste images are stored anywhere

---

## License

Private project — Sortyx Waste Management.

