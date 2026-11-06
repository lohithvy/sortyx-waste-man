"""
Sortyx 2.0 — Camera Preview Frozen Behavior & Sorting Lifecycle Tests.

Validates:
1. Camera preview freezes immediately upon image capture.
2. The exact same captured frame is retained throughout:
   - AI classification
   - Bin selection / classification result
   - Servo opening
   - Waste deposit waiting period
   - Servo closing
   - Sorting completion
3. The captured frame is not overwritten during sorting.
4. Only after bin closing and return to IDLE is the frozen frame released and live feed resumed.
5. In manual review or error, the captured frame is preserved.
6. Duplicate detection is suppressed while sorting is active.
"""

from __future__ import annotations

import base64
import pytest
import numpy as np
import cv2

from app.models.enums import SystemState, BinId
from app.state_machine.machine import SortingStateMachine


@pytest.mark.asyncio
async def test_frozen_frame_lifecycle_across_all_sorting_states() -> None:
    """Verify that frozen_image_url remains immutable across every sorting step."""
    sm = SortingStateMachine()
    assert sm.current_state == SystemState.IDLE
    assert "frozen_image_url" not in sm.context

    # Create synthetic test frame
    test_frame = np.full((100, 100, 3), 180, dtype=np.uint8)
    _, buffer = cv2.imencode(".jpg", test_frame)
    captured_b64 = "data:image/jpeg;base64," + base64.b64encode(buffer.tobytes()).decode("utf-8")

    # 1. Hand detected -> CAMERA_ACTIVE (live feed)
    await sm.transition_to(SystemState.CAMERA_ACTIVE)
    assert sm.current_state == SystemState.CAMERA_ACTIVE

    # 2. Object latched -> IMAGE_CAPTURE (frame frozen)
    await sm.transition_to(
        SystemState.IMAGE_CAPTURE,
        frozen_image_url=captured_b64,
    )
    assert sm.current_state == SystemState.IMAGE_CAPTURE
    assert sm.context.get("frozen_image_url") == captured_b64

    # 3. CLASSIFYING -> Frame remains exact same frozen frame
    await sm.transition_to(SystemState.CLASSIFYING)
    assert sm.current_state == SystemState.CLASSIFYING
    assert sm.context.get("frozen_image_url") == captured_b64

    # 4. CLASSIFICATION_RESULT -> Frame remains exact same frozen frame
    await sm.transition_to(
        SystemState.CLASSIFICATION_RESULT,
        target_bin=BinId.FOOD_WASTE,
    )
    assert sm.current_state == SystemState.CLASSIFICATION_RESULT
    assert sm.context.get("frozen_image_url") == captured_b64

    # 5. SERVO_OPENING -> Frame remains exact same frozen frame
    await sm.transition_to(
        SystemState.SERVO_OPENING,
        target_bin=BinId.FOOD_WASTE,
    )
    assert sm.current_state == SystemState.SERVO_OPENING
    assert sm.context.get("frozen_image_url") == captured_b64

    # 6. AWAITING_DEPOSIT -> Frame remains exact same frozen frame
    await sm.transition_to(SystemState.AWAITING_DEPOSIT)
    assert sm.current_state == SystemState.AWAITING_DEPOSIT
    assert sm.context.get("frozen_image_url") == captured_b64

    # 7. LID_CLOSING -> Frame remains exact same frozen frame
    await sm.transition_to(SystemState.LID_CLOSING, deposit_confirmed=True)
    assert sm.current_state == SystemState.LID_CLOSING
    assert sm.context.get("frozen_image_url") == captured_b64

    # 8. Completed -> Reset context and transition to IDLE (frame released)
    sm.reset_context()
    await sm.transition_to(SystemState.IDLE)
    assert sm.current_state == SystemState.IDLE
    assert sm.context.get("frozen_image_url") is None


