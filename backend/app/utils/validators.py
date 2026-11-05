"""
Sortyx 2.0 — Input and data validators.

Clean, standalone validation and sanitisation functions.
"""

from __future__ import annotations

import re
from typing import Optional

from app.models.enums import WasteCategory, BinId


def validate_category(raw: str) -> WasteCategory:
    """Validate and normalise category strings to WasteCategory enum.

    Raises ValueError if invalid.
    """
    cleaned = raw.strip().lower().replace("-", "_").replace(" ", "_")
    valid_map = {
        "bio": WasteCategory.BIO,
        "organic": WasteCategory.ORGANIC,
        "non_bio": WasteCategory.NON_BIO,
        "nonbio": WasteCategory.NON_BIO,
    }
    if cleaned not in valid_map:
        raise ValueError(f"Invalid waste category: '{raw}'. Must be bio, organic, or non_bio.")
    return valid_map[cleaned]


def validate_confidence(raw: float) -> float:
    """Clamp and round confidence between 0.0 and 1.0."""
    return round(max(0.0, min(1.0, float(raw))), 4)


def validate_distance(dist: Optional[float]) -> Optional[float]:
    """Validate ultrasonic distance reading in centimetres.

    HC-SR04 typical range is 2cm to 400cm. Returns None if invalid.
    """
    if dist is None:
        return None
    try:
        val = float(dist)
        if 2.0 <= val <= 400.0:
            return round(val, 2)
        return None
    except (ValueError, TypeError):
        return None


def sanitize_waste_name(name: str) -> str:
    """Sanitise waste name for display and storage (strip harmful chars, cap length)."""
    if not name:
        return "Unknown Item"
    cleaned = re.sub(r"[^\w\s\-\.,/()&']", "", name).strip()
    return cleaned[:100] if cleaned else "Unknown Item"


def is_valid_bin_id(bin_id: str) -> bool:
    """Check if a string matches one of the known BinId values."""
    return bin_id.lower() in {b.value for b in BinId}

