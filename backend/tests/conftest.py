"""
Sortyx 2.0 — Pytest Fixtures and Test Helpers.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock

from app.models.enums import BinId, WasteCategory, ClassificationStatus, SortingStatus
from app.schemas.classification import GeminiClassificationResponse, ClassificationResult
from app.schemas.hardware import HardwareConfig
from app.services.classification_service import ClassificationService
from app.services.servo_service import ServoService
from app.services.ultrasonic_service import UltrasonicService
from app.state_machine.machine import SortingStateMachine


@pytest.fixture
def hardware_config() -> HardwareConfig:
    """Default hardware config in NOT_CONFIGURED state."""
    return HardwareConfig()


@pytest.fixture
def classification_service() -> ClassificationService:
    """Standard classification validation service with 75% threshold."""
    return ClassificationService(confidence_threshold=0.75)


@pytest.fixture
def servo_service(hardware_config: HardwareConfig) -> ServoService:
    """Servo service running in simulation mode."""
    return ServoService(config=hardware_config, simulation_mode=True)


@pytest.fixture
def ultrasonic_service(hardware_config: HardwareConfig) -> UltrasonicService:
    """Ultrasonic service running in simulation mode."""
    return UltrasonicService(config=hardware_config, simulation_mode=True)


@pytest.fixture
def state_machine() -> SortingStateMachine:
    """Fresh state machine starting in IDLE."""
    return SortingStateMachine()


@pytest.fixture
def sample_organic_response() -> GeminiClassificationResponse:
    return GeminiClassificationResponse(
        waste_name="Banana Peel",
        category="food_waste",
        confidence=0.96,
        reason="Fresh fruit peel decomposes quickly into compost.",
        is_hazardous=False,
        requires_manual_review=False,
    )


@pytest.fixture
def sample_bio_response() -> GeminiClassificationResponse:
    return GeminiClassificationResponse(
        waste_name="Cardboard Box",
        category="recyclable",
        confidence=0.91,
        reason="Untreated cellulose fibre decomposes naturally.",
        is_hazardous=False,
        requires_manual_review=False,
    )


@pytest.fixture
def sample_non_bio_response() -> GeminiClassificationResponse:
    return GeminiClassificationResponse(
        waste_name="Chips Packet Wrapper",
        category="non_recyclable",
        confidence=0.98,
        reason="Polyethylene film does not decompose naturally.",
        is_hazardous=False,
        requires_manual_review=False,
    )


@pytest.fixture
def sample_hazardous_response() -> GeminiClassificationResponse:
    return GeminiClassificationResponse(
        waste_name="Toxic Pesticide Chemical",
        category="hazardous",
        confidence=0.95,
        reason="Hazardous electronic battery requiring special e-waste disposal.",
        is_hazardous=True,
        requires_manual_review=True,
    )

