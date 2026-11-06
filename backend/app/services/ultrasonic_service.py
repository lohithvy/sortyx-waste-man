"""
Sortyx 2.0 — Ultrasonic Bin Fill & Deposit Monitoring Service.

Manages independent HC-SR04 ultrasonic distance sensors across all three bins:
  - Bin 1 (Organic): TRIG=GPIO 17, ECHO=GPIO 24
  - Bin 2 (Bio):     TRIG=GPIO 22, ECHO=GPIO 27
  - Bin 3 (Non-Bio): TRIG=GPIO 23, ECHO=GPIO 6

Key architectural guarantees:
1. Independent per-bin reading and state tracking.
2. Async background polling (default every 10s via asyncio.to_thread) to never block camera or state machine.
3. Strict simulation / failure integrity: distances are real or None (NEVER fabricated).
4. Status reporting: ONLINE, OFFLINE, NOT_CONFIGURED, SIMULATION, ERROR.
5. Median filtering for noise rejection.
"""

from __future__ import annotations

import asyncio
import statistics
import time
from typing import Dict, List, Optional, Tuple

from app.core.config import get_settings
from app.core.logging_config import get_logger
from app.models.enums import BinId, SensorStatus
from app.schemas.hardware import HardwareConfig, UltrasonicConfig
from app.hardware.gpio_controller import GPIOController

logger = get_logger(__name__)


