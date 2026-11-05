"""
Sortyx 2.0 — Raspberry Pi 4 Hardware Compatibility & Connection Diagnostics.

Provides non-destructive verification of:
1. Host CPU architecture & Raspberry Pi 4 hardware model detection.
2. Linux OS kernel and distribution release.
3. Python environment and required hardware drivers.
4. I2C kernel module status (/dev/i2c-1) and PCA9685 (0x40) probe.
5. GPIO controller access permissions (/dev/gpiomem).
6. Camera device availability (V4L2 /dev/video0 or USB webcam).
7. Simulation mode requirement evaluation.
"""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.core.logging_config import get_logger

logger = get_logger(__name__)


class DiagnosticItem(BaseModel):
    """Result of an individual subsystem check."""

    name: str
    status: str  # "ok", "warning", "error", "info"
    details: str
    recommendation: Optional[str] = None


class HardwareDiagnosticReport(BaseModel):
    """Full hardware diagnostic report."""

    is_raspberry_pi: bool = False
    model_name: str = "Unknown"
    architecture: str = ""
    os_name: str = ""
    python_version: str = ""
    simulation_mode_required: bool = True
    subsystems: List[DiagnosticItem] = Field(default_factory=list)
    can_activate_physical_hardware: bool = False
    overall_status: str = "simulation"  # "ready", "simulation", "degraded"


