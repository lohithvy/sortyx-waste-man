"""
Sortyx 2.0 — WebSocket message schemas.

Typed Pydantic models for every WebSocket message the server can
broadcast to connected frontend clients.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.models.enums import SystemState, SensorStatus, WasteCategory


class WSMessage(BaseModel):
    """Envelope for all WebSocket messages."""

    type: str = Field(..., description="Message type identifier")
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StateUpdate(BaseModel):
    """Broadcast when the system state machine transitions."""

    type: str = "state_update"
    state: SystemState
    previous_state: Optional[SystemState] = None
    context: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BinStatusUpdate(BaseModel):
    """Broadcast when bin fill level changes."""

    type: str = "bin_status_update"
    bin_id: str
    display_name: str = ""
    fill_percentage: float = 0.0
    distance_cm: Optional[float] = None
    sensor_status: SensorStatus = SensorStatus.NOT_CONFIGURED
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SensorUpdate(BaseModel):
    """Broadcast with raw sensor readings."""

    type: str = "sensor_update"
    bin_id: str
    distance_cm: float
    fill_percentage: float
    sensor_status: SensorStatus = SensorStatus.ONLINE
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ClassificationUpdate(BaseModel):
    """Broadcast when a classification result is available."""

    type: str = "classification_update"
    waste_name: str = ""
    category: Optional[WasteCategory] = None
    confidence: float = 0.0
    reason: str = ""
    is_hazardous: bool = False
    requires_manual_review: bool = False
    bin_id: Optional[str] = None
    image_url: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class QuotaUpdate(BaseModel):
    """Broadcast when Gemini AI quota status changes or during active quota standby."""

    type: str = "quota_update"
    quota_exceeded: bool = False
    message: str = ""
    retry_after_seconds: int = 0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ErrorMessage(BaseModel):
    """Broadcast when the system encounters an error."""

    type: str = "error"
    error_code: str = "UNKNOWN"
    message: str = "An unexpected error occurred"
    recoverable: bool = True
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
