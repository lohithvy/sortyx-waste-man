"""
Sortyx 2.0 — State Machine Engine.

Executes deterministic state transitions for the complete sorting lifecycle.
Emits events to registered listeners (e.g. WebSocket connection manager).
Guarantees hardware safety and prevents illegal or accidental transitions.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Dict, List, Optional

from app.core.logging_config import get_logger
from app.models.enums import SystemState
from app.state_machine.states import (
    BaseState,
    IdleState,
    PersonDetectedState,
    CameraActiveState,
    ImageCaptureState,
    ClassifyingState,
    ClassificationResultState,
    ServoOpeningState,
    AwaitingDepositState,
    LidClosingState,
    ManualReviewState,
    ErrorState,
)

logger = get_logger(__name__)


class SortingStateMachine:
    """State machine coordinator for Sortyx 2.0."""

    def __init__(self) -> None:
        self._states: Dict[SystemState, BaseState] = {
            SystemState.IDLE: IdleState(),
            SystemState.PERSON_DETECTED: PersonDetectedState(),
            SystemState.CAMERA_ACTIVE: CameraActiveState(),
            SystemState.IMAGE_CAPTURE: ImageCaptureState(),
            SystemState.CLASSIFYING: ClassifyingState(),
            SystemState.CLASSIFICATION_RESULT: ClassificationResultState(),
            SystemState.SERVO_OPENING: ServoOpeningState(),
            SystemState.AWAITING_DEPOSIT: AwaitingDepositState(),
            SystemState.LID_CLOSING: LidClosingState(),
            SystemState.MANUAL_REVIEW: ManualReviewState(),
            SystemState.ERROR: ErrorState(),
        }

        self._current_state_enum = SystemState.IDLE
        self._current_state = self._states[SystemState.IDLE]
        self._context: Dict[str, Any] = {}
        self._timeout_task: Optional[asyncio.Task] = None
        self._listeners: List[Callable[[SystemState, SystemState, Dict[str, Any]], Coroutine[Any, Any, None]]] = []

    @property
    def current_state(self) -> SystemState:
        """Current state enum value."""
        return self._current_state_enum

    @property
    def context(self) -> Dict[str, Any]:
        """Data dictionary shared across states."""
        return self._context

    def add_listener(
        self,
        listener: Callable[[SystemState, SystemState, Dict[str, Any]], Coroutine[Any, Any, None]],
    ) -> None:
        """Register an async callback for state change notifications."""
        self._listeners.append(listener)

    async def transition_to(self, target: SystemState, **kwargs: Any) -> bool:
        """Attempt to transition from the current state to the target state.

        Returns True if successful, False if transition is disallowed.
        """
        if not self._current_state.can_transition_to(target):
            # Allow forced transition to ERROR or IDLE during emergencies
            if target not in (SystemState.ERROR, SystemState.IDLE):
                logger.warning(
                    "Illegal transition rejected: %s -> %s",
                    self._current_state_enum.value,
                    target.value,
                )
                return False

        previous = self._current_state_enum
        logger.info("State transition: %s -> %s", previous.value, target.value)

        # Cancel any active state timeout
        if self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()

        # Update context
        self._context.update(kwargs)

        # Exit old state
        await self._current_state.on_exit(self._context)

        # Enter new state
        self._current_state_enum = target
        self._current_state = self._states[target]
        await self._current_state.on_enter(self._context)

        # Notify listeners
        for listener in self._listeners:
            try:
                await listener(target, previous, self._context)
            except Exception as exc:
                logger.error("State listener failed: %s", exc)

        # Schedule state timeout if applicable
        if self._current_state.timeout_seconds:
            self._timeout_task = asyncio.create_task(
                self._handle_state_timeout(target, self._current_state.timeout_seconds)
            )

        return True

    async def _handle_state_timeout(self, state: SystemState, duration: float) -> None:
        """Trigger fallback if the state takes longer than its timeout limit."""
        try:
            await asyncio.sleep(duration)
            if self._current_state_enum == state:
                logger.warning(
                    "State %s timed out after %.1fs. Transitioning to fallback.",
                    state.value,
                    duration,
                )
                if state in (SystemState.AWAITING_DEPOSIT, SystemState.SERVO_OPENING):
                    await self.transition_to(SystemState.LID_CLOSING)
                elif state in (SystemState.MANUAL_REVIEW, SystemState.ERROR, SystemState.CAMERA_ACTIVE):
                    await self.transition_to(SystemState.IDLE)
        except asyncio.CancelledError:
            pass

    def reset_context(self) -> None:
        """Clear detection and temporary data when returning to IDLE."""
        self._context.clear()

    def stop(self) -> None:
        """Cancel any active timeout task and clear listeners."""
        if self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()
            self._timeout_task = None

