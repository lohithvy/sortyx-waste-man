"""
Sortyx 2.0 — Domain enumerations.

Canonical string enums for waste categories, system states, sensor
statuses, and bin identifiers used across the entire application.
"""

from __future__ import annotations

from enum import Enum


class WasteCategory(str, Enum):
    """Classification categories for waste items."""

    FOOD_WASTE = "food_waste"
    RECYCLABLE = "recyclable"
    NON_RECYCLABLE = "non_recyclable"

    # Backward compatibility aliases
    ORGANIC = "food_waste"
    BIO = "recyclable"
    NON_BIO = "non_recyclable"

    @classmethod
    def _missing_(cls, value: object):
        if isinstance(value, str):
            v = value.strip().lower().replace("-", "_").replace(" ", "_")
            aliases = {
                "organic": cls.FOOD_WASTE,
                "bio": cls.RECYCLABLE,
                "biodegradable": cls.RECYCLABLE,
                "non_bio": cls.NON_RECYCLABLE,
                "nonbio": cls.NON_RECYCLABLE,
                "food": cls.FOOD_WASTE,
                "food_waste": cls.FOOD_WASTE,
                "recyclable": cls.RECYCLABLE,
                "non_recyclable": cls.NON_RECYCLABLE,
            }
            if v in aliases:
                return aliases[v]
        return super()._missing_(value)

    @property
    def display_name(self) -> str:
        _names = {
            "food_waste": "Food Waste",
            "recyclable": "Recyclable",
            "non_recyclable": "Non-Recyclable",
        }
        return _names.get(self.value, self.value.replace("_", " ").title())


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

    FOOD_WASTE = "food_waste"
    RECYCLABLE = "recyclable"
    NON_RECYCLABLE = "non_recyclable"

    # Backward compatibility aliases
    ORGANIC = "food_waste"
    BIO = "recyclable"
    NON_BIO = "non_recyclable"

    @classmethod
    def _missing_(cls, value: object):
        if isinstance(value, str):
            v = value.strip().lower().replace("-", "_").replace(" ", "_")
            aliases = {
                "organic": cls.FOOD_WASTE,
                "bio": cls.RECYCLABLE,
                "biodegradable": cls.RECYCLABLE,
                "non_bio": cls.NON_RECYCLABLE,
                "nonbio": cls.NON_RECYCLABLE,
                "food": cls.FOOD_WASTE,
                "food_waste": cls.FOOD_WASTE,
                "recyclable": cls.RECYCLABLE,
                "non_recyclable": cls.NON_RECYCLABLE,
                "bin_1": cls.FOOD_WASTE,
                "bin_2": cls.RECYCLABLE,
                "bin_3": cls.NON_RECYCLABLE,
                "1": cls.FOOD_WASTE,
                "2": cls.RECYCLABLE,
                "3": cls.NON_RECYCLABLE,
            }
            if v in aliases:
                return aliases[v]
        return super()._missing_(value)

    @property
    def display_name(self) -> str:
        """Human-readable bin category label."""
        _names = {
            "food_waste": "Food Waste",
            "recyclable": "Recyclable",
            "non_recyclable": "Non-Recyclable",
        }
        return _names.get(self.value, self.value.replace("_", " ").title())

    @property
    def bin_number(self) -> int:
        """Physical bin number (1, 2, or 3)."""
        _nums = {
            "food_waste": 1,
            "recyclable": 2,
            "non_recyclable": 3,
        }
        return _nums.get(self.value, 1)

    @property
    def full_title(self) -> str:
        """Standardized UI Title e.g. 'Bin 1 – Food Waste'."""
        return f"Bin {self.bin_number} – {self.display_name}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


CATEGORY_TO_BIN: dict[WasteCategory, BinId] = {
    WasteCategory.FOOD_WASTE: BinId.FOOD_WASTE,
    WasteCategory.RECYCLABLE: BinId.RECYCLABLE,
    WasteCategory.NON_RECYCLABLE: BinId.NON_RECYCLABLE,
}
