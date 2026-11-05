"""
Sortyx 2.0 — Cloud Run AI Service Unit Tests.

Covers:
1. Base64 image encoding and data URL structure.
2. JSON payload format (image_base64, location, classification_method).
3. Response parsing: Food Waste, Recyclable (Bio/Non-Bio), Non-Recyclable.
4. HTTP errors: 500, 503, 504, connection errors, and timeouts.
5. Malformed or invalid JSON responses.
6. Safe category mapping (never defaulting unknown to non-bio).
7. Hazardous item detection and manual review routing.
8. Low-confidence item manual review routing.
9. Quota lockout and cooldown mechanics on HTTP 429.
10. AI Factory instantiation for both CLOUD_RUN and VERTEX_AI providers.
"""

from __future__ import annotations

import base64
import json
import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.core.config import Settings
from app.core.exceptions import (
    CloudRunAPIError,
    CloudRunQuotaExceededError,
    AIProviderError,
    AIQuotaExceededError,
)
from app.schemas.classification import GeminiClassificationResponse
from app.services.ai_factory import create_ai_service
from app.services.base_ai_service import BaseAIService
from app.services.cloud_run_service import (
    CloudRunService,
    map_cloud_run_classification,
    DEFAULT_CLOUD_RUN_ENDPOINT,
)

SAMPLE_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00"


def _make_svc(**kwargs) -> CloudRunService:
    defaults = {
        "endpoint": DEFAULT_CLOUD_RUN_ENDPOINT,
        "timeout": 10.0,
        "confidence_threshold": 0.70,
    }
    defaults.update(kwargs)
    return CloudRunService(**defaults)


def _mock_response(status_code: int = 200, json_data: dict | None = None, text: str = "") -> MagicMock:
    mock = MagicMock(spec=requests.Response)
    mock.status_code = status_code
    mock.text = text or (json.dumps(json_data) if json_data else "")
    if json_data is not None:
        mock.json.return_value = json_data
    else:
        mock.json.side_effect = json.JSONDecodeError("Expecting value", "", 0)
    return mock


# ===========================================================================
# 1. Request Format & Base64 Conversion
# ===========================================================================

class TestCloudRunRequestFormat:
    def test_base64_data_uri_format(self):
        svc = _make_svc()
        with patch.object(svc._session, "post") as mock_post:
            mock_post.return_value = _mock_response(200, {
                "classification": "FOOD WASTE",
                "confidence": 0.95,
                "item_name": "Banana peel",
                "explanation": "Fruit scrap",
            })
            svc._sync_classify(SAMPLE_JPEG)

            mock_post.assert_called_once()
            _, kwargs = mock_post.call_args
            payload = kwargs["json"]

            assert "image_base64" in payload
            assert payload["image_base64"].startswith("data:image/jpeg;base64,")
            raw_b64 = payload["image_base64"].replace("data:image/jpeg;base64,", "")
            assert base64.b64decode(raw_b64) == SAMPLE_JPEG

    def test_json_request_payload_structure(self):
        svc = _make_svc()
        with patch.object(svc._session, "post") as mock_post:
            mock_post.return_value = _mock_response(200, {
                "classification": "FOOD WASTE",
                "confidence": 0.92,
                "item_name": "Apple core",
                "explanation": "Organic food",
            })
            svc._sync_classify(SAMPLE_JPEG)

            _, kwargs = mock_post.call_args
            payload = kwargs["json"]
            assert payload["location"] == "edge_device"
            assert payload["classification_method"] == "vertex_ai"
            assert kwargs["headers"] == {"Content-Type": "application/json"}
            assert kwargs["timeout"] == 10.0

    def test_empty_image_bytes_raises_error(self):
        svc = _make_svc()
        with pytest.raises(CloudRunAPIError, match="Empty image bytes"):
            svc._sync_classify(b"")


# ===========================================================================
# 2. Response Parsing & Category Mapping
# ===========================================================================

