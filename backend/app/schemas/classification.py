"""
Sortyx 2.0 — Classification schemas.

Pydantic models for Gemini AI requests, responses, and the validated
classification result that drives bin assignment.
"""

from __future__ import annotations

from typing import Optional, Any

from pydantic import BaseModel, Field, field_validator

from app.models.enums import WasteCategory, ClassificationStatus, BinId, CATEGORY_TO_BIN


class GeminiClassificationRequest(BaseModel):
    """Payload sent to the Gemini classification service.

    ``image_base64`` carries the JPEG frame encoded as a base64 string.
    The raw image is **never** persisted to disk.
    """

    image_base64: str = Field(
        ...,
        min_length=1,
        description="Base64-encoded JPEG image data",
    )


class GeminiClassificationResponse(BaseModel):
    """Structured JSON returned by the Gemini model.

    This schema mirrors the JSON format we instruct Gemini to produce.
    """

    waste_name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Human-readable name of the identified waste item",
    )
    category: Optional[str] = Field(
        default=None,
        description="Classification category: bio, organic, non_bio, or null",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Model confidence score between 0.0 and 1.0",
    )
    reason: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Brief explanation of the classification decision",
    )
    is_hazardous: bool = Field(
        default=False,
        description="Whether the item is flagged as hazardous waste",
    )
    requires_manual_review: bool = Field(
        default=False,
        description="Whether the item needs human review",
    )

    @field_validator("category", mode="before")
    @classmethod
    def _normalise_category(cls, v: Any) -> Optional[str]:
        """Accept case-insensitive category values and normalise."""
        if v is None:
            return None
        if not isinstance(v, str):
            return None
        normalised = v.strip().lower().replace("-", "_").replace(" ", "_")
        if normalised in ("none", "null", "unknown", "other", "unidentified", "ambiguous", ""):
            return None
        aliases = {
            "organic": "food_waste",
            "bio": "recyclable",
            "biodegradable": "recyclable",
            "non_bio": "non_recyclable",
            "nonbio": "non_recyclable",
            "food": "food_waste",
            "food_waste": "food_waste",
            "recyclable": "recyclable",
            "non_recyclable": "non_recyclable",
        }
        if normalised in aliases:
            return aliases[normalised]
        if normalised == "hazardous":
            return "hazardous"
        valid = {c.value for c in WasteCategory}
        raise ValueError(
            f"Invalid category '{v}'. Must be one of: {', '.join(valid)} or null"
        )

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, v: Any) -> float:
        try:
            val = float(v)
            return round(max(0.0, min(1.0, val)), 4)
        except (TypeError, ValueError):
            return 0.0


class ClassificationResult(BaseModel):
    """Validated classification result with bin assignment.

    Produced by ``ClassificationService.validate_classification`` after
    checking confidence thresholds, hazardous flags, etc.
    """

    waste_name: str
    category: Optional[WasteCategory] = None
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    is_hazardous: bool = False
    requires_manual_review: bool = False
    classification_status: ClassificationStatus = ClassificationStatus.PENDING
    bin_id: Optional[BinId] = None
    decision_reason: str = ""

    @field_validator("bin_id", mode="before")
    @classmethod
    def _coerce_bin_id(cls, v: Optional[str]) -> Optional[BinId]:
        if v is None:
            return None
        if isinstance(v, BinId):
            return v
        try:
            return BinId(v)
        except ValueError:
            return None

    def should_activate_servo(self) -> bool:
        """Return ``True`` only when it is safe to open a bin lid."""
        return (
            self.classification_status == ClassificationStatus.CLASSIFIED
            and self.bin_id is not None
            and not self.is_hazardous
            and not self.requires_manual_review
        )
