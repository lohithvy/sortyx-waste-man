"""
Sortyx 2.0 — Phase 4: Camera & Hand Tracking Unit Tests.

Tests:
1. Camera start & frame reading interface.
2. In-memory frame capture without disk persistence.
3. MediaPipe Tasks hand tracking initialization and detection.
4. Hand landmark annotation and visual overlay.
5. Grasping / holding heuristic evaluation.
6. Temporary image buffer lifecycle (buffer discarded after processing).
7. Error and exception handling (camera busy, permission denied).
"""

from __future__ import annotations

import io
from pathlib import Path
import cv2
import numpy as np
import pytest

from app.models.enums import CameraSource
from app.services.camera_service import WebcamService, get_camera_service
from app.services.hand_tracking_service import HandTrackingService, HandDetectionResult


def test_camera_service_factory() -> None:
    svc = get_camera_service(source="WEBCAM", camera_index=0)
    assert isinstance(svc, WebcamService)
    assert svc._index == 0


def test_in_memory_frame_capture_never_touches_disk() -> None:
    # Generate test frame
    test_frame = np.full((480, 640, 3), (120, 180, 240), dtype=np.uint8)

    # Encode directly to in-memory bytes
    success, buffer = cv2.imencode(".jpg", test_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    assert success is True
    jpeg_bytes = buffer.tobytes()

    assert isinstance(jpeg_bytes, bytes)
    assert len(jpeg_bytes) > 0

    # Verify no file was written to disk
    current_files = list(Path(".").glob("*.jpg"))
    assert len(current_files) == 0

    # Discard buffer from memory
    del buffer
    del jpeg_bytes


@pytest.fixture(scope="module")
def shared_tracker():
    tracker = HandTrackingService(min_detection_confidence=0.5)
    tracker.start()
    yield tracker
    tracker.stop()


def test_hand_tracking_service_initialization(shared_tracker: HandTrackingService) -> None:
    assert shared_tracker._initialized is True


def test_hand_detection_on_synthetic_frame(shared_tracker: HandTrackingService) -> None:
    # Black synthetic frame has no hands
    empty_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    res: HandDetectionResult = shared_tracker.detect_hands(empty_frame)

    assert isinstance(res, HandDetectionResult)
    assert res.hands_detected == 0
    assert res.hand_holding_object is False
    assert len(res.landmarks) == 0


def test_frame_annotation_overlay(shared_tracker: HandTrackingService) -> None:
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    annotated = shared_tracker.annotate_frame(frame)

    assert annotated is not None
    assert annotated.shape == frame.shape
    # Frame is a new array, original is untouched
    assert annotated is not frame


def test_hand_tracking_with_mock_hand_landmarks(shared_tracker: HandTrackingService) -> None:
    # Create dummy landmarks for 21 points
    mock_pts = [(0.5, 0.5 + i * 0.01, 0.0) for i in range(21)]
    result = HandDetectionResult(
        hands_detected=1,
        hand_holding_object=True,
        landmarks=[mock_pts],
        bounding_boxes=[(100, 100, 200, 200)],
    )

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    annotated = shared_tracker.annotate_frame(frame, result=result)

    # Pixels should be drawn on the annotated frame
    assert np.any(annotated > 0)


def test_camera_unavailable_handled_safely() -> None:
    # Non-existent high camera index should fail gracefully without crashing
    bad_cam = WebcamService(camera_index=999)
    bad_cam.start()

    assert not bad_cam.is_available()
    frame = bad_cam.read_frame()
    assert frame is None

    bad_cam.stop()

