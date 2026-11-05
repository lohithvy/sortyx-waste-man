"""
Sortyx 2.0 — Hardware Abstraction & Simulation Unit Tests (Phase 5).

Verifies:
1. PCA9685 controller abstraction, channel validation, and smooth motion.
2. Servo service mutual exclusion, timeout watchdog auto-close, and emergency stop.
3. Ultrasonic sensor abstraction, calibration calculations, and deposit confirmation.
4. Hardware diagnostics report generation and compatibility checks.
5. Safety rules: physical hardware activation disabled when unconfigured.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.hardware.diagnostics import HardwareDiagnostics
from app.hardware.pca9685 import PCA9685Controller
from app.models.enums import BinId, SensorStatus
from app.schemas.hardware import BinHardwareConfig, HardwareConfig, ServoConfig, UltrasonicConfig
from app.services.servo_service import ServoService
from app.services.ultrasonic_service import UltrasonicService


# ---------------------------------------------------------------------------
# 1. PCA9685 Low-Level Controller Tests
# ---------------------------------------------------------------------------

def test_pca9685_unconfigured_channel_rejected() -> None:
    """Channels < 0 or > 15 must be rejected without hardware actuation."""
    ctrl = PCA9685Controller(simulation_mode=True)
    assert ctrl.set_servo_angle(channel=-1, angle=90) is False
    assert ctrl.set_servo_angle(channel=16, angle=90) is False


def test_pca9685_simulation_angle_setting() -> None:
    """In simulation mode, angle setting succeeds and updates internal state."""
    ctrl = PCA9685Controller(simulation_mode=True)
    success = ctrl.set_servo_angle(channel=0, angle=90)
    assert success is True
    assert ctrl._current_angles.get(0) == 90

    # Angle clamped to 0-180
    ctrl.set_servo_angle(channel=0, angle=250)
    assert ctrl._current_angles.get(0) == 180


@pytest.mark.asyncio
async def test_pca9685_smooth_movement() -> None:
    """Smooth movement transitions to target angle safely."""
    ctrl = PCA9685Controller(simulation_mode=True)
    success = await ctrl.move_smooth(
        channel=1,
        start_angle=0,
        target_angle=90,
        step_deg=10,
        step_delay_s=0.001,
    )
    assert success is True
    assert ctrl._current_angles.get(1) == 90


def test_pca9685_disable_channel() -> None:
    """Disabling channel releases PWM signal without errors."""
    ctrl = PCA9685Controller(simulation_mode=True)
    ctrl.disable_channel(channel=0)
    # Does not crash on unconfigured channel
    ctrl.disable_channel(channel=-1)


# ---------------------------------------------------------------------------
# 2. Servo Service High-Level Orchestration Tests
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_hardware_config() -> HardwareConfig:
    cfg = HardwareConfig()
    cfg.bins["bio"] = BinHardwareConfig(
        servo=ServoConfig(channel=0, open_angle=90, close_angle=0, max_open_duration=30.0),
        ultrasonic=UltrasonicConfig(trigger_pin=23, echo_pin=24, empty_distance_cm=30.0, full_distance_cm=5.0),
    )
    cfg.bins["organic"] = BinHardwareConfig(
        servo=ServoConfig(channel=1, open_angle=85, close_angle=5, max_open_duration=30.0),
        ultrasonic=UltrasonicConfig(trigger_pin=17, echo_pin=27, empty_distance_cm=35.0, full_distance_cm=5.0),
    )
    cfg.bins["non_bio"] = BinHardwareConfig(
        servo=ServoConfig(channel=2, open_angle=100, close_angle=0, max_open_duration=30.0),
        ultrasonic=UltrasonicConfig(trigger_pin=5, echo_pin=6, empty_distance_cm=40.0, full_distance_cm=8.0),
    )
    return cfg


@pytest.mark.asyncio
async def test_servo_mutual_exclusion(mock_hardware_config: HardwareConfig) -> None:
    """Opening a new bin must automatically close any currently open bin."""
    ctrl = PCA9685Controller(simulation_mode=True)
    svc = ServoService(config=mock_hardware_config, controller=ctrl, simulation_mode=True)

    # Open Bio
    await svc.open_bin(BinId.BIO)
    assert svc.active_bin == BinId.BIO

    # Open Organic -> Bio must be closed first
    await svc.open_bin(BinId.ORGANIC)
    assert svc.active_bin == BinId.ORGANIC


@pytest.mark.asyncio
async def test_servo_watchdog_auto_close(mock_hardware_config: HardwareConfig) -> None:
    """Watchdog timer must auto-close open lid when duration expires."""
    ctrl = PCA9685Controller(simulation_mode=True)
    svc = ServoService(config=mock_hardware_config, controller=ctrl, simulation_mode=True)

    # Open with short 0.1s timeout
    await svc.open_bin(BinId.BIO, timeout_seconds=0.1)
    assert svc.active_bin == BinId.BIO

    # Wait for watchdog
    await asyncio.sleep(0.15)
    assert svc.active_bin is None


@pytest.mark.asyncio
async def test_servo_emergency_stop(mock_hardware_config: HardwareConfig) -> None:
    """Emergency stop commands all bins to close angle immediately."""
    ctrl = PCA9685Controller(simulation_mode=True)
    svc = ServoService(config=mock_hardware_config, controller=ctrl, simulation_mode=True)

    await svc.open_bin(BinId.ORGANIC)
    assert svc.active_bin == BinId.ORGANIC

    await svc.close_all_bins()
    assert svc.active_bin is None


# ---------------------------------------------------------------------------
# 3. Ultrasonic Distance & Fill-Level Calibration Tests
# ---------------------------------------------------------------------------

def test_ultrasonic_unconfigured_sensor_reports_none() -> None:
    """Unconfigured sensors return None and NOT_CONFIGURED status (never fake numbers)."""
    cfg = HardwareConfig()  # Default: all channels -1
    svc = UltrasonicService(config=cfg, simulation_mode=True)

    fill_pct, dist, status = svc.get_bin_fill_status(BinId.BIO)
    assert dist is None
    assert fill_pct == 0.0
    assert status == SensorStatus.NOT_CONFIGURED


def test_ultrasonic_fill_percentage_boundaries(mock_hardware_config: HardwareConfig) -> None:
    """Validate fill percentage calculations across empty, full, and clamped ranges."""
    svc = UltrasonicService(config=mock_hardware_config, simulation_mode=True)

    # Bio: empty=30.0cm, full=5.0cm (span = 25cm)
    # Empty (30cm) -> 0%
    assert svc.calculate_fill_percentage(BinId.BIO, 30.0) == 0.0

    # Full (5cm) -> 100%
    assert svc.calculate_fill_percentage(BinId.BIO, 5.0) == 100.0

    # Half (17.5cm) -> 50%
    assert svc.calculate_fill_percentage(BinId.BIO, 17.5) == 50.0

    # Overfilled (< 5cm, e.g. 2cm) -> clamped to 100%
    assert svc.calculate_fill_percentage(BinId.BIO, 2.0) == 100.0

    # Distance beyond empty (> 30cm, e.g. 45cm) -> clamped to 0%
    assert svc.calculate_fill_percentage(BinId.BIO, 45.0) == 0.0

    # Distance is None -> 0%
    assert svc.calculate_fill_percentage(BinId.BIO, None) == 0.0


def test_ultrasonic_deposit_confirmation_heuristic(mock_hardware_config: HardwareConfig) -> None:
    """Distance decrease >= min_change_threshold confirms waste deposit."""
    svc = UltrasonicService(config=mock_hardware_config, simulation_mode=True)

    # Baseline 25cm, current 22cm -> delta 3cm >= 2cm threshold -> Confirmed
    with patch.object(svc, "read_distance", return_value=22.0):
        confirmed, reason = svc.attempt_deposit_confirmation(BinId.BIO, baseline_distance=25.0)
        assert confirmed is True
        assert "confirmed" in reason.lower()

    # Baseline 25cm, current 24.5cm -> delta 0.5cm < 2cm threshold -> Unconfirmed
    with patch.object(svc, "read_distance", return_value=24.5):
        confirmed, reason = svc.attempt_deposit_confirmation(BinId.BIO, baseline_distance=25.0)
        assert confirmed is False


# ---------------------------------------------------------------------------
# 4. Hardware Diagnostics Tests
# ---------------------------------------------------------------------------

def test_hardware_diagnostics_report() -> None:
    """Hardware diagnostics executes non-destructively and returns structured findings."""
    report = HardwareDiagnostics.run_full_diagnostics()

    assert report.architecture != ""
    assert report.python_version != ""
    assert report.os_name != ""
    assert len(report.subsystems) >= 4
    assert report.overall_status in ("ready", "simulation", "degraded")

