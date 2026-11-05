# Sortyx 2.0 — Troubleshooting

## Common Issues

### Backend

#### "GEMINI_API_KEY is not configured"
- Check that `backend/.env` exists and contains `GEMINI_API_KEY=<your-key>`
- Verify the key is valid at [Google AI Studio](https://aistudio.google.com/apikey)

#### "SUPABASE_URL is not configured"
- Check that `backend/.env` contains `SUPABASE_URL=https://your-project.supabase.co`
- Verify the URL in your Supabase dashboard → Settings → API

#### Camera not opening
- Check camera index: try `CAMERA_INDEX=1` if default `0` doesn't work
- On Linux: verify `/dev/video0` exists (`ls /dev/video*`)
- On Pi: ensure camera is enabled via `raspi-config`
- Try: `python -c "import cv2; cap = cv2.VideoCapture(0); print(cap.isOpened())"`

#### MediaPipe import error on Raspberry Pi
- Ensure you're using 64-bit Raspberry Pi OS
- Ensure Python version is 3.11 or 3.12
- Try: `pip install numpy==1.26.4` then reinstall mediapipe

#### Port 8000 already in use
- Find the process: `lsof -i :8000` (Linux) or `netstat -ano | findstr :8000` (Windows)
- Kill it or use a different port: `uvicorn app.main:app --port 8001`

### Frontend

#### Blank page after `npm run dev`
- Check browser console for errors
- Verify backend is running at `http://localhost:8000`
- Check Vite proxy configuration in `vite.config.ts`

#### WebSocket connection failed
- Ensure backend is running
- Check that CORS origins in `config/application.example.yaml` include your dev URL
- Try refreshing the page

### Hardware (Raspberry Pi)

#### I2C device not detected
```bash
# Check I2C is enabled
sudo raspi-config  # → Interface Options → I2C

# Check wiring
sudo i2cdetect -y 1
# Should show 0x40 for PCA9685
```

#### Servo not moving
- Check external 5V power supply is connected to PCA9685 V+
- Verify servo wire colors: signal (orange) → PWM, power (red) → V+, ground (brown) → GND
- Verify channel number matches `config/hardware.yaml`
- Test with simulation mode first

#### Ultrasonic sensor reading -1 or NaN
- Check voltage divider on ECHO pin (5V → 3.3V)
- Verify TRIGGER and ECHO GPIO numbers in config
- Check wiring connections
- Sensor may be disconnected — check `sensor_status` in dashboard

#### "Sensor not configured" on dashboard
- Update `config/hardware.yaml` with actual GPIO pins
- Restart the backend
- Set `SIMULATION_MODE=false` in `.env`

### Database

#### "Failed to connect to Supabase"
- Verify internet connection
- Check `SUPABASE_URL` and `SUPABASE_SECRET_KEY` in `backend/.env`
- Verify the Supabase project is active (not paused)

#### Events not appearing in statistics
- Only `sorting_status = 'completed'` events are counted
- Check the `sorting_events` table directly in Supabase dashboard
- Verify timezone — statistics use IST (Asia/Kolkata)

## Logs

Backend logs are printed to stdout by default. For file logging:

```yaml
# config/application.yaml
logging:
  file_enabled: true
  file_path: logs/sortyx.log
```

**Never share log files** without first checking they contain no API keys.

## Emergency Stop

If servos are stuck or behaving unexpectedly:

1. **API:** `POST http://localhost:8000/api/emergency-stop`
2. **Physical:** Disconnect the external 5V power supply to the PCA9685
3. **Software:** Stop the backend process (`Ctrl+C` or `kill`)

