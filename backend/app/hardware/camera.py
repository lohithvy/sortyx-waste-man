"""
Sortyx 2.0 — Camera Hardware Factory and Abstraction.

Factory function that returns the configured camera implementation
(OpenCV VideoCapture for USB webcam or PiCamera2 for Raspberry Pi CSI camera).
Both implementations provide identical grab/read interfaces yielding in-memory frames.
"""

from __future__ import annotations

from typing import Union
from app.core.logging_config import get_logger
from app.models.enums import CameraSource
from app.services.camera_service import CameraService, get_camera_service

logger = get_logger(__name__)


def create_camera_service(
    source: Union[CameraSource, str] = CameraSource.WEBCAM,
    device_index: int = 0,
    width: int = 1280,
    height: int = 720,
    fps: int = 30,
    auto_reconnect: bool = True,
) -> CameraService:
    """Instantiate and return the appropriate camera service based on configuration."""
    source_str = source.value if isinstance(source, CameraSource) else str(source)
    return get_camera_service(
        source=source_str,
        camera_index=device_index,
        width=width,
        height=height,
        fps=fps,
        auto_reconnect=auto_reconnect,
    )
