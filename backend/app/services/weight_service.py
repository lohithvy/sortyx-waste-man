"""
Sortyx 2.0 — Weight Monitoring & HX711 Load Cell Service.

Coordinates three independent HX711 24-bit load cell amplifiers:
  - Bin 1 (Food Waste):    DT=GPIO 5,  SCK=GPIO 11
  - Bin 2 (Recyclable):    DT=GPIO 13, SCK=GPIO 19
  - Bin 3 (Non-Recyclable):DT=GPIO 26, SCK=GPIO 21

Key architectural requirements:
1. Handle uncalibrated offsets (Tare and Scale default to None/empty).
2. Report weight as unavailable (None) with display "Not Calibrated" until calibrated.
3. NEVER report fabricated weights.
4. Provide independent per-bin tare() and calibrate(known_weight_g) functions.
5. Strict isolation: failure or timeout on one bin's load cell never impacts the others.
6. Enforce WEIGHT_RULE=false: weight data is strictly for monitoring and analytics;
   it MUST NEVER alter classification decisions, safety overrides, or bin selection.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from app.core.config import get_settings
from app.core.logging_config import get_logger
from app.hardware.hx711 import HX711Controller
from app.models.enums import BinId, SensorStatus

logger = get_logger(__name__)


class WeightService:
    """Manages HX711 load cell readings and calibration across all bins."""

    def __init__(
        self,
        simulation_mode: bool = True,
        weight_rule_enabled: bool = False,
    ) -> None:
        self.simulation_mode = simulation_mode
        self.weight_rule_enabled = weight_rule_enabled
        settings = get_settings()

        # Enforce WEIGHT_RULE=false constraint from settings
        if settings.hardware.weight_rule is not None:
            self.weight_rule_enabled = settings.hardware.weight_rule

        if self.weight_rule_enabled:
            logger.warning(
                "WEIGHT_RULE is enabled in configuration, but safety constraint dictates "
                "weight must NOT override AI classification."
            )

        # Initialize independent controllers for each bin
        self._controllers: Dict[BinId, HX711Controller] = {
            BinId.FOOD_WASTE: HX711Controller(
                dt_pin=settings.hardware.hx711_dt_1,
                sck_pin=settings.hardware.hx711_sck_1,
                tare_offset=settings.hardware.hx711_tare_1,
                scale_factor=settings.hardware.hx711_scale_1,
                simulation_mode=simulation_mode,
                bin_name="food_waste",
            ),
            BinId.RECYCLABLE: HX711Controller(
                dt_pin=settings.hardware.hx711_dt_2,
                sck_pin=settings.hardware.hx711_sck_2,
                tare_offset=settings.hardware.hx711_tare_2,
                scale_factor=settings.hardware.hx711_scale_2,
                simulation_mode=simulation_mode,
                bin_name="recyclable",
            ),
            BinId.NON_RECYCLABLE: HX711Controller(
                dt_pin=settings.hardware.hx711_dt_3,
                sck_pin=settings.hardware.hx711_sck_3,
                tare_offset=settings.hardware.hx711_tare_3,
                scale_factor=settings.hardware.hx711_scale_3,
                simulation_mode=simulation_mode,
                bin_name="non_recyclable",
            ),
        }

        # Cached weights per bin
        self._latest_weights: Dict[BinId, Optional[float]] = {
            BinId.FOOD_WASTE: None,
            BinId.RECYCLABLE: None,
            BinId.NON_RECYCLABLE: None,
        }

        # Per-bin lock lazily initialized on active event loop
        self._locks: Dict[BinId, asyncio.Lock] = {}
        self._running: bool = False
        self._bg_task: Optional[asyncio.Task] = None
        self.read_interval_s: float = 2.0

    def _get_lock(self, bin_id: BinId) -> asyncio.Lock:
        """Lazily initialize asyncio.Lock on current event loop."""
        if bin_id not in self._locks:
            self._locks[bin_id] = asyncio.Lock()
        return self._locks[bin_id]

    def get_controller(self, bin_id: BinId) -> Optional[HX711Controller]:
        """Get the low-level HX711 controller for a bin."""
        return self._controllers.get(bin_id)

    def is_calibrated(self, bin_id: BinId) -> bool:
        """Check if load cell for a bin has valid calibration parameters."""
        ctrl = self._controllers.get(bin_id)
        return ctrl.is_calibrated if ctrl else False

    def get_sensor_status(self, bin_id: BinId) -> SensorStatus:
        """Evaluate status of the HX711 sensor."""
        ctrl = self._controllers.get(bin_id)
        if not ctrl or ctrl.dt_pin < 0 or ctrl.sck_pin < 0:
            return SensorStatus.NOT_CONFIGURED

        if self.simulation_mode:
            return SensorStatus.SIMULATION

        if not ctrl.is_calibrated:
            return SensorStatus.UNCALIBRATED

        return SensorStatus.ONLINE

    def read_weight(self, bin_id: BinId) -> Optional[float]:
        """Synchronously read weight in grams.

        Returns None if in simulation, uncalibrated, or on timeout.
        Never fabricates weights.
        """
        ctrl = self._controllers.get(bin_id)
        if not ctrl:
            return None

        if self.simulation_mode or not ctrl.is_calibrated:
            return None

        try:
            val = ctrl.read_weight_g()
            self._latest_weights[bin_id] = val
            return val
        except Exception as exc:
            logger.error("Error reading weight for bin '%s': %s", bin_id.value, exc)
            return None

    async def read_weight_async(self, bin_id: BinId) -> Optional[float]:
        """Asynchronously read weight off-thread with per-bin locking."""
        ctrl = self._controllers.get(bin_id)
        if not ctrl or self.simulation_mode or not ctrl.is_calibrated:
            return None

        lock = self._get_lock(bin_id)
        async with lock:
            val = await asyncio.to_thread(ctrl.read_weight_g)
            self._latest_weights[bin_id] = val
            return val

    async def tare_bin(self, bin_id: BinId, samples: int = 15) -> Optional[float]:
        """Perform tare zero-offset calibration for the specified bin."""
        ctrl = self._controllers.get(bin_id)
        if not ctrl or self.simulation_mode:
            return None

        lock = self._get_lock(bin_id)
        async with lock:
            return await asyncio.to_thread(ctrl.tare, samples)

    async def calibrate_bin(
        self,
        bin_id: BinId,
        known_weight_g: float,
        samples: int = 15,
    ) -> Optional[float]:
        """Calculate and store scale factor given a known reference mass."""
        ctrl = self._controllers.get(bin_id)
        if not ctrl or self.simulation_mode:
            return None

        lock = self._get_lock(bin_id)
        async with lock:
            return await asyncio.to_thread(ctrl.calibrate, known_weight_g, samples)

    def get_bin_weight_summary(self, bin_id: BinId) -> Dict[str, Any]:
        """Get structured status and weight report for a specific bin."""
        ctrl = self._controllers.get(bin_id)
        status = self.get_sensor_status(bin_id)
        is_cal = ctrl.is_calibrated if ctrl else False
        val_g = self._latest_weights.get(bin_id)
        weight_kg = round(val_g / 1000.0, 2) if (val_g is not None and is_cal) else None

        if not is_cal:
            weight_display = "Not Calibrated"
        elif weight_kg is not None:
            weight_display = f"{weight_kg:.2f} kg"
        else:
            weight_display = "Not Calibrated"

        # Verify physical load cell connection:
        # A load cell is physically connected ONLY when:
        # 1. Hardware simulation mode is OFF.
        # 2. RPi GPIO controller is initialized.
        # 3. DT pin responds (is_ready / not floating).
        is_connected = False
        if not self.simulation_mode and ctrl and getattr(ctrl, "_initialized", False) and getattr(ctrl, "_gpio", None) is not None:
            try:
                is_connected = bool(ctrl.is_ready())
            except Exception:
                is_connected = False

        load_cell_status = "Load Cell Connected" if is_connected else "Load Cell Disconnected"

        return {
            "bin": bin_id.value,
            "bin_number": bin_id.bin_number,
            "category": bin_id.value,
            "displayName": bin_id.display_name,
            "title": bin_id.full_title,
            "weight_g": val_g if is_cal else None,
            "weight_kg": weight_kg,
            "weight_display": weight_display,
            "is_calibrated": is_cal,
            "load_cell_connected": is_connected,
            "load_cell_status": load_cell_status,
            "status": status.value,
            "tare_offset": ctrl.tare_offset if ctrl else None,
            "scale_factor": ctrl.scale_factor if ctrl else None,
            "dt_pin": ctrl.dt_pin if ctrl else None,
            "sck_pin": ctrl.sck_pin if ctrl else None,
        }

    def get_all_weights_summary(self) -> Dict[str, Dict[str, Any]]:
        """Return comprehensive weight sensor status across all three bins, including backward-compatible aliases."""
        res = {
            b.value: self.get_bin_weight_summary(b)
            for b in [BinId.FOOD_WASTE, BinId.RECYCLABLE, BinId.NON_RECYCLABLE]
        }
        res["organic"] = res.get("food_waste", {})
        res["bio"] = res.get("recyclable", {})
        res["non_bio"] = res.get("non_recyclable", {})
        return res

    async def _poll_loop(self) -> None:
        """Background asynchronous polling worker reading each load cell and syncing UI."""
        logger.info("HX711 load cell background polling worker started (interval=%.1fs).", self.read_interval_s)
        from app.api.websocket import ws_manager

        while self._running:
            try:
                for b in (BinId.FOOD_WASTE, BinId.RECYCLABLE, BinId.NON_RECYCLABLE):
                    if not self._running:
                        break
                    await self.read_weight_async(b)
                    summary = self.get_bin_weight_summary(b)
                    try:
                        await ws_manager.broadcast_json({
                            "type": "weight_update",
                            "payload": {
                                "bin_id": b.value,
                                "bin_number": b.bin_number,
                                "category": b.value,
                                "display_name": b.display_name,
                                "title": b.full_title,
                                "weight_kg": summary["weight_kg"],
                                "weight_display": summary["weight_display"],
                                "is_calibrated": summary["is_calibrated"],
                                "load_cell_connected": summary["load_cell_connected"],
                                "load_cell_status": summary["load_cell_status"],
                            },
                        })
                    except Exception:
                        pass
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("HX711 polling loop cycle: %s", exc)

            try:
                await asyncio.sleep(self.read_interval_s)
            except asyncio.CancelledError:
                break

    def start_background_polling(self) -> None:
        """Start non-blocking periodic background load cell polling."""
        if not self._running:
            self._running = True
            self._bg_task = asyncio.create_task(self._poll_loop())

    def stop_background_polling(self) -> None:
        """Stop background load cell polling worker cleanly."""
        self._running = False
        if self._bg_task and not self._bg_task.done():
            self._bg_task.cancel()
            self._bg_task = None
        logger.info("HX711 load cell background polling stopped.")

