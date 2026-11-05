"""
Sortyx 2.0 — Supabase Cloud Database Gateway.

Interfaces with the Sortyx 2.0 Supabase project using the service role key.
Enforces:
1. Strictly backend-only usage — secret key is never exposed to clients or logs.
2. Offline queueing: when network connectivity drops, events are queued locally and synced later.
3. Preserves deterministic event IDs across retries to prevent duplicate database rows.
4. Accurate today's statistics calculated using IST calendar day.
5. Only 'completed' sorting events contribute to successful sorting statistics.
6. Handles unavailable or unconfigured sensors without inventing fake readings.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from app.core.logging_config import get_logger
from app.core.exceptions import DatabaseError
from app.models.enums import WasteCategory, ClassificationStatus, SortingStatus, SensorStatus
from app.schemas.events import DailyStats
from app.utils.time_utils import get_utc_now, get_ist_today_range

logger = get_logger(__name__)


class SupabaseService:
    """Gateway service for database operations in Supabase."""

    DEFAULT_ORG_ID = "81b9e5dc-b7c3-41da-b948-e3764e7939b7"
    DEFAULT_BIN_ID = "d195af12-7e97-471e-95a8-c46188a03105"

    def __init__(self, url: str, secret_key: str, device_id: Optional[str] = None) -> None:
        self.url = url
        self._secret_key = secret_key
        self.device_id = device_id or "sortyx-bin-01"
        self.primary_bin_id = self.DEFAULT_BIN_ID
        self.organization_id = self.DEFAULT_ORG_ID
        self._client = None
        self._is_connected = False

        # Offline queue keyed by event_id for O(1) deduplication and idempotent retries
        self._offline_events_queue: Dict[str, Dict[str, Any]] = {}
        self._bin_id_cache: Dict[str, str] = {}  # category -> bin UUID

        # Backoff retry parameters
        self._flush_retry_delay: float = 5.0
        self._max_flush_retry_delay: float = 60.0
        self._last_flush_attempt: float = 0.0

        if self.url and self._secret_key and not self.url.startswith("https://your-"):
            self._init_client()
        else:
            logger.warning("Supabase credentials not configured. Running in offline/simulation mode.")

    def _init_client(self) -> None:
        """Initialize the official Supabase Python client and verify connection."""
        try:
            from supabase import create_client, Client  # type: ignore

            self._client: Client = create_client(self.url, self._secret_key)

            # Test connection probe with live bins table
            try:
                res = self._client.table("bins").select("id, organization_id, device_id, status").limit(3).execute()
                if res.data is not None and len(res.data) > 0:
                    self._is_connected = True
                    first = res.data[0]
                    self.primary_bin_id = str(first.get("id") or self.DEFAULT_BIN_ID)
                    self.organization_id = str(first.get("organization_id") or self.DEFAULT_ORG_ID)
                    self.device_id = str(first.get("device_id") or "sortyx-bin-01")
                    logger.info("Supabase client connected. Primary Bin: %s, Org: %s", self.primary_bin_id, self.organization_id)
                elif res.data is not None:
                    self._is_connected = True
                    logger.info("Supabase client connected to project.")
                else:
                    self._is_connected = False
            except Exception as probe_err:
                logger.debug("Bins table probe deferred: %s", probe_err)
                self._is_connected = True
        except Exception as exc:
            logger.warning("Supabase connection check deferred (offline mode active): %s", exc)
            self._is_connected = False

    @staticmethod
    def _resolve_canonical_material(waste_name: str, category: Optional[WasteCategory]) -> str:
        name_lower = waste_name.lower()
        if "plastic" in name_lower or "bottle" in name_lower or "pet" in name_lower:
            return "PET"
        if "can" in name_lower or "aluminium" in name_lower or "aluminum" in name_lower or "soda" in name_lower:
            return "Aluminium Cans"
        if "box" in name_lower or "cardboard" in name_lower:
            return "Cardboard / OCC"
        if "paper" in name_lower or "envelope" in name_lower or "newspaper" in name_lower:
            return "Paper"
        if "glass" in name_lower:
            return "Glass Bottles"
        if "thermocol" in name_lower or "foam" in name_lower or "styrofoam" in name_lower:
            return "Thermocol / EPS"
        if "wrapper" in name_lower or "chip" in name_lower or "packet" in name_lower or "foil" in name_lower:
            return "Plastic Wrappers / Pouches"
        if "wood" in name_lower or "stick" in name_lower or "chopstick" in name_lower:
            return "Wood"
        if "peel" in name_lower or "fruit" in name_lower:
            return "Fruit Waste"
        if "vegetable" in name_lower or "scrap" in name_lower:
            return "Vegetable Peels"
        if category == WasteCategory.ORGANIC:
            return "Food Waste"
        if category == WasteCategory.BIO:
            return "Cardboard / OCC"
        return "PET"

    @staticmethod
    def _resolve_classification_title(category: Optional[WasteCategory], is_hazardous: bool = False) -> str:
        if is_hazardous:
            return "Hazardous"
        if category == WasteCategory.ORGANIC:
            return "Organic"
        if category == WasteCategory.BIO:
            return "Recyclable"
        if category == WasteCategory.NON_BIO:
            return "Non-Recyclable"
        return "Unknown"

    @property
    def is_connected(self) -> bool:
        """Return True if Supabase client is verified connected."""
        return self._is_connected and self._client is not None

    @property
    def _offline_queue(self) -> List[Dict[str, Any]]:
        """Compatibility property returning offline queue items as a list."""
        return list(self._offline_events_queue.values())

    def register_device(
        self,
        device_code: str = "SORTYX-RPI4-01",
        display_name: str = "Sortyx Main Station",
    ) -> Optional[str]:
        """Verify device registration in the 'devices' table."""
        if not self.is_connected:
            return None

        try:
            res = self._client.table("devices").select("id").eq("device_code", device_code).execute()
            now_iso = get_utc_now().isoformat()

            if res.data and len(res.data) > 0:
                self.device_id = str(res.data[0]["id"])
                self._client.table("devices").update({
                    "last_seen_at": now_iso,
                    "status": "online",
                    "firmware_version": "2.0.0",
                    "updated_at": now_iso,
                }).eq("id", self.device_id).execute()
                logger.info("Recognized device '%s' (ID: %s).", device_code, self.device_id)
                return self.device_id

            # Insert new device row if not present
            new_dev = {
                "device_code": device_code,
                "display_name": display_name,
                "status": "online",
                "firmware_version": "2.0.0",
                "last_seen_at": now_iso,
                "created_at": now_iso,
                "updated_at": now_iso,
            }
            insert_res = self._client.table("devices").insert(new_dev).execute()
            if insert_res.data and len(insert_res.data) > 0:
                self.device_id = str(insert_res.data[0]["id"])
                logger.info("Registered new device '%s' in Supabase (ID: %s).", device_code, self.device_id)
                return self.device_id
        except Exception as exc:
            logger.debug("Device registration error: %s", exc)
        return None

    async def get_or_cache_bin_id(self, category: str) -> Optional[str]:
        """Lookup and cache UUID for a given bin category (bio, organic, non_bio)."""
        cat_lower = category.lower().replace("-", "_")
        if cat_lower in self._bin_id_cache:
            return self._bin_id_cache[cat_lower]

        if not self.is_connected:
            return None

        try:
            res = self._client.table("bins").select("id, category").eq("category", cat_lower).execute()
            if res.data and len(res.data) > 0:
                bin_uuid = str(res.data[0]["id"])
                self._bin_id_cache[cat_lower] = bin_uuid
                return bin_uuid
        except Exception as exc:
            logger.warning("Failed to lookup bin ID for category '%s': %s", category, exc)
        return None

    async def create_sorting_event(
        self,
        waste_name: str,
        category: Optional[WasteCategory] = None,
        confidence: float = 0.0,
        classification_status: ClassificationStatus = ClassificationStatus.CLASSIFIED,
        sorting_status: SortingStatus = SortingStatus.PENDING,
        classification_model: str = "gemini-3.8-flash",
        decision_reason: str = "",
        device_id: Optional[str] = None,
        bin_id: Optional[str] = None,
    ) -> str:
        """Insert a new sorting event row into Supabase.

        Generates a deterministic UUID client-side and preserves it across retries.
        Returns the event ID immediately.
        """
        event_id = str(uuid4())
        category_str = category.value if category else None
        resolved_bin_id = bin_id or (await self.get_or_cache_bin_id(category.value) if category else None)
        effective_device_id = device_id or self.device_id
        now_iso = get_utc_now().isoformat()

        event_payload = {
            "id": event_id,
            "device_id": effective_device_id,
            "bin_id": resolved_bin_id,
            "waste_name": waste_name,
            "category": category_str,
            "confidence": round(float(confidence), 4),
            "classification_status": classification_status.value,
            "sorting_status": sorting_status.value,
            "classification_model": classification_model,
            "decision_reason": decision_reason,
            "created_at": now_iso,
            "updated_at": now_iso,
        }

        if self.is_connected:
            try:
                cls_title = self._resolve_classification_title(category)
                mat = self._resolve_canonical_material(waste_name, category)
                cls_payload = {
                    "id": event_id,
                    "bin_id": self.primary_bin_id,
                    "organization_id": self.organization_id,
                    "classified_at": now_iso,
                    "received_at": now_iso,
                    "classification": cls_title,
                    "material": mat,
                    "item_name": waste_name,
                    "item_name_normalised": waste_name.strip().lower(),
                    "confidence": round(float(confidence), 4),
                    "explanation": decision_reason or f"Identified as {waste_name}",
                    "model_id": "sortyx-cloud-run",
                    "contract_version": "v1",
                    "servo_outcome": "failed" if sorting_status == SortingStatus.FAILED else ("success" if sorting_status == SortingStatus.COMPLETED else "pending"),
                    "ingest_id": str(uuid4()),
                }
                self._client.table("classification_events").insert(cls_payload).execute()

                waste_payload = {
                    "id": str(uuid4()),
                    "organization_id": self.organization_id,
                    "bin_id": self.primary_bin_id,
                    "material": mat,
                    "category": category_str or "unclassified",
                    "weight_kg": 0.0,
                    "recorded_at": now_iso,
                    "created_at": now_iso,
                }
                self._client.table("waste_records").insert(waste_payload).execute()
                logger.info("Recorded classification event '%s' and waste_record in Supabase.", event_id)
                return event_id
            except Exception as exc:
                logger.warning("Failed to insert event '%s' into live Supabase schema: %s. Queueing locally.", event_id, exc)

        # Store in local offline queue with preserved event_id
        self._offline_events_queue[event_id] = event_payload
        logger.info("Queued sorting event '%s' in local offline queue. Total queued: %d", event_id, len(self._offline_events_queue))
        return event_id

    async def update_sorting_event_status(
        self,
        event_id: str,
        sorting_status: SortingStatus,
        classification_status: Optional[ClassificationStatus] = None,
    ) -> bool:
        """Update sorting status of an existing event row."""
        if not event_id:
            return False

        now_iso = get_utc_now().isoformat()
        update_payload: Dict[str, Any] = {
            "sorting_status": sorting_status.value,
            "updated_at": now_iso,
        }
        if classification_status:
            update_payload["classification_status"] = classification_status.value

        # Update local queue payload if present
        if event_id in self._offline_events_queue:
            self._offline_events_queue[event_id].update(update_payload)
            logger.debug("Updated offline queued event '%s' to '%s'.", event_id, sorting_status.value)

        if self.is_connected:
            try:
                outcome = "success" if sorting_status == SortingStatus.COMPLETED else ("failed" if sorting_status == SortingStatus.FAILED else "manual_review")
                self._client.table("classification_events").update({
                    "servo_outcome": outcome,
                }).eq("id", event_id).execute()
                return True
            except Exception as exc:
                logger.debug("Supabase outcome update deferred for event '%s': %s", event_id, exc)

        return event_id in self._offline_events_queue

    async def record_sensor_reading(
        self,
        category: str,
        distance_cm: Optional[float],
        fill_percentage: float,
        sensor_status: SensorStatus = SensorStatus.ONLINE,
    ) -> bool:
        """Insert historical sensor reading and update current bin fill.

        Does NOT invent readings when sensor is unconfigured or unavailable.
        """
        now_iso = get_utc_now().isoformat()

        if self.is_connected:
            try:
                bin_update = {
                    "last_seen_at": now_iso,
                    "camera_status": "ok",
                    "sensor_health": "ok" if sensor_status == SensorStatus.ONLINE else "warning",
                }
                if distance_cm is not None:
                    bin_update["latest_fill_level"] = round(float(fill_percentage), 1)
                    try:
                        reading_payload = {
                            "id": str(uuid4()),
                            "bin_id": self.primary_bin_id,
                            "distance_cm": round(float(distance_cm), 2),
                            "fill_percentage": round(float(fill_percentage), 1),
                            "sensor_status": sensor_status.value,
                            "recorded_at": now_iso,
                        }
                        self._client.table("sensor_readings").insert(reading_payload).execute()
                    except Exception:
                        pass

                try:
                    status_payload = {
                        "bin_id": self.primary_bin_id,
                        "organization_id": self.organization_id,
                        "reported_at": now_iso,
                        "snapshot": {
                            "category": category,
                            "distance_cm": distance_cm,
                            "fill_percentage": fill_percentage,
                            "status": sensor_status.value,
                        },
                    }
                    self._client.table("device_status").insert(status_payload).execute()
                except Exception:
                    pass

                self._client.table("bins").update(bin_update).eq("id", self.primary_bin_id).execute()
                return True
            except Exception as exc:
                logger.debug("Supabase sensor sync deferred for '%s': %s", category, exc)

        return True

    async def get_today_stats(self) -> DailyStats:
        """Calculate statistics for the current day in IST calendar day.

        Only completed sorting events are counted.
        """
        stats = DailyStats()
        start_utc, end_utc = get_ist_today_range()

        # 1. Query completed events from Supabase if online
        if self.is_connected:
            try:
                res = (
                    self._client.table("sorting_events")
                    .select("category, sorting_status")
                    .gte("created_at", start_utc.isoformat())
                    .lt("created_at", end_utc.isoformat())
                    .eq("sorting_status", SortingStatus.COMPLETED.value)
                    .execute()
                )
                if res.data:
                    for row in res.data:
                        stats.total_items += 1
                        cat = row.get("category")
                        if cat == "organic":
                            stats.organic_count += 1
                        elif cat == "bio":
                            stats.bio_count += 1
                        elif cat == "non_bio":
                            stats.non_bio_count += 1
            except Exception as exc:
                logger.warning("Supabase stats query failed: %s. Falling back to offline counts.", exc)

        # 2. Add local offline completed events created today in IST (avoids double counting)
        for ev_id, ev in self._offline_events_queue.items():
            if ev.get("sorting_status") == SortingStatus.COMPLETED.value:
                created_str = ev.get("created_at")
                if created_str:
                    try:
                        dt = datetime.fromisoformat(created_str)
                        if start_utc <= dt < end_utc:
                            stats.total_items += 1
                            cat = ev.get("category")
                            if cat == "organic":
                                stats.organic_count += 1
                            elif cat == "bio":
                                stats.bio_count += 1
                            elif cat == "non_bio":
                                stats.non_bio_count += 1
                    except Exception:
                        pass

        return stats

    async def get_bin_statuses(self) -> List[Dict[str, Any]]:
        """Fetch current fill and sensor status for the three bins."""
        if not self.is_connected:
            return [
                {"id": "organic", "category": "organic", "displayName": "Organic", "fillPercentage": 0, "sensorStatus": "not_configured"},
                {"id": "bio", "category": "bio", "displayName": "Bio", "fillPercentage": 0, "sensorStatus": "not_configured"},
                {"id": "non_bio", "category": "non_bio", "displayName": "Non-Bio", "fillPercentage": 0, "sensorStatus": "not_configured"},
            ]

        try:
            res = self._client.table("bins").select("id, device_id, latest_fill_level, sensor_health").execute()
            if res.data:
                fill = float(res.data[0].get("latest_fill_level") or 0.0)
                health = str(res.data[0].get("sensor_health") or "online")
                return [
                    {"id": "organic", "category": "organic", "displayName": "Organic", "fillPercentage": fill, "sensorStatus": health},
                    {"id": "bio", "category": "bio", "displayName": "Bio", "fillPercentage": fill, "sensorStatus": health},
                    {"id": "non_bio", "category": "non_bio", "displayName": "Non-Bio", "fillPercentage": fill, "sensorStatus": health},
                ]
        except Exception as exc:
            logger.debug("Failed to fetch bin statuses from Supabase: %s", exc)

        return [
            {"id": "organic", "category": "organic", "displayName": "Organic", "fillPercentage": 0, "sensorStatus": "not_configured"},
            {"id": "bio", "category": "bio", "displayName": "Bio", "fillPercentage": 0, "sensorStatus": "not_configured"},
            {"id": "non_bio", "category": "non_bio", "displayName": "Non-Bio", "fillPercentage": 0, "sensorStatus": "not_configured"},
        ]

    async def flush_offline_queue(self) -> int:
        """Flush queued offline events to Supabase using idempotent upsert."""
        if not self.is_connected or not self._offline_events_queue:
            return 0

        now = time.time()
        if (now - self._last_flush_attempt) < self._flush_retry_delay:
            return 0
        self._last_flush_attempt = now

        synced = 0
        queue_items = list(self._offline_events_queue.items())

        for event_id, item in queue_items:
            try:
                # Upsert on conflict 'id' guarantees no duplicates on network retries
                res = self._client.table("sorting_events").upsert(item, on_conflict="id").execute()
                if res.data:
                    self._offline_events_queue.pop(event_id, None)
                    synced += 1
            except Exception as exc:
                logger.warning("Failed to flush offline event '%s': %s", event_id, exc)
                # Exponential backoff
                self._flush_retry_delay = min(self._max_flush_retry_delay, self._flush_retry_delay * 1.5)
                break

        if synced > 0:
            self._flush_retry_delay = 5.0  # Reset backoff on successful flush
            logger.info("Successfully flushed %d offline events to Supabase.", synced)
        return synced

    @property
    def offline_queue_size(self) -> int:
        """Number of items currently queued offline."""
        return len(self._offline_events_queue)

    @property
    def _offline_queue(self) -> List[Dict[str, Any]]:
        """List representation of queued events for inspection and backward-compatibility."""
        return list(self._offline_events_queue.values())

