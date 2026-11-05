"""
Sortyx 2.0 — Hand Tracking and Object Interaction Service.

Detects human hands, landmarks, and hand-held object interactions using:
1. Google MediaPipe Tasks HandLandmarker (modern API, with hand_landmarker.task)
2. MediaPipe Solutions Hands (legacy fallback for older Pi OS packages)
3. OpenCV skin/contour defect heuristic fallback (ensures zero crashes)

Provides frame annotation for the live video stream (visualizing landmarks & interaction).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Tuple

import cv2
import numpy as np

from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Model task file location
_MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
MODEL_TASK_PATH = _MODELS_DIR / "hand_landmarker.task"

# MediaPipe Hand standard skeleton connections (pairs of landmark indices)
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),        # Thumb
    (0, 5), (5, 6), (6, 7), (7, 8),        # Index
    (5, 9), (9, 10), (10, 11), (11, 12),   # Middle
    (9, 13), (13, 14), (14, 15), (15, 16), # Ring
    (13, 17), (17, 18), (18, 19), (19, 20),# Pinky
    (0, 17),                               # Palm base
]


@dataclass
class HandDetectionResult:
    """Outcome of a hand-detection analysis pass."""

    hands_detected: int = 0
    hand_holding_object: bool = False
    landmarks: List[List[Tuple[float, float, float]]] = field(default_factory=list)
    bounding_boxes: List[Tuple[int, int, int, int]] = field(default_factory=list)


class HandTrackingService:
    """Detects hands, landmarks, and object grasping interactions."""

    def __init__(
        self,
        model_complexity: int = 0,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
        max_num_hands: int = 2,
    ) -> None:
        self.min_detection_confidence = min_detection_confidence
        self.min_tracking_confidence = min_tracking_confidence
        self.max_num_hands = max_num_hands

        self._task_detector = None
        self._legacy_detector = None
        self._backend = "none"
        self._initialized = False

    def start(self) -> None:
        """Initialize the hand detection backend."""
        if self._initialized:
            return

        # 1. Try MediaPipe Tasks HandLandmarker
        if MODEL_TASK_PATH.exists():
            try:
                import mediapipe as mp
                from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions
                from mediapipe.tasks.python import BaseOptions

                options = HandLandmarkerOptions(
                    base_options=BaseOptions(model_asset_path=str(MODEL_TASK_PATH)),
                    num_hands=self.max_num_hands,
                    min_hand_detection_confidence=self.min_detection_confidence,
                    min_tracking_confidence=self.min_tracking_confidence,
                )
                self._task_detector = HandLandmarker.create_from_options(options)
                self._backend = "mediapipe_tasks"
                self._initialized = True
                logger.info("MediaPipe Tasks HandLandmarker initialized successfully.")
                return
            except Exception as exc:
                logger.warning("MediaPipe Tasks initialization failed: %s", exc)

        # 2. Try legacy mp.solutions.hands
        try:
            import mediapipe as mp
            if hasattr(mp, "solutions") and hasattr(mp.solutions, "hands"):
                self._legacy_detector = mp.solutions.hands.Hands(
                    static_image_mode=False,
                    max_num_hands=self.max_num_hands,
                    min_detection_confidence=self.min_detection_confidence,
                    min_tracking_confidence=self.min_tracking_confidence,
                )
                self._backend = "mediapipe_legacy"
                self._initialized = True
                logger.info("Legacy MediaPipe Solutions Hands initialized successfully.")
                return
        except Exception as exc:
            logger.debug("Legacy MediaPipe hands not available: %s", exc)

        # 3. Fallback to OpenCV skin-tone detector
        self._backend = "opencv_contour"
        self._initialized = True
        logger.info("Operating in OpenCV skin-tone hand tracking fallback mode.")

    def stop(self) -> None:
        """Release detector resources."""
        if self._task_detector:
            try:
                self._task_detector.close()
            except Exception:
                pass
            self._task_detector = None

        if self._legacy_detector:
            try:
                self._legacy_detector.close()
            except Exception:
                pass
            self._legacy_detector = None

        self._initialized = False
        logger.info("HandTrackingService stopped.")

    def detect_hands(self, frame: np.ndarray) -> HandDetectionResult:
        """Process a BGR frame and return detected hands, landmarks, and interaction flag."""
        if not self._initialized:
            self.start()

        h, w, _ = frame.shape

        if self._backend == "mediapipe_tasks" and self._task_detector:
            return self._detect_tasks(frame, w, h)
        elif self._backend == "mediapipe_legacy" and self._legacy_detector:
            return self._detect_legacy(frame, w, h)
        else:
            return self._detect_opencv_fallback(frame, w, h)

    def _detect_tasks(self, frame: np.ndarray, width: int, height: int) -> HandDetectionResult:
        import mediapipe as mp

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        res = self._task_detector.detect(mp_image)

        if not res.hand_landmarks:
            return HandDetectionResult()

        all_landmarks = []
        boxes = []
        is_holding = False

        for hand_lms in res.hand_landmarks:
            pts = [(lm.x, lm.y, lm.z) for lm in hand_lms]
            all_landmarks.append(pts)

            # Bounding box
            xs = [int(p[0] * width) for p in pts]
            ys = [int(p[1] * height) for p in pts]
            min_x, max_x = max(0, min(xs)), min(width, max(xs))
            min_y, max_y = max(0, min(ys)), min(height, max(ys))
            boxes.append((min_x, min_y, max_x - min_x, max_y - min_y))

            # Grasping / holding heuristic: finger tips curled relative to MCP knuckles
            tips = [8, 12, 16, 20]
            mcps = [5, 9, 13, 17]
            curled = sum(1 for t, m in zip(tips, mcps) if pts[t][1] > pts[m][1])
            if curled >= 2 or len(res.hand_landmarks) >= 1:
                is_holding = True

        return HandDetectionResult(
            hands_detected=len(res.hand_landmarks),
            hand_holding_object=is_holding,
            landmarks=all_landmarks,
            bounding_boxes=boxes,
        )

    def _detect_legacy(self, frame: np.ndarray, width: int, height: int) -> HandDetectionResult:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res = self._legacy_detector.process(rgb)

        if not res.multi_hand_landmarks:
            return HandDetectionResult()

        all_landmarks = []
        boxes = []
        is_holding = False

        for hand_lms in res.multi_hand_landmarks:
            pts = [(lm.x, lm.y, lm.z) for lm in hand_lms.landmark]
            all_landmarks.append(pts)

            xs = [int(p[0] * width) for p in pts]
            ys = [int(p[1] * height) for p in pts]
            min_x, max_x = max(0, min(xs)), min(width, max(xs))
            min_y, max_y = max(0, min(ys)), min(height, max(ys))
            boxes.append((min_x, min_y, max_x - min_x, max_y - min_y))

            tips = [8, 12, 16, 20]
            mcps = [5, 9, 13, 17]
            curled = sum(1 for t, m in zip(tips, mcps) if pts[t][1] > pts[m][1])
            if curled >= 2:
                is_holding = True

        return HandDetectionResult(
            hands_detected=len(res.multi_hand_landmarks),
            hand_holding_object=is_holding,
            landmarks=all_landmarks,
            bounding_boxes=boxes,
        )

    def _detect_opencv_fallback(self, frame: np.ndarray, width: int, height: int) -> HandDetectionResult:
        """Skin color thresholding & contour detection fallback."""
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        lower_skin = np.array([0, 20, 70], dtype=np.uint8)
        upper_skin = np.array([25, 255, 255], dtype=np.uint8)

        mask = cv2.inRange(hsv, lower_skin, upper_skin)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.dilate(mask, kernel, iterations=2)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        valid_boxes = []

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > 10000:  # Hand-sized area
                x, y, w_box, h_box = cv2.boundingRect(cnt)
                valid_boxes.append((x, y, w_box, h_box))

        num = len(valid_boxes)
        return HandDetectionResult(
            hands_detected=num,
            hand_holding_object=num > 0,
            landmarks=[],
            bounding_boxes=valid_boxes,
        )

    def annotate_frame(self, frame: np.ndarray, result: Optional[HandDetectionResult] = None) -> np.ndarray:
        """Draw hand landmarks, skeleton connections, and tracking badges on the preview frame."""
        annotated = frame.copy()
        h, w, _ = frame.shape

        if result is None:
            result = self.detect_hands(frame)

        # Draw skeleton connections & landmarks
        for pts in result.landmarks:
            # Draw lines
            for idx1, idx2 in HAND_CONNECTIONS:
                if idx1 < len(pts) and idx2 < len(pts):
                    p1 = (int(pts[idx1][0] * w), int(pts[idx1][1] * h))
                    p2 = (int(pts[idx2][0] * w), int(pts[idx2][1] * h))
                    cv2.line(annotated, p1, p2, (200, 130, 255), 2, cv2.LINE_AA)

            # Draw landmark nodes
            for p in pts:
                cx, cy = int(p[0] * w), int(p[1] * h)
                cv2.circle(annotated, (cx, cy), 4, (34, 197, 94), -1, cv2.LINE_AA)
                cv2.circle(annotated, (cx, cy), 5, (255, 255, 255), 1, cv2.LINE_AA)

        # Draw bounding boxes
        for x, y, bw, bh in result.bounding_boxes:
            cv2.rectangle(annotated, (x, y), (x + bw, y + bh), (147, 51, 234), 2)

        # Overlay status pill
        if result.hands_detected > 0:
            status_text = "Hand Detected" if not result.hand_holding_object else "Object Held"
            color = (34, 197, 94) if not result.hand_holding_object else (147, 51, 234)

            # Draw background pill
            cv2.rectangle(annotated, (15, 15), (170, 45), (20, 20, 25), -1)
            cv2.rectangle(annotated, (15, 15), (170, 45), color, 1)
            cv2.circle(annotated, (30, 30), 5, color, -1)
            cv2.putText(
                annotated,
                status_text,
                (45, 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )

        return annotated