class TestCloudRunResponseParsing:
    def test_food_waste_maps_to_organic(self):
        svc = _make_svc()
        with patch.object(svc._session, "post") as mock_post:
            mock_post.return_value = _mock_response(200, {
                "classification": "FOOD WASTE",
                "confidence": 0.96,
                "item_name": "Banana Peel",
                "bin_color": "Orange",
                "explanation": "Biodegradable fresh fruit skin decomposes naturally.",
                "ai_provider": "Vertex AI gemini-2.5-flash-lite",
            })
            r = svc._sync_classify(SAMPLE_JPEG)

            assert r.category == "organic"
            assert r.waste_name == "Banana Peel"
            assert r.confidence == 0.96
            assert r.is_hazardous is False
            assert r.requires_manual_review is False

    def test_recyclable_paper_cardboard_maps_to_bio(self):
        svc = _make_svc()
        with patch.object(svc._session, "post") as mock_post:
            mock_post.return_value = _mock_response(200, {
                "classification": "RECYCLABLE",
                "confidence": 0.93,
                "item_name": "Cardboard Box",
                "bin_color": "Green",
                "explanation": "Clean corrugated cardboard packaging material.",
                "ai_provider": "Vertex AI gemini-2.5-flash-lite",
            })
            r = svc._sync_classify(SAMPLE_JPEG)

            assert r.category == "bio"
            assert r.waste_name == "Cardboard Box"
            assert r.confidence == 0.93
            assert r.requires_manual_review is False

    def test_recyclable_plastic_bottle_maps_to_non_bio(self):
        svc = _make_svc()
        with patch.object(svc._session, "post") as mock_post:
            mock_post.return_value = _mock_response(200, {
                "classification": "RECYCLABLE",
                "confidence": 0.97,
                "item_name": "PET Plastic Bottle",
                "bin_color": "Green",
                "explanation": "Clear plastic water bottle is standard recyclable polymer.",
                "ai_provider": "Vertex AI gemini-2.5-flash-lite",
            })
            r = svc._sync_classify(SAMPLE_JPEG)

            assert r.category == "non_bio"
            assert r.waste_name == "PET Plastic Bottle"
            assert r.confidence == 0.97
            assert r.requires_manual_review is False

    def test_recyclable_metal_can_maps_to_non_bio(self):
        svc = _make_svc()
        with patch.object(svc._session, "post") as mock_post:
            mock_post.return_value = _mock_response(200, {
                "classification": "RECYCLABLE",
                "confidence": 0.94,
                "item_name": "Aluminium Soda Can",
                "bin_color": "Green",
                "explanation": "Aluminium beverage can.",
            })
            r = svc._sync_classify(SAMPLE_JPEG)

            assert r.category == "non_bio"
            assert r.waste_name == "Aluminium Soda Can"
            assert r.requires_manual_review is False

    def test_non_recyclable_plastic_wrapper_maps_to_non_bio(self):
        svc = _make_svc()
        with patch.object(svc._session, "post") as mock_post:
            mock_post.return_value = _mock_response(200, {
                "classification": "NON-RECYCLABLE",
                "confidence": 0.89,
                "item_name": "Chips Packet / Plastic Wrapper",
                "bin_color": "Black",
                "explanation": "Multilayer metallized plastic film wrapper.",
            })
            r = svc._sync_classify(SAMPLE_JPEG)

            assert r.category == "non_bio"
            assert r.waste_name == "Chips Packet / Plastic Wrapper"
            assert r.requires_manual_review is False

    def test_non_recyclable_banana_peel_maps_to_organic(self):
        """When /api/classify returns Non-Recyclable for banana peel, map to organic."""
        svc = _make_svc()
        with patch.object(svc._session, "post") as mock_post:
            mock_post.return_value = _mock_response(200, {
                "classification": "Non-Recyclable",
                "confidence": 0.95,
                "item_name": "Banana peel organic food waste",
                "bin_color": "Black",
                "explanation": "Organic food waste is generally not recyclable in standard recycling programs.",
                "ai_provider": "Vertex AI gemini-2.5-flash-lite",
            })
            r = svc._sync_classify(SAMPLE_JPEG)

            assert r.category == "organic"
            assert r.waste_name == "Banana peel organic food waste"
            assert r.confidence == 0.95
            assert r.requires_manual_review is False

    def test_thermocol_maps_to_non_bio(self):
        svc = _make_svc()
        with patch.object(svc._session, "post") as mock_post:
            mock_post.return_value = _mock_response(200, {
                "classification": "Non-Recyclable",
                "confidence": 0.91,
                "item_name": "Thermocol piece",
                "explanation": "Expanded polystyrene packaging.",
            })
            r = svc._sync_classify(SAMPLE_JPEG)

            assert r.category == "non_bio"
            assert r.requires_manual_review is False

    def test_wood_maps_to_bio(self):
        svc = _make_svc()
        with patch.object(svc._session, "post") as mock_post:
            mock_post.return_value = _mock_response(200, {
                "classification": "Recyclable",
                "confidence": 0.88,
                "item_name": "Wooden craft stick",
                "explanation": "Untreated natural wood material.",
            })
            r = svc._sync_classify(SAMPLE_JPEG)

            assert r.category == "bio"
            assert r.requires_manual_review is False

    def test_confidence_is_genuine_and_not_hardcoded(self):
        for score in (0.72, 0.81, 0.88, 0.95, 0.99):
            svc = _make_svc()
            with patch.object(svc._session, "post") as mock_post:
                mock_post.return_value = _mock_response(200, {
                    "classification": "FOOD WASTE",
                    "confidence": score,
                    "item_name": "Orange peel",
                    "explanation": "Fruit",
                })
                r = svc._sync_classify(SAMPLE_JPEG)
                assert r.confidence == score

    def test_model_name_extracted_from_ai_provider(self):
        svc = _make_svc()
        with patch.object(svc._session, "post") as mock_post:
            mock_post.return_value = _mock_response(200, {
                "classification": "FOOD WASTE",
                "confidence": 0.95,
                "item_name": "Apple",
                "explanation": "Fruit",
                "ai_provider": "Vertex AI gemini-2.5-flash-lite",
            })
            svc._sync_classify(SAMPLE_JPEG)
            assert svc.model_name == "Vertex AI gemini-2.5-flash-lite"


