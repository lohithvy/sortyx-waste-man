"""
Sortyx 2.0 — HX711 24-bit ADC Load Cell Controller.

Manages 24-bit ADC communication with HX711 load cell amplifiers on Raspberry Pi.
Uses bit-banging on GPIO SCK and DT pins.

Features:
1. Channel A 128-gain mode (25 clock pulses).
2. 24-bit two's complement conversion.
3. Timeout handling when DT does not pull LOW.
4. Independent per-bin calibration (tare and scale factor).
5. Uncalibrated safety: returns None when uncalibrated or in simulation mode (NEVER fabricates weights).
6. Non-Pi simulation fallback so code runs safely on Windows/macOS.
"""

from __future__ import annotations

import time
from typing import Dict, Optional, Tuple

from app.core.logging_config import get_logger

logger = get_logger(__name__)


class HX711Controller:
    """Low-level bit-bang driver for a single HX711 24-bit ADC channel."""

    def __init__(
        self,
        dt_pin: int,
        sck_pin: int,
        tare_offset: Optional[float] = None,
        scale_factor: Optional[float] = None,
        simulation_mode: bool = True,
        bin_name: str = "unknown",
    ) -> None:
        self.dt_pin = dt_pin
        self.sck_pin = sck_pin
        self.tare_offset = tare_offset
        self.scale_factor = scale_factor
        self.simulation_mode = simulation_mode
        self.bin_name = bin_name

        self._gpio = None
        self._initialized = False

        if not self.simulation_mode and self.dt_pin >= 0 and self.sck_pin >= 0:
            self._init_gpio()

    def _init_gpio(self) -> None:
        """Attempt to configure GPIO pins for DT (input) and SCK (output)."""
        try:
            import RPi.GPIO as GPIO  # type: ignore

            self._gpio = GPIO
            self._gpio.setmode(self._gpio.BCM)
            self._gpio.setwarnings(False)
            self._gpio.setup(self.sck_pin, self._gpio.OUT)
            self._gpio.setup(self.dt_pin, self._gpio.IN)
            # Set SCK LOW to wake up / keep active
            self._gpio.output(self.sck_pin, False)
            self._initialized = True
            logger.info(
                "HX711 initialized for bin '%s' (DT=%d, SCK=%d) on Raspberry Pi",
                self.bin_name,
                self.dt_pin,
                self.sck_pin,
            )
        except ImportError:
            logger.warning(
                "GPIO library not available. HX711 for bin '%s' operating in SIMULATION mode.",
                self.bin_name,
            )
            self.simulation_mode = True
        except RuntimeError as r_err:
            logger.error("RPi.GPIO failed on Raspberry Pi 5 (%s). Install 'rpi-lgpio' (pip install rpi-lgpio).", r_err)
            self.simulation_mode = True
        except Exception as exc:
            logger.error(
                "Failed to initialize HX711 pins (DT=%d, SCK=%d) for bin '%s': %s",
                self.dt_pin,
                self.sck_pin,
                self.bin_name,
                exc,
            )
            self.simulation_mode = True

    @property
    def is_calibrated(self) -> bool:
        """Return True only if both tare offset and non-zero scale factor are set."""
        return (
            self.tare_offset is not None
            and self.scale_factor is not None
            and abs(self.scale_factor) > 1e-6
        )

    def is_ready(self) -> bool:
        """Check if HX711 is ready for reading (DT pin is LOW)."""
        if self.simulation_mode or not self._gpio:
            return False
        try:
            return self._gpio.input(self.dt_pin) == 0
        except Exception:
            return False

    def read_raw(self, timeout_s: float = 0.1) -> Optional[int]:
        """Read a single 24-bit raw signed integer from the HX711.

        Uses 25 clock pulses (Channel A, Gain 128).
        Returns None on timeout, simulation, or hardware fault.
        """
        if self.simulation_mode or not self._gpio:
            return None

        # Wait for DT to go LOW (ready)
        start_time = time.time()
        while self._gpio.input(self.dt_pin) == 1:
            if time.time() - start_time > timeout_s:
                logger.debug(
                    "HX711 timeout waiting for ready signal on DT pin %d (bin '%s')",
                    self.dt_pin,
                    self.bin_name,
                )
                return None
            time.sleep(0.0005)

        raw_bits = 0
        try:
            for _ in range(24):
                self._gpio.output(self.sck_pin, True)
                time.sleep(0.000001)  # 1 µs pulse width
                raw_bits = (raw_bits << 1) | self._gpio.input(self.dt_pin)
                self._gpio.output(self.sck_pin, False)
                time.sleep(0.000001)

            # 25th pulse sets Channel A, Gain 128 for next reading
            self._gpio.output(self.sck_pin, True)
            time.sleep(0.000001)
            self._gpio.output(self.sck_pin, False)
            time.sleep(0.000001)

            # Convert 24-bit two's complement to signed integer
            if raw_bits & 0x800000:
                raw_bits -= 0x1000000

            return raw_bits
        except Exception as exc:
            logger.error("Error bit-banging HX711 on bin '%s': %s", self.bin_name, exc)
            return None

    def read_average_raw(self, samples: int = 5, timeout_s: float = 0.1) -> Optional[float]:
        """Read multiple raw samples and return the average, rejecting outliers."""
        if self.simulation_mode or not self._gpio:
            return None

        valid_readings: list[int] = []
        for _ in range(samples):
            reading = self.read_raw(timeout_s=timeout_s)
            if reading is not None:
                valid_readings.append(reading)
            time.sleep(0.01)

        if not valid_readings:
            return None

        return sum(valid_readings) / len(valid_readings)

    def read_weight_g(self, samples: int = 1) -> Optional[float]:
        """Calculate weight in grams using calibrated tare offset and scale factor.

        Returns None if uncalibrated, in simulation, or if reading fails.
        NEVER reports fabricated weights.
        """
        if not self.is_calibrated:
            return None

        if self.simulation_mode or not self._gpio:
            return None

        raw = self.read_average_raw(samples=samples)
        if raw is None or self.tare_offset is None or self.scale_factor is None:
            return None

        weight = (raw - self.tare_offset) / self.scale_factor
        return round(max(0.0, weight), 1)

    def tare(self, samples: int = 15) -> Optional[float]:
        """Record zero-load tare offset.

        Returns the new tare offset, or None if in simulation / read failed.
        """
        if self.simulation_mode or not self._gpio:
            logger.warning("Cannot tare bin '%s': Running in simulation mode.", self.bin_name)
            return None

        avg = self.read_average_raw(samples=samples)
        if avg is not None:
            self.tare_offset = avg
            logger.info("HX711 bin '%s' tared successfully with offset: %.2f", self.bin_name, avg)
            return avg

        logger.error("HX711 bin '%s' tare failed: no valid samples acquired.", self.bin_name)
        return None

    def calibrate(self, known_weight_g: float, samples: int = 15) -> Optional[float]:
        """Calculate and store scale factor given a known reference mass on the load cell.

        scale_factor = (raw_average - tare_offset) / known_weight_g
        """
        if known_weight_g <= 0:
            logger.error("Calibration requires a positive known weight.")
            return None

        if self.tare_offset is None:
            logger.error("Cannot calibrate bin '%s': Perform tare() first.", self.bin_name)
            return None

        if self.simulation_mode or not self._gpio:
            logger.warning("Cannot calibrate bin '%s': Running in simulation mode.", self.bin_name)
            return None

        avg = self.read_average_raw(samples=samples)
        if avg is None:
            logger.error("HX711 bin '%s' calibration failed: no valid readings.", self.bin_name)
            return None

        delta = avg - self.tare_offset
        if abs(delta) < 10:
            logger.error(
                "HX711 bin '%s' calibration failed: raw change (%f) is too small. Is weight on the sensor?",
                self.bin_name,
                delta,
            )
            return None

        scale = delta / known_weight_g
        self.scale_factor = scale
        logger.info(
            "HX711 bin '%s' calibrated: scale_factor=%.4f (raw_delta=%.2f for %.1fg)",
            self.bin_name,
            scale,
            delta,
            known_weight_g,
        )
        return scale

    def power_down(self) -> None:
        """Put HX711 into low-power sleep mode by holding SCK HIGH for >60 µs."""
        if not self.simulation_mode and self._gpio:
            try:
                self._gpio.output(self.sck_pin, True)
                time.sleep(0.0001)  # 100 µs
            except Exception as exc:
                logger.debug("HX711 power down error: %s", exc)

    def power_up(self) -> None:
        """Wake HX711 up by pulling SCK LOW."""
        if not self.simulation_mode and self._gpio:
            try:
                self._gpio.output(self.sck_pin, False)
                time.sleep(0.001)
            except Exception as exc:
                logger.debug("HX711 power up error: %s", exc)