class HardwareDiagnostics:
    """Hardware compatibility and connection checker for Sortyx 2.0."""

    @classmethod
    def run_full_diagnostics(cls) -> HardwareDiagnosticReport:
        """Run all compatibility and connection probes."""
        report = HardwareDiagnosticReport()
        report.architecture = platform.machine()
        report.python_version = platform.python_version()
        report.os_name = f"{platform.system()} {platform.release()}"

        # 1. Detect Raspberry Pi Model
        rpi_detected, model = cls._detect_raspberry_pi()
        report.is_raspberry_pi = rpi_detected
        report.model_name = model

        report.subsystems.append(
            DiagnosticItem(
                name="Host Platform",
                status="ok" if rpi_detected else "info",
                details=f"Hardware: {model} ({report.architecture}), OS: {report.os_name}",
                recommendation=None if rpi_detected else "Running on development laptop. Use SIMULATION_MODE=true.",
            )
        )

        # 2. Check Python Version
        py_major, py_minor = sys.version_info.major, sys.version_info.minor
        py_ok = (py_major == 3 and py_minor >= 10)
        report.subsystems.append(
            DiagnosticItem(
                name="Python Runtime",
                status="ok" if py_ok else "warning",
                details=f"Python {platform.python_version()} ({sys.executable})",
                recommendation=None if py_ok else "Python 3.10+ is recommended for Raspberry Pi OS Bookworm.",
            )
        )

        # 3. Check I2C Subsystem & PCA9685
        i2c_item = cls._check_i2c()
        report.subsystems.append(i2c_item)

        # 4. Check GPIO Subsystem
        gpio_item = cls._check_gpio()
        report.subsystems.append(gpio_item)

        # 5. Check Camera Subsystem
        cam_item = cls._check_camera()
        report.subsystems.append(cam_item)

        # 6. Overall readiness evaluation
        all_hw_ok = (
            rpi_detected
            and i2c_item.status == "ok"
            and gpio_item.status == "ok"
            and cam_item.status == "ok"
        )
        report.can_activate_physical_hardware = all_hw_ok
        report.simulation_mode_required = not all_hw_ok

        if all_hw_ok:
            report.overall_status = "ready"
        elif rpi_detected:
            report.overall_status = "degraded"
        else:
            report.overall_status = "simulation"

        return report

    @classmethod
    def _detect_raspberry_pi(cls) -> tuple[bool, str]:
        """Detect if host is a real Raspberry Pi hardware board."""
        # 1. Check device-tree model (Linux Pi standard)
        dt_model = Path("/proc/device-tree/model")
        if dt_model.exists():
            try:
                model_str = dt_model.read_text(encoding="utf-8", errors="ignore").strip().rstrip("\x00")
                if "Raspberry Pi" in model_str:
                    return True, model_str
            except Exception:
                pass

        # 2. Check /proc/cpuinfo
        cpuinfo = Path("/proc/cpuinfo")
        if cpuinfo.exists():
            try:
                content = cpuinfo.read_text(encoding="utf-8", errors="ignore")
                for line in content.splitlines():
                    if line.startswith("Model") and "Raspberry Pi" in line:
                        return True, line.split(":", 1)[1].strip()
            except Exception:
                pass

        # Development environment (Windows, Mac, or non-Pi Linux)
        return False, platform.platform()

    @classmethod
    def _check_i2c(cls) -> DiagnosticItem:
        """Check I2C bus and probe address 0x40."""
        i2c_dev = Path("/dev/i2c-1")
        if not i2c_dev.exists():
            return DiagnosticItem(
                name="I2C Controller & PCA9685",
                status="info" if os.name == "nt" else "warning",
                details="/dev/i2c-1 not present.",
                recommendation="Enable I2C via 'sudo raspi-config nonint do_i2c 0' and verify with 'ls /dev/i2c*'.",
            )

        # Test I2C permission
        if not os.access(str(i2c_dev), os.R_OK | os.W_OK):
            return DiagnosticItem(
                name="I2C Controller & PCA9685",
                status="error",
                details=f"Permission denied accessing {i2c_dev}.",
                recommendation="Add user to i2c group: 'sudo usermod -aG i2c $USER' then log out and back in.",
            )

        # Probe PCA9685 at 0x40
        try:
            import smbus2  # type: ignore

            with smbus2.SMBus(1) as bus:
                bus.read_byte_data(0x40, 0x00)
                return DiagnosticItem(
                    name="I2C Controller & PCA9685",
                    status="ok",
                    details="PCA9685 confirmed responding at I2C address 0x40 on bus 1.",
                    recommendation=None,
                )
        except ImportError:
            return DiagnosticItem(
                name="I2C Controller & PCA9685",
                status="warning",
                details="I2C device file exists, but python library 'smbus2' is not installed for hardware probe.",
                recommendation="Install smbus2 via 'pip install smbus2'.",
            )
        except Exception as exc:
            return DiagnosticItem(
                name="I2C Controller & PCA9685",
                status="warning",
                details=f"I2C device exists, but address 0x40 did not acknowledge: {exc}",
                recommendation="Verify PCA9685 wiring (SDA->Pin 3, SCL->Pin 5, VCC->Pin 1) and external 5V power.",
            )

    @classmethod
    def _check_gpio(cls) -> DiagnosticItem:
        """Check Raspberry Pi 5 / Pi 4 GPIO access."""
        # On Raspberry Pi 5 (RP1 southbridge), GPIO is exposed via /dev/gpiochip4 or /dev/gpiochip*
        # On Raspberry Pi 4 / legacy, GPIO is exposed via /dev/gpiomem
        has_pi5_gpio = Path("/dev/gpiochip4").exists() or Path("/dev/gpiochip0").exists()
        has_legacy_gpio = Path("/dev/gpiomem").exists()

        if not has_pi5_gpio and not has_legacy_gpio:
            return DiagnosticItem(
                name="GPIO Controller (HC-SR04)",
                status="info" if os.name == "nt" else "warning",
                details="Hardware GPIO device node (/dev/gpiochip4 or /dev/gpiomem) not present.",
                recommendation="GPIO device nodes available on Raspberry Pi only. Simulation active.",
            )

        try:
            import RPi.GPIO as GPIO  # type: ignore

            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            target_info = "RP1 Southbridge (/dev/gpiochip4) on Raspberry Pi 5" if has_pi5_gpio else "BCM2711 (/dev/gpiomem) on Raspberry Pi 4"
            return DiagnosticItem(
                name="GPIO Controller (HC-SR04)",
                status="ok",
                details=f"GPIO initialized in BCM mode via {target_info}.",
                recommendation=None,
            )
        except ImportError:
            return DiagnosticItem(
                name="GPIO Controller (HC-SR04)",
                status="warning",
                details="GPIO library not installed.",
                recommendation="Install 'rpi-lgpio' for Raspberry Pi 5 via 'pip install rpi-lgpio' or 'sudo apt install python3-rpi-lgpio'.",
            )
        except Exception as exc:
            return DiagnosticItem(
                name="GPIO Controller (HC-SR04)",
                status="error",
                details=f"Failed to access GPIO: {exc}",
                recommendation="Ensure user has permissions: 'sudo usermod -aG gpio $USER' and that rpi-lgpio is installed.",
            )

    @classmethod
    def _check_camera(cls) -> DiagnosticItem:
        """Check camera device availability."""
        # Check Linux video device
        video0 = Path("/dev/video0")
        if video0.exists():
            return DiagnosticItem(
                name="Camera Interface",
                status="ok",
                details=f"Camera hardware detected at {video0}.",
                recommendation=None,
            )

        # On non-Linux or USB webcam, test OpenCV index 0
        try:
            import cv2

            cap = cv2.VideoCapture(0)
            available = cap.isOpened()
            cap.release()
            if available:
                return DiagnosticItem(
                    name="Camera Interface",
                    status="ok",
                    details="Camera interface open and responsive on device index 0.",
                    recommendation=None,
                )
        except Exception:
            pass

        return DiagnosticItem(
            name="Camera Interface",
            status="warning",
            details="No camera device detected on /dev/video0 or index 0.",
            recommendation="Connect USB webcam or Pi Camera Ribbon cable, and enable camera via 'sudo raspi-config nonint do_camera 0'.",
        )

