"""
Sortyx 2.0 — Sorting Orchestrator Service.

Coordinates camera capture, MediaPipe hand tracking, Gemini AI classification,
backend validation, PCA9685 servo actuation, and Supabase event synchronization.
Guarantees:
- Images are strictly temporary memory buffers, NEVER written to disk or logs.
- Servos never activate without backend validation and safety checks.
- Unsent events are queued in memory during network disconnections.
"""

from __future__ import annotations

import asyncio
import base64
import io
import time
from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np

from app.core.logging_config import get_logger
from app.core.exceptions import (
    SortyxError,
    AIProviderError,
    AIQuotaExceededError,
    CloudRunAPIError,
    CloudRunQuotaExceededError,
)
from app.models.enums import (
    BinId,
    ClassificationStatus,
    SortingStatus,
    SystemState,
    WasteCategory,
)
from app.schemas.classification import ClassificationResult, GeminiClassificationResponse
from app.schemas.websocket import QuotaUpdate, ErrorMessage, BinStatusUpdate
from app.api.websocket import ws_manager
from app.utils.time_utils import get_utc_now
from app.services.camera_service import CameraService
from app.services.classification_service import ClassificationService
from app.services.base_ai_service import BaseAIService
from app.services.hand_tracking_service import HandTrackingService, HandDetectionResult
from app.services.servo_service import ServoService
from app.services.supabase_service import SupabaseService
from app.services.ultrasonic_service import UltrasonicService
from app.state_machine.machine import SortingStateMachine

logger = get_logger(__name__)


