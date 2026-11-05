"""
Sortyx 2.0 — Environment and Application Configuration.

Loads configuration from backend/.env using pydantic-settings.
Provides typed access to Gemini, Supabase, camera, device, and app settings.
Resolves backend/.env accurately regardless of current working directory.
"""

from __future__ import annotations

import os
from pathlib import Path
from enum import Enum
from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Locate backend/.env reliably relative to this file
_CORE_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _CORE_DIR.parent.parent
ENV_FILE = _BACKEND_DIR / ".env"


class CameraSource(str, Enum):
    WEBCAM = "WEBCAM"
    RASPBERRY_PI = "RASPBERRY_PI"


class AIProvider(str, Enum):
    CLOUD_RUN = "CLOUD_RUN"


class _SortyxBase(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


class CloudRunSettings(_SortyxBase):
    """Sortyx Cloud Run Classification API configuration.

    Connects to the existing Sortyx Cloud Run service:
    https://sortyx-classify-5bwsw4lr6q-uc.a.run.app/api/classify
    """

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        env_prefix="CLOUD_RUN_",
        extra="ignore",
    )

    endpoint: str = "https://sortyx-classify-5bwsw4lr6q-uc.a.run.app/api/classify"
    timeout: float = 15.0


class SupabaseSettings(_SortyxBase):
    """Supabase project configuration."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        env_prefix="SUPABASE_",
        extra="ignore",
    )

    url: str = ""
    secret_key: str = ""


class DeviceSettings(_SortyxBase):
    """Device authentication configuration."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        env_prefix="DEVICE_",
        extra="ignore",
    )

    api_secret: str = ""


class CameraSettings(_SortyxBase):
    """Camera hardware configuration."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        env_prefix="CAMERA_",
        extra="ignore",
    )

    type: str = "USB_WEBCAM"
    source: CameraSource = CameraSource.WEBCAM
    index: int = 0
    alt_indices: str = "1,2"
    backend: str = "v4l2"
    width: int = 1280
    height: int = 720
    fps: int = 30
    auto_reconnect: bool = True


class HardwareSettings(_SortyxBase):
    """Raspberry Pi hardware pins and driver configuration."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gpio_numbering: str = "BCM"

    # Ultrasonic Sensor Pins (BCM)
    ultrasonic_trig_1: int = 17
    ultrasonic_echo_1: int = 24

    ultrasonic_trig_2: int = 22
    ultrasonic_echo_2: int = 27

    ultrasonic_trig_3: int = 23
    ultrasonic_echo_3: int = 6

    ultrasonic_samples: int = 1
    ultrasonic_timeout_s: float = 0.1
    sensor_read_interval_s: float = 10.0

    # HX711 Load Cell Pins (BCM)
    hx711_dt_1: int = 5
    hx711_sck_1: int = 11

    hx711_dt_2: int = 13
    hx711_sck_2: int = 19

    hx711_dt_3: int = 26
    hx711_sck_3: int = 21

    # Calibration offsets (empty by default)
    hx711_tare_1: Optional[float] = None
    hx711_tare_2: Optional[float] = None
    hx711_tare_3: Optional[float] = None

    hx711_scale_1: Optional[float] = None
    hx711_scale_2: Optional[float] = None
    hx711_scale_3: Optional[float] = None

    weight_rule: bool = False

    # PCA9685 I2C Servo Controller
    pca9685_i2c_bus: int = 1
    pca9685_address: int = 0x40
    servo_pwm_hz: int = 50

    servo_open_deg: int = 50
    servo_close_deg: int = 0

    servo_hold_s: float = 3.0
    servo_settle_s: float = 0.5

    servo_range_deg: int = 180

    servo_channel_1: int = 0
    servo_channel_2: int = 1
    servo_channel_3: int = 2

    # Servo pulse width range (defaults to None to use driver defaults unless configured)
    servo_pulse_min_us: Optional[int] = None
    servo_pulse_max_us: Optional[int] = None

    @field_validator(
        "hx711_tare_1", "hx711_tare_2", "hx711_tare_3",
        "hx711_scale_1", "hx711_scale_2", "hx711_scale_3",
        mode="before",
    )
    @classmethod
    def _parse_optional_float(cls, v: object) -> Optional[float]:
        if v is None or v == "" or (isinstance(v, str) and not v.strip()):
            return None
        return float(v)

    @field_validator("pca9685_address", mode="before")
    @classmethod
    def _parse_address(cls, v: object) -> int:
        if isinstance(v, str):
            v_str = v.strip()
            if v_str.lower().startswith("0x"):
                return int(v_str, 16)
            return int(v_str)
        return int(v)


class AppSettings(_SortyxBase):
    """Application behavior and safety parameters."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    log_level: str = "INFO"
    simulation_mode: bool = True
    confidence_threshold: float = 0.75
    ai_provider: AIProvider = AIProvider.CLOUD_RUN

    @field_validator("confidence_threshold", mode="after")
    @classmethod
    def _validate_threshold(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("confidence_threshold must be between 0.0 and 1.0")
        return v


class Settings(BaseSettings):
    """Root composed settings for Sortyx 2.0."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    cloud_run: CloudRunSettings = Field(default_factory=CloudRunSettings)
    supabase: SupabaseSettings = Field(default_factory=SupabaseSettings)
    camera: CameraSettings = Field(default_factory=CameraSettings)
    hardware: HardwareSettings = Field(default_factory=HardwareSettings)
    device: DeviceSettings = Field(default_factory=DeviceSettings)
    app: AppSettings = Field(default_factory=AppSettings)


@lru_cache()
def get_settings() -> Settings:
    """Return cached Settings singleton."""
    return Settings()
