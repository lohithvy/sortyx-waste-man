# Sortyx 2.0 — Hardware Wiring & Physical Integration Guide

> ⚠️ **CRITICAL SAFETY DIRECTIVES:**
> 1. All hardware parameters remain `NOT_CONFIGURED` (-1) in software until physically verified on the board.
> 2. Keep `SIMULATION_MODE=true` in `backend/.env` during initial wiring and testing.
> 3. **NEVER** power servo motors from the Raspberry Pi 4 5V or 3.3V pins. A dedicated external 5V/4-6A regulated DC power supply is mandatory.
> 4. The external power supply Ground and the Raspberry Pi Ground **MUST be connected together (Common Ground)** to establish a common electrical reference for PWM signals.
> 5. **NEVER** connect HC-SR04 ECHO pins directly to Raspberry Pi GPIOs without a voltage divider. ECHO outputs 5V logic which will permanently damage 3.3V Raspberry Pi SoC GPIO pins.

---

## 1. Components Required

| Component | Quantity | Purpose | Power Source |
|-----------|----------|---------|--------------|
| Raspberry Pi 4 Model B (4GB+) | 1 | Main application processor | Official USB-C 5V/3.0A power supply |
| PCA9685 16-channel 12-bit PWM driver | 1 | High-precision I2C servo controller | Logic from Pi 3.3V; Servos from External 5V |
| High-torque servo motors (MG996R / SG90) | 3 | Independent Bio, Organic, Non-Bio lids | External 5V DC power supply via PCA9685 V+ terminal |
| HC-SR04 or HC-SR04P ultrasonic distance sensors | 3 | Real-time bin fill monitoring & drop sensing | Pi 5V header pins (VCC); Grounds to Pi GND |
| Resistors: 1.0 kΩ (1/4W) | 3 | Voltage divider R1 for ECHO pins | Passive |
| Resistors: 2.0 kΩ (1/4W) | 3 | Voltage divider R2 for ECHO pins | Passive |
| Regulated 5V DC Power Supply (4A to 6A) | 1 | High-current servo motor power | Wall mains adapter |
| USB Webcam or Raspberry Pi Camera Module | 1 | Live detection & hand tracking | USB port or CSI camera ribbon slot |
| Breadboard, terminal blocks, jumper wires | As needed | Common ground and signal interconnects | — |

---

## 2. Raspberry Pi 4 Model B 40-Pin Header Reference

```
                   3.3V Power [ 1] [ 2] 5V Power
       (SDA1) GPIO 2 [ 3] [ 4] 5V Power
       (SCL1) GPIO 3 [ 5] [ 6] Ground
              GPIO 4 [ 7] [ 8] GPIO 14 (TXD0)
              Ground [ 9] [10] GPIO 15 (RXD0)
             GPIO 17 [11] [12] GPIO 18 (PCM_CLK)
             GPIO 27 [13] [14] Ground
             GPIO 22 [15] [16] GPIO 23
           3.3V Power [17] [18] GPIO 24
    (SPI0_MOSI) GPIO 10 [19] [20] Ground
    (SPI0_MISO) GPIO 9  [21] [22] GPIO 25
    (SPI0_SCLK) GPIO 11 [23] [24] GPIO 8 (CE0)
              Ground [25] [26] GPIO 7 (CE1)
             GPIO 0  [27] [28] GPIO 1
              GPIO 5 [29] [30] Ground
              GPIO 6 [31] [32] GPIO 12
             GPIO 13 [33] [34] Ground
             GPIO 19 [35] [36] GPIO 16
             GPIO 26 [37] [38] GPIO 20
              Ground [39] [40] GPIO 21
```

---

## 3. PCA9685 Servo Driver to Raspberry Pi 4

The PCA9685 connects via the hardware I2C-1 bus:

| PCA9685 Pin | Raspberry Pi 4 Pin | Raspberry Pi Pin Name | Wire Color Recommendation | Notes |
|-------------|-------------------|----------------------|---------------------------|-------|
| **VCC** | Pin 1 | 3.3V Power | Red | Powers the PCA9685 controller logic |
| **GND** | Pin 6 | Ground | Black | Logic ground |
| **SDA** | Pin 3 | GPIO 2 (SDA1) | Yellow | I2C Serial Data |
| **SCL** | Pin 5 | GPIO 3 (SCL1) | Blue | I2C Serial Clock |
| **OE** | Unconnected | — | — | Active-low output enable (pulled down internally) |
| **V+ (Screw Terminal)** | External +5V PSU | — | Heavy Gauge Red | **MANDATORY:** Dedicated external power |
| **GND (Screw Terminal)** | External GND PSU & Pi GND | Pin 9, 14, or 20 | Heavy Gauge Black | **COMMON GROUND** shared with Pi |

### Verifying I2C Connection on Raspberry Pi:
```bash
sudo raspi-config nonint do_i2c 0
sudo apt install -y i2c-tools
sudo i2cdetect -y 1
```
Expected output: The table should display `40` at row `40:`, confirming the PCA9685 chip is responding at `0x40`.

---

## 4. Servo Motor Connections

