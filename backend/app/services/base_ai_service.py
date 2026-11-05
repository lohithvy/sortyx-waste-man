"""
Sortyx 2.0 — Base AI Classification Provider Interface.

Defines the contract that both Google Gemini and Groq AI providers adhere to.
Ensures seamless interchangeability without modifying state machines or validation logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict

from app.schemas.classification import GeminiClassificationResponse


class BaseAIService(ABC):
    """Abstract base class for waste classification AI providers."""

    @abstractmethod
    def initialise(self) -> None:
        """Create and verify provider client connection."""
        pass

    @abstractmethod
    def is_quota_exceeded(self) -> bool:
        """Check if provider rate limits or quotas are active."""
        pass

    @property
    @abstractmethod
    def quota_status(self) -> Dict[str, Any]:
        """Return structured quota status dictionary for dashboard status APIs."""
        pass

    @abstractmethod
    def reset_quota_state(self) -> None:
        """Reset in-memory quota tracking after cooldown expiry."""
        pass

    @abstractmethod
    async def classify_waste(self, image_bytes: bytes) -> GeminiClassificationResponse:
        """Analyze temporary in-memory frame bytes and return classification response."""
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return provider identifier (e.g. 'GEMINI' or 'GROQ')."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return active model identifier."""
        pass

