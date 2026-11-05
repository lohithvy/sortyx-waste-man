"""
Sortyx 2.0 — REST API Endpoints.

Provides HTTP routes for system status, bin levels, daily statistics,
manual servo testing (secured), emergency stop, and the live camera stream.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List
import cv2
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.logging_config import get_logger
from app.models.enums import BinId, SystemState
from app.schemas.events import DailyStats
from app.schemas.hardware import SystemStatusResponse
from app.hardware.diagnostics import HardwareDiagnostics, HardwareDiagnosticReport
from app.services.camera_service import enumerate_cameras

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["sortyx"])


class CameraSelectRequest(BaseModel):
    index: int = Field(..., ge=0, description="Device index to switch camera to")


@router.get("/health")
async def health_check() -> Dict[str, str]:
    """Simple health probe for monitoring."""
    return {"status": "ok", "system": "Sortyx 2.0"}


@router.get("/diagnostics", response_model=HardwareDiagnosticReport)
async def get_hardware_diagnostics() -> HardwareDiagnosticReport:
    """Run non-destructive hardware connection & compatibility diagnostics."""
    return HardwareDiagnostics.run_full_diagnostics()


@router.get("/status", response_model=SystemStatusResponse)
async def get_system_status(request: Request) -> SystemStatusResponse:
    """Return current operational snapshot of the Sortyx system."""
    app_state = request.app.state
    sm = getattr(app_state, "state_machine", None)
    current_state = sm.current_state if sm else SystemState.IDLE

    ultrasonic = getattr(app_state, "ultrasonic_service", None)
    sensor_statuses = ultrasonic.sensor_statuses if ultrasonic else {}

    camera = getattr(app_state, "camera_service", None)
    camera_ok = camera.is_available() if camera else False

    servos = getattr(app_state, "servo_service", None)
    servo_ok = not getattr(app_state.settings.app, "simulation_mode", True)

    ai_svc = getattr(app_state, "ai_service", None)
    gemini_quota = ai_svc.quota_status if ai_svc else {}
    provider_name = getattr(ai_svc, "provider_name", "CLOUD_RUN") if ai_svc else "CLOUD_RUN"
    model_name = getattr(ai_svc, "model_name", "sortyx-cloud-run") if ai_svc else "sortyx-cloud-run"

    return SystemStatusResponse(
        state=current_state,
        simulation_mode=getattr(app_state.settings.app, "simulation_mode", True),
        camera_available=camera_ok,
        servo_connected=servo_ok,
        sensor_statuses=sensor_statuses,
        gemini_quota=gemini_quota,
        ai_provider=provider_name,
        ai_model=model_name,
        version="2.0.0",
    )


@router.get("/camera/devices")
async def get_camera_devices(request: Request) -> List[Dict[str, Any]]:
    """Return all detected video capture devices and whether external/active."""
    camera = getattr(request.app.state, "camera_service", None)
    active_idx = getattr(camera, "_index", 0) if camera else 0
    return enumerate_cameras(active_index=active_idx)


@router.post("/camera/select")
async def select_camera_device(payload: CameraSelectRequest, request: Request) -> Dict[str, Any]:
    """Switch active camera device to specified index at runtime."""
    camera = getattr(request.app.state, "camera_service", None)
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Camera service not available",
        )

    if hasattr(camera, "switch_camera"):
        success = camera.switch_camera(payload.index)
        status_info = camera.get_status() if hasattr(camera, "get_status") else {}
        return {
            "status": "ok" if success else "failed",
            "index": payload.index,
            "connected": success,
            "camera_status": status_info,
        }
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Active camera backend does not support dynamic device switching",
    )


@router.post("/camera/reconnect")
async def reconnect_camera_device(request: Request) -> Dict[str, Any]:
    """Manually trigger camera reconnection."""
    camera = getattr(request.app.state, "camera_service", None)
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Camera service not available",
        )

    if hasattr(camera, "reconnect"):
        success = camera.reconnect()
        return {"status": "ok" if success else "failed", "connected": success}
    return {"status": "ok", "connected": camera.is_available()}


@router.get("/camera/status")
async def get_camera_status(request: Request) -> Dict[str, Any]:
    """Return current camera hardware and connection status."""
    camera = getattr(request.app.state, "camera_service", None)
    if not camera:
        return {"is_connected": False, "index": -1, "device_name": "None"}
    if hasattr(camera, "get_status"):
        return camera.get_status()
    return {
        "is_connected": camera.is_available(),
        "index": 0,
        "device_name": "Standard Camera",
    }


@router.get("/camera/stream")
async def camera_stream(request: Request) -> StreamingResponse:
    """Stream live camera feed (MJPEG) with hand tracking overlay.

    Frames are strictly temporary in memory and are never saved to disk.
    Stream continues uninterrupted during AI classification without freezing.
    """
    camera = getattr(request.app.state, "camera_service", None)
    tracker = getattr(request.app.state, "hand_tracking_service", None)

    async def frame_generator():
        while True:
            if not camera or not camera.is_available():
                await asyncio.sleep(0.08)
                continue

            frame = camera.read_frame()
            if frame is None:
                await asyncio.sleep(0.033)
                continue

            # Annotate with hand landmarks if available (in memory only)
            annotated = tracker.annotate_frame(frame) if tracker else frame

            # Encode to JPEG in memory
            ret, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if ret:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"
                )
            await asyncio.sleep(0.033)  # ~30 FPS

    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/camera/captured")
async def get_captured_frame(request: Request) -> Response:
    """Return the currently frozen in-memory JPEG frame."""
    sorting = getattr(request.app.state, "sorting_service", None)
    if sorting and sorting.frozen_frame_bytes:
        return Response(content=sorting.frozen_frame_bytes, media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="No captured frame available")


@router.get("/bins")
async def get_bins(request: Request) -> List[Dict[str, Any]]:
    """Return real-time fill level and sensor status for each bin."""
    supabase = getattr(request.app.state, "supabase_service", None)
    if supabase:
        return await supabase.get_bin_statuses()

    return [
        {"id": "organic", "category": "organic", "displayName": "Organic", "fillPercentage": 0, "sensorStatus": "not_configured"},
        {"id": "bio", "category": "bio", "displayName": "Bio", "fillPercentage": 0, "sensorStatus": "not_configured"},
        {"id": "non_bio", "category": "non_bio", "displayName": "Non-Bio", "fillPercentage": 0, "sensorStatus": "not_configured"},
    ]


@router.get("/stats/today", response_model=DailyStats)
async def get_today_stats(request: Request) -> DailyStats:
    """Return count of items segregated today (IST calendar day)."""
    supabase = getattr(request.app.state, "supabase_service", None)
    if supabase:
        return await supabase.get_today_stats()
    return DailyStats()


@router.post("/servo/{bin_id}/open")
async def open_bin(bin_id: str, request: Request) -> Dict[str, Any]:
    """Manually command a servo to open (for testing / calibration)."""
    try:
        bin_enum = BinId(bin_id.lower())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid bin '{bin_id}'. Must be bio, organic, or non_bio.",
        )

    servos = getattr(request.app.state, "servo_service", None)
    if not servos:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Servo service not initialized.")

    success = await servos.open_bin(bin_enum)
    return {"bin": bin_id, "opened": success}


@router.post("/servo/{bin_id}/close")
async def close_bin(bin_id: str, request: Request) -> Dict[str, Any]:
    """Manually command a servo to close."""
    try:
        bin_enum = BinId(bin_id.lower())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid bin '{bin_id}'. Must be bio, organic, or non_bio.",
        )

    servos = getattr(request.app.state, "servo_service", None)
    if not servos:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Servo service not initialized.")

    success = await servos.close_bin(bin_enum)
    return {"bin": bin_id, "closed": success}


@router.post("/emergency-stop")
async def emergency_stop(request: Request) -> Dict[str, str]:
    """Safety override: Immediately close all bin lids and abort ongoing movements."""
    servos = getattr(request.app.state, "servo_service", None)
    if servos:
        await servos.close_all_bins()

    sm = getattr(request.app.state, "state_machine", None)
    if sm:
        await sm.transition_to(SystemState.IDLE)

    logger.warning("Emergency stop triggered via REST API.")
    return {"status": "emergency_stop_executed", "message": "All bins closed."}


# ---------------------------------------------------------------------------
# Hardware Preflight & Weight Monitoring Endpoints
# ---------------------------------------------------------------------------


class WeightCalibrateRequest(BaseModel):
    known_weight_g: float = Field(..., gt=0.0, description="Reference mass in grams placed on load cell")


@router.get("/hardware/validation")
async def get_hardware_validation(request: Request) -> Dict[str, Any]:
    """Return pre-flight 10-step hardware validation and pin assignment status."""
    from app.hardware.startup_validator import HardwareStartupValidator

    settings = getattr(request.app.state, "settings", None)
    report = HardwareStartupValidator.run_preflight_checks(
        settings=settings,
        strict_refuse_on_conflict=False,
    )
    return report.model_dump(mode="json")


@router.get("/hardware/weight/status")
async def get_weight_status(request: Request) -> Dict[str, Any]:
    """Return live status and weights for all HX711 load cells."""
    weight_svc = getattr(request.app.state, "weight_service", None)
    if not weight_svc:
        raise HTTPException(status_code=503, detail="Weight service not initialized")
    return weight_svc.get_all_weights_summary()


@router.post("/hardware/weight/{bin_id}/tare")
async def tare_load_cell(bin_id: str, request: Request) -> Dict[str, Any]:
    """Trigger zero-offset tare calibration for specified bin's HX711 load cell."""
    try:
        bin_enum = BinId(bin_id.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid bin '{bin_id}'.")

    weight_svc = getattr(request.app.state, "weight_service", None)
    if not weight_svc:
        raise HTTPException(status_code=503, detail="Weight service not initialized")

    offset = await weight_svc.tare_bin(bin_enum)
    return {
        "bin": bin_id,
        "tare_offset": offset,
        "success": offset is not None,
    }


@router.post("/hardware/weight/{bin_id}/calibrate")
async def calibrate_load_cell(
    bin_id: str,
    payload: WeightCalibrateRequest,
    request: Request,
) -> Dict[str, Any]:
    """Calculate and store scale factor given a known reference mass placed on load cell."""
    try:
        bin_enum = BinId(bin_id.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid bin '{bin_id}'.")

    weight_svc = getattr(request.app.state, "weight_service", None)
    if not weight_svc:
        raise HTTPException(status_code=503, detail="Weight service not initialized")

    scale = await weight_svc.calibrate_bin(bin_enum, payload.known_weight_g)
    return {
        "bin": bin_id,
        "scale_factor": scale,
        "known_weight_g": payload.known_weight_g,
        "success": scale is not None,
    }