Each bin lid servo has a standard 3-pin plug that connects to a PCA9685 header channel:
- **PWM (Top pin, Yellow/Orange)**: Signal from PCA9685
- **V+ (Middle pin, Red)**: +5V from external power rail
- **GND (Bottom pin, Brown/Black)**: Ground return

### Channel Assignment Configuration (`config/hardware.yaml`):

| Bin Lid | Target Servo Channel | Calibrated Open Angle | Calibrated Close Angle | Pulse Range (µs) |
|---------|---------------------|----------------------|-----------------------|------------------|
| **Bio** | `NOT_CONFIGURED` (e.g. 0) | `NOT_CONFIGURED` (e.g. 90°) | `NOT_CONFIGURED` (e.g. 0°) | 500 – 2500 µs |
| **Organic** | `NOT_CONFIGURED` (e.g. 1) | `NOT_CONFIGURED` (e.g. 90°) | `NOT_CONFIGURED` (e.g. 0°) | 500 – 2500 µs |
| **Non-Bio** | `NOT_CONFIGURED` (e.g. 2) | `NOT_CONFIGURED` (e.g. 90°) | `NOT_CONFIGURED` (e.g. 0°) | 500 – 2500 µs |

---

## 5. HC-SR04 Ultrasonic Distance Sensors & Voltage Divider

HC-SR04 ultrasonic sensors run on 5V VCC and output a 5V logic pulse on ECHO. A 2-resistor voltage divider is **required** on each ECHO line:

### Voltage Divider Circuit:
```
           +5V Pulse
HC-SR04      │
ECHO Pin ────┴─── [ 1.0 kΩ (R1) ] ───┬───> Raspberry Pi GPIO Input (3.3V safe)
                                     │
                               [ 2.0 kΩ (R2) ]
                                     │
                                    GND
```
$$\text{Output Voltage} = 5.0\text{V} \times \frac{2.0\text{k}\Omega}{1.0\text{k}\Omega + 2.0\text{k}\Omega} = 3.33\text{V}$$

### Recommended Wiring Map:

| Sensor | Sensor Pin | Connection | Voltage Level |
|--------|------------|------------|---------------|
| **All Sensors** | VCC | Raspberry Pi Pin 2 or 4 (5V Rail) | 5.0V |
| **All Sensors** | GND | Raspberry Pi Pin 9, 14, 20, 30, or 34 (GND) | 0V (Ground) |
| **Bio Sensor** | TRIG | Raspberry Pi BCM GPIO (e.g. GPIO 23 / Pin 16) | 3.3V Out |
| **Bio Sensor** | ECHO | Through 1kΩ / 2kΩ divider to Pi BCM GPIO (e.g. GPIO 24 / Pin 18) | 3.3V In |
| **Organic Sensor** | TRIG | Raspberry Pi BCM GPIO (e.g. GPIO 17 / Pin 11) | 3.3V Out |
| **Organic Sensor** | ECHO | Through 1kΩ / 2kΩ divider to Pi BCM GPIO (e.g. GPIO 27 / Pin 13) | 3.3V In |
| **Non-Bio Sensor** | TRIG | Raspberry Pi BCM GPIO (e.g. GPIO 5 / Pin 29) | 3.3V Out |
| **Non-Bio Sensor** | ECHO | Through 1kΩ / 2kΩ divider to Pi BCM GPIO (e.g. GPIO 6 / Pin 31) | 3.3V In |

---

## 6. Sensor Calibration Procedure

To calculate accurate fill percentages:
1. Mount the ultrasonic sensor securely in the lid or center top of each bin pointing straight down to the bottom.
2. Ensure no obstructions (cables, mechanical hinges) cross the ultrasonic cone.
3. Run the interactive calibration CLI:
   ```bash
   python3 scripts/test_hardware_cli.py
   ```
4. Choose option **2 (Ultrasonic Sensors Test & Calibration)**.
5. Calibrate **Empty Distance**:
   - Ensure bin is completely empty.
   - The CLI takes 10 consecutive readings and records the median distance to the bottom floor.
6. Calibrate **Full Distance**:
   - Fill the bin to its maximum allowable fill line (or place a flat cardboard target at the full height).
   - The CLI takes 10 consecutive readings and records the median distance to the full line.
7. Enter these measured values into `config/hardware.yaml`:
   ```yaml
   ultrasonic_sensors:
     bio:
       empty_distance_cm: 32.5
       full_distance_cm: 6.0
   ```

---

## 7. Pre-Power Safety Checklist

Before setting `SIMULATION_MODE=false` in `backend/.env`:
- [ ] Visual inspection: No loose wire strands bridging neighboring pins on PCA9685 or 40-pin header.
- [ ] External power supply is strictly wired to PCA9685 V+ and GND screw terminals.
- [ ] Raspberry Pi GND and External Power GND are firmly connected together.
- [ ] Multimeter test: Check voltage on each HC-SR04 ECHO line while triggering; confirm peak voltage never exceeds 3.3V.
- [ ] Run `python3 scripts/diagnose_hardware.py` and confirm all subsystems show `✓ [OK]`.
- [ ] Test each servo individually using `python3 scripts/test_hardware_cli.py` before live automated segregation.
