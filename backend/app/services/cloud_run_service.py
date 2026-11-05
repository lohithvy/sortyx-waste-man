"""
Sortyx 2.0 — Cloud Run AI Classification Provider.

Connects Sortyx 2.0 to the existing Sortyx Cloud Run classification service:
https://sortyx-classify-5bwsw4lr6q-uc.a.run.app/api/three-classify

Features:
- Pure HTTP client using requests with connection pooling and timeouts.
- Converts captured in-memory JPEG frames to Base64 data URLs.
- Never saves images to disk.
- Safe mapping layer translating Cloud Run categories (FOOD WASTE, RECYCLABLE,
  NON-RECYCLABLE) into Sortyx 2.0 categories (organic, bio, non_bio).
- Strict safety rules: hazardous, low-confidence, or ambiguous items route to
  manual review with null category. Never hardcodes confidence or forces guesses.
- Quota and rate-limit tracking with cooldown lockout on HTTP 429.
"""

from __future__ import annotations

import asyncio
import base64
import re
import time
from typing import Any, Dict, Optional, Tuple

import requests

from app.core.logging_config import get_logger
from app.core.exceptions import (
    CloudRunAPIError,
    CloudRunQuotaExceededError,
    AIProviderError,
    AIQuotaExceededError,
)
from app.schemas.classification import GeminiClassificationResponse
from app.services.base_ai_service import BaseAIService

logger = get_logger(__name__)

DEFAULT_CLOUD_RUN_ENDPOINT = (
    "https://sortyx-classify-5bwsw4lr6q-uc.a.run.app/api/classify"
)

# 1. Hazardous waste keywords (highest priority safety rule)
HAZARDOUS_KEYWORDS = frozenset({
    "battery", "batteries", "lithium", "chemical", "poison", "toxic",
    "syringe", "needle", "e-waste", "electronic", "circuit", "mercury",
    "paint", "pesticide", "aerosol", "flammable", "corrosive", "acid",
})

# 2. Organic food waste keywords
ORGANIC_KEYWORDS = frozenset({
    "food", "fruit", "fruits", "vegetable", "vegetables", "peel", "peels",
    "skin", "banana", "apple", "orange", "citrus", "core", "scraps", "scrap",
    "leftover", "leftovers", "cooked", "meal", "rice", "bread", "chapati",
    "curry", "meat", "fish", "chicken", "bone", "bones", "eggshell", "eggshells",
    "egg", "tea", "coffee", "grounds", "organic", "compost", "compostable",
    "kitchen waste", "food waste", "banana peel", "fruit peel", "vegetable scrap",
})

# 3. Bio (biodegradable non-food) keywords
BIO_KEYWORDS = frozenset({
    "paper", "cardboard", "carton", "newspaper", "magazine", "corrugated",
    "cellulose", "kraft", "box", "wood", "wooden", "leaves", "leaf",
    "plant", "twigs", "stick", "sawdust", "coconut shell", "bamboo",
})

# 4. Non-Bio keywords (plastics, metals, glass, wrappers, thermocol)
NON_BIO_KEYWORDS = frozenset({
    "plastic", "pet", "hdpe", "pvc", "ldpe", "pp", "ps", "polyester",
    "bottle", "container", "jug", "jar", "metal", "can", "tin", "aluminium",
    "aluminum", "steel", "glass", "tub", "tray", "foil", "wire", "pipe",
    "wrapper", "sachet", "packet", "chips", "crisps", "snack",
    "thermocol", "styrofoam", "polystyrene", "rubber", "vinyl", "synthetic",
    "pouch", "straw", "cutlery", "film", "bag", "bubble wrap", "laminate",
})


def _contains_any_keyword(text: str, keywords: frozenset[str]) -> bool:
    """Check if any keyword appears as a whole word or distinct phrase in text."""
    text_clean = text.lower()
    for kw in keywords:
        if " " in kw:
            if kw in text_clean:
                return True
        else:
            if re.search(rf"\b{re.escape(kw)}\b", text_clean):
                return True
    return False


