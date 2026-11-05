"""
Sortyx 2.0 — Hardware Abstraction Unit Tests.
"""

from __future__ import annotations

import pytest

from app.models.enums import BinId, SensorStatus
from app.schemas.hardware import HardwareConfig, BinHardwareConfig, ServoConfig, UltrasonicConfig
from app.services.servo_service import ServoService
from app.services.ultrasonic_service import UltrasonicService


@pytest.mark.asyncio
async def test_unconfigured_servo_fails_safely() -> None:
    # All channels default to -1 (NOT_CONFIGURED)
    config = HardwareConfig()
    servo_svc = ServoService(config=config, simulation_mode=False)

    assert not servo_svc.is_configured(BinId.ORGANIC)
    success = await servo_svc.open_bin(BinId.ORGANIC)
    assert success is False
    assert servo_svc.active_bin is None


@pytest.mark.asyncio
async def test_simulated_servo_open_and_close(servo_service: ServoService) -> None:
    # In simulation mode, operations succeed and maintain state
    opened = await servo_service.open_bin(BinId.ORGANIC)
    assert opened is True
    assert servo_service.active_bin == BinId.ORGANIC

    closed = await servo_service.close_bin(BinId.ORGANIC)
    assert closed is True
    assert servo_service.active_bin is None


@pytest.mark.asyncio
async def test_simulated_servo_never_opens_multiple(servo_service: ServoService) -> None:
    await servo_service.open_bin(BinId.ORGANIC)
    assert servo_service.active_bin == BinId.ORGANIC

    # Opening Bio should automatically close Organic
    await servo_service.open_bin(BinId.BIO)
    assert servo_service.active_bin == BinId.BIO


def test_fill_percentage_calculation(ultrasonic_service: UltrasonicService) -> None:
    # Default config: empty = 30cm, full = 5cm
    # At 30cm -> 0%
    assert ultrasonic_service.calculate_fill_percentage(BinId.ORGANIC, 30.0) == 0.0

    # At 5cm -> 100%
    assert ultrasonic_service.calculate_fill_percentage(BinId.ORGANIC, 5.0) == 100.0

    # At 17.5cm -> 50%
    assert ultrasonic_service.calculate_fill_percentage(BinId.ORGANIC, 17.5) == 50.0

    # Out of range clamped
    assert ultrasonic_service.calculate_fill_percentage(BinId.ORGANIC, 50.0) == 0.0
    assert ultrasonic_service.calculate_fill_percentage(BinId.ORGANIC, 1.0) == 100.0


def test_unconfigured_ultrasonic_reports_not_configured() -> None:
    config = HardwareConfig()
    svc = UltrasonicService(config=config, simulation_mode=False)
    statuses = svc.sensor_statuses
    assert statuses["bio"] == SensorStatus.NOT_CONFIGURED
    assert statuses["organic"] == SensorStatus.NOT_CONFIGURED
    assert statuses["non_bio"] == SensorStatus.NOT_CONFIGURED

