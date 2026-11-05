# Sortyx 2.0 — System Architecture

## Overview

Sortyx 2.0 follows a layered, modular architecture with clear separation of concerns:

```
┌───────────────────────────────────────────────────────┐
│                    Presentation Layer                   │
│              React + TypeScript + Vite                  │
│         (Single-window kiosk dashboard)                │
└─────────────────────┬─────────────────────────────────┘
                      │ WebSocket (real-time) + REST API
┌─────────────────────▼─────────────────────────────────┐
│                    Application Layer                    │
│                  FastAPI (Python)                       │
│  ┌─────────────────────────────────────────────────┐  │
│  │              State Machine Engine                │  │
│  │   IDLE → DETECTED → ACTIVE → CAPTURE →          │  │
│  │   CLASSIFY → RESULT → SERVO → DEPOSIT →         │  │
│  │   CLOSING → IDLE                                 │  │
│  └─────────────────────────────────────────────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐             │
│  │ Camera   │ │ Hand     │ │ Gemini   │             │
│  │ Service  │ │ Tracking │ │ Service  │             │
│  └──────────┘ └──────────┘ └──────────┘             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐             │
│  │ Classif. │ │ Sorting  │ │ Supabase │             │
│  │ Validator│ │ Service  │ │ Service  │             │
│  └──────────┘ └──────────┘ └──────────┘             │
└─────────────────────┬─────────────────────────────────┘
                      │
┌─────────────────────▼─────────────────────────────────┐
│                   Hardware Layer                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐              │
│  │ PCA9685  │ │ GPIO     │ │ Camera   │              │
│  │ Driver   │ │ Controller│ │ HAL     │              │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘              │
│       │            │            │                      │
│  ┌────▼────┐  ┌────▼────┐  ┌───▼────┐                │
│  │ 3 Servo │  │ 3 Ultra │  │ Camera │                │
│  │ Motors  │  │ Sensors │  │ Module │                │
│  └─────────┘  └─────────┘  └────────┘                │
└───────────────────────────────────────────────────────┘
                      │
┌─────────────────────▼─────────────────────────────────┐
│                   Cloud Layer                          │
│         Supabase (PostgreSQL + RLS)                    │
│         Google Gemini API                              │
└───────────────────────────────────────────────────────┘
```

## Module Dependency Graph

```
main.py
├── api/routes.py          → REST endpoints
├── api/websocket.py       → WebSocket manager
├── core/config.py         → Settings from .env + YAML
├── core/security.py       → Device auth, rate limiting
├── services/
│   ├── sorting_service.py → Main orchestrator
│   │   ├── camera_service.py
│   │   ├── hand_tracking_service.py
│   │   ├── gemini_service.py
│   │   ├── classification_service.py
│   │   ├── servo_service.py
│   │   ├── ultrasonic_service.py
│   │   └── supabase_service.py
│   └── (each service is independently testable)
├── state_machine/
│   ├── machine.py         → State machine engine
│   └── states.py          → Individual state definitions
└── hardware/
    ├── pca9685.py         → Servo driver abstraction
    ├── gpio_controller.py → Ultrasonic sensor GPIO
    └── camera.py          → Camera HAL factory
```

## Communication Patterns

### Frontend ↔ Backend

| Channel | Protocol | Purpose |
|---------|----------|---------|
| REST API | HTTP (localhost) | Actions, queries, status |
| WebSocket | WS (localhost) | Real-time state, sensor, classification updates |

### Backend ↔ Cloud

| Service | Protocol | Purpose |
|---------|----------|---------|
| Gemini | HTTPS | Waste image classification |
| Supabase | HTTPS | Database CRUD, event logging |

### Backend ↔ Hardware

| Interface | Protocol | Purpose |
|-----------|----------|---------|
| PCA9685 | I2C | Servo control |
| HC-SR04 | GPIO | Ultrasonic distance reading |
| Camera | USB/CSI | Video capture |

## Data Flow

### Classification Pipeline

```
Camera Frame (memory only)
    ↓
Hand Detection (MediaPipe)
    ↓
Stable Frame Selection
    ↓
Base64 Encoding (in memory)
    ↓
Gemini API Request (HTTPS)
    ↓
JSON Response Parsing
    ↓
Backend Validation (confidence, category, hazard check)
    ↓
Servo Command (if validated)
    ↓
Image Buffer Discarded ← NEVER saved to disk
```

### Event Recording Pipeline

```
Classification Result
    ↓
Sorting Event Created (status: pending)
    ↓
Servo Activated → Event Updated (bin_opening)
    ↓
Deposit Detected → Event Updated (deposit_confirmed)
    ↓
Lid Closed → Event Updated (completed)
    ↓
Supabase Sync (or offline queue)
```

## Simulation Mode

When `SIMULATION_MODE=true`:
- Servo commands are logged but not sent to hardware
- Ultrasonic readings return configurable test values
- Camera uses laptop webcam via OpenCV
- All simulated data is clearly marked in logs and UI
- Simulated readings are NEVER displayed as real sensor data

## Error Recovery

| Failure | Recovery Action |
|---------|----------------|
| Camera disconnected | Return to IDLE, show error |
| Gemini timeout | No servo activation, show error |
| Gemini malformed response | No servo activation, show error |
| Servo timeout | Emergency close, error state |
| Sensor failure | Mark bin as unavailable |
| Internet disconnected | Queue events locally, retry |
| Application crash | Conservative restart, verify servo states |

