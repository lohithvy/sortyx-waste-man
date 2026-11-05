"""
Sortyx 2.0 — State Machine & Workflow Unit Tests.
"""

from __future__ import annotations

import pytest

from app.models.enums import SystemState
from app.state_machine.machine import SortingStateMachine


@pytest.mark.asyncio
async def test_state_machine_initial_state(state_machine: SortingStateMachine) -> None:
    assert state_machine.current_state == SystemState.IDLE


@pytest.mark.asyncio
async def test_valid_sorting_lifecycle(state_machine: SortingStateMachine) -> None:
    # 1. IDLE -> PERSON_DETECTED
    assert await state_machine.transition_to(SystemState.PERSON_DETECTED)
    assert state_machine.current_state == SystemState.PERSON_DETECTED

    # 2. PERSON_DETECTED -> CAMERA_ACTIVE
    assert await state_machine.transition_to(SystemState.CAMERA_ACTIVE)
    assert state_machine.current_state == SystemState.CAMERA_ACTIVE

    # 3. CAMERA_ACTIVE -> IMAGE_CAPTURE
    assert await state_machine.transition_to(SystemState.IMAGE_CAPTURE)
    assert state_machine.current_state == SystemState.IMAGE_CAPTURE

    # 4. IMAGE_CAPTURE -> CLASSIFYING
    assert await state_machine.transition_to(SystemState.CLASSIFYING)
    assert state_machine.current_state == SystemState.CLASSIFYING

    # 5. CLASSIFYING -> CLASSIFICATION_RESULT
    assert await state_machine.transition_to(SystemState.CLASSIFICATION_RESULT)
    assert state_machine.current_state == SystemState.CLASSIFICATION_RESULT

    # 6. CLASSIFICATION_RESULT -> SERVO_OPENING
    assert await state_machine.transition_to(SystemState.SERVO_OPENING)
    assert state_machine.current_state == SystemState.SERVO_OPENING

    # 7. SERVO_OPENING -> AWAITING_DEPOSIT
    assert await state_machine.transition_to(SystemState.AWAITING_DEPOSIT)
    assert state_machine.current_state == SystemState.AWAITING_DEPOSIT

    # 8. AWAITING_DEPOSIT -> LID_CLOSING
    assert await state_machine.transition_to(SystemState.LID_CLOSING)
    assert state_machine.current_state == SystemState.LID_CLOSING

    # 9. LID_CLOSING -> IDLE
    assert await state_machine.transition_to(SystemState.IDLE)
    assert state_machine.current_state == SystemState.IDLE


@pytest.mark.asyncio
async def test_invalid_transition_rejected(state_machine: SortingStateMachine) -> None:
    assert state_machine.current_state == SystemState.IDLE
    # IDLE cannot directly jump to SERVO_OPENING without detection and classification
    rejected = await state_machine.transition_to(SystemState.SERVO_OPENING)
    assert rejected is False
    assert state_machine.current_state == SystemState.IDLE


@pytest.mark.asyncio
async def test_emergency_transition_to_error(state_machine: SortingStateMachine) -> None:
    await state_machine.transition_to(SystemState.CAMERA_ACTIVE)
    # Emergency transition to ERROR is always allowed
    assert await state_machine.transition_to(SystemState.ERROR)
    assert state_machine.current_state == SystemState.ERROR
    # From ERROR can only recover to IDLE
    assert await state_machine.transition_to(SystemState.IDLE)
    assert state_machine.current_state == SystemState.IDLE


@pytest.mark.asyncio
async def test_manual_review_path(state_machine: SortingStateMachine) -> None:
    await state_machine.transition_to(SystemState.CAMERA_ACTIVE)
    await state_machine.transition_to(SystemState.IMAGE_CAPTURE)
    await state_machine.transition_to(SystemState.CLASSIFYING)

    # Classifying -> MANUAL_REVIEW
    assert await state_machine.transition_to(SystemState.MANUAL_REVIEW)
    assert state_machine.current_state == SystemState.MANUAL_REVIEW

    # MANUAL_REVIEW -> IDLE
    assert await state_machine.transition_to(SystemState.IDLE)
    assert state_machine.current_state == SystemState.IDLE


@pytest.mark.asyncio
async def test_state_listener_called(state_machine: SortingStateMachine) -> None:
    events = []

    async def listener(target, previous, context):
        events.append((previous, target))

    state_machine.add_listener(listener)
    await state_machine.transition_to(SystemState.CAMERA_ACTIVE)

    assert len(events) == 1
    assert events[0] == (SystemState.IDLE, SystemState.CAMERA_ACTIVE)

