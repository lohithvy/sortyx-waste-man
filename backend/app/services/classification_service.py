"""
Sortyx 2.0 — Classification validation service.

This module is the **single authority** that decides whether a Gemini
classification result should trigger a servo activation.  It validates
confidence, category, hazardous flags, and maps the result to a bin.
"""

from __future__ import annotations

from app.core.logging_config import get_logger
from app.core.exceptions import ClassificationError
from app.models.enums import (
    WasteCategory,
    ClassificationStatus,
    BinId,
    CATEGORY_TO_BIN,
)
from app.schemas.classification import (
    GeminiClassificationResponse,
    ClassificationResult,
)

logger = get_logger(__name__)


class ClassificationService:
    """Validate and enrich raw Gemini classifications.

    Parameters
    ----------
    confidence_threshold:
        Minimum confidence required to accept a classification.
        Defaults to ``0.75`` (75 %).
    """

    def __init__(self, confidence_threshold: float = 0.75) -> None:
        if not 0.0 <= confidence_threshold <= 1.0:
            raise ClassificationError(
                f"Invalid confidence_threshold: {confidence_threshold}"
            )
        self._threshold = confidence_threshold
        logger.info(
            "ClassificationService initialised (threshold=%.0f%%)",
            confidence_threshold * 100,
        )

    # -- public API ----------------------------------------------------------

    def validate_classification(
        self, response: GeminiClassificationResponse
    ) -> ClassificationResult:
        """Validate a Gemini response and produce a final result.

        Decision hierarchy (evaluated top-to-bottom; first match wins):

        1. **Hazardous** → ``HAZARDOUS`` status, no servo.
        2. **Manual review requested** → ``MANUAL_REVIEW`` status, no servo.
        3. **Invalid category** → ``REJECTED``, no servo.
        4. **Low confidence** (below threshold) → ``REJECTED``, no servo.
        5. **Accepted** → ``CLASSIFIED`` with bin assignment, servo OK.

        Parameters
        ----------
        response:
            The raw classification from Gemini.

        Returns
        -------
        ClassificationResult
            Enriched result that includes bin assignment and a flag
            indicating whether the servo should activate.
        """
        waste_name = response.waste_name.strip()
        confidence = response.confidence
        reason = response.reason

        logger.info(
            "Validating classification: name=%s, category=%s, confidence=%.2f, "
            "hazardous=%s, manual_review=%s",
            waste_name,
            response.category,
            confidence,
            response.is_hazardous,
            response.requires_manual_review,
        )

        # ---- 1. Hazardous ---------------------------------------------------
        if response.is_hazardous or response.category == "hazardous":
            logger.warning("HAZARDOUS item detected: %s", waste_name)
            return ClassificationResult(
                waste_name=waste_name,
                category=None,
                confidence=confidence,
                reason=reason,
                is_hazardous=True,
                requires_manual_review=True,
                classification_status=ClassificationStatus.HAZARDOUS,
                bin_id=None,
                decision_reason="Item flagged as hazardous — servo will NOT activate",
            )

        # ---- 2. Manual review or Unknown ------------------------------------
        if (
            response.requires_manual_review
            or response.category is None
            or waste_name.lower() in ("unknown", "unidentified", "unidentified object", "none", "ambiguous", "hand", "human hand", "person", "empty hand", "")
            or response.category in ("unknown", "other", "none", "manual_review", "unidentified")
        ):
            logger.info("Manual review requested for: %s", waste_name)
            return ClassificationResult(
                waste_name=waste_name,
                category=None,
                confidence=confidence,
                reason=reason,
                is_hazardous=False,
                requires_manual_review=True,
                classification_status=ClassificationStatus.MANUAL_REVIEW,
                bin_id=None,
                decision_reason="Manual review required — servo will NOT activate",
            )

        # ---- 3. Category validation -----------------------------------------
        try:
            category = WasteCategory(response.category)
        except (ValueError, KeyError):
            logger.warning("Invalid category '%s' for item: %s", response.category, waste_name)
            return ClassificationResult(
                waste_name=waste_name,
                category=None,  # Do not classify unknown objects as Non-Bio by default
                confidence=confidence,
                reason=reason,
                is_hazardous=False,
                requires_manual_review=True,
                classification_status=ClassificationStatus.MANUAL_REVIEW,
                bin_id=None,
                decision_reason=f"Unknown or unmapped category '{response.category}' requires manual review",
            )

        # ---- 4. Confidence check --------------------------------------------
        if confidence < self._threshold:
            logger.info(
                "Low confidence (%.2f < %.2f) for: %s",
                confidence,
                self._threshold,
                waste_name,
            )
            return ClassificationResult(
                waste_name=waste_name,
                category=category,
                confidence=confidence,
                reason=reason,
                is_hazardous=False,
                requires_manual_review=False,
                classification_status=ClassificationStatus.REJECTED,
                bin_id=None,
                decision_reason=(
                    f"Confidence {confidence:.0%} below threshold {self._threshold:.0%}"
                ),
            )

        # ---- 5. Accepted ----------------------------------------------------
        bin_id = CATEGORY_TO_BIN[category]
        logger.info(
            "Classification ACCEPTED: %s -> %s (bin=%s, conf=%.0f%%)",
            waste_name,
            category.value,
            bin_id.value,
            confidence * 100,
        )
        return ClassificationResult(
            waste_name=waste_name,
            category=category,
            confidence=confidence,
            reason=reason,
            is_hazardous=False,
            requires_manual_review=False,
            classification_status=ClassificationStatus.CLASSIFIED,
            bin_id=bin_id,
            decision_reason=f"Classified as {category.value} with {confidence:.0%} confidence",
        )

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _safe_category(raw: Optional[str]) -> Optional[WasteCategory]:
        """Best-effort conversion; returns None if not a valid category."""
        if not raw:
            return None
        try:
            return WasteCategory(raw)
        except ValueError:
            return None
