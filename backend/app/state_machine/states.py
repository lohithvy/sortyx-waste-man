"""
Sortyx 2.0 — State Machine State Definitions.

Defines the individual behavior, entry/exit hooks, allowed transitions,
and timeouts for all 10 states of the Sortyx sorting cycle.
"""

from __future__ import annotations

import abc
from typing import Any, Dict, List, Optional, Set

from app.models.enums import SystemState


class BaseState(abc.ABC):
    """Abstract base class for all state machine states."""

    state: SystemState
    allowed_transitions: Set[SystemState]
    timeout_seconds: Optional[float] = None

    def __init__(self) -> None:
        pass

    def can_transition_to(self, target: SystemState) -> bool:
        """Check if target state is a valid transition."""
        return target in self.allowed_transitions

    async def on_enter(self, context: Dict[str, Any]) -> None:
        """Invoked when entering this state."""
        pass

    async def on_exit(self, context: Dict[str, Any]) -> None:
        """Invoked when exiting this state."""
        pass


class IdleState(BaseState):
    """State 1 — System is idle, displaying Sortyx1 waiting screen."""

    state = SystemState.IDLE
    allowed_transitions = {
        SystemState.PERSON_DETECTED,
        SystemState.CAMERA_ACTIVE,
        SystemState.ERROR,
    }


class PersonDetectedState(BaseState):
    """State 2 — Presence/hand detected; transitioning to active camera UI."""

    state = SystemState.PERSON_DETECTED
    allowed_transitions = {
        SystemState.CAMERA_ACTIVE,
        SystemState.IDLE,
        SystemState.ERROR,
    }
    timeout_seconds = 10.0


class CameraActiveState(BaseState):
    """State 3 — Live camera feed active, hand tracking detecting waste item."""

    state = SystemState.CAMERA_ACTIVE
    allowed_transitions = {
        SystemState.IMAGE_CAPTURE,
        SystemState.IDLE,
        SystemState.ERROR,
    }
    timeout_seconds = 60.0  # Return to idle if no stable interaction within 60s


class ImageCaptureState(BaseState):
    """State 4 — Temporary in-memory frame captured for classification."""

    state = SystemState.IMAGE_CAPTURE
    allowed_transitions = {
        SystemState.CLASSIFYING,
        SystemState.CAMERA_ACTIVE,
        SystemState.ERROR,
    }
    timeout_seconds = 5.0


class ClassifyingState(BaseState):
    """State 5 — Calling Gemini AI model and validating structured response."""

    state = SystemState.CLASSIFYING
    allowed_transitions = {
        SystemState.CLASSIFICATION_RESULT,
        SystemState.MANUAL_REVIEW,
        SystemState.CAMERA_ACTIVE,
        SystemState.ERROR,
    }
    timeout_seconds = 20.0


class ClassificationResultState(BaseState):
    """State 6 — Displaying detected waste name, category, confidence, and target bin."""

    state = SystemState.CLASSIFICATION_RESULT
    allowed_transitions = {
        SystemState.SERVO_OPENING,
        SystemState.MANUAL_REVIEW,
        SystemState.IDLE,
        SystemState.ERROR,
    }
    timeout_seconds = 10.0


class ServoOpeningState(BaseState):
    """State 7 — Backend validated; activating PCA9685 servo to open target bin."""

    state = SystemState.SERVO_OPENING
    allowed_transitions = {
        SystemState.AWAITING_DEPOSIT,
        SystemState.LID_CLOSING,
        SystemState.ERROR,
    }
    timeout_seconds = 10.0


class AwaitingDepositState(BaseState):
    """State 8 — Bin open; awaiting user deposit, monitoring ultrasonic readings."""

    state = SystemState.AWAITING_DEPOSIT
    allowed_transitions = {
        SystemState.LID_CLOSING,
        SystemState.ERROR,
    }
    timeout_seconds = 20.0  # Auto-close lid after 20s safe timeout


class LidClosingState(BaseState):
    """State 9 — Closing servo-controlled lid and confirming completion."""

    state = SystemState.LID_CLOSING
    allowed_transitions = {
        SystemState.IDLE,
        SystemState.ERROR,
    }
    timeout_seconds = 10.0


class ManualReviewState(BaseState):
    """Safe State — Hazardous item, unknown object, or low confidence."""

    state = SystemState.MANUAL_REVIEW
    allowed_transitions = {
        SystemState.IDLE,
        SystemState.CAMERA_ACTIVE,
    }
    timeout_seconds = 15.0


class ErrorState(BaseState):
    """Safe State — Hardware or API exception; lids closed, safe recovery."""

    state = SystemState.ERROR
    allowed_transitions = {
        SystemState.IDLE,
    }
    timeout_seconds = 5.0

