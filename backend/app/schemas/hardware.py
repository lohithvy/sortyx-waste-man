"""
Sortyx 2.0 — Hardware configuration schemas.

Pydantic models for servo, ultrasonic sensor, and overall hardware
configuration loaded from a YAML file.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
import yaml

from pydantic import BaseModel, Field

from app.models.enums import SensorStatus, SystemState


class ServoConfig(BaseModel):
    """Configuration for a single servo channel on the PCA9685."""

    channel: int = Field(default=-1, description="PCA9685 channel (-1 = NOT_CONFIGURED)")
    open_angle: int = Field(default=90, ge=0, le=180, description="Angle when lid is open")
    close_angle: int = Field(default=0, ge=0, le=180, description="Angle when lid is closed")
    movement_speed: float = Field(
        default=0.02,
        ge=0.001,
        le=0.5,
        description="Delay in seconds between step angle increments for smooth actuation",
    )
    step_angle: int = Field(
        default=2,
        ge=1,
        le=15,
        description="Degrees per step increment during smooth lid movement",
    )
    pulse_width_min: int = Field(default=500, ge=400, le=1000, description="Minimum pulse width (µs)")
    pulse_width_max: int = Field(default=2500, ge=2000, le=3000, description="Maximum pulse width (µs)")
    max_open_duration: float = Field(
        default=30.0,
        ge=1.0,
        le=120.0,
        description="Maximum seconds the lid stays open before auto-close watchdog",
    )

    @property
    def is_configured(self) -> bool:
        return self.channel >= 0


class UltrasonicConfig(BaseModel):
    """Configuration for a single ultrasonic distance sensor (HC-SR04)."""

    trigger_pin: int = Field(default=-1, description="GPIO trigger pin (-1 = NOT_CONFIGURED)")
    echo_pin: int = Field(default=-1, description="GPIO echo pin (-1 = NOT_CONFIGURED)")
    empty_distance_cm: float = Field(
        default=30.0,
        ge=0.0,
        description="Distance reading when the bin is empty (calibrated)",
    )
    full_distance_cm: float = Field(
        default=5.0,
        ge=0.0,
        description="Distance reading when the bin is full (calibrated)",
    )
    reading_interval: float = Field(
        default=2.0,
        ge=0.5,
        le=10.0,
        description="Seconds between periodic background fill-level readings",
    )
    median_filter_size: int = Field(
        default=5,
        ge=3,
        le=15,
        description="Number of consecutive readings for moving median smoothing",
    )
    min_change_threshold_cm: float = Field(
        default=2.0,
        ge=0.5,
        le=20.0,
        description="Minimum distance change in cm to detect waste deposit",
    )
    min_valid_distance_cm: float = Field(default=2.0, ge=1.0, description="Minimum valid distance limit")
    max_valid_distance_cm: float = Field(default=400.0, le=500.0, description="Maximum valid distance limit")

    @property
    def is_configured(self) -> bool:
        return self.trigger_pin >= 0 and self.echo_pin >= 0


class BinHardwareConfig(BaseModel):
    """Combined servo + sensor config for one bin."""

    servo: ServoConfig = ServoConfig()
    ultrasonic: UltrasonicConfig = UltrasonicConfig()


class HardwareConfig(BaseModel):
    """Full hardware configuration, loaded directly from environment settings (.env).
    
    Populates PCA9685 servo channels and HC-SR04 ultrasonic sensor pins from HardwareSettings.
    """

    pca9685_address: int = Field(default=0x40, description="I2C address of PCA9685")
    pca9685_bus: int = Field(default=1, description="I2C bus number")
    pwm_frequency: int = Field(default=50, description="PWM frequency in Hz (typically 50 for analog/digital servos)")
    servo_max_open_seconds: float = Field(
        default=30.0,
        ge=1.0,
        le=120.0,
        description="Maximum time a bin lid may remain open before safety watchdog close",
    )
    bins: dict[str, BinHardwareConfig] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        """Ensure bins are populated with .env hardware connections if not explicitly provided."""
        if not self.bins:
            try:
                from app.core.config import get_settings
                settings = get_settings()
                hw = settings.hardware

                self.pca9685_address = hw.pca9685_address
                self.pca9685_bus = hw.pca9685_i2c_bus
                self.pwm_frequency = hw.servo_pwm_hz
                self.servo_max_open_seconds = hw.servo_hold_s

                mapping = [
                    ("food_waste", "organic", hw.servo_channel_1, hw.ultrasonic_trig_1, hw.ultrasonic_echo_1),
                    ("recyclable", "bio", hw.servo_channel_2, hw.ultrasonic_trig_2, hw.ultrasonic_echo_2),
                    ("non_recyclable", "non_bio", hw.servo_channel_3, hw.ultrasonic_trig_3, hw.ultrasonic_echo_3),
                ]

                for cat, alias, chan, trig, echo in mapping:
                    s_obj = ServoConfig(
                        channel=chan,
                        open_angle=hw.servo_open_deg,
                        close_angle=hw.servo_close_deg,
                        max_open_duration=hw.servo_hold_s,
                    )
                    u_obj = UltrasonicConfig(
                        trigger_pin=trig,
                        echo_pin=echo,
                    )
                    bin_hw = BinHardwareConfig(servo=s_obj, ultrasonic=u_obj)
                    self.bins[cat] = bin_hw
                    self.bins[alias] = bin_hw
            except Exception:
                pass

    @classmethod
    def from_settings(cls, settings: Optional[Any] = None) -> HardwareConfig:
        """Create HardwareConfig initialized directly from .env HardwareSettings."""
        if settings is None:
            from app.core.config import get_settings
            settings = get_settings()
        hw = settings.hardware

        cfg = cls(
            pca9685_address=hw.pca9685_address,
            pca9685_bus=hw.pca9685_i2c_bus,
            pwm_frequency=hw.servo_pwm_hz,
            servo_max_open_seconds=hw.servo_hold_s,
        )

        mapping = [
            ("food_waste", "organic", hw.servo_channel_1, hw.ultrasonic_trig_1, hw.ultrasonic_echo_1),
            ("recyclable", "bio", hw.servo_channel_2, hw.ultrasonic_trig_2, hw.ultrasonic_echo_2),
            ("non_recyclable", "non_bio", hw.servo_channel_3, hw.ultrasonic_trig_3, hw.ultrasonic_echo_3),
        ]

        for cat, alias, chan, trig, echo in mapping:
            s_obj = ServoConfig(
                channel=chan,
                open_angle=hw.servo_open_deg,
                close_angle=hw.servo_close_deg,
                max_open_duration=hw.servo_hold_s,
            )
            u_obj = UltrasonicConfig(
                trigger_pin=trig,
                echo_pin=echo,
            )
            bin_hw = BinHardwareConfig(servo=s_obj, ultrasonic=u_obj)
            cfg.bins[cat] = bin_hw
            cfg.bins[alias] = bin_hw

        return cfg

    @classmethod
    def load_from_yaml(cls, yaml_path: Optional[Path | str] = None) -> HardwareConfig:
        """Load configuration from a YAML file.

        Interprets 'NOT_CONFIGURED' values as -1 so the system starts safely.
        """
        if yaml_path is None:
            # Default search paths
            candidates = [
                Path("config/hardware.yaml"),
                Path("../config/hardware.yaml"),
                Path(__file__).resolve().parent.parent.parent.parent / "config" / "hardware.yaml",
            ]
            for c in candidates:
                if c.exists():
                    yaml_path = c
                    break

        if yaml_path is None or not Path(yaml_path).exists():
            # Return unconfigured safe defaults
            return cls()

        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            def _clean_val(v: Any) -> Any:
                if isinstance(v, str) and (v.upper() == "NOT_CONFIGURED" or v.strip() == ""):
                    return -1
                return v

            pca_data = data.get("pca9685", {})
            servos_data = data.get("servos", {})
            ultra_data = data.get("ultrasonic_sensors", {})

            cfg = cls(
                pca9685_address=int(pca_data.get("i2c_address", 0x40)),
                pca9685_bus=int(pca_data.get("i2c_bus", 1)),
                pwm_frequency=int(pca_data.get("pwm_frequency", 50)),
            )

            for category in ["bio", "organic", "non_bio"]:
                s_cfg = servos_data.get(category, {})
                u_cfg = ultra_data.get(category, {})

                servo_obj = ServoConfig(
                    channel=int(_clean_val(s_cfg.get("channel", -1))),
                    open_angle=int(_clean_val(s_cfg.get("open_angle", 90))),
                    close_angle=int(_clean_val(s_cfg.get("close_angle", 0))),
                    movement_speed=float(s_cfg.get("movement_speed", 0.02)),
                    pulse_width_min=int(s_cfg.get("pulse_width_min", 500)),
                    pulse_width_max=int(s_cfg.get("pulse_width_max", 2500)),
                    max_open_duration=float(s_cfg.get("max_open_duration", 30.0)),
                )

                ultra_obj = UltrasonicConfig(
                    trigger_pin=int(_clean_val(u_cfg.get("trigger_pin", -1))),
                    echo_pin=int(_clean_val(u_cfg.get("echo_pin", -1))),
                    empty_distance_cm=float(_clean_val(u_cfg.get("empty_distance_cm", 30.0))),
                    full_distance_cm=float(_clean_val(u_cfg.get("full_distance_cm", 5.0))),
                    reading_interval=float(u_cfg.get("reading_interval", 2.0)),
                    median_filter_size=int(u_cfg.get("median_filter_size", 5)),
                )

                cfg.bins[category] = BinHardwareConfig(servo=servo_obj, ultrasonic=ultra_obj)

            return cfg
        except Exception:
            return cls()


class SystemStatusResponse(BaseModel):
    """Snapshot of the overall system health returned by the status API."""

    state: SystemState = SystemState.IDLE
    simulation_mode: bool = True
    camera_available: bool = False
    servo_connected: bool = False
    sensor_statuses: dict[str, SensorStatus] = Field(default_factory=dict)
    gemini_quota: dict[str, Any] = Field(default_factory=dict)
    ai_provider: str = "GEMINI"
    ai_model: str = "gemini-3.8-flash"
    uptime_seconds: float = 0.0
    last_classification_at: Optional[datetime] = None
    version: str = "2.0.0"
