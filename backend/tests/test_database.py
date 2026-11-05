"""
Sortyx 2.0 — Database Service Unit Tests.
"""

from __future__ import annotations

import pytest

from app.models.enums import ClassificationStatus, SortingStatus, WasteCategory
from app.services.supabase_service import SupabaseService


@pytest.mark.asyncio
async def test_offline_event_creation_and_queueing() -> None:
    # Service with placeholder URL operates in offline queue mode
    svc = SupabaseService(url="https://your-project.supabase.co", secret_key="dummy_key")
    assert not svc.is_connected

    event_id = await svc.create_sorting_event(
        waste_name="Banana Peel",
        category=WasteCategory.ORGANIC,
        confidence=0.95,
        classification_status=ClassificationStatus.CLASSIFIED,
        sorting_status=SortingStatus.PENDING,
    )
    assert event_id is not None
    assert len(svc._offline_queue) == 1
    assert svc._offline_queue[0]["waste_name"] == "Banana Peel"


@pytest.mark.asyncio
async def test_offline_event_status_update() -> None:
    svc = SupabaseService(url="https://your-project.supabase.co", secret_key="dummy_key")
    event_id = await svc.create_sorting_event(
        waste_name="Apple Core",
        category=WasteCategory.ORGANIC,
        confidence=0.92,
        sorting_status=SortingStatus.PENDING,
    )

    success = await svc.update_sorting_event_status(
        event_id=event_id,
        sorting_status=SortingStatus.COMPLETED,
    )
    assert success is True
    assert svc._offline_queue[0]["sorting_status"] == SortingStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_daily_statistics_offline_counts_completed_only() -> None:
    svc = SupabaseService(url="https://your-project.supabase.co", secret_key="dummy_key")

    # Add 1 completed organic
    ev1 = await svc.create_sorting_event(
        waste_name="Banana",
        category=WasteCategory.ORGANIC,
        confidence=0.9,
        sorting_status=SortingStatus.COMPLETED,
    )
    # Add 1 pending bio (should NOT count)
    ev2 = await svc.create_sorting_event(
        waste_name="Paper",
        category=WasteCategory.BIO,
        confidence=0.88,
        sorting_status=SortingStatus.PENDING,
    )

    stats = await svc.get_today_stats()
    assert stats.total_items == 1
    assert stats.organic_count == 1
    assert stats.bio_count == 0
    assert stats.non_bio_count == 0