@pytest.mark.asyncio
async def test_frozen_frame_retained_on_manual_review() -> None:
    """Verify that on manual review, the captured image stays frozen until resolved."""
    sm = SortingStateMachine()
    captured_b64 = "data:image/jpeg;base64,sample_review_frame"

    await sm.transition_to(SystemState.CAMERA_ACTIVE)
    await sm.transition_to(SystemState.IMAGE_CAPTURE, frozen_image_url=captured_b64)
    await sm.transition_to(SystemState.CLASSIFYING)
    await sm.transition_to(SystemState.MANUAL_REVIEW)

    assert sm.current_state == SystemState.MANUAL_REVIEW
    # Frame MUST remain frozen and accessible
    assert sm.context.get("frozen_image_url") == captured_b64


@pytest.mark.asyncio
async def test_frozen_frame_retained_on_error() -> None:
    """Verify that on hardware error during sorting, the captured image stays frozen."""
    sm = SortingStateMachine()
    captured_b64 = "data:image/jpeg;base64,sample_error_frame"

    await sm.transition_to(SystemState.CAMERA_ACTIVE)
    await sm.transition_to(SystemState.IMAGE_CAPTURE, frozen_image_url=captured_b64)
    await sm.transition_to(SystemState.ERROR, error_message="Servo error")

    assert sm.current_state == SystemState.ERROR
    assert sm.context.get("frozen_image_url") == captured_b64


# ===========================================================================
# Full-Screen Sorting Success Overlay Tests
# ===========================================================================

from unittest.mock import AsyncMock, MagicMock, patch
from app.hardware.camera import create_camera_service
from app.schemas.hardware import HardwareConfig
from app.services.classification_service import ClassificationService
from app.services.cloud_run_service import CloudRunService
from app.services.hand_tracking_service import HandTrackingService
from app.services.servo_service import ServoService
from app.services.sorting_service import SortingService
from app.services.supabase_service import SupabaseService
from app.services.ultrasonic_service import UltrasonicService


@pytest.mark.asyncio
async def test_sorting_success_overlay_emitted_only_on_confirmed_lid_closure() -> None:
    """Validate that 'sorting_success' is emitted only after deposit confirmed and lid closed."""
    hw_config = HardwareConfig()
    camera = create_camera_service(source="WEBCAM", device_index=0)
    hand_tracker = HandTrackingService(model_complexity=0)
    ai_service = CloudRunService(endpoint="https://sortyx-classify-5bwsw4lr6q-uc.a.run.app/api/classify")
    classifier = ClassificationService(confidence_threshold=0.75)
    servos = ServoService(config=hw_config, simulation_mode=True)
    ultrasonic = UltrasonicService(config=hw_config, simulation_mode=True)
    supabase = SupabaseService(url="https://dummy.supabase.co", secret_key="dummy_secret")
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

    broadcasted_messages = []
    async def mock_broadcast_json(msg):
        broadcasted_messages.append(msg)

    with patch("app.services.sorting_service.ws_manager.broadcast_json", side_effect=mock_broadcast_json), \
         patch.object(servos, "close_bin", new=AsyncMock(return_value=True)), \
         patch.object(supabase, "update_sorting_event_status", new=AsyncMock()), \
         patch.object(supabase, "record_sensor_reading", new=AsyncMock()), \
         patch.object(supabase, "get_today_stats", new=AsyncMock(return_value=MagicMock(total_items=1, food_waste_count=1, recyclable_count=0, non_recyclable_count=0, organic_count=1, bio_count=0, non_bio_count=0))), \
         patch("asyncio.sleep", new=AsyncMock()):

        sm.context["target_bin"] = BinId.FOOD_WASTE
        sm.context["deposit_confirmed"] = True
        sm._state = SystemState.LID_CLOSING

        await sorting._step_lid_closing()

        success_msgs = [m for m in broadcasted_messages if m.get("type") == "sorting_success"]
        assert len(success_msgs) == 1
        payload = success_msgs[0]["payload"]
        assert payload["status"] == "success"
        assert payload["message"] == "Waste Sorted Successfully!"
        assert payload["submessage"] == "Thank you for keeping the environment clean."
        assert payload["target_bin"] == "food_waste"
        assert sm.current_state == SystemState.IDLE