class UltrasonicService:
    """Monitors ultrasonic distance sensors and calculates fill levels."""

    def __init__(
        self,
        config: Optional[HardwareConfig] = None,
        gpio_controller: Optional[GPIOController] = None,
        simulation_mode: bool = True,
        filter_size: int = 5,
        read_interval_s: Optional[float] = None,
        timeout_s: Optional[float] = None,
    ) -> None:
        settings = get_settings()
        self.simulation_mode = simulation_mode
        self.filter_size = filter_size
        self.gpio = gpio_controller or GPIOController(simulation_mode=simulation_mode)
        self.read_interval_s = read_interval_s or settings.hardware.sensor_read_interval_s
        self.timeout_s = timeout_s or settings.hardware.ultrasonic_timeout_s

        if config is None:
            self.config = HardwareConfig()
            self._sync_pins_from_settings(settings)
        else:
            self.config = config

        # Moving window of readings per bin
        self._history: Dict[BinId, List[float]] = {
            BinId.FOOD_WASTE: [],
            BinId.RECYCLABLE: [],
            BinId.NON_RECYCLABLE: [],
        }

        # Latest validated distance per bin
        self._latest_distances: Dict[BinId, Optional[float]] = {
            BinId.FOOD_WASTE: None,
            BinId.RECYCLABLE: None,
            BinId.NON_RECYCLABLE: None,
        }

        # Sensor status tracking
        self._sensor_statuses: Dict[BinId, SensorStatus] = {}
        self._bg_task: Optional[asyncio.Task] = None
        self._running = False

        self._init_sensors()

    def _sync_pins_from_settings(self, settings) -> None:
        """Ensure pin assignments match confirmed HardwareSettings."""
        pin_mappings = {
            BinId.FOOD_WASTE: (settings.hardware.ultrasonic_trig_1, settings.hardware.ultrasonic_echo_1),
            BinId.RECYCLABLE: (settings.hardware.ultrasonic_trig_2, settings.hardware.ultrasonic_echo_2),
            BinId.NON_RECYCLABLE: (settings.hardware.ultrasonic_trig_3, settings.hardware.ultrasonic_echo_3),
        }
        for b, (trig, echo) in pin_mappings.items():
            key = b.value
            if key not in self.config.bins:
                continue
            u_cfg = self.config.bins[key].ultrasonic
            if not u_cfg.is_configured:
                u_cfg.trigger_pin = trig
                u_cfg.echo_pin = echo

    def _get_bin_config(self, bin_id: BinId) -> UltrasonicConfig:
        key = bin_id.value
        if key in self.config.bins and self.config.bins[key].ultrasonic.is_configured:
            return self.config.bins[key].ultrasonic
        alias_map = {
            BinId.FOOD_WASTE: "organic",
            BinId.RECYCLABLE: "bio",
            BinId.NON_RECYCLABLE: "non_bio",
        }
        alias = alias_map.get(bin_id)
        if alias and alias in self.config.bins and self.config.bins[alias].ultrasonic.is_configured:
            return self.config.bins[alias].ultrasonic
        if key in self.config.bins:
            return self.config.bins[key].ultrasonic
        return UltrasonicConfig()

    def _init_sensors(self) -> None:
        """Initialize GPIO pin modes for configured sensors."""
        for b in BinId:
            cfg = self._get_bin_config(b)
            if not cfg.is_configured:
                self._sensor_statuses[b] = SensorStatus.NOT_CONFIGURED
                logger.info("Ultrasonic sensor for bin '%s' is NOT_CONFIGURED.", b.value)
            elif self.simulation_mode:
                self._sensor_statuses[b] = SensorStatus.SIMULATION
            else:
                success = self.gpio.setup_pins(cfg.trigger_pin, cfg.echo_pin)
                self._sensor_statuses[b] = SensorStatus.ONLINE if success else SensorStatus.ERROR

    def read_distance(self, bin_id: BinId) -> Optional[float]:
        """Synchronously take or retrieve filtered reading.

        Returns None if sensor is in simulation mode or unavailable.
        Never fabricates distances.
        """
        cfg = self._get_bin_config(bin_id)

        if not cfg.is_configured:
            self._sensor_statuses[bin_id] = SensorStatus.NOT_CONFIGURED
            return None

        if self.simulation_mode:
            self._sensor_statuses[bin_id] = SensorStatus.SIMULATION
            return None

        raw = self.gpio.read_distance_cm(cfg.trigger_pin, cfg.echo_pin, timeout_s=self.timeout_s)
        if raw is None:
            self._sensor_statuses[bin_id] = SensorStatus.OFFLINE
            return self._latest_distances[bin_id]

        # Valid reading acquired
        self._sensor_statuses[bin_id] = SensorStatus.ONLINE
        history = self._history[bin_id]
        history.append(raw)
        if len(history) > self.filter_size:
            history.pop(0)

        filtered = statistics.median(history)
        self._latest_distances[bin_id] = round(filtered, 2)
        return self._latest_distances[bin_id]

    async def read_distance_async(self, bin_id: BinId) -> Optional[float]:
        """Perform distance measurement off-thread to avoid event loop blocking."""
        return await asyncio.to_thread(self.read_distance, bin_id)

    def calculate_fill_percentage(self, bin_id: BinId, distance_cm: Optional[float]) -> float:
        """Calculate bin fill level (0.0 to 100.0%) from ultrasonic distance.

        empty_distance_cm: distance from sensor to empty bottom
        full_distance_cm: distance from sensor to full level near the top
        """
        if distance_cm is None:
            return 0.0

        cfg = self._get_bin_config(bin_id)
        empty = cfg.empty_distance_cm
        full = cfg.full_distance_cm

        if empty <= full:
            return 0.0

        dist = max(full, min(empty, distance_cm))
        percentage = ((empty - dist) / (empty - full)) * 100.0
        return round(max(0.0, min(100.0, percentage)), 1)

    def get_bin_fill_status(self, bin_id: BinId) -> Tuple[float, Optional[float], SensorStatus]:
        """Return (fill_percentage, distance_cm, sensor_status) for given bin."""
        status = self._sensor_statuses.get(bin_id, SensorStatus.NOT_CONFIGURED)
        dist = self._latest_distances.get(bin_id)
        fill_pct = self.calculate_fill_percentage(bin_id, dist)
        return fill_pct, dist, status

    def get_sensor_status(self, bin_id: BinId) -> SensorStatus:
        """Return SensorStatus for given bin."""
        return self._sensor_statuses.get(bin_id, SensorStatus.NOT_CONFIGURED)

    def attempt_deposit_confirmation(
        self,
        bin_id: BinId,
        baseline_distance: Optional[float],
        min_change_cm: float = 2.0,
    ) -> Tuple[bool, str]:
        """Evaluate if an item drop was detected based on fill level change."""
        cfg = self._get_bin_config(bin_id)
        if not cfg.is_configured:
            return False, "Sensors not configured for drop confirmation."

        current = self.read_distance(bin_id)
        if baseline_distance is None or current is None:
            return False, "Insufficient sensor readings to confirm deposit."

        threshold = cfg.min_change_threshold_cm or min_change_cm
        if (baseline_distance - current) >= threshold:
            return True, f"Distance decreased by {baseline_distance - current:.1f}cm (deposit confirmed)."

        return False, "No measurable level change detected."

    def calibrate_empty(self, bin_id: BinId, samples: int = 10) -> Optional[float]:
        """Collect multiple sensor readings of an empty bin and calculate median empty distance."""
        cfg = self._get_bin_config(bin_id)
        if not cfg.is_configured or self.simulation_mode:
            logger.warning(
                "Cannot calibrate empty distance for '%s': sensor unconfigured or in simulation.",
                bin_id.value,
            )
            return None

        readings = []
        for _ in range(samples):
            dist = self.gpio.read_distance_cm(cfg.trigger_pin, cfg.echo_pin, timeout_s=self.timeout_s)
            if dist is not None and cfg.min_valid_distance_cm <= dist <= cfg.max_valid_distance_cm:
                readings.append(dist)
            time.sleep(0.06)

        if not readings:
            logger.error("Calibration failed for '%s': zero valid distance readings.", bin_id.value)
            return None

        median_dist = round(statistics.median(readings), 2)
        cfg.empty_distance_cm = median_dist
        logger.info(
            "Calibrated '%s' empty distance to %.2f cm (from %d samples).",
            bin_id.value,
            median_dist,
            len(readings),
        )
        return median_dist

    def calibrate_full(self, bin_id: BinId, samples: int = 10) -> Optional[float]:
        """Collect multiple sensor readings of a full bin and calculate median full distance."""
        cfg = self._get_bin_config(bin_id)
        if not cfg.is_configured or self.simulation_mode:
            logger.warning(
                "Cannot calibrate full distance for '%s': sensor unconfigured or in simulation.",
                bin_id.value,
            )
            return None

        readings = []
        for _ in range(samples):
            dist = self.gpio.read_distance_cm(cfg.trigger_pin, cfg.echo_pin, timeout_s=self.timeout_s)
            if dist is not None and cfg.min_valid_distance_cm <= dist <= cfg.max_valid_distance_cm:
                readings.append(dist)
            time.sleep(0.06)

        if not readings:
            logger.error("Calibration failed for '%s': zero valid distance readings.", bin_id.value)
            return None

        median_dist = round(statistics.median(readings), 2)
        cfg.full_distance_cm = median_dist
        logger.info(
            "Calibrated '%s' full distance to %.2f cm (from %d samples).",
            bin_id.value,
            median_dist,
            len(readings),
        )
        return median_dist

    async def _poll_loop(self) -> None:
        """Background asynchronous polling worker reading each bin without blocking."""
        logger.info("Ultrasonic background polling worker started (interval=%.1fs).", self.read_interval_s)
        while self._running:
            try:
                for b in BinId:
                    if not self._running:
                        break
                    await self.read_distance_async(b)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error in ultrasonic background polling loop: %s", exc)

            try:
                await asyncio.sleep(self.read_interval_s)
            except asyncio.CancelledError:
                break

    def start_background_polling(self) -> None:
        """Start non-blocking periodic background sensor polling."""
        if not self._running:
            self._running = True
            self._bg_task = asyncio.create_task(self._poll_loop())

    def stop_background_polling(self) -> None:
        """Stop background polling worker cleanly."""
        self._running = False
        if self._bg_task and not self._bg_task.done():
            self._bg_task.cancel()
            self._bg_task = None
        logger.info("Ultrasonic background polling stopped.")

    @property
    def sensor_statuses(self) -> Dict[str, SensorStatus]:
        """Current status dictionary for all bins, including backward-compatible aliases."""
        statuses = {b.value: self._sensor_statuses.get(b, SensorStatus.NOT_CONFIGURED) for b in BinId}
        statuses["organic"] = statuses.get("food_waste", SensorStatus.NOT_CONFIGURED)
        statuses["bio"] = statuses.get("recyclable", SensorStatus.NOT_CONFIGURED)
        statuses["non_bio"] = statuses.get("non_recyclable", SensorStatus.NOT_CONFIGURED)
        return statuses
