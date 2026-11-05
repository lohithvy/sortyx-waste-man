"""
Sortyx 2.0 — AI Classification Validation Unit Tests.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.enums import BinId, ClassificationStatus, WasteCategory
from app.schemas.classification import GeminiClassificationResponse, ClassificationResult
from app.services.classification_service import ClassificationService


def test_valid_organic_classification(
    classification_service: ClassificationService,
    sample_organic_response: GeminiClassificationResponse,
) -> None:
    result = classification_service.validate_classification(sample_organic_response)
    assert result.category == WasteCategory.ORGANIC
    assert result.bin_id == BinId.ORGANIC
    assert result.classification_status == ClassificationStatus.CLASSIFIED
    assert result.confidence >= 0.75
    assert not result.is_hazardous


def test_valid_bio_classification(
    classification_service: ClassificationService,
    sample_bio_response: GeminiClassificationResponse,
) -> None:
    result = classification_service.validate_classification(sample_bio_response)
    assert result.category == WasteCategory.BIO
    assert result.bin_id == BinId.BIO
    assert result.classification_status == ClassificationStatus.CLASSIFIED
    assert not result.is_hazardous


def test_valid_non_bio_classification(
    classification_service: ClassificationService,
    sample_non_bio_response: GeminiClassificationResponse,
) -> None:
    result = classification_service.validate_classification(sample_non_bio_response)
    assert result.category == WasteCategory.NON_BIO
    assert result.bin_id == BinId.NON_BIO
    assert result.classification_status == ClassificationStatus.CLASSIFIED
    assert not result.is_hazardous


def test_low_confidence_rejected(classification_service: ClassificationService) -> None:
    low_conf = GeminiClassificationResponse(
        waste_name="Ambiguous Object",
        category="organic",
        confidence=0.45,  # Below 0.75
        reason="Uncertain image resolution.",
        is_hazardous=False,
        requires_manual_review=False,
    )
    result = classification_service.validate_classification(low_conf)
    assert result.classification_status == ClassificationStatus.REJECTED
    assert result.bin_id is None  # Never assigns a bin on low confidence


def test_hazardous_waste_never_assigned_bin(
    classification_service: ClassificationService,
    sample_hazardous_response: GeminiClassificationResponse,
) -> None:
    result = classification_service.validate_classification(sample_hazardous_response)
    assert result.is_hazardous is True
    assert result.bin_id is None
    assert result.classification_status in (
        ClassificationStatus.HAZARDOUS,
        ClassificationStatus.MANUAL_REVIEW,
    )


def test_manual_review_item_never_assigned_bin(
    classification_service: ClassificationService,
) -> None:
    review_item = GeminiClassificationResponse(
        waste_name="Chemical Bottle",
        category="non_bio",
        confidence=0.88,
        reason="Contains liquid residue.",
        is_hazardous=False,
        requires_manual_review=True,
    )
    result = classification_service.validate_classification(review_item)
    assert result.requires_manual_review is True
    assert result.bin_id is None


def test_malformed_category_raises() -> None:
    with pytest.raises(ValidationError):
        GeminiClassificationResponse(
            waste_name="Sample Item",
            category="nuclear_waste",  # Invalid category
            confidence=0.90,
            reason="Sample",
            is_hazardous=False,
            requires_manual_review=False,
        )

