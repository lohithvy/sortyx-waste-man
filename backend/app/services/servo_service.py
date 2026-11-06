"""
Sortyx 2.0 — Servo Motor Control Service.

Coordinates lid opening and closing across the three bins (bio, organic, non_bio).
Enforces critical safety rules:
1. Never activate unconfigured channels (-1).
2. Never open multiple bins simultaneously.
3. Automatically schedule lid close after timeout (default 30s).
4. Provide emergency stop to immediately close all lids.
5. In simulation mode, log clearly without hardware calls.
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional, Dict

from app.core.logging_config import get_logger
from app.core.exceptions import ServoError
from app.models.enums import BinId
from app.schemas.hardware import HardwareConfig, ServoConfig
from app.hardware.pca9685 import PCA9685Controller

logger = get_logger(__name__)


class ServoService:
    """High-level servo control service for Sortyx 2.0."""

    def __init__(
        self,
        config: HardwareConfig,
        controller: Optional[PCA9685Controller] = None,
        simulation_mode: bool = True,
    ) -> None:
        self.config = config
        self.simulation_mode = simulation_mode
        self.controller = controller or PCA9685Controller(
            i2c_address=config.pca9685_address,
            i2c_bus=config.pca9685_bus,
            simulation_mode=simulation_mode,
        )

        self._active_bin: Optional[BinId] = None
        self._open_since: Optional[float] = None
        self._auto_close_task: Optional[asyncio.Task] = None

    def _get_bin_config(self, bin_id: BinId) -> ServoConfig:
        """Retrieve servo configuration for given bin."""
        key = bin_id.value
        if key in self.config.bins and self.config.bins[key].servo.is_configured:
            return self.config.bins[key].servo
        alias_map = {
            BinId.FOOD_WASTE: "organic",
            BinId.RECYCLABLE: "bio",
            BinId.NON_RECYCLABLE: "non_bio",
        }
        alias = alias_map.get(bin_id)
        if alias and alias in self.config.bins and self.config.bins[alias].servo.is_configured:
            return self.config.bins[alias].servo
        if key in self.config.bins:
            return self.config.bins[key].servo
        return ServoConfig()

    def is_configured(self, bin_id: BinId) -> bool:
        """Check if servo channel for bin is configured (channel >= 0)."""
        cfg = self._get_bin_config(bin_id)
        return cfg.is_configured

    async def open_bin(self, bin_id: BinId, timeout_seconds: Optional[float] = None) -> bool:
        """Open the lid for the specified bin.

        Safety: Closes any currently open bin first. Never allows multiple bins open.
        """
        cfg = self._get_bin_config(bin_id)

        if not cfg.is_configured and not self.simulation_mode:
            logger.warning(
                "Cannot open bin '%s': Servo channel is NOT_CONFIGURED.",
                bin_id.value,
            )
            return False

        # Close any other open bin first
        if self._active_bin and self._active_bin != bin_id:
            logger.info("Closing currently active bin '%s' before opening '%s'", self._active_bin.value, bin_id.value)
            await self.close_bin(self._active_bin)

        max_duration = timeout_seconds or cfg.max_open_duration or self.config.servo_max_open_seconds

        logger.info(
            "Opening lid for '%s' bin (channel=%d, angle=%d°, timeout=%.1fs, smooth=True)",
            bin_id.value,
            cfg.channel,
            cfg.open_angle,
            max_duration,
        )

        success = await self.controller.move_smooth(
            channel=cfg.channel,
            start_angle=cfg.close_angle,
            target_angle=cfg.open_angle,
            step_deg=cfg.step_angle,
            step_delay_s=cfg.movement_speed,
            pulse_min=cfg.pulse_width_min,
            pulse_max=cfg.pulse_width_max,
        )
        if success or self.simulation_mode:
            self._active_bin = bin_id
            self._open_since = time.time()

            # Schedule safety auto-close
            if self._auto_close_task and not self._auto_close_task.done():
                self._auto_close_task.cancel()

            self._auto_close_task = asyncio.create_task(
                self._schedule_auto_close(bin_id, max_duration)
            )
            return True

        return False

    async def close_bin(self, bin_id: BinId) -> bool:
        """Close the lid for the specified bin using smooth actuation."""
        cfg = self._get_bin_config(bin_id)

        if not cfg.is_configured and not self.simulation_mode:
            logger.warning("Cannot close bin '%s': Servo channel is NOT_CONFIGURED.", bin_id.value)
            return False

        logger.info(
            "Closing lid for '%s' bin (channel=%d, angle=%d°, smooth=True)",
            bin_id.value,
            cfg.channel,
            cfg.close_angle,
        )

        success = await self.controller.move_smooth(
            channel=cfg.channel,
            start_angle=cfg.open_angle,
            target_angle=cfg.close_angle,
            step_deg=cfg.step_angle,
            step_delay_s=cfg.movement_speed,
            pulse_min=cfg.pulse_width_min,
            pulse_max=cfg.pulse_width_max,
        )

        # Release PWM signal to eliminate idle holding current and servo buzz
        self.controller.disable_channel(cfg.channel)

        if self._active_bin == bin_id:
            self._active_bin = None
            self._open_since = None

        if self._auto_close_task and not self._auto_close_task.done():
            self._auto_close_task.cancel()

        return success or self.simulation_mode

    async def close_all_bins(self) -> None:
        """Emergency stop: Immediately close all three bin lids."""
        logger.warning("EMERGENCY STOP: Closing all bin lids immediately.")
        for b in BinId:
            try:
                cfg = self._get_bin_config(b)
                if cfg.is_configured or self.simulation_mode:
                    self.controller.set_servo_angle(cfg.channel, cfg.close_angle)
            except Exception as exc:
                logger.error("Error closing bin '%s' during emergency stop: %s", b.value, exc)

        self._active_bin = None
        self._open_since = None
        if self._auto_close_task and not self._auto_close_task.done():
            self._auto_close_task.cancel()

    async def _schedule_auto_close(self, bin_id: BinId, duration: float) -> None:
        """Safety timeout task: automatically closes lid if not closed in time."""
        try:
            await asyncio.sleep(duration)
            if self._active_bin == bin_id:
                logger.warning(
                    "Safety timeout (%.1fs) expired for bin '%s'. Auto-closing lid.",
                    duration,
                    bin_id.value,
                )
                await self.close_bin(bin_id)
        except asyncio.CancelledError:
            pass

    @property
    def active_bin(self) -> Optional[BinId]:
        """Currently open bin, if any."""
        return self._active_bin

    def is_bin_open(self, bin_id: BinId) -> bool:
        """Return True if specified bin is currently open."""
        return self._active_bin == bin_id

    def is_any_bin_open(self) -> bool:
        """Return True if any bin is currently open."""
        return self._active_bin is not None

