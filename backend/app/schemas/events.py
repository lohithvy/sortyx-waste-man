"""
Sortyx 2.0 — Event and statistics schemas.

Pydantic models for sorting events, sensor readings, daily statistics,
and bin status representations.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, computed_field

from app.models.enums import (
    WasteCategory,
    ClassificationStatus,
    SortingStatus,
    SensorStatus,
)


# ---------------------------------------------------------------------------
# Sorting events
# ---------------------------------------------------------------------------


class SortingEventCreate(BaseModel):
    """Data required to create a new sorting event row."""

    device_id: UUID
    bin_id: Optional[UUID] = None
    waste_name: str = Field(..., min_length=1, max_length=200)
    category: WasteCategory
    confidence: float = Field(..., ge=0.0, le=1.0)
    classification_status: ClassificationStatus = ClassificationStatus.PENDING
    sorting_status: SortingStatus = SortingStatus.PENDING
    classification_model: str = "gemini-2.0-flash"
    decision_reason: str = ""


class SortingEventUpdate(BaseModel):
    """Mutable fields for an existing sorting event."""

    bin_id: Optional[UUID] = None
    classification_status: Optional[ClassificationStatus] = None
    sorting_status: Optional[SortingStatus] = None
    decision_reason: Optional[str] = None


class SortingEventResponse(BaseModel):
    """Full sorting event as returned to callers."""

    id: UUID
    device_id: UUID
    bin_id: Optional[UUID] = None
    waste_name: str
    category: WasteCategory
    confidence: float
    classification_status: ClassificationStatus
    sorting_status: SortingStatus
    classification_model: str
    decision_reason: str
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Sensor readings
# ---------------------------------------------------------------------------


class SensorReadingCreate(BaseModel):
    """Data required to insert a sensor reading row."""

    bin_id: UUID
    distance_cm: float = Field(..., ge=0.0)
    fill_percentage: float = Field(..., ge=0.0, le=100.0)
    sensor_status: SensorStatus = SensorStatus.ONLINE


# ---------------------------------------------------------------------------
# Aggregations
# ---------------------------------------------------------------------------


class DailyStats(BaseModel):
    """Summary statistics for the current day (IST timezone)."""

    total_items: int = 0
    bio_count: int = 0
    organic_count: int = 0
    non_bio_count: int = 0
    hazardous_count: int = 0
    manual_review_count: int = 0
    average_confidence: float = 0.0
    failed_count: int = 0

    @computed_field
    @property
    def totalItems(self) -> int:
        return self.total_items

    @computed_field
    @property
    def organic(self) -> int:
        return self.organic_count

    @computed_field
    @property
    def bio(self) -> int:
        return self.bio_count

    @computed_field
    @property
    def nonBio(self) -> int:
        return self.non_bio_count


class BinStatus(BaseModel):
    """Current status of a single waste bin."""

    id: UUID
    category: str
    display_name: str
    fill_percentage: float = Field(ge=0.0, le=100.0, default=0.0)
    distance_cm: Optional[float] = None
    sensor_status: SensorStatus = SensorStatus.NOT_CONFIGURED
    last_read_at: Optional[datetime] = None
