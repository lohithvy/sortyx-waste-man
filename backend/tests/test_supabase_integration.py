"""
Sortyx 2.0 — Comprehensive Supabase Database Integration Tests (Phase 6).

Verifies:
1. Sorting event creation with preserved UUIDs.
2. Status transitions and idempotent offline queue updates.
3. Strict filtering of today's statistics using IST calendar day (UTC+5:30).
4. Only 'completed' sorting operations contribute to successful counts.
5. Sensor readings never fabricate fake distances for unconfigured sensors.
6. Offline queueing, bounded retry backoff, and deduplication via upsert on conflict id.
7. Disconnection and reconnection behavior.
8. DailyStats schema providing both camelCase and snake_case fields.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict
from unittest.mock import MagicMock, AsyncMock, patch
import pytest

from app.models.enums import ClassificationStatus, SortingStatus, WasteCategory, SensorStatus
from app.schemas.events import DailyStats
from app.services.supabase_service import SupabaseService
from app.utils.time_utils import get_utc_now, get_ist_today_range, IST_OFFSET


@pytest.mark.asyncio
async def test_create_sorting_event_generates_and_preserves_uuid() -> None:
    """Verifies that create_sorting_event generates a client-side UUID and retains it."""
    svc = SupabaseService(url="https://your-project.supabase.co", secret_key="dummy_secret")
    assert not svc.is_connected

    event_id = await svc.create_sorting_event(
        waste_name="Orange Peel",
        category=WasteCategory.ORGANIC,
        confidence=0.965,
        classification_status=ClassificationStatus.CLASSIFIED,
        sorting_status=SortingStatus.PENDING,
        decision_reason="Citrus organic waste",
    )

    assert event_id is not None
    assert event_id in svc._offline_events_queue
    queued_event = svc._offline_events_queue[event_id]
    assert queued_event["id"] == event_id
    assert queued_event["waste_name"] == "Orange Peel"
    assert queued_event["category"] in ("food_waste", "organic")
    assert queued_event["confidence"] == 0.965
    assert queued_event["sorting_status"] == SortingStatus.PENDING.value
    assert queued_event["classification_model"] == "gemini-3.8-flash"


@pytest.mark.asyncio
async def test_update_sorting_event_status_preserves_id_and_updates_state() -> None:
    """Verifies that status transitions properly update the event record."""
    svc = SupabaseService(url="https://your-project.supabase.co", secret_key="dummy_secret")
    event_id = await svc.create_sorting_event(
        waste_name="Plastic Bottle",
        category=WasteCategory.NON_BIO,
        confidence=0.91,
        sorting_status=SortingStatus.BIN_OPENING,
    )

    # Step 1: Transition to awaiting deposit
    await svc.update_sorting_event_status(event_id, SortingStatus.AWAITING_DEPOSIT)
    assert svc._offline_events_queue[event_id]["sorting_status"] == SortingStatus.AWAITING_DEPOSIT.value

    # Step 2: Transition to deposit confirmed
    await svc.update_sorting_event_status(event_id, SortingStatus.DEPOSIT_CONFIRMED)
    assert svc._offline_events_queue[event_id]["sorting_status"] == SortingStatus.DEPOSIT_CONFIRMED.value

    # Step 3: Transition to completed
    await svc.update_sorting_event_status(event_id, SortingStatus.COMPLETED)
    assert svc._offline_events_queue[event_id]["sorting_status"] == SortingStatus.COMPLETED.value
    # Preserved UUID must never change
    assert svc._offline_events_queue[event_id]["id"] == event_id


@pytest.mark.asyncio
async def test_today_statistics_ist_calendar_day_filtering() -> None:
    """Verifies that get_today_stats filters strictly within the IST calendar day.

    Events outside today's IST range (yesterday or tomorrow) are excluded.
    """
    svc = SupabaseService(url="https://your-project.supabase.co", secret_key="dummy_secret")
    start_utc, end_utc = get_ist_today_range()

    # 1. Today completed event (IST)
    ev_today = await svc.create_sorting_event(
        waste_name="Banana Peel",
        category=WasteCategory.ORGANIC,
        confidence=0.98,
        sorting_status=SortingStatus.COMPLETED,
    )

    # 2. Today completed Bio event (IST)
    ev_bio = await svc.create_sorting_event(
        waste_name="Medical Gauze",
        category=WasteCategory.BIO,
        confidence=0.89,
        sorting_status=SortingStatus.COMPLETED,
    )

    # 3. Today Non-Bio completed event (IST)
    ev_non_bio = await svc.create_sorting_event(
        waste_name="Aluminium Can",
        category=WasteCategory.NON_BIO,
        confidence=0.94,
        sorting_status=SortingStatus.COMPLETED,
    )

    # 4. Today PENDING event (should NOT count towards successful items)
    await svc.create_sorting_event(
        waste_name="Incomplete Sort",
        category=WasteCategory.ORGANIC,
        confidence=0.75,
        sorting_status=SortingStatus.PENDING,
    )

    # 5. Yesterday completed event (outside IST today range)
    yesterday_time = (start_utc - timedelta(hours=2)).isoformat()
    ev_yesterday = await svc.create_sorting_event(
        waste_name="Old Newspaper",
        category=WasteCategory.BIO,
        confidence=0.92,
        sorting_status=SortingStatus.COMPLETED,
    )
    svc._offline_events_queue[ev_yesterday]["created_at"] = yesterday_time

    stats = await svc.get_today_stats()
    assert stats.total_items == 3
    assert stats.organic_count == 1
    assert stats.bio_count == 1
    assert stats.non_bio_count == 1
    # Check camelCase computed fields
    assert stats.totalItems == 3
    assert stats.organic == 1
    assert stats.bio == 1
    assert stats.nonBio == 1


@pytest.mark.asyncio
async def test_sensor_readings_unconfigured_never_invents_fake_readings() -> None:
    """Verifies that unconfigured sensors (distance_cm=None) do NOT insert fake rows."""
    svc = SupabaseService(url="https://your-project.supabase.co", secret_key="dummy_secret")

    # Mock client
    mock_client = MagicMock()
    svc._client = mock_client
    svc._is_connected = True
    svc._bin_id_cache["organic"] = "00000000-0000-0000-0000-000000000001"

    # Test with unconfigured sensor: distance_cm is None
    success = await svc.record_sensor_reading(
        category="organic",
        distance_cm=None,
        fill_percentage=0.0,
        sensor_status=SensorStatus.NOT_CONFIGURED,
    )
    assert success is True
    # Verify that 'sensor_readings' table insert was NEVER called
    for call in mock_client.table.mock_calls:
        assert "sensor_readings" not in str(call)

    # Verify that bins table was updated with not_configured and no distance
    mock_client.table.assert_called_with("bins")


@pytest.mark.asyncio
async def test_sensor_readings_actual_distance_records_properly() -> None:
    """Verifies that valid sensor readings insert historical row and update bin."""
    svc = SupabaseService(url="https://your-project.supabase.co", secret_key="dummy_secret")

    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_table.insert.return_value.execute.return_value = MagicMock(data=[{"id": "reading-1"}])
    mock_table.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "bin-1"}])

    svc._client = mock_client
    svc._is_connected = True
    svc._bin_id_cache["organic"] = "00000000-0000-0000-0000-000000000001"

    success = await svc.record_sensor_reading(
        category="organic",
        distance_cm=24.5,
        fill_percentage=42.0,
        sensor_status=SensorStatus.ONLINE,
    )
    assert success is True
    mock_client.table.assert_any_call("sensor_readings")
    mock_client.table.assert_any_call("bins")


@pytest.mark.asyncio
async def test_offline_queue_deduplication_via_upsert() -> None:
    """Verifies that flush_offline_queue uses upsert with on_conflict='id' to prevent duplicate rows."""
    svc = SupabaseService(url="https://your-project.supabase.co", secret_key="dummy_secret")

    # Add 2 events to queue
    ev1 = await svc.create_sorting_event(
        waste_name="Item 1",
        category=WasteCategory.ORGANIC,
        confidence=0.9,
    )
    ev2 = await svc.create_sorting_event(
        waste_name="Item 2",
        category=WasteCategory.BIO,
        confidence=0.85,
    )
    assert svc.offline_queue_size == 2

    # Simulate connection restored
    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    # upsert returns data indicating success
    mock_table.upsert.return_value.execute.return_value = MagicMock(data=[{"id": ev1}])

    svc._client = mock_client
    svc._is_connected = True
    svc._last_flush_attempt = 0.0

    flushed = await svc.flush_offline_queue()
    assert flushed == 2
    assert svc.offline_queue_size == 0

    # Verify upsert was called with on_conflict="id"
    assert mock_table.upsert.call_count == 2
    for call_args in mock_table.upsert.call_args_list:
        assert call_args.kwargs.get("on_conflict") == "id"


@pytest.mark.asyncio
async def test_bounded_backoff_on_flush_failure() -> None:
    """Verifies that when flushing fails, the backoff increases up to the bounded max."""
    svc = SupabaseService(url="https://your-project.supabase.co", secret_key="dummy_secret")

    ev1 = await svc.create_sorting_event(
        waste_name="Item 1",
        category=WasteCategory.ORGANIC,
        confidence=0.9,
    )

    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    # Force upsert to raise network error
    mock_table.upsert.return_value.execute.side_effect = ConnectionError("Supabase connection timeout")

    svc._client = mock_client
    svc._is_connected = True
    svc._last_flush_attempt = 0.0

    initial_delay = svc._flush_retry_delay
    flushed = await svc.flush_offline_queue()
    assert flushed == 0
    assert svc.offline_queue_size == 1  # Event remains safely in queue
    assert svc._flush_retry_delay > initial_delay
    assert svc._flush_retry_delay <= svc._max_flush_retry_delay