# ===========================================================================
# 3. Safety & Manual Review Routing
# ===========================================================================

class TestCloudRunSafetyAndManualReview:
    def test_hazardous_battery_flagged_and_requires_manual_review(self):
        svc = _make_svc()
        with patch.object(svc._session, "post") as mock_post:
            mock_post.return_value = _mock_response(200, {
                "classification": "NON-RECYCLABLE",
                "confidence": 0.96,
                "item_name": "Lithium-Ion Battery",
                "bin_color": "Black",
                "explanation": "Hazardous battery requiring specialized e-waste dropoff.",
            })
            r = svc._sync_classify(SAMPLE_JPEG)

            assert r.is_hazardous is True
            assert r.category is None
            assert r.requires_manual_review is True

    def test_hazardous_chemicals_flagged_and_requires_manual_review(self):
        svc = _make_svc()
        with patch.object(svc._session, "post") as mock_post:
            mock_post.return_value = _mock_response(200, {
                "classification": "NON-RECYCLABLE",
                "confidence": 0.92,
                "item_name": "Pesticide Bottle / Toxic Chemical",
                "explanation": "Corrosive chemical container",
            })
            r = svc._sync_classify(SAMPLE_JPEG)

            assert r.is_hazardous is True
            assert r.category is None
            assert r.requires_manual_review is True

    def test_low_confidence_routes_to_manual_review(self):
        svc = _make_svc(confidence_threshold=0.75)
        with patch.object(svc._session, "post") as mock_post:
            mock_post.return_value = _mock_response(200, {
                "classification": "FOOD WASTE",
                "confidence": 0.55,  # Below threshold
                "item_name": "Unclear Organic Item",
                "explanation": "Too blurry to identify",
            })
            r = svc._sync_classify(SAMPLE_JPEG)

            assert r.category is None
            assert r.requires_manual_review is True

    def test_unknown_classification_routes_to_manual_review(self):
        svc = _make_svc()
        with patch.object(svc._session, "post") as mock_post:
            mock_post.return_value = _mock_response(200, {
                "classification": "Unknown",
                "confidence": 0.95,
                "item_name": "Unknown Item",
                "bin_color": "Black",
                "explanation": "Could not parse AI response",
            })
            r = svc._sync_classify(SAMPLE_JPEG)

            assert r.category is None
            assert r.requires_manual_review is True

    def test_ambiguous_recyclable_without_material_routes_to_manual_review(self):
        svc = _make_svc()
        with patch.object(svc._session, "post") as mock_post:
            mock_post.return_value = _mock_response(200, {
                "classification": "RECYCLABLE",
                "confidence": 0.90,
                "item_name": "General Recyclable Object",
                "explanation": "Unspecified material",
            })
            r = svc._sync_classify(SAMPLE_JPEG)

            # Neither bio nor non-bio keywords matched -> safe manual review
            assert r.category is None
            assert r.requires_manual_review is True

    def test_ambiguous_mixed_material_routes_to_manual_review(self):
        svc = _make_svc()
        with patch.object(svc._session, "post") as mock_post:
            mock_post.return_value = _mock_response(200, {
                "classification": "RECYCLABLE",
                "confidence": 0.88,
                "item_name": "Plastic-lined paper coffee cup",
                "explanation": "Paper carton with internal plastic film lining",
            })
            r = svc._sync_classify(SAMPLE_JPEG)

            # Contains both bio (paper) and non-bio (plastic) keywords -> ambiguous
            assert r.category is None
            assert r.requires_manual_review is True


