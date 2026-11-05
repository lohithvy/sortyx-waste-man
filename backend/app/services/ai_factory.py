"""
Sortyx 2.0 — AI Provider Factory.

Instantiates the Sortyx Cloud Run Classification API service
(reusing the deployed Vertex AI model without requiring local Google ADC or API keys).
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.logging_config import get_logger
from app.services.base_ai_service import BaseAIService
from app.services.cloud_run_service import CloudRunService

logger = get_logger(__name__)


def create_ai_service(settings: Settings) -> BaseAIService:
    """Instantiate and return the configured AI classification provider (Cloud Run)."""
    logger.info(
        "Selecting CLOUD_RUN as AI classification provider (endpoint=%s, timeout=%.1fs)",
        settings.cloud_run.endpoint,
        settings.cloud_run.timeout,
    )
    return CloudRunService(
        endpoint=settings.cloud_run.endpoint,
        timeout=settings.cloud_run.timeout,
        confidence_threshold=settings.app.confidence_threshold,
    )
