"""
Sortyx 2.0 — Domain enumerations.

Canonical string enums for waste categories, system states, sensor
statuses, and bin identifiers used across the entire application.
"""

from __future__ import annotations

from enum import Enum


class WasteCategory(str, Enum):
    """Classification categories for waste items."""

    BIO = "bio"
    ORGANIC = "organic"
    NON_BIO = "non_bio"


class SystemState(str, Enum):
    """All valid states of the sorting state machine."""

    IDLE = "idle"
    PERSON_DETECTED = "person_detected"
    CAMERA_ACTIVE = "camera_active"
    IMAGE_CAPTURE = "image_capture"
    CLASSIFYING = "classifying"
    CLASSIFICATION_RESULT = "classification_result"
    SERVO_OPENING = "servo_opening"
    AWAITING_DEPOSIT = "awaiting_deposit"
    LID_CLOSING = "lid_closing"
    ERROR = "error"
    MANUAL_REVIEW = "manual_review"


class ClassificationStatus(str, Enum):
    """Outcome of the AI classification step."""

    PENDING = "pending"
    CLASSIFIED = "classified"
    REJECTED = "rejected"
    FAILED = "failed"
    HAZARDOUS = "hazardous"
    MANUAL_REVIEW = "manual_review"


class SortingStatus(str, Enum):
    """Physical sorting progress after classification."""

    PENDING = "pending"
    BIN_OPENING = "bin_opening"
    AWAITING_DEPOSIT = "awaiting_deposit"
    DEPOSIT_CONFIRMED = "deposit_confirmed"
    DEPOSIT_UNCONFIRMED = "deposit_unconfirmed"
    CLOSING = "closing"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class SensorStatus(str, Enum):
    """Health / availability status of a hardware sensor."""

    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"
    NOT_CONFIGURED = "not_configured"
    UNCALIBRATED = "uncalibrated"
    SIMULATION = "simulation"


class CameraSource(str, Enum):
    """Supported camera hardware backends."""

    WEBCAM = "WEBCAM"
    RASPBERRY_PI = "RASPBERRY_PI"


# ---------------------------------------------------------------------------
# Bin identifier mapping
# ---------------------------------------------------------------------------


class BinId(str, Enum):
    """Logical bin identifiers and their display names."""

    BIO = "bio"
    ORGANIC = "organic"
    NON_BIO = "non_bio"

    @property
    def display_name(self) -> str:
        """Human-readable bin label."""
        _names = {
            "bio": "Biodegradable",
            "organic": "Organic",
            "non_bio": "Non-Biodegradable",
        }
        return _names[self.value]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


CATEGORY_TO_BIN: dict[WasteCategory, BinId] = {
    WasteCategory.BIO: BinId.BIO,
    WasteCategory.ORGANIC: BinId.ORGANIC,
    WasteCategory.NON_BIO: BinId.NON_BIO,
}