# ===========================================================================
# 4. HTTP Errors, Timeouts & Connection Failures
# ===========================================================================

class TestCloudRunHTTPErrors:
    def test_http_500_server_error_raises_cloud_run_error(self):
        svc = _make_svc()
        with patch.object(svc._session, "post") as mock_post:
            mock_post.return_value = _mock_response(500, text="Internal Server Error")
            with pytest.raises(CloudRunAPIError, match="HTTP 500"):
                svc._sync_classify(SAMPLE_JPEG)

    def test_http_503_service_unavailable_raises_cloud_run_error(self):
        svc = _make_svc()
        with patch.object(svc._session, "post") as mock_post:
            mock_post.return_value = _mock_response(503, text="AI Service not ready")
            with pytest.raises(CloudRunAPIError, match="HTTP 503"):
                svc._sync_classify(SAMPLE_JPEG)

    def test_http_504_gateway_timeout_raises_cloud_run_error(self):
        svc = _make_svc()
        with patch.object(svc._session, "post") as mock_post:
            mock_post.return_value = _mock_response(504, text="Gateway Timeout")
            with pytest.raises(CloudRunAPIError, match="HTTP 504"):
                svc._sync_classify(SAMPLE_JPEG)

    def test_timeout_exception_raises_cloud_run_error(self):
        svc = _make_svc(timeout=5.0)
        with patch.object(svc._session, "post") as mock_post:
            mock_post.side_effect = requests.exceptions.Timeout("Connection timed out")
            with pytest.raises(CloudRunAPIError, match="timed out"):
                svc._sync_classify(SAMPLE_JPEG)

    def test_connection_error_raises_cloud_run_error(self):
        svc = _make_svc()
        with patch.object(svc._session, "post") as mock_post:
            mock_post.side_effect = requests.exceptions.ConnectionError("DNS failure")
            with pytest.raises(CloudRunAPIError, match="connection failed"):
                svc._sync_classify(SAMPLE_JPEG)

    def test_malformed_json_raises_cloud_run_error(self):
        svc = _make_svc()
        with patch.object(svc._session, "post") as mock_post:
            mock_post.return_value = _mock_response(200, text="<html>502 Bad Gateway</html>")
            with pytest.raises(CloudRunAPIError, match="Malformed JSON"):
                svc._sync_classify(SAMPLE_JPEG)

    def test_non_dict_json_raises_cloud_run_error(self):
        svc = _make_svc()
        with patch.object(svc._session, "post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200, json=lambda: ["array", "not", "dict"])
            with pytest.raises(CloudRunAPIError, match="not a JSON object"):
                svc._sync_classify(SAMPLE_JPEG)


# ===========================================================================
# 5. Quota Lockout & Cooldown Mechanics
# ===========================================================================

class TestCloudRunQuotaAndCooldown:
    def test_http_429_triggers_quota_lockout(self):
        svc = _make_svc()
        with patch.object(svc._session, "post") as mock_post:
            mock_post.return_value = _mock_response(429, text="Rate limit exceeded")
            with pytest.raises(CloudRunQuotaExceededError) as exc_info:
                svc._sync_classify(SAMPLE_JPEG)

            assert exc_info.value.retry_delay_seconds == 60.0
            assert svc.is_quota_exceeded() is True

    def test_quota_lockout_blocks_subsequent_requests(self):
        svc = _make_svc()
        svc._quota_exceeded = True
        svc._quota_retry_after = time.time() + 300.0

        with pytest.raises(CloudRunQuotaExceededError):
            svc._sync_classify(SAMPLE_JPEG)

    def test_quota_cooldown_expires(self):
        svc = _make_svc()
        svc._quota_exceeded = True
        svc._quota_retry_after = time.time() - 1.0  # Already expired

        assert svc.is_quota_exceeded() is False

    def test_reset_quota_clears_lockout(self):
        svc = _make_svc()
        svc._quota_exceeded = True
        svc._quota_retry_after = time.time() + 300.0

        svc.reset_quota_state()
        assert svc.is_quota_exceeded() is False
        assert svc.quota_status["quota_exceeded"] is False


# ===========================================================================
# 6. AI Factory Integration & Contract Compliance
# ===========================================================================

class TestAIFactoryIntegration:
    def test_factory_creates_cloud_run_service_for_cloud_run(self):
        settings = Settings()
        settings.app.ai_provider = "CLOUD_RUN"
        settings.cloud_run.endpoint = "https://sortyx-classify-5bwsw4lr6q-uc.a.run.app/api/classify"

        svc = create_ai_service(settings)
        assert isinstance(svc, CloudRunService)
        assert svc.provider_name == "CLOUD_RUN"
        assert svc.endpoint == "https://sortyx-classify-5bwsw4lr6q-uc.a.run.app/api/classify"

    def test_factory_creates_cloud_run_service_for_vertex_ai(self):
        # Migrated VERTEX_AI setting routes to Cloud Run API
        settings = Settings()
        settings.app.ai_provider = "VERTEX_AI"

        svc = create_ai_service(settings)
        assert isinstance(svc, CloudRunService)

    def test_contract_compliance(self):
        svc = _make_svc()
        assert isinstance(svc, BaseAIService)
        assert hasattr(svc, "initialise")
        assert hasattr(svc, "is_quota_exceeded")
        assert hasattr(svc, "quota_status")
        assert hasattr(svc, "reset_quota_state")
        assert hasattr(svc, "classify_waste")
        assert isinstance(svc.quota_status, dict)
        assert "quota_exceeded" in svc.quota_status
        assert "retry_after_seconds" in svc.quota_status

