"""
Sortyx 2.0 — FastAPI Backend Main Application.

Entry point for the backend server running on Raspberry Pi (or laptop in simulation).
Coordinates hardware lifecycle, WebSocket broadcast, and REST endpoints.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.logging_config import setup_logging, get_logger
from app.api.routes import router as api_router
from app.api.websocket import ws_manager
from app.hardware.camera import create_camera_service
from app.hardware.pca9685 import PCA9685Controller
from app.hardware.gpio_controller import GPIOController
from app.models.enums import SystemState
from app.schemas.hardware import HardwareConfig
from app.schemas.websocket import StateUpdate, ClassificationUpdate
from app.services.classification_service import ClassificationService
from app.services.ai_factory import create_ai_service
from app.services.hand_tracking_service import HandTrackingService
from app.services.servo_service import ServoService
from app.services.sorting_service import SortingService
from app.services.supabase_service import SupabaseService
from app.services.ultrasonic_service import UltrasonicService
from app.services.weight_service import WeightService
from app.hardware.startup_validator import HardwareStartupValidator
from app.state_machine.machine import SortingStateMachine

# Initialize structured logging
setup_logging()
logger = get_logger("sortyx.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown lifecycle."""
    settings = get_settings()
    app.state.settings = settings

    logger.info("==================================================")
    logger.info("   Starting Sortyx 2.0 Backend (Simulation=%s)   ", settings.app.simulation_mode)
    logger.info("==================================================")

    # 1. Run Pre-flight Hardware Checks (Refuses startup on pin conflicts)
    validation_report = HardwareStartupValidator.run_preflight_checks(
        settings=settings,
        strict_refuse_on_conflict=True,
    )
    app.state.validation_report = validation_report
    logger.info("Hardware pre-flight check PASSED.")

    # 2. Hardware config loaded directly from .env connections
    hw_config = HardwareConfig.from_settings(settings)

    # 3. Instantiate services
    camera_svc = create_camera_service(
        source=settings.camera.source,
        device_index=settings.camera.index,
        width=settings.camera.width,
        height=settings.camera.height,
        fps=settings.camera.fps,
        auto_reconnect=settings.camera.auto_reconnect,
    )
    hand_tracker_svc = HandTrackingService(model_complexity=0)
    ai_svc = create_ai_service(settings)
    classifier_svc = ClassificationService(
        confidence_threshold=settings.app.confidence_threshold
    )
    servo_svc = ServoService(
        config=hw_config,
        simulation_mode=settings.app.simulation_mode,
    )
    ultrasonic_svc = UltrasonicService(
        config=hw_config,
        simulation_mode=settings.app.simulation_mode,
    )
    weight_svc = WeightService(
        simulation_mode=settings.app.simulation_mode,
        weight_rule_enabled=settings.hardware.weight_rule,
    )
    supabase_svc = SupabaseService(
        url=settings.supabase.url,
        secret_key=settings.supabase.secret_key,
    )
    sm = SortingStateMachine()

    # 3. Connect state machine transitions to WebSocket broadcast
    async def on_state_change(target: SystemState, previous: SystemState, context: dict) -> None:
        classification_res = context.get("classification_result")
        waste_name = ""
        category_val = None
        confidence = 0.0

        if classification_res:
            waste_name = getattr(classification_res, "waste_name", "")
            cat_obj = getattr(classification_res, "category", None)
            category_val = cat_obj.value if hasattr(cat_obj, "value") else str(cat_obj or "")
            confidence = getattr(classification_res, "confidence", 0.0)

        # 1. State update
        msg = StateUpdate(
            state=target,
            previous_state=previous,
            context={
                "waste_name": waste_name,
                "category": category_val,
                "confidence": confidence,
                "frozen_image_url": context.get("frozen_image_url"),
                "reposition_message": context.get("reposition_message"),
            },
        )
        await ws_manager.broadcast_json(msg.model_dump(mode="json"))

        # 2. Classification result update
        if classification_res and target in (SystemState.CLASSIFICATION_RESULT, SystemState.MANUAL_REVIEW):
            class_msg = ClassificationUpdate(
                waste_name=waste_name,
                category=getattr(classification_res, "category", None),
                confidence=confidence,
                reason=getattr(classification_res, "reason", ""),
                is_hazardous=getattr(classification_res, "is_hazardous", False),
                requires_manual_review=getattr(classification_res, "requires_manual_review", False),
                bin_id=getattr(classification_res.bin_id, "value", None) if hasattr(classification_res, "bin_id") and classification_res.bin_id else None,
                image_url=context.get("frozen_image_url"),
            )
            await ws_manager.broadcast_json(class_msg.model_dump(mode="json"))

    sm.add_listener(on_state_change)

    # 4. Sorting orchestrator
    sorting_svc = SortingService(
        camera=camera_svc,
        hand_tracker=hand_tracker_svc,
        ai_service=ai_svc,
        classifier=classifier_svc,
        servos=servo_svc,
        ultrasonic=ultrasonic_svc,
        supabase=supabase_svc,
        state_machine=sm,
    )

    # Save to app state
    app.state.camera_service = camera_svc
    app.state.hand_tracking_service = hand_tracker_svc
    app.state.ai_service = ai_svc
    app.state.gemini_service = ai_svc  # Backward-compatible alias
    app.state.classification_service = classifier_svc
    app.state.servo_service = servo_svc
    app.state.ultrasonic_service = ultrasonic_svc
    app.state.weight_service = weight_svc
    app.state.supabase_service = supabase_svc
    app.state.state_machine = sm
    app.state.sorting_service = sorting_svc

    # Start non-blocking sensor background polling & orchestrator
    ultrasonic_svc.start_background_polling()
    weight_svc.start_background_polling()
    await sorting_svc.start()

    logger.info("Sortyx 2.0 services successfully initialized.")

    yield

    # Shutdown (Safely returns servos to 0°, stops camera, stops sensor polling, releases GPIO)
    logger.info("Shutting down Sortyx 2.0 services...")
    ultrasonic_svc.stop_background_polling()
    weight_svc.stop_background_polling()
    await sorting_svc.stop()
    await servo_svc.close_all_bins()
    camera_svc.stop()
    servo_svc.controller.emergency_stop()
    ultrasonic_svc.gpio.cleanup()
    logger.info("Hardware resources released safely. Shutdown complete.")


app = FastAPI(
    title="Sortyx 2.0 Backend",
    description="Automated Smart Waste Segregation API for Raspberry Pi 5",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS configuration restricted to local frontend dev servers
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount REST routes
app.include_router(api_router)


# WebSocket endpoint for real-time frontend synchronization
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as exc:
        logger.debug("WebSocket error: %s", exc)
        ws_manager.disconnect(websocket)