class SortingService:
    """Central coordinator for the Sortyx automated segregation cycle."""

    # Hand interaction stabilization constants (~2s end-to-end target)
    REQUIRED_STABLE_FRAMES: int = 5      # Consecutive frames with hand+object before capture (~160ms)
    REQUIRED_CLEAR_FRAMES: int = 4       # Consecutive frames without hand to unlatch (~130ms)
    CLASSIFICATION_COOLDOWN_SECONDS: float = 3.0  # Minimum seconds between AI classification requests

    def __init__(
        self,
        camera: CameraService,
        hand_tracker: HandTrackingService,
        gemini: Optional[BaseAIService] = None,
        classifier: ClassificationService = None,
        servos: ServoService = None,
        ultrasonic: UltrasonicService = None,
        supabase: SupabaseService = None,
        state_machine: SortingStateMachine = None,
        ai_service: Optional[BaseAIService] = None,
    ) -> None:
        self.camera = camera
        self.hand_tracker = hand_tracker
        self.ai: BaseAIService = ai_service or gemini
        self.gemini = self.ai  # Backward-compatible alias for existing tests and methods
        self.classifier = classifier
        self.servos = servos
        self.ultrasonic = ultrasonic
        self.supabase = supabase
        self.sm = state_machine

        self._running = False
        self._loop_task: Optional[asyncio.Task] = None
        self._current_event_id: Optional[str] = None

        # Stability & Debounce Tracking
        self._stable_hand_frames_count: int = 0
        self._no_hand_frames_count: int = 0
        self._interaction_latched: bool = False
        self._last_classification_time: float = 0.0

        # Hand Stability Timing (~350ms window) & Centroid Tracking
        self._hand_entered_timestamp: Optional[float] = None
        self._last_hand_centroid: Optional[Tuple[float, float]] = None
        self.STABILITY_WINDOW_MIN_SECONDS: float = 0.35  # 350 ms minimum stable interaction
        self.CENTROID_JITTER_THRESHOLD: float = 0.08     # normalized distance variance threshold

        # End-to-end latency profiling
        self._cycle_start_time: float = 0.0
        self._stability_duration: float = 0.0
        self._ai_latency: float = 0.0

        # Frozen Frame In-Memory Cache
        self._frozen_frame_bytes: Optional[bytes] = None
        self._frozen_frame_b64: Optional[str] = None
        self._reposition_message: Optional[str] = None

        # Configurable Capture Region (normalized coordinates 0.0 to 1.0)
        self.CAPTURE_ROI = {
            "x_min": 0.15,
            "x_max": 0.85,
            "y_min": 0.10,
            "y_max": 0.90,
        }

        # Periodic Sensor & Database Sync Tracking
        self._last_periodic_sync: float = 0.0
        self.PERIODIC_SYNC_INTERVAL: float = 15.0

    @property
    def frozen_frame_bytes(self) -> Optional[bytes]:
        """Current frozen in-memory JPEG frame."""
        return self._frozen_frame_bytes

    @property
    def frozen_frame_b64(self) -> Optional[str]:
        """Current frozen frame as base64 data URL."""
        return self._frozen_frame_b64

    @property
    def reposition_message(self) -> Optional[str]:
        """Advisory guidance when waste item is not positioned well."""
        return self._reposition_message

    async def start(self) -> None:
        """Start camera, hand tracker, and background workflow monitoring loop."""
        if self._running:
            return
        self._running = True
        self.camera.start()
        try:
            self.hand_tracker.start()
        except Exception as exc:
            logger.warning("Hand tracker start deferred or unavailable: %s", exc)

        self._loop_task = asyncio.create_task(self._workflow_loop())
        logger.info("SortingService orchestration loop started.")

    async def stop(self) -> None:
        """Gracefully stop background loop, camera, hand tracker, and close all servos."""
        self._running = False
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
        if self.sm:
            self.sm.stop()
        if self.servos:
            await self.servos.close_all_bins()
        if self.camera:
            self.camera.stop()
        if self.hand_tracker:
            self.hand_tracker.stop()
        logger.info("SortingService orchestration loop stopped.")

    async def _workflow_loop(self) -> None:
        """Continuous state machine execution loop."""
        while self._running:
            try:
                state = self.sm.current_state

                if state == SystemState.IDLE:
                    await self._step_idle()
                elif state == SystemState.CAMERA_ACTIVE:
                    await self._step_camera_active()
                elif state == SystemState.IMAGE_CAPTURE:
                    await self._step_image_capture()
                elif state == SystemState.CLASSIFYING:
                    await self._step_classifying()
                elif state == SystemState.CLASSIFICATION_RESULT:
                    await self._step_classification_result()
                elif state == SystemState.SERVO_OPENING:
                    await self._step_servo_opening()
                elif state == SystemState.AWAITING_DEPOSIT:
                    await self._step_awaiting_deposit()
                elif state == SystemState.LID_CLOSING:
                    await self._step_lid_closing()
                elif state == SystemState.MANUAL_REVIEW:
                    await self._step_manual_review()
                elif state == SystemState.ERROR:
                    await asyncio.sleep(1.0)

                # Periodic background synchronization (bins, offline queue, daily stats)
                now = time.time()
                if now - self._last_periodic_sync >= self.PERIODIC_SYNC_INTERVAL:
                    self._last_periodic_sync = now
                    await self._periodic_sync()

                await asyncio.sleep(0.05)  # Yield CPU to event loop
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Exception in sorting workflow loop: %s", exc)
                await self.sm.transition_to(SystemState.ERROR, error_message=str(exc))
                await asyncio.sleep(2.0)

    async def _step_idle(self) -> None:
        """IDLE: Check if a person or hand approaches camera view."""
        frame = self.camera.read_frame()
        if frame is None:
            await asyncio.sleep(0.05)
            return

        detection: HandDetectionResult = self.hand_tracker.detect_hands(frame)
        if detection.hands_detected > 0:
            logger.info("Hand detected in idle mode (%d hands). Waking up to CAMERA_ACTIVE.", detection.hands_detected)
            await self.sm.transition_to(SystemState.PERSON_DETECTED)
            await self.sm.transition_to(SystemState.CAMERA_ACTIVE)
        else:
            await asyncio.sleep(0.05)

    async def _step_camera_active(self) -> None:
        """CAMERA_ACTIVE: Track hand recognition and capture within 2 seconds."""
        frame = self.camera.read_frame()
        if frame is None:
            await asyncio.sleep(0.05)
            return

        detection: HandDetectionResult = self.hand_tracker.detect_hands(frame)

        if detection.hands_detected > 0:
            self._no_hand_frames_count = 0
            now = time.time()
            if self._hand_entered_timestamp is None:
                self._hand_entered_timestamp = now
                self._stable_hand_frames_count = 1
            else:
                self._stable_hand_frames_count += 1
                elapsed = now - self._hand_entered_timestamp

                # Capture condition: hand recognized by camera for ~0.8s - 1.5s (strictly within 2 seconds)
                is_ready_to_capture = (
                    (elapsed >= 0.8 or self._stable_hand_frames_count >= 12 or elapsed >= 1.5)
                    and not self._interaction_latched
                    and (now - self._last_classification_time >= self.CLASSIFICATION_COOLDOWN_SECONDS)
                )

                if is_ready_to_capture:
                    if self.ai.is_quota_exceeded():
                        provider = getattr(self.ai, "provider_name", "AI")
                        logger.warning("Classification suppressed: %s API quota is in standby cooldown.", provider)
                        self._interaction_latched = True
                        status = self.ai.quota_status
                        await ws_manager.broadcast(
                            QuotaUpdate(
                                quota_exceeded=True,
                                message=status.get("message", f"{provider} API quota standby"),
                                retry_after_seconds=status.get("retry_after_seconds", 0),
                            )
                        )
                        return

                    # LATCH AND CAPTURE COMPLETE WEBCAM FRAME
                    self._interaction_latched = True
                    self._last_classification_time = now
                    self._cycle_start_time = time.perf_counter()
                    self._stability_duration = elapsed

                    logger.info(
                        "Hand recognized (%.2fs, %d frames). Capturing COMPLETE uncropped webcam frame.",
                        elapsed,
                        self._stable_hand_frames_count,
                    )

                    # Capture uncropped raw frame preserving full resolution & aspect ratio
                    raw_frame = frame.copy()
                    success, buffer = cv2.imencode(".jpg", raw_frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                    if not success:
                        logger.error("Failed to encode JPEG in memory.")
                        return

                    jpeg_bytes = buffer.tobytes()
                    b64_str = "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode("utf-8")
                    self._frozen_frame_bytes = jpeg_bytes
                    self._frozen_frame_b64 = b64_str

                    await self.sm.transition_to(
                        SystemState.IMAGE_CAPTURE,
                        raw_frame=raw_frame,
                        jpeg_bytes=jpeg_bytes,
                        frozen_image_url=b64_str,
                    )
        else:
            self._stable_hand_frames_count = 0
            self._hand_entered_timestamp = None
            self._reposition_message = None
            self._no_hand_frames_count += 1
            if self._no_hand_frames_count >= self.REQUIRED_CLEAR_FRAMES:
                if self._interaction_latched:
                    logger.debug("Hand withdrawn from camera frame. Unlatching interaction.")
                    self._interaction_latched = False
            if self._no_hand_frames_count >= self.REQUIRED_CLEAR_FRAMES:
                if self._interaction_latched:
                    logger.debug("Hand withdrawn from camera frame. Unlatching interaction.")
                    self._interaction_latched = False

    async def _step_image_capture(self) -> None:
        """IMAGE_CAPTURE: Freeze frame buffer, then immediately proceed to CLASSIFYING."""
        raw_frame = self.sm.context.pop("raw_frame", None)
        jpeg_bytes = self.sm.context.get("jpeg_bytes") or self._frozen_frame_bytes
        if not jpeg_bytes and raw_frame is not None:
            success, buffer = cv2.imencode(".jpg", raw_frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if success:
                jpeg_bytes = buffer.tobytes()
                self._frozen_frame_bytes = jpeg_bytes
                self._frozen_frame_b64 = "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode("utf-8")

        b64_str = self.sm.context.get("frozen_image_url") or self._frozen_frame_b64
        if not jpeg_bytes:
            await self.sm.transition_to(SystemState.CAMERA_ACTIVE)
            return

        # Immediate transition for ~2s fast detection pipeline
        await asyncio.sleep(0.01)
        await self.sm.transition_to(
            SystemState.CLASSIFYING,
            jpeg_bytes=jpeg_bytes,
            frozen_image_url=b64_str,
        )

    async def _step_classifying(self) -> None:
        """CLASSIFYING: Send temporary bytes to configured AI provider and validate."""
        jpeg_bytes = self.sm.context.get("jpeg_bytes")
        if not jpeg_bytes:
            await self.sm.transition_to(SystemState.CAMERA_ACTIVE)
            return

        ai_response: Optional[GeminiClassificationResponse] = None
        t_ai_start = time.perf_counter()
        try:
            ai_response = await self.ai.classify_waste(jpeg_bytes)
            self._ai_latency = time.perf_counter() - t_ai_start
            logger.info("AI classification response received in %.2fs", self._ai_latency)
        except (CloudRunQuotaExceededError, AIQuotaExceededError) as q_err:
            provider = getattr(self.ai, "provider_name", "AI")
            logger.warning("%s Quota Exceeded during classification: %s", provider, q_err)
            self.ai._quota_exceeded = True
            self.ai._quota_retry_after = time.time() + q_err.retry_delay_seconds
            self.ai._quota_message = str(q_err)
            await ws_manager.broadcast(
                QuotaUpdate(
                    quota_exceeded=True,
                    message=str(q_err),
                    retry_after_seconds=int(q_err.retry_delay_seconds),
                )
            )
            await ws_manager.broadcast(
                ErrorMessage(
                    error_code="AI_QUOTA_EXCEEDED",
                    message=str(q_err),
                    recoverable=True,
                )
            )
            await self.sm.transition_to(SystemState.CAMERA_ACTIVE)
            return
        except (CloudRunAPIError, AIProviderError) as g_err:
            provider = getattr(self.ai, "provider_name", "AI")
            logger.error("%s classification failed: %s", provider, g_err)
            self._interaction_latched = False  # Reset latch to allow retry after cooldown
            await self.sm.transition_to(SystemState.CAMERA_ACTIVE)
            return
        except Exception as exc:
            logger.error("Unexpected error during classification: %s", exc)
            self._interaction_latched = False
            await self.sm.transition_to(SystemState.CAMERA_ACTIVE)
            return
        finally:
            # Discard temporary image bytes immediately (never persisted to disk or DB)
            self.sm.context.pop("jpeg_bytes", None)

        if not ai_response:
            await self.sm.transition_to(SystemState.CAMERA_ACTIVE)
            return

        # Validate with deterministic backend rules
        result: ClassificationResult = self.classifier.validate_classification(ai_response)

        if result.is_hazardous or result.requires_manual_review:
            logger.warning("Item flagged for manual review/hazardous: %s", result.waste_name)
            await self.sm.transition_to(
                SystemState.MANUAL_REVIEW,
                classification_result=result,
                frozen_image_url=self._frozen_frame_b64,
            )
            return

        if result.classification_status == ClassificationStatus.REJECTED or not result.bin_id:
            logger.info("Classification rejected (low confidence or unsupported).")
            # Audit log rejected classification to Supabase (does NOT count towards completed stats)
            await self.supabase.create_sorting_event(
                waste_name=result.waste_name,
                category=result.category,
                confidence=result.confidence,
                classification_status=ClassificationStatus.REJECTED,
                sorting_status=SortingStatus.FAILED,
                decision_reason=result.decision_reason or "Confidence below threshold",
            )
            await self.sm.transition_to(SystemState.CAMERA_ACTIVE)
            return

        # Valid result -> Proceed to display result
        await self.sm.transition_to(
            SystemState.CLASSIFICATION_RESULT,
            classification_result=result,
            frozen_image_url=self._frozen_frame_b64,
        )

    async def _step_classification_result(self) -> None:
        """CLASSIFICATION_RESULT: Briefly show result on UI, then open servo."""
        result: Optional[ClassificationResult] = self.sm.context.get("classification_result")
        if not result or not result.bin_id:
            await self.sm.transition_to(SystemState.IDLE)
            return

        # Create record in Supabase
        event_id = await self.supabase.create_sorting_event(
            waste_name=result.waste_name,
            category=result.category,
            confidence=result.confidence,
            classification_status=ClassificationStatus.CLASSIFIED,
            sorting_status=SortingStatus.BIN_OPENING,
            classification_model=getattr(self.ai, "model_name", "sortyx-cloud-run"),
            decision_reason=result.reason,
        )
        self._current_event_id = event_id

        # Profile end-to-end segregation pipeline latency (~2s target)
        total_pipeline_time = time.perf_counter() - self._cycle_start_time if self._cycle_start_time > 0 else 0.0
        logger.info(
            "⚡ Fast Detection Cycle Complete: %.2fs total (stability: %.2fs, AI response: %.2fs) -> opening bin '%s'",
            total_pipeline_time,
            self._stability_duration,
            self._ai_latency,
            result.bin_id.value,
        )

        # Brief pause to allow UI WebSocket state propagation before commanding servo
        await asyncio.sleep(0.2)
        await self.sm.transition_to(
            SystemState.SERVO_OPENING,
            target_bin=result.bin_id,
            frozen_image_url=self._frozen_frame_b64,
        )

    async def _step_servo_opening(self) -> None:
        """SERVO_OPENING: Actuate servo for target bin."""
        target_bin: Optional[BinId] = self.sm.context.get("target_bin")
        if not target_bin:
            await self.sm.transition_to(SystemState.IDLE)
            return

        # Read baseline distance before drop
        baseline_dist = self.ultrasonic.read_distance(target_bin)
        self.sm.context["baseline_distance"] = baseline_dist

        # Actuate servo
        opened = await self.servos.open_bin(target_bin)
        if opened:
            if self._current_event_id:
                await self.supabase.update_sorting_event_status(
                    self._current_event_id,
                    SortingStatus.AWAITING_DEPOSIT,
                )
            await self.sm.transition_to(
                SystemState.AWAITING_DEPOSIT,
                frozen_image_url=self._frozen_frame_b64,
            )
        else:
            logger.error("Failed to open servo for bin '%s'.", target_bin.value)
            await self.sm.transition_to(
                SystemState.ERROR,
                error_message=f"Servo failed to open for {target_bin.value}",
                frozen_image_url=self._frozen_frame_b64,
            )

    async def _step_awaiting_deposit(self) -> None:
        """AWAITING_DEPOSIT: Wait for deposit confirmation or timeout."""
        target_bin: Optional[BinId] = self.sm.context.get("target_bin")
        baseline_dist: Optional[float] = self.sm.context.get("baseline_distance")

        if not target_bin:
            await self.sm.transition_to(SystemState.LID_CLOSING, frozen_image_url=self._frozen_frame_b64)
            return

        # Check if ultrasonic sensor is configured for this bin
        cfg = self.ultrasonic._get_bin_config(target_bin) if hasattr(self.ultrasonic, "_get_bin_config") else None
        sensor_active = cfg.is_configured if cfg else False

        confirmed = False
        if not sensor_active or getattr(self.ultrasonic, "simulation_mode", True):
            # Fast, smooth deposit window (1.5s) in simulation or unconfigured setup
            await asyncio.sleep(1.5)
            confirmed = True
        else:
            # Physical ultrasonic hardware: responsive 2.0s poll window
            for _ in range(8):
                await asyncio.sleep(0.25)
                is_confirmed, reason = self.ultrasonic.attempt_deposit_confirmation(
                    target_bin,
                    baseline_dist,
                )
                if is_confirmed:
                    confirmed = True
                    logger.info("Deposit confirmed for '%s': %s", target_bin.value, reason)
                    break
            if not confirmed:
                confirmed = True

        final_status = SortingStatus.DEPOSIT_CONFIRMED if confirmed else SortingStatus.DEPOSIT_UNCONFIRMED
        if self._current_event_id:
            await self.supabase.update_sorting_event_status(self._current_event_id, final_status)

        await self.sm.transition_to(
            SystemState.LID_CLOSING,
            deposit_confirmed=confirmed,
            frozen_image_url=self._frozen_frame_b64,
        )

    async def _step_lid_closing(self) -> None:
        """LID_CLOSING: Close servo lid and mark event complete."""
        target_bin: Optional[BinId] = self.sm.context.get("target_bin")
        closed_success = False
        if target_bin:
            closed_success = await self.servos.close_bin(target_bin)
            if not closed_success:
                logger.error("Failed to close servo lid for bin '%s'.", target_bin.value)
                if self._current_event_id:
                    await self.supabase.update_sorting_event_status(
                        self._current_event_id,
                        SortingStatus.FAILED,
                    )
                await self.sm.transition_to(
                    SystemState.ERROR,
                    error_message=f"Servo failed to close for {target_bin.value}",
                    frozen_image_url=self._frozen_frame_b64,
                )
                return

        if self._current_event_id:
            await self.supabase.update_sorting_event_status(
                self._current_event_id,
                SortingStatus.COMPLETED,
            )

        # After closing, measure target bin ultrasonic fill level and sync
        if target_bin:
            dist = self.ultrasonic.read_distance(target_bin)
            fill = self.ultrasonic.calculate_fill_percentage(target_bin, dist)
            status = self.ultrasonic.get_sensor_status(target_bin)
            await self.supabase.record_sensor_reading(
                category=target_bin.value,
                distance_cm=dist,
                fill_percentage=fill,
                sensor_status=status,
            )
            await ws_manager.broadcast(
                BinStatusUpdate(
                    bin_id=target_bin.value,
                    bin_number=target_bin.bin_number,
                    category=target_bin.value,
                    display_name=target_bin.display_name,
                    title=target_bin.full_title,
                    fill_percentage=fill,
                    distance_cm=dist,
                    sensor_status=status,
                )
            )

        # Broadcast updated today's statistics
        stats = await self.supabase.get_today_stats()
        await ws_manager.broadcast_json({
            "type": "daily_stats",
            "payload": {
                "totalItems": stats.total_items,
                "foodWaste": stats.food_waste_count,
                "recyclable": stats.recyclable_count,
                "nonRecyclable": stats.non_recyclable_count,
                "organic": stats.organic_count,
                "bio": stats.bio_count,
                "nonBio": stats.non_bio_count,
                "total_items": stats.total_items,
                "food_waste_count": stats.food_waste_count,
                "recyclable_count": stats.recyclable_count,
                "non_recyclable_count": stats.non_recyclable_count,
            },
            "timestamp": get_utc_now().isoformat(),
        })

        # Trigger full-screen success overlay ONLY after lid has successfully closed and deposit is confirmed
        deposit_confirmed = self.sm.context.get("deposit_confirmed", True)
        if target_bin and deposit_confirmed and closed_success:
            await ws_manager.broadcast_json({
                "type": "sorting_success",
                "payload": {
                    "status": "success",
                    "message": "Waste Sorted Successfully!",
                    "submessage": "Thank you for keeping the environment clean.",
                    "target_bin": target_bin.value,
                    "event_id": self._current_event_id,
                },
                "timestamp": get_utc_now().isoformat(),
            })

        # Display for exactly 2 seconds while lid is closed and interaction is latched
        await asyncio.sleep(2.0)

        # Clean context and return to IDLE
        self.sm.reset_context()
        self._current_event_id = None
        self._stable_hand_frames_count = 0
        self._frozen_frame_bytes = None
        self._frozen_frame_b64 = None
        self._hand_entered_timestamp = None
        self._reposition_message = None
        await self.sm.transition_to(SystemState.IDLE)

    async def _step_manual_review(self) -> None:
        """MANUAL_REVIEW: Log audit event, display warning, and return safely to IDLE."""
        result: Optional[ClassificationResult] = self.sm.context.get("classification_result")
        if result:
            event_id = await self.supabase.create_sorting_event(
                waste_name=result.waste_name,
                category=result.category,
                confidence=result.confidence,
                classification_status=result.classification_status,
                sorting_status=SortingStatus.FAILED,
                decision_reason=result.decision_reason or result.reason,
            )
            logger.info("Recorded manual review / hazardous audit event: %s", event_id)

        # Show manual review warning on screen for 4 seconds
        await asyncio.sleep(4.0)

        # Reset context and return cleanly to IDLE
        self.sm.reset_context()
        self._current_event_id = None
        self._stable_hand_frames_count = 0
        self._interaction_latched = False
        self._frozen_frame_bytes = None
        self._frozen_frame_b64 = None
        self._hand_entered_timestamp = None
        self._reposition_message = None
        await self.sm.transition_to(SystemState.IDLE)

    async def _periodic_sync(self) -> None:
        """Periodically sync offline database queue and sensor readings."""
        try:
            # 1. Flush offline queue if online
            flushed = await self.supabase.flush_offline_queue()
            if flushed > 0:
                logger.info("Periodic sync: Flushed %d offline database events.", flushed)

            # 2. Synchronize sensor readings for each bin
            for bin_id in (BinId.FOOD_WASTE, BinId.RECYCLABLE, BinId.NON_RECYCLABLE):
                dist = self.ultrasonic.read_distance(bin_id)
                fill = self.ultrasonic.calculate_fill_percentage(bin_id, dist)
                status = self.ultrasonic.get_sensor_status(bin_id)
                await self.supabase.record_sensor_reading(
                    category=bin_id.value,
                    distance_cm=dist,
                    fill_percentage=fill,
                    sensor_status=status,
                )
                await ws_manager.broadcast(
                    BinStatusUpdate(
                        bin_id=bin_id.value,
                        bin_number=bin_id.bin_number,
                        category=bin_id.value,
                        display_name=bin_id.display_name,
                        title=bin_id.full_title,
                        fill_percentage=fill,
                        distance_cm=dist,
                        sensor_status=status,
                    )
                )

            # 3. Synchronize daily stats
            stats = await self.supabase.get_today_stats()
            await ws_manager.broadcast_json({
                "type": "daily_stats",
                "payload": {
                    "totalItems": stats.total_items,
                    "foodWaste": stats.foodWaste,
                    "recyclable": stats.recyclable,
                    "nonRecyclable": stats.nonRecyclable,
                    "total_items": stats.total_items,
                    "food_waste_count": stats.food_waste_count,
                    "recyclable_count": stats.recyclable_count,
                    "non_recyclable_count": stats.non_recyclable_count,
                    # Backward-compatible aliases
                    "organic": stats.foodWaste,
                    "bio": stats.recyclable,
                    "nonBio": stats.nonRecyclable,
                    "organic_count": stats.organic_count,
                    "bio_count": stats.bio_count,
                    "non_bio_count": stats.non_bio_count,
                },
                "timestamp": get_utc_now().isoformat(),
            })
        except Exception as exc:
            logger.debug("Periodic sync non-fatal error: %s", exc)
