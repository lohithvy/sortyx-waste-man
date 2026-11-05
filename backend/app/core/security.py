"""
Sortyx 2.0 — Device authentication and request security.

Provides HMAC-based device authentication with replay protection
(nonce cache + timestamp window) and a simple in-memory token-bucket
rate limiter.  Secrets are **never** logged or exposed.
"""

from __future__ import annotations

import hashlib
import hmac
import time
import threading
from collections import OrderedDict
from typing import Optional

from app.core.logging_config import get_logger
from app.core.exceptions import AuthenticationError

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Nonce cache with TTL — replay protection
# ---------------------------------------------------------------------------


class NonceCache:
    """Thread-safe nonce cache with automatic TTL eviction.

    Prevents request replay attacks by remembering recently-used nonces.
    """

    def __init__(self, ttl_seconds: int = 300, max_size: int = 10_000) -> None:
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._cache: OrderedDict[str, float] = OrderedDict()
        self._lock = threading.Lock()

    def _evict_expired(self) -> None:
        """Remove entries older than TTL (must be called under lock)."""
        now = time.time()
        while self._cache:
            oldest_nonce, ts = next(iter(self._cache.items()))
            if now - ts > self._ttl:
                self._cache.pop(oldest_nonce)
            else:
                break

    def check_and_store(self, nonce: str) -> bool:
        """Return ``True`` if the nonce is fresh (not replayed).

        The nonce is stored for future replay detection.  Returns
        ``False`` if the nonce was already seen within the TTL window.
        """
        with self._lock:
            self._evict_expired()
            if nonce in self._cache:
                return False
            # Evict oldest if at capacity
            if len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)
            self._cache[nonce] = time.time()
            return True


# ---------------------------------------------------------------------------
# Token-bucket rate limiter
# ---------------------------------------------------------------------------


class RateLimiter:
    """Simple in-memory token-bucket rate limiter.

    Parameters
    ----------
    rate:
        Tokens added per second.
    capacity:
        Maximum bucket size.
    """

    def __init__(self, rate: float = 10.0, capacity: int = 20) -> None:
        self._rate = rate
        self._capacity = capacity
        self._tokens: float = float(capacity)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def allow(self) -> bool:
        """Return ``True`` if the request is allowed, consuming one token."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(
                self._capacity, self._tokens + elapsed * self._rate
            )
            self._last_refill = now
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False


# ---------------------------------------------------------------------------
# HMAC request verification
# ---------------------------------------------------------------------------

# Module-level singletons (initialised lazily)
_nonce_cache: Optional[NonceCache] = None
_rate_limiter: Optional[RateLimiter] = None


def _get_nonce_cache() -> NonceCache:
    global _nonce_cache
    if _nonce_cache is None:
        _nonce_cache = NonceCache()
    return _nonce_cache


def _get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


def compute_signature(
    secret: str,
    timestamp: str,
    nonce: str,
    body: str = "",
) -> str:
    """Compute the expected HMAC-SHA256 signature for a request.

    The message is ``timestamp + nonce + body`` encoded as UTF-8.
    """
    message = f"{timestamp}{nonce}{body}".encode("utf-8")
    return hmac.new(
        secret.encode("utf-8"), message, hashlib.sha256
    ).hexdigest()


def verify_device_request(
    secret: str,
    signature: str,
    timestamp: str,
    nonce: str,
    body: str = "",
    max_age_seconds: int = 300,
) -> bool:
    """Verify an incoming device request.

    Performs the following checks (in order):

    1. **Rate limiting** — reject if the global bucket is empty.
    2. **Timestamp freshness** — reject if the request is older than
       *max_age_seconds*.
    3. **Replay protection** — reject if the nonce has been seen before.
    4. **HMAC verification** — reject if the signature does not match.

    Parameters
    ----------
    secret:
        The shared device API secret. **Never logged.**
    signature:
        The ``X-Signature`` header sent by the device.
    timestamp:
        The ``X-Timestamp`` header (ISO-8601 or unix epoch string).
    nonce:
        The ``X-Nonce`` header (unique per request).
    body:
        Raw request body string (empty for GET requests).
    max_age_seconds:
        Maximum allowed age of the timestamp.

    Returns
    -------
    bool
        ``True`` if the request passes all checks.

    Raises
    ------
    AuthenticationError
        Descriptive error if any check fails.
    """
    # 1. Rate limiting
    if not _get_rate_limiter().allow():
        logger.warning("Rate limit exceeded for device request")
        raise AuthenticationError("Rate limit exceeded. Try again later.")

    # 2. Timestamp freshness
    try:
        request_time = float(timestamp)
    except (ValueError, TypeError):
        raise AuthenticationError("Invalid timestamp format")

    age = abs(time.time() - request_time)
    if age > max_age_seconds:
        logger.warning("Stale device request rejected (age=%.1fs)", age)
        raise AuthenticationError("Request timestamp is too old or too far in the future")

    # 3. Replay protection
    if not _get_nonce_cache().check_and_store(nonce):
        logger.warning("Replay attempt detected (nonce reuse)")
        raise AuthenticationError("Duplicate nonce — possible replay attack")

    # 4. HMAC verification
    expected = compute_signature(secret, timestamp, nonce, body)
    if not hmac.compare_digest(expected, signature):
        logger.warning("Invalid HMAC signature for device request")
        raise AuthenticationError("Invalid request signature")

    logger.debug("Device request verified successfully")
    return True


def reset_security_state() -> None:
    """Reset module-level singletons.  Intended for testing only."""
    global _nonce_cache, _rate_limiter
    _nonce_cache = None
    _rate_limiter = None