def map_cloud_run_classification(
    classification: str,
    item_name: str,
    confidence: float,
    explanation: str,
    bin_color: str = "",
    confidence_threshold: float = 0.70,
) -> Tuple[Optional[str], bool, bool]:
    """Map Cloud Run classification response to Sortyx 2.0 categories.

    Uses item_name and explanation to identify the actual material,
    never relying on the recyclable label alone.

    Returns:
        (category, is_hazardous, requires_manual_review)
        category is one of: 'organic', 'bio', 'non_bio', or None.
    """
    cls_clean = (classification or "").strip().upper()
    item_lower = (item_name or "").lower()
    exp_lower = (explanation or "").lower()
    full_text = f"{item_lower} {exp_lower}"

    # 1. Hazardous waste check (highest priority safety rule)
    if _contains_any_keyword(full_text, HAZARDOUS_KEYWORDS):
        logger.warning("Hazardous item detected in Cloud Run output: '%s'", item_name)
        return None, True, True

    # 2. Low confidence or unparseable check
    if confidence < confidence_threshold:
        logger.info(
            "Confidence %.2f below threshold %.2f -> manual review",
            confidence,
            confidence_threshold,
        )
        return None, False, True

    if (
        cls_clean in ("UNKNOWN", "OTHER", "UNIDENTIFIED", "")
        or "unknown" in item_lower
        or "could not parse" in exp_lower
    ):
        logger.info("Unidentified/Unknown item from Cloud Run -> manual review")
        return None, False, True

    # 3. Detect material characteristics from item_name and explanation
    is_organic = _contains_any_keyword(full_text, ORGANIC_KEYWORDS) or cls_clean in (
        "FOOD WASTE",
        "FOOD_WASTE",
        "FOOD",
        "ORGANIC",
    )
    is_bio = _contains_any_keyword(full_text, BIO_KEYWORDS)
    is_non_bio = _contains_any_keyword(full_text, NON_BIO_KEYWORDS) or cls_clean in (
        "PLASTIC",
        "METAL",
        "GLASS",
    )

    # 4. Ambiguous or mixed materials check
    matched_categories = [is_organic, is_bio, is_non_bio].count(True)
    if matched_categories > 1:
        logger.info(
            "Item '%s' contains mixed or ambiguous materials -> manual review",
            item_name,
        )
        return None, False, True

    # 5. Clear single-category mapping
    if is_organic:
        return "organic", False, False

    if is_bio:
        return "bio", False, False

    if is_non_bio:
        return "non_bio", False, False

    # 6. Safety fallback: If material cannot be determined from text, never guess
    logger.info(
        "Item '%s' material could not be determined reliably -> manual review",
        item_name,
    )
    return None, False, True


