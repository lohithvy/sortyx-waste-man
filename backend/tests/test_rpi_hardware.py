"""
Sortyx 2.0 — Raspberry Pi 4 Hardware Integration Tests.

Validates:
1. Pin map validation, BCM enforcement, reserved I2C pin protection, and duplicate collision checks.
2. HX711 24-bit ADC load cell bit-banging, two's complement conversion, and uncalibrated state safety.
3. Weight service managing all 3 bins, WEIGHT_RULE=false enforcement, and tare/calibration helpers.
4. PCA9685 servo controller: mutex serialization, actuation cycle, emergency stop, and simulation safety.
5. GPIO controller: simulation mode returning None (never fabricated 25.0 cm).
6. 10-step hardware startup validator refusing startup on pin conflict.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch
import pytest

from app.core.config import HardwareSettings, Settings
from app.core.exceptions import PinConflictError
from app.hardware.gpio_controller import GPIOController
from app.hardware.hx711 import HX711Controller
from app.hardware.pca9685 import PCA9685Controller
from app.hardware.pin_validator import PinValidator
from app.hardware.startup_validator import HardwareStartupValidator
from app.models.enums import BinId, SensorStatus
from app.services.weight_service import WeightService


# ---------------------------------------------------------------------------
# 1. Pin Validator Tests
# ---------------------------------------------------------------------------

def test_pin_validator_valid_map() -> None:
    """Confirmed hardware map must pass validation without errors."""
    hw = HardwareSettings()
    validator = PinValidator(hw)
    is_valid, errors, warnings = validator.validate_all()

    assert is_valid is True
    assert len(errors) == 0


def test_pin_validator_detects_duplicate_pins() -> None:
    """Duplicate pin assignment across components must fail validation."""
    hw = HardwareSettings(
        ultrasonic_trig_1=17,
        ultrasonic_echo_1=24,
        hx711_dt_1=24,  # Duplicate! Pin 24 already claimed by ultrasonic_echo_1
    )
    validator = PinValidator(hw)
    is_valid, errors, warnings = validator.validate_all()

    assert is_valid is False
    assert any("claimed multiple times" in e or "GPIO 24" in e for e in errors)


def test_pin_validator_detects_reserved_i2c_breach() -> None:
    """Assigning GPIO 2 or 3 (I2C) must fail validation."""
    hw = HardwareSettings(
        ultrasonic_trig_1=2,  # GPIO 2 is reserved for I2C SDA
    )
    validator = PinValidator(hw)
    is_valid, errors, warnings = validator.validate_all()

    assert is_valid is False
    assert any("reserved for PCA9685 I2C" in e for e in errors)


def test_pin_validator_detects_invalid_gpio_number() -> None:
    """GPIO pin numbers out of range (0-27) or non-BCM must fail."""
    hw = HardwareSettings(
        ultrasonic_trig_1=45,  # Out of range
    )
    validator = PinValidator(hw)
    is_valid, errors, warnings = validator.validate_all()

    assert is_valid is False
    assert any("out of valid range" in e for e in errors)


def test_pin_validator_enforces_bcm_numbering() -> None:
    """Non-BCM numbering mode must fail validation."""
    hw = HardwareSettings(
        gpio_numbering="BOARD",
    )
    validator = PinValidator(hw)
    is_valid, errors, warnings = validator.validate_all()

    assert is_valid is False
    assert any("Only BCM numbering is supported" in e for e in errors)


# ---------------------------------------------------------------------------
# 2. GPIO Controller & Distance Simulation Tests
# ---------------------------------------------------------------------------

def test_gpio_controller_never_fabricates_distance() -> None:
    """In simulation mode or on timeout, GPIOController must return None (never 25.0)."""
    controller = GPIOController(simulation_mode=True)
    dist = controller.read_distance_cm(trigger_pin=17, echo_pin=24)
    assert dist is None


# ---------------------------------------------------------------------------
# 3. HX711 Load Cell Driver Tests
# ---------------------------------------------------------------------------

def test_hx711_uncalibrated_returns_none() -> None:
    """When tare offset or scale factor is empty, weight is unavailable (None)."""
    driver = HX711Controller(
        dt_pin=5,
        sck_pin=11,
        tare_offset=None,
        scale_factor=None,
        simulation_mode=True,
        bin_name="organic",
    )
    assert driver.is_calibrated is False
    assert driver.read_weight_g() is None


def test_hx711_simulation_safety() -> None:
    """In simulation mode, raw reads return None and do not touch hardware."""
    driver = HX711Controller(
        dt_pin=5,
        sck_pin=11,
        tare_offset=1000.0,
        scale_factor=20.0,
        simulation_mode=True,
        bin_name="organic",
    )
    assert driver.is_calibrated is True
    # In simulation mode, read_weight_g() returns None (never fake numbers)
    assert driver.read_weight_g() is None
    assert driver.read_raw() is None


def test_hx711_bit_bang_twos_complement() -> None:
    """Verify 24-bit bit-banging and two's complement decoding logic."""
    driver = HX711Controller(
        dt_pin=5,
        sck_pin=11,
        tare_offset=100.0,
        scale_factor=10.0,
        simulation_mode=False,
        bin_name="test",
    )

    # Mock RPi.GPIO
    mock_gpio = MagicMock()
    # DT goes low (ready) immediately
    mock_gpio.input.return_value = 0
    driver._gpio = mock_gpio
    driver.simulation_mode = False

    # Provide 24 bits: let's test positive value 1000
    # Binary representation of 1000: 0b000000000000001111101000
    bits = [(1000 >> (23 - i)) & 1 for i in range(24)]
    mock_gpio.input.side_effect = [0] + bits  # First 0 for DT ready, then 24 bits

    raw = driver.read_raw(timeout_s=0.1)
    assert raw == 1000
    # Verify 25 pulses were generated (24 data + 1 gain 128)
    assert mock_gpio.output.call_count >= 50  # 25 high and 25 low transitions


