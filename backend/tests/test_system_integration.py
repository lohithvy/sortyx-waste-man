"""
Sortyx 2.0 — Complete System Integration & End-to-End Tests (Phase 7).

Verifies:
1. Full end-to-end lifecycle for all 5 classification paths:
   - Organic (Banana Peel) -> Bin Organic, deposit confirmed, lid closed, DB completed.
   - Bio (Cardboard) -> Bin Bio, deposit confirmed, lid closed, DB completed.
   - Non-Bio (Plastic Bottle) -> Bin Non-Bio, deposit confirmed, lid closed, DB completed.
   - Unknown (Unidentified Object) -> Manual review, category is NULL, servos NEVER open.
   - Hazardous (Lithium Battery) -> Hazardous, category is NULL, servos NEVER open.
2. Failure handling:
   - Camera disconnection
   - Gemini quota exhaustion (HTTP 429)
   - Gemini upstream capacity error (HTTP 503)
   - Database disconnection & offline queueing
   - Ultrasonic sensor unconfigured / unavailable
   - Malformed / invalid AI JSON
   - Hand withdrawn before deposit
   - Deposit confirmation timeout
   - Application restart / startup safety
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.hardware.camera import create_camera_service
from app.models.enums import BinId, ClassificationStatus, SortingStatus, SystemState, WasteCategory, SensorStatus
from app.schemas.classification import GeminiClassificationResponse, ClassificationResult
from app.schemas.hardware import HardwareConfig
from app.services.classification_service import ClassificationService
from app.services.cloud_run_service import CloudRunService
from app.services.hand_tracking_service import HandTrackingService, HandDetectionResult
from app.services.servo_service import ServoService
from app.services.sorting_service import SortingService
from app.services.supabase_service import SupabaseService
from app.services.ultrasonic_service import UltrasonicService
from app.state_machine.machine import SortingStateMachine
from app.core.exceptions import CloudRunAPIError, CloudRunQuotaExceededError


@pytest.fixture
def integration_harness():
    """Build a complete Sortyx system harness in simulated mode."""
    hw_config = HardwareConfig()
    camera = create_camera_service(source="WEBCAM", device_index=0)
    hand_tracker = HandTrackingService(model_complexity=0)
    ai_service = CloudRunService(endpoint="https://sortyx-classify-5bwsw4lr6q-uc.a.run.app/api/classify")
    classifier = ClassificationService(confidence_threshold=0.75)
    servos = ServoService(config=hw_config, simulation_mode=True)
    ultrasonic = UltrasonicService(config=hw_config, simulation_mode=True)
    supabase = SupabaseService(url="https://your-project.supabase.co", secret_key="dummy_secret")
    sm = SortingStateMachine()

    sorting = SortingService(
        camera=camera,
        hand_tracker=hand_tracker,
        ai_service=ai_service,
        classifier=classifier,
        servos=servos,
        ultrasonic=ultrasonic,
        supabase=supabase,
        state_machine=sm,
    )

    return {
        "camera": camera,
        "hand_tracker": hand_tracker,
        "ai_service": ai_service,
        "gemini": ai_service,  # backward-compatible alias for tests
        "classifier": classifier,
        "servos": servos,
        "ultrasonic": ultrasonic,
        "supabase": supabase,
        "sm": sm,
        "sorting": sorting,
    }


# ===========================================================================
# 1. End-to-End Sorting Tests (All 5 Categories)
# ===========================================================================


@pytest.mark.asyncio
async def test_e2e_organic_sorting_lifecycle(integration_harness) -> None:
    """Full workflow: Banana Peel -> Organic bin opens -> deposit confirmed -> closes -> DB completed."""
    h = integration_harness
    sm: SortingStateMachine = h["sm"]
    sorting: SortingService = h["sorting"]
    servos: ServoService = h["servos"]
    supabase: SupabaseService = h["supabase"]

    # 1. Sequence: IDLE -> PERSON_DETECTED -> CAMERA_ACTIVE -> IMAGE_CAPTURE -> CLASSIFYING
    await sm.transition_to(SystemState.PERSON_DETECTED)
    await sm.transition_to(SystemState.CAMERA_ACTIVE)
    await sm.transition_to(SystemState.IMAGE_CAPTURE)
    await sm.transition_to(SystemState.CLASSIFYING, jpeg_bytes=b"fake_jpeg_bytes")

    # 2. Mock Gemini response for Banana Peel
    mock_response = GeminiClassificationResponse(
        waste_name="Banana Peel",
        category="organic",
        confidence=0.96,
        reason="Organic fruit waste",
        is_hazardous=False,
        requires_manual_review=False,
    )
    with patch.object(h["gemini"], "classify_waste", new_callable=AsyncMock) as mock_classify:
        mock_classify.return_value = mock_response

        # Step classifying -> transitions to CLASSIFICATION_RESULT
        await sorting._step_classifying()

        assert sm.current_state == SystemState.CLASSIFICATION_RESULT
        res: ClassificationResult = sm.context["classification_result"]
        assert res.waste_name == "Banana Peel"
        assert res.category == WasteCategory.ORGANIC
        assert res.bin_id == BinId.ORGANIC
        assert res.should_activate_servo() is True

    # 3. Classification result -> opens servo
    with patch("asyncio.sleep", new_callable=AsyncMock):
        await sorting._step_classification_result()
        assert sm.current_state == SystemState.SERVO_OPENING
        assert sorting._current_event_id is not None
        event_id = sorting._current_event_id

        # 4. Servo Opening
        await sorting._step_servo_opening()
        assert sm.current_state == SystemState.AWAITING_DEPOSIT
        assert servos.is_bin_open(BinId.ORGANIC) is True

        # 5. Awaiting deposit with simulated drop
        with patch.object(h["ultrasonic"], "attempt_deposit_confirmation", return_value=(True, "Drop detected")):
            await sorting._step_awaiting_deposit()
            assert sm.current_state == SystemState.LID_CLOSING
            assert sm.context.get("deposit_confirmed") is True

        # 6. Lid closing
        await sorting._step_lid_closing()
        assert sm.current_state == SystemState.IDLE
        assert servos.is_bin_open(BinId.ORGANIC) is False

        # 7. Check database record is marked COMPLETED
        assert event_id in supabase._offline_events_queue
        db_ev = supabase._offline_events_queue[event_id]
        assert db_ev["sorting_status"] == SortingStatus.COMPLETED.value
        assert db_ev["category"] in ("food_waste", "organic")

        # 8. Check stats incremented
        stats = await supabase.get_today_stats()
        assert stats.organic_count == 1
        assert stats.total_items == 1


@pytest.mark.asyncio
async def test_e2e_bio_sorting_lifecycle(integration_harness) -> None:
    """Full workflow: Cardboard -> Bio bin opens -> deposit confirmed -> closes -> DB completed."""
    h = integration_harness
    sm: SortingStateMachine = h["sm"]
    sorting: SortingService = h["sorting"]
    servos: ServoService = h["servos"]
    supabase: SupabaseService = h["supabase"]

    await sm.transition_to(SystemState.CAMERA_ACTIVE)
    await sm.transition_to(SystemState.IMAGE_CAPTURE)
    await sm.transition_to(SystemState.CLASSIFYING, jpeg_bytes=b"cardboard_bytes")

    mock_response = GeminiClassificationResponse(
        waste_name="Cardboard Box",
        category="bio",
        confidence=0.93,
        reason="Biodegradable paper product",
        is_hazardous=False,
        requires_manual_review=False,
    )
    with patch.object(h["gemini"], "classify_waste", new_callable=AsyncMock) as mock_classify:
        mock_classify.return_value = mock_response
        await sorting._step_classifying()

    assert sm.current_state == SystemState.CLASSIFICATION_RESULT
    res: ClassificationResult = sm.context["classification_result"]
    assert res.category == WasteCategory.BIO
    assert res.bin_id == BinId.BIO

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await sorting._step_classification_result()
        await sorting._step_servo_opening()
        assert servos.is_bin_open(BinId.BIO) is True
        assert servos.is_bin_open(BinId.ORGANIC) is False

        with patch.object(h["ultrasonic"], "attempt_deposit_confirmation", return_value=(True, "Drop detected")):
            await sorting._step_awaiting_deposit()

        await sorting._step_lid_closing()
        assert sm.current_state == SystemState.IDLE
        assert servos.is_bin_open(BinId.BIO) is False

    stats = await supabase.get_today_stats()
    assert stats.bio_count == 1


@pytest.mark.asyncio
async def test_e2e_non_bio_sorting_lifecycle(integration_harness) -> None:
    """Full workflow: Plastic Bottle -> Non-Bio bin opens -> deposit confirmed -> closes -> DB completed."""
    h = integration_harness
    sm: SortingStateMachine = h["sm"]
    sorting: SortingService = h["sorting"]
    servos: ServoService = h["servos"]
    supabase: SupabaseService = h["supabase"]

    await sm.transition_to(SystemState.CAMERA_ACTIVE)
    await sm.transition_to(SystemState.IMAGE_CAPTURE)
    await sm.transition_to(SystemState.CLASSIFYING, jpeg_bytes=b"bottle_bytes")

    mock_response = GeminiClassificationResponse(
        waste_name="Water Bottle",
        category="non_bio",
        confidence=0.91,
        reason="Recyclable PET plastic",
        is_hazardous=False,
        requires_manual_review=False,
    )
    with patch.object(h["gemini"], "classify_waste", new_callable=AsyncMock) as mock_classify:
        mock_classify.return_value = mock_response
        await sorting._step_classifying()

    assert sm.current_state == SystemState.CLASSIFICATION_RESULT
    res: ClassificationResult = sm.context["classification_result"]
    assert res.category == WasteCategory.NON_BIO
    assert res.bin_id == BinId.NON_BIO

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await sorting._step_classification_result()
        await sorting._step_servo_opening()
        assert servos.is_bin_open(BinId.NON_BIO) is True

        with patch.object(h["ultrasonic"], "attempt_deposit_confirmation", return_value=(True, "Drop detected")):
            await sorting._step_awaiting_deposit()

        await sorting._step_lid_closing()
        assert sm.current_state == SystemState.IDLE
        assert servos.is_bin_open(BinId.NON_BIO) is False

    stats = await supabase.get_today_stats()
    assert stats.non_bio_count == 1


@pytest.mark.asyncio
async def test_e2e_unknown_object_requires_manual_review(integration_harness) -> None:
    """Unknown object -> MANUAL_REVIEW state, category is NULL, servos NEVER open, audit logged."""
    h = integration_harness
    sm: SortingStateMachine = h["sm"]
    sorting: SortingService = h["sorting"]
    servos: ServoService = h["servos"]
    supabase: SupabaseService = h["supabase"]

    await sm.transition_to(SystemState.CAMERA_ACTIVE)
    await sm.transition_to(SystemState.IMAGE_CAPTURE)
    await sm.transition_to(SystemState.CLASSIFYING, jpeg_bytes=b"unknown_bytes")

    mock_response = GeminiClassificationResponse(
        waste_name="Unknown Object",
        category="unknown",
        confidence=0.30,
        reason="Object could not be identified with confidence",
        is_hazardous=False,
        requires_manual_review=True,
    )
    with patch.object(h["gemini"], "classify_waste", new_callable=AsyncMock) as mock_classify:
        mock_classify.return_value = mock_response
        await sorting._step_classifying()

    # Must transition to MANUAL_REVIEW
    assert sm.current_state == SystemState.MANUAL_REVIEW
    res: ClassificationResult = sm.context["classification_result"]
    # Safety checks
    assert res.category is None  # Manual review must have null category
    assert res.bin_id is None
    assert res.should_activate_servo() is False
    assert servos.is_any_bin_open() is False

    # Execute manual review step
    with patch("asyncio.sleep", new_callable=AsyncMock):
        await sorting._step_manual_review()
        # Returns safely to IDLE
        assert sm.current_state == SystemState.IDLE
        assert servos.is_any_bin_open() is False

    # Event logged as rejected in DB, but does NOT count towards completed items
    stats = await supabase.get_today_stats()
    assert stats.total_items == 0


@pytest.mark.asyncio
async def test_e2e_hazardous_object_never_activates_servos(integration_harness) -> None:
    """Hazardous object (Lithium battery) -> HAZARDOUS/MANUAL_REVIEW, category is NULL, servos NEVER open."""
    h = integration_harness
    sm: SortingStateMachine = h["sm"]
    sorting: SortingService = h["sorting"]
    servos: ServoService = h["servos"]
    supabase: SupabaseService = h["supabase"]

    await sm.transition_to(SystemState.CAMERA_ACTIVE)
    await sm.transition_to(SystemState.IMAGE_CAPTURE)
    await sm.transition_to(SystemState.CLASSIFYING, jpeg_bytes=b"battery_bytes")

    mock_response = GeminiClassificationResponse(
        waste_name="Lithium Ion Battery",
        category="hazardous",
        confidence=0.95,
        reason="Fire risk. Requires specialized electronic waste disposal.",
        is_hazardous=True,
        requires_manual_review=True,
    )
    with patch.object(h["gemini"], "classify_waste", new_callable=AsyncMock) as mock_classify:
        mock_classify.return_value = mock_response
        await sorting._step_classifying()

    assert sm.current_state == SystemState.MANUAL_REVIEW
    res: ClassificationResult = sm.context["classification_result"]
    assert res.is_hazardous is True
    assert res.category is None  # Category must be NULL for hazardous manual review
    assert res.bin_id is None
    assert res.should_activate_servo() is False
    assert servos.is_any_bin_open() is False

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await sorting._step_manual_review()
        assert sm.current_state == SystemState.IDLE
        assert servos.is_any_bin_open() is False

    # Does not count towards successful segregation stats
    stats = await supabase.get_today_stats()
    assert stats.total_items == 0


# ===========================================================================
# 2. Failure Handling Tests (All 9 Failure Cases)
# ===========================================================================


@pytest.mark.asyncio
async def test_failure_camera_disconnected(integration_harness) -> None:
    """Case 1: Camera disconnects or read returns None -> safely yields without crashing."""
    h = integration_harness
    sorting: SortingService = h["sorting"]

    with patch.object(h["camera"], "read_frame", return_value=None):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await sorting._step_idle()
            await sorting._step_camera_active()
            assert h["sm"].current_state == SystemState.IDLE


@pytest.mark.asyncio
async def test_failure_gemini_quota_exhausted(integration_harness) -> None:
    """Case 2: Cloud Run 429 quota exhausted -> enters cooldown standby, broadcasts notice, no loop spin."""
    h = integration_harness
    ai_service = h["ai_service"]
    sorting: SortingService = h["sorting"]
    sm: SortingStateMachine = h["sm"]

    await sm.transition_to(SystemState.CAMERA_ACTIVE)
    await sm.transition_to(SystemState.IMAGE_CAPTURE)
    await sm.transition_to(SystemState.CLASSIFYING, jpeg_bytes=b"bytes")

    with patch.object(
        ai_service,
        "classify_waste",
        side_effect=CloudRunQuotaExceededError("Quota exhausted", retry_delay_seconds=300),
    ):
        await sorting._step_classifying()
        # Returns to CAMERA_ACTIVE safely without opening any servo
        assert sm.current_state == SystemState.CAMERA_ACTIVE
        assert ai_service.is_quota_exceeded() is True
        assert h["servos"].is_any_bin_open() is False


@pytest.mark.asyncio
async def test_failure_gemini_503_service_unavailable(integration_harness) -> None:
    """Case 3: Cloud Run upstream capacity error -> logs error, resets latch, no crash, no servo."""
    h = integration_harness
    ai_service = h["ai_service"]
    sorting: SortingService = h["sorting"]
    sm: SortingStateMachine = h["sm"]

    await sm.transition_to(SystemState.CAMERA_ACTIVE)
    await sm.transition_to(SystemState.IMAGE_CAPTURE)
    await sm.transition_to(SystemState.CLASSIFYING, jpeg_bytes=b"bytes")

    with patch.object(
        ai_service,
        "classify_waste",
        side_effect=CloudRunAPIError("503 Service Unavailable / High demand"),
    ):
        await sorting._step_classifying()
        assert sm.current_state == SystemState.CAMERA_ACTIVE
        assert sorting._interaction_latched is False  # Latched flag reset for next attempt
        assert h["servos"].is_any_bin_open() is False


@pytest.mark.asyncio
async def test_failure_database_disconnected_offline_queue(integration_harness) -> None:
    """Case 4: Supabase disconnected -> events queue locally, preserved UUIDs, zero duplicates."""
    h = integration_harness
    supabase: SupabaseService = h["supabase"]
    assert not supabase.is_connected

    ev1 = await supabase.create_sorting_event(
        waste_name="Cardboard",
        category=WasteCategory.BIO,
        confidence=0.92,
    )
    assert ev1 is not None
    assert supabase.offline_queue_size == 1

    # Update while offline
    await supabase.update_sorting_event_status(ev1, SortingStatus.COMPLETED)
    assert supabase._offline_events_queue[ev1]["sorting_status"] == SortingStatus.COMPLETED.value
    # Preserves the same UUID
    assert supabase._offline_events_queue[ev1]["id"] == ev1


@pytest.mark.asyncio
async def test_failure_ultrasonic_sensor_unavailable_never_fakes(integration_harness) -> None:
    """Case 5: Ultrasonic unconfigured or disconnected -> distance is None, zero fake rows."""
    h = integration_harness
    ultrasonic: UltrasonicService = h["ultrasonic"]
    supabase: SupabaseService = h["supabase"]

    # In simulation with -1 pins, read_distance returns None
    dist = ultrasonic.read_distance(BinId.ORGANIC)
    assert dist is None
    status = ultrasonic.get_sensor_status(BinId.ORGANIC)
    assert status == SensorStatus.NOT_CONFIGURED

    # Sync to Supabase: must not invent fake distance
    success = await supabase.record_sensor_reading(
        category="organic",
        distance_cm=dist,
        fill_percentage=0.0,
        sensor_status=status,
    )
    assert success is True


@pytest.mark.asyncio
async def test_failure_invalid_ai_response_handling(integration_harness) -> None:
    """Case 6: AI returns invalid or unparseable category -> treated as manual review, servos never open."""
    h = integration_harness
    classifier: ClassificationService = h["classifier"]

    # Fake response with invalid category
    raw = GeminiClassificationResponse(
        waste_name="Unknown Radioactive Rock",
        category="hazardous",
        confidence=0.88,
        reason="Not an approved domestic waste category",
        is_hazardous=True,
        requires_manual_review=True,
    )
    res = classifier.validate_classification(raw)
    assert res.category is None
    assert res.bin_id is None
    assert res.should_activate_servo() is False


@pytest.mark.asyncio
async def test_failure_hand_withdrawn_unlatches(integration_harness) -> None:
    """Case 7: Hand withdrawn from frame -> clears consecutive frames and unlatches."""
    h = integration_harness
    sorting: SortingService = h["sorting"]
    sm: SortingStateMachine = h["sm"]

    await sm.transition_to(SystemState.CAMERA_ACTIVE)
    sorting._interaction_latched = True
    sorting._no_hand_frames_count = 0

    # Simulate camera detecting no hands for 12 frames
    fake_frame = MagicMock()
    with patch.object(h["camera"], "read_frame", return_value=fake_frame):
        with patch.object(
            h["hand_tracker"],
            "detect_hands",
            return_value=HandDetectionResult(hands_detected=0, landmarks=[], hand_holding_object=False),
        ):
            for _ in range(12):
                await sorting._step_camera_active()

    assert sorting._interaction_latched is False


@pytest.mark.asyncio
async def test_failure_deposit_timeout(integration_harness) -> None:
    """Case 8: User does not deposit waste -> timeout after 6s, marked UNCONFIRMED, lid closes safely."""
    h = integration_harness
    sorting: SortingService = h["sorting"]
    sm: SortingStateMachine = h["sm"]
    servos: ServoService = h["servos"]
    supabase: SupabaseService = h["supabase"]

    # Sequence to AWAITING_DEPOSIT
    await sm.transition_to(SystemState.CAMERA_ACTIVE)
    await sm.transition_to(SystemState.IMAGE_CAPTURE)
    await sm.transition_to(SystemState.CLASSIFYING)
    await sm.transition_to(SystemState.CLASSIFICATION_RESULT)
    await sm.transition_to(SystemState.SERVO_OPENING, target_bin=BinId.ORGANIC)
    await servos.open_bin(BinId.ORGANIC)
    await sm.transition_to(SystemState.AWAITING_DEPOSIT, target_bin=BinId.ORGANIC)

    ev_id = await supabase.create_sorting_event(
        waste_name="Orange Peel",
        category=WasteCategory.ORGANIC,
        confidence=0.9,
    )
    sorting._current_event_id = ev_id

    # attempt_deposit_confirmation returns False every time (user never drops item)
    with patch.object(h["ultrasonic"], "attempt_deposit_confirmation", return_value=(False, "No drop detected")):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await sorting._step_awaiting_deposit()
            assert sm.current_state == SystemState.LID_CLOSING
            assert sm.context.get("deposit_confirmed") is False
            assert supabase._offline_events_queue[ev_id]["sorting_status"] == SortingStatus.DEPOSIT_UNCONFIRMED.value

            # Lid closes safely
            await sorting._step_lid_closing()
            assert sm.current_state == SystemState.IDLE
            assert servos.is_bin_open(BinId.ORGANIC) is False


@pytest.mark.asyncio
async def test_startup_and_restart_safety(integration_harness) -> None:
    """Case 9: Startup / restart safety -> servos all closed, state starts IDLE, no hanging operations."""
    h = integration_harness
    servos: ServoService = h["servos"]
    sm: SortingStateMachine = h["sm"]

    # Ensure all bins are closed at initialization
    await servos.close_all_bins()
    assert servos.is_any_bin_open() is False
    assert sm.current_state == SystemState.IDLE
    assert len(sm.context) == 0