class CloudRunService(BaseAIService):
    """Sortyx 2.0 AI Provider interfacing with the existing Sortyx Cloud Run service."""

    def __init__(
        self,
        endpoint: str = DEFAULT_CLOUD_RUN_ENDPOINT,
        timeout: float = 15.0,
        confidence_threshold: float = 0.70,
    ) -> None:
        self._endpoint = endpoint.strip() or DEFAULT_CLOUD_RUN_ENDPOINT
        self._timeout = max(3.0, float(timeout))
        self._confidence_threshold = float(confidence_threshold)
        self._session: Optional[requests.Session] = None
        self._last_ai_provider: str = "Cloud Run Gemini 3 (Vertex AI)"

        # Quota and rate-limit tracking
        self._quota_exceeded: bool = False
        self._quota_retry_after: float = 0.0
        self._quota_message: str = ""

        self.initialise()

    # -- BaseAIService contract properties ------------------------------------

    @property
    def provider_name(self) -> str:
        return "CLOUD_RUN"

    @property
    def model_name(self) -> str:
        return self._last_ai_provider

    @property
    def endpoint(self) -> str:
        return self._endpoint

    # -- Lifecycle -----------------------------------------------------------

    def initialise(self) -> None:
        """Create a requests session with keep-alive pooling."""
        try:
            self._session = requests.Session()
            logger.info(
                "CloudRunService initialised with endpoint: %s (timeout=%.1fs)",
                self._endpoint,
                self._timeout,
            )
        except Exception as exc:
            logger.error("Failed to initialise CloudRunService session: %s", exc)
            self._session = None

    # -- Quota and rate limit tracking ---------------------------------------

    def is_quota_exceeded(self) -> bool:
        """Check if rate limit cooldown is active."""
        if not self._quota_exceeded:
            return False
        if time.time() >= self._quota_retry_after:
            logger.info("Cloud Run rate-limit cooldown expired. Resuming classification.")
            self._quota_exceeded = False
            return False
        return True

    @property
    def quota_status(self) -> Dict[str, Any]:
        """Return structured quota status dictionary for frontend / monitoring."""
        exceeded = self.is_quota_exceeded()
        remaining_s = max(0, int(self._quota_retry_after - time.time())) if exceeded else 0
        return {
            "quota_exceeded": exceeded,
            "message": self._quota_message if exceeded else "",
            "retry_after_seconds": remaining_s,
        }

    def reset_quota_state(self) -> None:
        """Manually clear rate limit lock."""
        self._quota_exceeded = False
        self._quota_retry_after = 0.0
        self._quota_message = ""

    # -- Classification ------------------------------------------------------

    async def classify_waste(self, image_bytes: bytes) -> GeminiClassificationResponse:
        """Asynchronously classify captured in-memory frame bytes via Cloud Run."""
        return await asyncio.to_thread(self._sync_classify, image_bytes)

    def _sync_classify(self, image_bytes: bytes) -> GeminiClassificationResponse:
        """Synchronously send Base64 data URL to Cloud Run and map response."""
        if self.is_quota_exceeded():
            raise CloudRunQuotaExceededError(
                self._quota_message
                or "Cloud Run API rate limit in effect. Please wait.",
                retry_delay_seconds=max(1.0, self._quota_retry_after - time.time()),
            )

        if not image_bytes:
            raise CloudRunAPIError("Empty image bytes provided for classification")

        # 1. Base64 conversion with data URL prefix
        b64_str = base64.b64encode(image_bytes).decode("utf-8")
        data_uri = f"data:image/jpeg;base64,{b64_str}"

        # 2. Build request payload preserving the legacy format
        payload = {
            "image_base64": data_uri,
            "location": "edge_device",
            "classification_method": "vertex_ai",
        }

        # 3. Execute HTTP POST
        session = self._session or requests.Session()
        t0 = time.time()

        try:
            resp = session.post(
                self._endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=self._timeout,
            )
        except requests.exceptions.Timeout as exc:
            logger.error("Cloud Run request timed out after %.1fs: %s", self._timeout, exc)
            raise CloudRunAPIError(f"Cloud Run request timed out after {self._timeout:.1f}s") from exc
        except requests.exceptions.ConnectionError as exc:
            logger.error("Failed to connect to Cloud Run service at %s: %s", self._endpoint, exc)
            raise CloudRunAPIError(f"Cloud Run connection failed: {exc}") from exc
        except requests.exceptions.RequestException as exc:
            logger.error("Cloud Run request exception: %s", exc)
            raise CloudRunAPIError(f"Cloud Run HTTP request failed: {exc}") from exc

        elapsed = time.time() - t0
        logger.info("Cloud Run response received in %.2fs (status=%d)", elapsed, resp.status_code)

        # 4. Handle HTTP status codes
        if resp.status_code == 429:
            retry_delay = 60.0
            self._quota_exceeded = True
            self._quota_retry_after = time.time() + retry_delay
            self._quota_message = "Cloud Run API rate limit reached. Standing by for 60s."
            raise CloudRunQuotaExceededError(
                self._quota_message,
                retry_delay_seconds=retry_delay,
            )

        if resp.status_code in (500, 502, 503, 504):
            raise CloudRunAPIError(
                f"Cloud Run server error (HTTP {resp.status_code}): {resp.text[:200]}"
            )

        if resp.status_code != 200:
            raise CloudRunAPIError(
                f"Cloud Run returned unexpected HTTP {resp.status_code}: {resp.text[:200]}"
            )

        # 5. Parse JSON
        try:
            data = resp.json()
        except Exception as exc:
            logger.error("Failed to parse JSON from Cloud Run response: %s", exc)
            raise CloudRunAPIError("Malformed JSON response from Cloud Run") from exc

        if not isinstance(data, dict):
            raise CloudRunAPIError("Cloud Run response root is not a JSON object")

        # 6. Extract fields
        raw_classification = str(data.get("classification") or "Unknown")
        raw_confidence = float(data.get("confidence") or 0.0)
        item_name = str(data.get("item_name") or "Unknown Item").strip()
        bin_color = str(data.get("bin_color") or "").strip()
        explanation = str(data.get("explanation") or "").strip()
        ai_provider = str(data.get("ai_provider") or "Vertex AI")
        self._last_ai_provider = ai_provider

        # Diagnostic log: record full raw response metadata without logging image Base64
        logger.info(
            "Cloud Run raw response: status=%d, classification='%s', item_name='%s', "
            "confidence=%.2f, bin_color='%s', explanation='%s', ai_provider='%s'",
            resp.status_code,
            raw_classification,
            item_name,
            raw_confidence,
            bin_color,
            explanation,
            ai_provider,
        )

        # 7. Apply safe mapping layer
        category, is_hazardous, requires_manual_review = map_cloud_run_classification(
            classification=raw_classification,
            item_name=item_name,
            confidence=raw_confidence,
            explanation=explanation,
            bin_color=bin_color,
            confidence_threshold=self._confidence_threshold,
        )

        # On successful response, clear quota flag
        self._quota_exceeded = False

        # 8. Construct standard response for downstream validation
        return GeminiClassificationResponse(
            waste_name=item_name or "Unknown Item",
            category=category,
            confidence=round(max(0.0, min(1.0, raw_confidence)), 4),
            reason=explanation or f"Classified by Cloud Run ({raw_classification})",
            is_hazardous=is_hazardous,
            requires_manual_review=requires_manual_review,
        )

