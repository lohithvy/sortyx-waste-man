"""
Sortyx 2.0 — Raspberry Pi GPIO Pin Validator & Conflict Detector.

Validates that:
1. GPIO numbering is set to BCM.
2. Reserved I2C pins (GPIO 2 and GPIO 3) are never assigned to sensors.
3. No two hardware components claim the same GPIO pin.
4. SPI and I2S conflicts are detected (GPIO 11, 19, 21 overlap).
5. All pins are within the valid Raspberry Pi BCM GPIO range (0-27).
6. Refuses hardware startup if any pin conflict is detected.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field

from app.core.exceptions import PinConflictError
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Reserved Raspberry Pi 4 hardware pins
RESERVED_I2C_PINS: Set[int] = {2, 3}  # GPIO 2 (SDA1), GPIO 3 (SCL1) for PCA9685

# Special function pins that conflict if peripherals are enabled
SPI0_PINS: Set[int] = {7, 8, 9, 10, 11}       # GPIO 11 is SPI0 SCLK (used by HX711_SCK_1)
I2S_PINS: Set[int] = {18, 19, 20, 21}         # GPIO 19 is I2S FS (HX711_SCK_2), GPIO 21 is I2S DOUT (HX711_SCK_3)
VALID_BCM_PINS: Set[int] = set(range(0, 28))   # Valid BCM GPIO 0 to 27


class PinAssignment(BaseModel):
    """Details of a single assigned GPIO pin."""

    name: str
    pin: int
    component: str
    bin_id: str
    direction: str  # "IN", "OUT", "I2C"


class PinValidationReport(BaseModel):
    """Result of GPIO pin configuration validation."""

    valid: bool
    gpio_numbering: str
    assigned_pins: Dict[int, PinAssignment] = Field(default_factory=dict)
    conflicts: List[str] = Field(default_factory=list)
    reserved_violations: List[str] = Field(default_factory=list)
    peripheral_warnings: List[str] = Field(default_factory=list)
    spi_disabled: bool = True
    i2s_disabled: bool = True


def check_raspberry_pi_overlays() -> Tuple[bool, bool, List[str]]:
    """Check if SPI or I2S kernel drivers are enabled on Raspberry Pi OS.

    Returns:
        (spi_enabled, i2s_enabled, warnings)
    """
    spi_enabled = False
    i2s_enabled = False
    warnings: List[str] = []

    # Check Linux device files
    if Path("/dev/spidev0.0").exists() or Path("/dev/spidev0.1").exists():
        spi_enabled = True
        warnings.append(
            "Kernel SPI device (/dev/spidev0.*) detected! SPI0 conflicts with HX711_SCK_1 on GPIO 11."
        )

    # Check config.txt files on Raspberry Pi
    config_paths = [
        Path("/boot/firmware/config.txt"),  # Debian Bookworm (RPi OS 12)
        Path("/boot/config.txt"),           # Debian Bullseye (RPi OS 11)
    ]
    for cfg_path in config_paths:
        if cfg_path.exists():
            try:
                content = cfg_path.read_text(encoding="utf-8", errors="ignore")
                for line in content.splitlines():
                    line = line.strip()
                    if line.startswith("#"):
                        continue
                    if "dtparam=spi=on" in line:
                        spi_enabled = True
                        warnings.append(
                            f"SPI enabled in {cfg_path}: 'dtparam=spi=on'. Must be set to 'off' to release GPIO 11."
                        )
                    if "dtparam=i2s=on" in line:
                        i2s_enabled = True
                        warnings.append(
                            f"I2S enabled in {cfg_path}: 'dtparam=i2s=on'. Must be set to 'off' to release GPIO 19 & 21."
                        )
            except Exception as exc:
                logger.debug("Could not inspect %s: %s", cfg_path, exc)

    return spi_enabled, i2s_enabled, warnings


def validate_pin_map(
    numbering: str = "BCM",
    ultrasonic_trig_1: int = 17,
    ultrasonic_echo_1: int = 24,
    ultrasonic_trig_2: int = 22,
    ultrasonic_echo_2: int = 27,
    ultrasonic_trig_3: int = 23,
    ultrasonic_echo_3: int = 6,
    hx711_dt_1: int = 5,
    hx711_sck_1: int = 11,
    hx711_dt_2: int = 13,
    hx711_sck_2: int = 19,
    hx711_dt_3: int = 26,
    hx711_sck_3: int = 21,
    strict_fail: bool = True,
) -> PinValidationReport:
    """Validate full GPIO pin map and refuse startup on conflict or reserved pin usage.

    Args:
        strict_fail: If True, raises PinConflictError on any detected conflict.
    """
    report = PinValidationReport(
        valid=True,
        gpio_numbering=numbering.upper(),
    )

    # 1. Numbering mode check
    if report.gpio_numbering != "BCM":
        msg = f"Invalid GPIO numbering: '{numbering}'. Only BCM numbering is supported. Sortyx 2.0 strictly requires BCM numbering."
        report.conflicts.append(msg)
        report.valid = False
        if strict_fail:
            raise PinConflictError(msg)

    # 2. Collect all sensor pin assignments
    declared_pins = [
        # Bin 1 (Organic)
        PinAssignment(name="ULTRASONIC_TRIG_1", pin=ultrasonic_trig_1, component="HC-SR04 Trigger", bin_id="bin_1_organic", direction="OUT"),
        PinAssignment(name="ULTRASONIC_ECHO_1", pin=ultrasonic_echo_1, component="HC-SR04 Echo (via 3.3V divider)", bin_id="bin_1_organic", direction="IN"),
        PinAssignment(name="HX711_DT_1", pin=hx711_dt_1, component="HX711 Data", bin_id="bin_1_organic", direction="IN"),
        PinAssignment(name="HX711_SCK_1", pin=hx711_sck_1, component="HX711 Clock", bin_id="bin_1_organic", direction="OUT"),

        # Bin 2 (Bio)
        PinAssignment(name="ULTRASONIC_TRIG_2", pin=ultrasonic_trig_2, component="HC-SR04 Trigger", bin_id="bin_2_bio", direction="OUT"),
        PinAssignment(name="ULTRASONIC_ECHO_2", pin=ultrasonic_echo_2, component="HC-SR04 Echo (via 3.3V divider)", bin_id="bin_2_bio", direction="IN"),
        PinAssignment(name="HX711_DT_2", pin=hx711_dt_2, component="HX711 Data", bin_id="bin_2_bio", direction="IN"),
        PinAssignment(name="HX711_SCK_2", pin=hx711_sck_2, component="HX711 Clock", bin_id="bin_2_bio", direction="OUT"),

        # Bin 3 (Non-Bio)
        PinAssignment(name="ULTRASONIC_TRIG_3", pin=ultrasonic_trig_3, component="HC-SR04 Trigger", bin_id="bin_3_non_bio", direction="OUT"),
        PinAssignment(name="ULTRASONIC_ECHO_3", pin=ultrasonic_echo_3, component="HC-SR04 Echo (via 3.3V divider)", bin_id="bin_3_non_bio", direction="IN"),
        PinAssignment(name="HX711_DT_3", pin=hx711_dt_3, component="HX711 Data", bin_id="bin_3_non_bio", direction="IN"),
        PinAssignment(name="HX711_SCK_3", pin=hx711_sck_3, component="HX711 Clock", bin_id="bin_3_non_bio", direction="OUT"),
    ]

    claimed_pins: Dict[int, List[PinAssignment]] = {}

    for item in declared_pins:
        # Check range
        if item.pin not in VALID_BCM_PINS:
            msg = f"Pin {item.name}={item.pin} is out of valid range (BCM GPIO 0-27)."
            report.conflicts.append(msg)
            report.valid = False

        # Check I2C reserved pins (GPIO 2, 3)
        if item.pin in RESERVED_I2C_PINS:
            msg = (
                f"RESERVED PIN VIOLATION: {item.name} is assigned to GPIO {item.pin}. "
                f"GPIO 2 and GPIO 3 are strictly reserved for PCA9685 I2C (SDA/SCL)."
            )
            report.reserved_violations.append(msg)
            report.valid = False

        claimed_pins.setdefault(item.pin, []).append(item)

    # 3. Detect duplicate pin assignments
    for pin, assignments in claimed_pins.items():
        if len(assignments) > 1:
            names = [f"'{a.name}' ({a.component} on {a.bin_id})" for a in assignments]
            msg = f"PIN CONFLICT: GPIO {pin} is claimed by multiple components: {', '.join(names)}."
            report.conflicts.append(msg)
            report.valid = False
        else:
            report.assigned_pins[pin] = assignments[0]

    # 4. Check SPI & I2S status
    spi_on, i2s_on, overlay_warnings = check_raspberry_pi_overlays()
    report.spi_disabled = not spi_on
    report.i2s_disabled = not i2s_on
    report.peripheral_warnings.extend(overlay_warnings)

    if spi_on:
        report.peripheral_warnings.append(
            "GPIO 11 is used by HX711_SCK_1. SPI0 must be disabled in /boot/firmware/config.txt."
        )
    if i2s_on:
        report.peripheral_warnings.append(
            "GPIO 19 and 21 are used by HX711 SCK pins. I2S must be disabled in /boot/firmware/config.txt."
        )

    # 5. Enforce startup refusal on conflict
    if not report.valid:
        error_details = "\n".join(report.reserved_violations + report.conflicts)
        logger.critical(
            "HARDWARE STARTUP REFUSED — GPIO Pin Conflicts Detected:\n%s",
            error_details,
        )
        if strict_fail:
            raise PinConflictError(
                f"Hardware startup refused due to GPIO pin conflicts:\n{error_details}"
            )
    else:
        logger.info(
            "GPIO Pin Map validated successfully (BCM mode, %d unique pins, zero conflicts).",
            len(report.assigned_pins),
        )

    return report


class PinValidator:
    """Object-oriented wrapper around validate_pin_map."""

    def __init__(self, hardware_settings: Optional[Any] = None) -> None:
        self.settings = hardware_settings

    def validate_all(self, strict_fail: bool = False) -> Tuple[bool, List[str], List[str]]:
        """Validate all assigned pins and return (is_valid, errors, warnings)."""
        hw = self.settings
        if hw is None:
            from app.core.config import get_settings
            hw = get_settings().hardware

        try:
            report = validate_pin_map(
                numbering=getattr(hw, "gpio_numbering", "BCM"),
                ultrasonic_trig_1=getattr(hw, "ultrasonic_trig_1", 17),
                ultrasonic_echo_1=getattr(hw, "ultrasonic_echo_1", 24),
                ultrasonic_trig_2=getattr(hw, "ultrasonic_trig_2", 22),
                ultrasonic_echo_2=getattr(hw, "ultrasonic_echo_2", 27),
                ultrasonic_trig_3=getattr(hw, "ultrasonic_trig_3", 23),
                ultrasonic_echo_3=getattr(hw, "ultrasonic_echo_3", 6),
                hx711_dt_1=getattr(hw, "hx711_dt_1", 5),
                hx711_sck_1=getattr(hw, "hx711_sck_1", 11),
                hx711_dt_2=getattr(hw, "hx711_dt_2", 13),
                hx711_sck_2=getattr(hw, "hx711_sck_2", 19),
                hx711_dt_3=getattr(hw, "hx711_dt_3", 26),
                hx711_sck_3=getattr(hw, "hx711_sck_3", 21),
                strict_fail=strict_fail,
            )
            errors = report.reserved_violations + report.conflicts
            return report.valid, errors, report.peripheral_warnings
        except PinConflictError as e:
            return False, [str(e)], []

    def get_claimed_pins(self) -> List[int]:
        """Return list of all currently configured GPIO pin numbers."""
        hw = self.settings
        if hw is None:
            from app.core.config import get_settings
            hw = get_settings().hardware
        return [
            getattr(hw, "ultrasonic_trig_1", 17),
            getattr(hw, "ultrasonic_echo_1", 24),
            getattr(hw, "ultrasonic_trig_2", 22),
            getattr(hw, "ultrasonic_echo_2", 27),
            getattr(hw, "ultrasonic_trig_3", 23),
            getattr(hw, "ultrasonic_echo_3", 6),
            getattr(hw, "hx711_dt_1", 5),
            getattr(hw, "hx711_sck_1", 11),
            getattr(hw, "hx711_dt_2", 13),
            getattr(hw, "hx711_sck_2", 19),
            getattr(hw, "hx711_dt_3", 26),
            getattr(hw, "hx711_sck_3", 21),
        ]

    def get_full_report(self) -> Dict[str, Any]:
        """Return full JSON-serializable report dictionary."""
        hw = self.settings
        if hw is None:
            from app.core.config import get_settings
            hw = get_settings().hardware
        report = validate_pin_map(
            numbering=getattr(hw, "gpio_numbering", "BCM"),
            ultrasonic_trig_1=getattr(hw, "ultrasonic_trig_1", 17),
            ultrasonic_echo_1=getattr(hw, "ultrasonic_echo_1", 24),
            ultrasonic_trig_2=getattr(hw, "ultrasonic_trig_2", 22),
            ultrasonic_echo_2=getattr(hw, "ultrasonic_echo_2", 27),
            ultrasonic_trig_3=getattr(hw, "ultrasonic_trig_3", 23),
            ultrasonic_echo_3=getattr(hw, "ultrasonic_echo_3", 6),
            hx711_dt_1=getattr(hw, "hx711_dt_1", 5),
            hx711_sck_1=getattr(hw, "hx711_sck_1", 11),
            hx711_dt_2=getattr(hw, "hx711_dt_2", 13),
            hx711_sck_2=getattr(hw, "hx711_sck_2", 19),
            hx711_dt_3=getattr(hw, "hx711_dt_3", 26),
            hx711_sck_3=getattr(hw, "hx711_sck_3", 21),
            strict_fail=False,
        )
        return report.model_dump(mode="json")