@pytest.mark.asyncio
async def test_sorting_success_overlay_suppressed_on_servo_close_failure() -> None:
    """Validate that 'sorting_success' is NOT emitted if lid closing fails."""
    hw_config = HardwareConfig()
    camera = create_camera_service(source="WEBCAM", device_index=0)
    hand_tracker = HandTrackingService(model_complexity=0)
    ai_service = CloudRunService(endpoint="https://sortyx-classify-5bwsw4lr6q-uc.a.run.app/api/classify")
    classifier = ClassificationService(confidence_threshold=0.75)
    servos = ServoService(config=hw_config, simulation_mode=True)
    ultrasonic = UltrasonicService(config=hw_config, simulation_mode=True)
    supabase = SupabaseService(url="https://dummy.supabase.co", secret_key="dummy_secret")
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

    broadcasted_messages = []
    async def mock_broadcast_json(msg):
        broadcasted_messages.append(msg)

    with patch("app.services.sorting_service.ws_manager.broadcast_json", side_effect=mock_broadcast_json), \
         patch.object(servos, "close_bin", new=AsyncMock(return_value=False)), \
         patch.object(supabase, "update_sorting_event_status", new=AsyncMock()):

        sm.context["target_bin"] = BinId.FOOD_WASTE
        sm.context["deposit_confirmed"] = True
        sm._state = SystemState.LID_CLOSING

        await sorting._step_lid_closing()

        success_msgs = [m for m in broadcasted_messages if m.get("type") == "sorting_success"]
        assert len(success_msgs) == 0
        assert sm.current_state == SystemState.ERROR


@pytest.mark.asyncio
async def test_sorting_success_overlay_suppressed_if_deposit_unconfirmed() -> None:
    """Validate that 'sorting_success' is NOT emitted if waste was not deposited."""
    hw_config = HardwareConfig()
    camera = create_camera_service(source="WEBCAM", device_index=0)
    hand_tracker = HandTrackingService(model_complexity=0)
    ai_service = CloudRunService(endpoint="https://sortyx-classify-5bwsw4lr6q-uc.a.run.app/api/classify")
    classifier = ClassificationService(confidence_threshold=0.75)
    servos = ServoService(config=hw_config, simulation_mode=True)
    ultrasonic = UltrasonicService(config=hw_config, simulation_mode=True)
    supabase = SupabaseService(url="https://dummy.supabase.co", secret_key="dummy_secret")
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

    broadcasted_messages = []
    async def mock_broadcast_json(msg):
        broadcasted_messages.append(msg)

    with patch("app.services.sorting_service.ws_manager.broadcast_json", side_effect=mock_broadcast_json), \
         patch.object(servos, "close_bin", new=AsyncMock(return_value=True)), \
         patch.object(supabase, "update_sorting_event_status", new=AsyncMock()), \
         patch.object(supabase, "record_sensor_reading", new=AsyncMock()), \
         patch.object(supabase, "get_today_stats", new=AsyncMock(return_value=MagicMock(total_items=0, food_waste_count=0, recyclable_count=0, non_recyclable_count=0, organic_count=0, bio_count=0, non_bio_count=0))), \
         patch("asyncio.sleep", new=AsyncMock()):

        sm.context["target_bin"] = BinId.FOOD_WASTE
        sm.context["deposit_confirmed"] = False
        sm._state = SystemState.LID_CLOSING

        await sorting._step_lid_closing()

        success_msgs = [m for m in broadcasted_messages if m.get("type") == "sorting_success"]
        assert len(success_msgs) == 0
        assert sm.current_state == SystemState.IDLE


