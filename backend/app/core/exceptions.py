"""
Sortyx 2.0 — Custom exception hierarchy.

All application-specific errors derive from ``SortyxError`` so that
upstream handlers can catch the full family with a single ``except``
clause while still matching on specific sub-categories.
"""

from __future__ import annotations


class SortyxError(Exception):
    """Base exception for all Sortyx application errors."""

    def __init__(self, message: str = "An unexpected error occurred") -> None:
        self.message = message
        super().__init__(self.message)


# ---------------------------------------------------------------------------
# Hardware errors
# ---------------------------------------------------------------------------


class HardwareError(SortyxError):
    """Base error for hardware-related failures."""

    def __init__(self, message: str = "Hardware error occurred") -> None:
        super().__init__(message)


class CameraError(HardwareError):
    """Camera initialisation, capture, or release failure."""

    def __init__(self, message: str = "Camera error occurred") -> None:
        super().__init__(message)


class ServoError(HardwareError):
    """Servo motor control failure."""

    def __init__(self, message: str = "Servo error occurred") -> None:
        super().__init__(message)


class SensorError(HardwareError):
    """Ultrasonic or other sensor failure."""

    def __init__(self, message: str = "Sensor error occurred") -> None:
        super().__init__(message)


class PinConflictError(HardwareError):
    """Raised when a GPIO pin conflict or reserved pin violation is detected."""

    def __init__(self, message: str = "GPIO pin conflict detected") -> None:
        super().__init__(message)


class CalibrationError(HardwareError):
    """Raised when calibration data is invalid or missing."""

    def __init__(self, message: str = "Calibration error occurred") -> None:
        super().__init__(message)


# ---------------------------------------------------------------------------
# Classification errors
# ---------------------------------------------------------------------------


class ClassificationError(SortyxError):
    """Error during waste classification pipeline."""

    def __init__(self, message: str = "Classification error occurred") -> None:
        super().__init__(message)


class AIProviderError(ClassificationError):
    """Base error communicating with an AI classification provider."""

    def __init__(self, message: str = "AI provider error occurred") -> None:
        super().__init__(message)


class AIQuotaExceededError(AIProviderError):
    """AI API rate limit or quota exceeded."""

    def __init__(
        self,
        message: str = "AI API quota exceeded. AI classification paused until quota resets.",
        retry_delay_seconds: float = 300.0,
    ) -> None:
        super().__init__(message)
        self.retry_delay_seconds = retry_delay_seconds


class GeminiError(AIProviderError):
    """Error communicating with Google Gemini API."""

    def __init__(self, message: str = "Gemini API error occurred") -> None:
        super().__init__(message)


class GeminiQuotaExceededError(GeminiError, AIQuotaExceededError):
    """Google Gemini API rate limit or quota exceeded (HTTP 429 RESOURCE_EXHAUSTED)."""

    def __init__(
        self,
        message: str = "Gemini API quota exceeded. AI classification paused until quota resets.",
        retry_delay_seconds: float = 300.0,
    ) -> None:
        super().__init__(message)
        self.retry_delay_seconds = retry_delay_seconds


class GroqError(AIProviderError):
    """Error communicating with Groq API."""

    def __init__(self, message: str = "Groq API error occurred") -> None:
        super().__init__(message)


class GroqQuotaExceededError(GroqError, AIQuotaExceededError):
    """Groq API rate limit or quota exceeded (HTTP 429)."""

    def __init__(
        self,
        message: str = "Groq API rate limit reached. AI classification paused.",
        retry_delay_seconds: float = 60.0,
    ) -> None:
        super().__init__(message)
        self.retry_delay_seconds = retry_delay_seconds


class CloudRunAPIError(AIProviderError):
    """Error communicating with Sortyx Cloud Run classification API."""

    def __init__(self, message: str = "Cloud Run classification API error occurred") -> None:
        super().__init__(message)


class CloudRunQuotaExceededError(CloudRunAPIError, AIQuotaExceededError):
    """Sortyx Cloud Run API rate limit or quota exceeded (HTTP 429)."""

    def __init__(
        self,
        message: str = "Cloud Run API rate limit exceeded. AI classification temporarily paused.",
        retry_delay_seconds: float = 60.0,
    ) -> None:
        super().__init__(message)
        self.retry_delay_seconds = retry_delay_seconds


class VertexAIError(CloudRunAPIError):
    """Error communicating with Google Vertex AI / Cloud Run API (backward compatibility)."""

    def __init__(self, message: str = "Vertex AI / Cloud Run error occurred") -> None:
        super().__init__(message)


class VertexAIQuotaExceededError(CloudRunQuotaExceededError, VertexAIError):
    """Vertex AI / Cloud Run rate limit or quota exceeded (backward compatibility)."""

    def __init__(
        self,
        message: str = "Vertex AI / Cloud Run quota exceeded. AI classification paused.",
        retry_delay_seconds: float = 60.0,
    ) -> None:
        super().__init__(message, retry_delay_seconds=retry_delay_seconds)


# ---------------------------------------------------------------------------
# Infrastructure errors
# ---------------------------------------------------------------------------


class DatabaseError(SortyxError):
    """Supabase or other database operation failure."""

    def __init__(self, message: str = "Database error occurred") -> None:
        super().__init__(message)


class AuthenticationError(SortyxError):
    """Device or API authentication failure."""

    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(message)


class ConfigurationError(SortyxError):
    """Invalid or missing application configuration."""

    def __init__(self, message: str = "Configuration error") -> None:
        super().__init__(message)
