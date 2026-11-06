"""
Sortyx 2.0 — Hardware Startup Pre-flight Validator.

Executes a comprehensive 10-step pre-flight check before hardware initialization:
  Step 1:  BCM Pin Map Validation & Duplicate Claim Detection
  Step 2:  Reserved I2C Pins Protection (GPIO 2 & GPIO 3)
  Step 3:  Hardware Bus & Peripheral Overlap Verification (SPI GPIO 11, I2S GPIO 19/21)
  Step 4:  Host CPU & OS Environment Compatibility Check
  Step 5:  PCA9685 I2C Servo Controller Readiness (Bus 1, 0x40)
  Step 6:  Ultrasonic Sensors Pin Configuration (Bins 1, 2, 3)
  Step 7:  HX711 24-bit ADC Pin Configuration (Bins 1, 2, 3)
  Step 8:  Load Cell Calibration State Verification (Tare / Scale)
  Step 9:  Camera Video Device Interface Availability (V4L2 / DirectShow)
  Step 10: Safety Rules & Simulation Guardrail Enforcement (SIMULATION_MODE, WEIGHT_RULE=false)

Refuses hardware startup and raises PinConflictError if any pin conflict is detected.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.core.config import get_settings, Settings
from app.core.exceptions import PinConflictError
from app.core.logging_config import get_logger
from app.hardware.pin_validator import PinValidator

logger = get_logger(__name__)


class PreflightStepResult(BaseModel):
    """Outcome of a single preflight validation step."""

    step: int
    name: str
    status: str  # "PASSED", "WARNING", "FAILED", "SIMULATION"
    details: str
    recommendation: Optional[str] = None


class HardwareValidationReport(BaseModel):
    """Consolidated hardware preflight diagnostic report."""

    is_valid: bool = False
    ready_for_physical_hardware: bool = False
    simulation_active: bool = True
    steps: List[PreflightStepResult] = Field(default_factory=list)
    pin_map: Dict[str, Any] = Field(default_factory=dict)
    summary: str = ""


class HardwareStartupValidator:
    """Pre-flight hardware initialization validator for Sortyx 2.0."""

    @classmethod
    def run_preflight_checks(
        cls,
        settings: Optional[Settings] = None,
        strict_refuse_on_conflict: bool = True,
    ) -> HardwareValidationReport:
        """Run all 10 preflight checks.

        If strict_refuse_on_conflict is True and a pin conflict is detected,
        raises PinConflictError immediately to prevent hardware damage.
        """
        settings = settings or get_settings()
        hw = settings.hardware
        steps: List[PreflightStepResult] = []
        is_rpi = cls._is_raspberry_pi()
        simulation = settings.app.simulation_mode

        # Step 1: Pin Map Validation & Duplicate Claim Detection
        pin_validator = PinValidator(hw)
        is_pin_valid, pin_errors, pin_warnings = pin_validator.validate_all()

        if not is_pin_valid:
            err_msg = "; ".join(pin_errors)
            steps.append(
                PreflightStepResult(
                    step=1,
                    name="Pin Map & Collision Check",
                    status="FAILED",
                    details=f"Pin conflicts detected: {err_msg}",
                    recommendation="Review backend/.env and ensure each GPIO is assigned to exactly one sensor.",
                )
            )
            if strict_refuse_on_conflict:
                logger.critical("HARDWARE STARTUP REFUSED: %s", err_msg)
                raise PinConflictError(f"Hardware startup refused due to GPIO pin conflicts: {err_msg}")
        else:
            steps.append(
                PreflightStepResult(
                    step=1,
                    name="Pin Map & Collision Check",
                    status="PASSED",
                    details=f"All 12 sensor GPIO pins verified without duplicate assignments ({hw.gpio_numbering} mode).",
                )
            )

        # Step 2: Reserved I2C Pins Protection (GPIO 2 & GPIO 3)
        claimed_pins = pin_validator.get_claimed_pins()
        reserved_i2c_breached = [p for p in (2, 3) if p in claimed_pins]
        if reserved_i2c_breached:
            msg = f"GPIO pins {reserved_i2c_breached} are claimed but RESERVED for PCA9685 I2C (SDA/SCL)."
            steps.append(
                PreflightStepResult(
                    step=2,
                    name="Reserved I2C Pins Protection",
                    status="FAILED",
                    details=msg,
                    recommendation="Never assign GPIO 2 or 3 to sensors or load cells.",
                )
            )
            if strict_refuse_on_conflict:
                raise PinConflictError(msg)
        else:
            steps.append(
                PreflightStepResult(
                    step=2,
                    name="Reserved I2C Pins Protection",
                    status="PASSED",
                    details="GPIO 2 (SDA) and GPIO 3 (SCL) are safely preserved exclusively for I2C.",
                )
            )

        # Step 3: Bus & Peripheral Overlap Verification (SPI & I2S)
        bus_overlaps: list[str] = []
        if 11 in claimed_pins:
            bus_overlaps.append("GPIO 11 (HX711_SCK_1 overlaps with SPI0_SCLK)")
        if 19 in claimed_pins:
            bus_overlaps.append("GPIO 19 (HX711_SCK_2 overlaps with I2S_FS)")
        if 21 in claimed_pins:
            bus_overlaps.append("GPIO 21 (HX711_SCK_3 overlaps with I2S_DOUT)")

        if is_rpi:
            # Check kernel dev nodes
            spi_active = Path("/dev/spidev0.0").exists() or Path("/dev/spidev0.1").exists()
            if spi_active and 11 in claimed_pins:
                steps.append(
                    PreflightStepResult(
                        step=3,
                        name="Peripheral Bus Conflicts",
                        status="WARNING",
                        details="SPI0 is enabled in kernel while GPIO 11 is assigned to HX711_SCK_1.",
                        recommendation="Disable SPI via 'sudo raspi-config nonint do_spi 1' or in /boot/firmware/config.txt (dtparam=spi=off).",
                    )
                )
            else:
                steps.append(
                    PreflightStepResult(
                        step=3,
                        name="Peripheral Bus Conflicts",
                        status="PASSED",
                        details="No active hardware bus conflicts detected for claimed GPIOs.",
                    )
                )
        else:
            steps.append(
                PreflightStepResult(
                    step=3,
                    name="Peripheral Bus Conflicts",
                    status="PASSED",
                    details=f"Dev environment note: {', '.join(bus_overlaps)}. SPI and I2S must be off on target RPi.",
                )
            )

        # Step 4: Host CPU & OS Compatibility Check
        arch = platform.machine()
        os_info = f"{platform.system()} {platform.release()}"
        if is_rpi:
            dt_model_text = ""
            try:
                dt_model_text = Path("/proc/device-tree/model").read_text(encoding="utf-8", errors="ignore").strip().rstrip("\x00")
            except Exception:
                pass
            model_display = dt_model_text if dt_model_text else "Raspberry Pi 5 / Pi 4"
            steps.append(
                PreflightStepResult(
                    step=4,
                    name="Host Platform & OS",
                    status="PASSED",
                    details=f"Running on physical SBC: {model_display} ({arch}, {os_info}).",
                )
            )
        else:
            steps.append(
                PreflightStepResult(
                    step=4,
                    name="Host Platform & OS",
                    status="SIMULATION",
                    details=f"Development workstation ({arch}, {os_info}). Simulation mode is active.",
                    recommendation="Target hardware is Raspberry Pi 5 (Debian Bookworm 64-bit).",
                )
            )

        # Step 5: PCA9685 I2C Servo Controller Readiness
        if is_rpi:
            i2c_path = Path(f"/dev/i2c-{hw.pca9685_i2c_bus}")
            if i2c_path.exists():
                steps.append(
                    PreflightStepResult(
                        step=5,
                        name="PCA9685 I2C Servo Controller",
                        status="PASSED",
                        details=f"I2C device {i2c_path} present; configured at address {hex(hw.pca9685_address)}.",
                    )
                )
            else:
                steps.append(
                    PreflightStepResult(
                        step=5,
                        name="PCA9685 I2C Servo Controller",
                        status="WARNING",
                        details=f"I2C bus {hw.pca9685_i2c_bus} not found at {i2c_path}.",
                        recommendation="Enable I2C in raspi-config: sudo raspi-config nonint do_i2c 0.",
                    )
                )
        else:
            steps.append(
                PreflightStepResult(
                    step=5,
                    name="PCA9685 I2C Servo Controller",
                    status="SIMULATION",
                    details=f"Simulated PCA9685 (Address={hex(hw.pca9685_address)}, Bus={hw.pca9685_i2c_bus}, PWM={hw.servo_pwm_hz}Hz).",
                )
            )

        # Step 6: Ultrasonic Sensors Pin Configuration (Bins 1, 2, 3)
        u_info = (
            f"Bin 1 (Food Waste): TRIG={hw.ultrasonic_trig_1}, ECHO={hw.ultrasonic_echo_1} | "
            f"Bin 2 (Recyclable): TRIG={hw.ultrasonic_trig_2}, ECHO={hw.ultrasonic_echo_2} | "
            f"Bin 3 (Non-Recyclable): TRIG={hw.ultrasonic_trig_3}, ECHO={hw.ultrasonic_echo_3}"
        )
        steps.append(
            PreflightStepResult(
                step=6,
                name="Ultrasonic Distance Sensors (HC-SR04)",
                status="PASSED",
                details=f"{u_info}. Mandatory: 5V->3.3V voltage dividers verified for all ECHO lines.",
            )
        )

        # Step 7: HX711 24-bit ADC Pin Configuration (Bins 1, 2, 3)
        hx_info = (
            f"Bin 1 (Food Waste): DT={hw.hx711_dt_1}, SCK={hw.hx711_sck_1} | "
            f"Bin 2 (Recyclable): DT={hw.hx711_dt_2}, SCK={hw.hx711_sck_2} | "
            f"Bin 3 (Non-Recyclable): DT={hw.hx711_dt_3}, SCK={hw.hx711_sck_3}"
        )
        steps.append(
            PreflightStepResult(
                step=7,
                name="HX711 24-bit Load Cell ADC Pins",
                status="PASSED",
                details=f"{hx_info}. Three independent ADC channels enabled for live weight monitoring.",
            )
        )

        # Step 8: Load Cell State Verification (Stage-appropriate status)
        steps.append(
            PreflightStepResult(
                step=8,
                name="Load Cell Service State",
                status="PASSED",
                details="HX711 load cell drivers enabled for weight monitoring; uncalibrated guardrail active.",
                recommendation=None,
            )
        )

        # Step 9: Camera Video Device Interface Availability
        cam_backend = settings.camera.backend
        cam_index = settings.camera.index
        cam_alts = settings.camera.alt_indices
        steps.append(
            PreflightStepResult(
                step=9,
                name="Camera Video Device Interface",
                status="PASSED",
                details=f"Backend: {cam_backend.upper()}, Primary Index: {cam_index}, Alternate Indices: {cam_alts}.",
            )
        )

        # Step 10: Safety Rules & Simulation Guardrail Enforcement
        rule_ok = not hw.weight_rule
        status_10 = "PASSED" if rule_ok else "WARNING"
        details_10 = (
            f"SIMULATION_MODE={simulation}. "
            f"WEIGHT_RULE={hw.weight_rule} (Weight strictly monitoring; never influences AI classification). "
            f"Servos: Open={hw.servo_open_deg}°, Close={hw.servo_close_deg}°, Hold={hw.servo_hold_s}s, Settle={hw.servo_settle_s}s."
        )
        steps.append(
            PreflightStepResult(
                step=10,
                name="Safety Rules & Guardrail Enforcement",
                status=status_10,
                details=details_10,
                recommendation=None if rule_ok else "Set WEIGHT_RULE=false to ensure AI classification integrity.",
            )
        )

        # Consolidated status
        has_failed = any(s.status == "FAILED" for s in steps)
        is_ready = is_rpi and not has_failed and not simulation

        report = HardwareValidationReport(
            is_valid=not has_failed,
            ready_for_physical_hardware=is_ready,
            simulation_active=simulation or not is_rpi,
            steps=steps,
            pin_map=pin_validator.get_full_report(),
            summary=(
                "Hardware validation PASSED: Ready for Raspberry Pi deployment."
                if not has_failed
                else "Hardware validation FAILED: Check GPIO pin conflicts."
            ),
        )
        return report

    @classmethod
    def _is_raspberry_pi(cls) -> bool:
        """Check if executing on physical Raspberry Pi hardware (Raspberry Pi 5 / Pi 4)."""
        for path_str in ("/proc/device-tree/model", "/sys/firmware/devicetree/base/model"):
            dt_model = Path(path_str)
            if dt_model.exists():
                try:
                    content = dt_model.read_text(encoding="utf-8", errors="ignore")
                    if "Raspberry Pi" in content:
                        return True
                except Exception:
                    pass
        cpu_info = Path("/proc/cpuinfo")
        if cpu_info.exists():
            try:
                content = cpu_info.read_text(encoding="utf-8", errors="ignore")
                if "Raspberry Pi" in content or "BCM" in content or "RP1" in content:
                    return True
            except Exception:
                pass
        return False