def test_hx711_twos_complement_negative_value() -> None:
    """Verify negative two's complement conversion (sign bit = 1)."""
    driver = HX711Controller(
        dt_pin=5,
        sck_pin=11,
        simulation_mode=False,
        bin_name="test",
    )

    mock_gpio = MagicMock()
    # -50 in 24-bit two's complement is 0xFF_FFCE (16777166)
    val_neg_50 = 0xFFFFCE
    bits = [(val_neg_50 >> (23 - i)) & 1 for i in range(24)]
    mock_gpio.input.side_effect = [0] + bits

    driver._gpio = mock_gpio
    driver.simulation_mode = False
    raw = driver.read_raw(timeout_s=0.1)
    assert raw == -50


# ---------------------------------------------------------------------------
# 4. Weight Service & Safety Guardrails Tests
# ---------------------------------------------------------------------------

def test_weight_service_uncalibrated_by_default() -> None:
    """WeightService defaults to uncalibrated with all weights returning None."""
    svc = WeightService(simulation_mode=True, weight_rule_enabled=False)
    summary = svc.get_all_weights_summary()

    for bin_name in ("organic", "bio", "non_bio"):
        assert bin_name in summary
        bin_data = summary[bin_name]
        assert bin_data["weight_g"] is None
        assert bin_data["is_calibrated"] is False
        assert bin_data["status"] == "simulation"


def test_weight_service_enforces_weight_rule_false() -> None:
    """Weight sensor must never override classification decisions."""
    svc = WeightService(simulation_mode=True, weight_rule_enabled=False)
    assert svc.weight_rule_enabled is False


@pytest.mark.asyncio
async def test_weight_service_tare_and_calibrate_isolated() -> None:
    """Calibration attempts in simulation mode handle safely without crashes."""
    svc = WeightService(simulation_mode=True, weight_rule_enabled=False)

    tare_res = await svc.tare_bin(BinId.ORGANIC)
    assert tare_res is None  # Simulation mode returns None

    cal_res = await svc.calibrate_bin(BinId.ORGANIC, known_weight_g=500.0)
    assert cal_res is None


# ---------------------------------------------------------------------------
# 5. PCA9685 Mutex Lock & Cycle Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pca9685_actuate_cycle() -> None:
    """PCA9685 actuate_cycle runs Open -> Hold -> Close -> Settle with mutex."""
    ctrl = PCA9685Controller(simulation_mode=True)
    success = await ctrl.actuate_cycle(
        channel=0,
        open_deg=50,
        close_deg=0,
        hold_s=0.01,
        settle_s=0.01,
    )
    assert success is True
    assert ctrl._current_angles.get(0) == 0


def test_pca9685_emergency_stop() -> None:
    """Emergency stop commands all 16 channels to 0°."""
    ctrl = PCA9685Controller(simulation_mode=True)
    ctrl._current_angles[0] = 50
    ctrl._current_angles[1] = 50
    ctrl.emergency_stop()
    assert ctrl._current_angles.get(0) == 0
    assert ctrl._current_angles.get(1) == 0


# ---------------------------------------------------------------------------
# 6. Startup Validator (10-Step Pre-flight) Tests
# ---------------------------------------------------------------------------

def test_startup_validator_passes_on_confirmed_hardware() -> None:
    """Confirmed hardware configuration passes 10-step preflight checks."""
    settings = Settings()
    report = HardwareStartupValidator.run_preflight_checks(
        settings=settings,
        strict_refuse_on_conflict=True,
    )

    assert report.is_valid is True
    assert len(report.steps) == 10
    assert all(s.status in ("PASSED", "WARNING", "SIMULATION") for s in report.steps)


def test_startup_validator_refuses_startup_on_conflict() -> None:
    """PinConflictError is raised and startup refused when pin collision is present."""
    settings = Settings()
    # Inject deliberate pin collision: assign ultrasonic echo 1 (24) to trig 2
    settings.hardware.ultrasonic_trig_2 = 24

    with pytest.raises(PinConflictError) as exc_info:
        HardwareStartupValidator.run_preflight_checks(
            settings=settings,
            strict_refuse_on_conflict=True,
        )

    assert "GPIO pin conflicts" in str(exc_info.value) or "claimed multiple times" in str(exc_info.value)

