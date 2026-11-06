"""
Sortyx 2.0 — Raspberry Pi GPIO Ultrasonic Sensor Controller.

Interfaces with HC-SR04 ultrasonic distance sensors on Raspberry Pi.

=============================================================================
CRITICAL HARDWARE SAFETY NOTE: 5V -> 3.3V VOLTAGE CONVERSION
=============================================================================
The HC-SR04 ultrasonic sensor operates at 5V VCC and outputs a 5V TTL logic
signal on its ECHO pin. The Raspberry Pi 4 GPIO pins are strictly 3.3V tolerant;
applying 5V directly to any GPIO pin will permanently destroy the BCM2711 SoC pin!

A voltage conversion circuit is MANDATORY for all ECHO lines:
  - Bin 1 ECHO (GPIO 24)
  - Bin 2 ECHO (GPIO 27)
  - Bin 3 ECHO (GPIO 6)

Recommended Voltage Divider:
  Sensor ECHO Pin ----[ 1 kΩ Resistor ]----+---- Raspberry Pi GPIO
                                            |
                                    [ 2 kΩ Resistor ]
                                            |
                                           GND
  V_out = 5V * (2000 / (1000 + 2000)) = 3.33V (Safe for 3.3V GPIO)

Alternatively, use a dedicated 5V to 3.3V bidirectional logic level shifter IC
(e.g., TXS0108E or BSS138). Never connect raw 5V sensor signals to GPIO!
=============================================================================
"""

from __future__ import annotations

import time
from typing import Optional

from app.core.logging_config import get_logger

logger = get_logger(__name__)


class GPIOController:
    """Manages Raspberry Pi GPIO operations for ultrasonic distance sensing using BCM numbering."""

    def __init__(self, simulation_mode: bool = True) -> None:
        self.simulation_mode = simulation_mode
        self._gpio = None
        self._initialized = False

        if not self.simulation_mode:
            self._init_gpio()

    def _init_gpio(self) -> None:
        """Attempt to initialize GPIO (RPi.GPIO or rpi-lgpio for Raspberry Pi 5) in BCM mode."""
        try:
            import RPi.GPIO as GPIO  # type: ignore

            self._gpio = GPIO
            self._gpio.setmode(self._gpio.BCM)
            self._gpio.setwarnings(False)
            self._initialized = True
            logger.info("GPIO hardware controller initialized successfully in BCM mode.")
        except ImportError:
            logger.warning("GPIO library not available (running on non-Pi OS). Operating in SIMULATION mode.")
            self.simulation_mode = True
        except RuntimeError as r_err:
            logger.error("RPi.GPIO failed on Raspberry Pi 5 (%s). Install 'rpi-lgpio' (pip install rpi-lgpio).", r_err)
            self.simulation_mode = True
        except Exception as exc:
            logger.error("Failed to initialize GPIO: %s", exc)
            self.simulation_mode = True

    def setup_pins(self, trigger_pin: int, echo_pin: int) -> bool:
        """Configure trigger pin as output, echo pin as input."""
        if trigger_pin < 0 or echo_pin < 0:
            return False

        if self.simulation_mode or not self._gpio:
            return True

        try:
            self._gpio.setup(trigger_pin, self._gpio.OUT)
            self._gpio.setup(echo_pin, self._gpio.IN)
            self._gpio.output(trigger_pin, False)
            time.sleep(0.02)
            return True
        except Exception as exc:
            logger.error(
                "Failed to setup GPIO pins (TRIG=%d, ECHO=%d): %s",
                trigger_pin,
                echo_pin,
                exc,
            )
            return False

    def read_distance_cm(
        self,
        trigger_pin: int,
        echo_pin: int,
        timeout_s: float = 0.1,
    ) -> Optional[float]:
        """Send a 10µs pulse on trigger and measure roundtrip echo time.

        Calculates distance = (elapsed_time * speed_of_sound) / 2.
        Speed of sound = 34300 cm/s.
        Returns None if in simulation mode, on timeout, or on invalid reading.
        Never fabricates distances.
        """
        if trigger_pin < 0 or echo_pin < 0:
            return None

        if self.simulation_mode or not self._gpio:
            # Strictly return None in simulation — never report fabricated distances
            return None

        try:
            # Ensure trigger is low before pulse
            self._gpio.output(trigger_pin, False)
            time.sleep(0.000002)  # 2 microseconds

            # 10 microsecond pulse on trigger
            self._gpio.output(trigger_pin, True)
            time.sleep(0.000010)  # 10 microseconds
            self._gpio.output(trigger_pin, False)

            start_time = time.time()
            pulse_start = start_time
            pulse_end = start_time
            timeout_deadline = start_time + timeout_s

            # Wait for echo to go HIGH
            while self._gpio.input(echo_pin) == 0:
                pulse_start = time.time()
                if pulse_start > timeout_deadline:
                    return None

            # Wait for echo to go LOW
            while self._gpio.input(echo_pin) == 1:
                pulse_end = time.time()
                if pulse_end > timeout_deadline:
                    return None

            duration = pulse_end - pulse_start
            distance = (duration * 34300.0) / 2.0

            if 2.0 <= distance <= 400.0:
                return round(distance, 2)
            return None
        except Exception as exc:
            logger.debug("Ultrasonic reading error (TRIG=%d, ECHO=%d): %s", trigger_pin, echo_pin, exc)
            return None

    def cleanup(self) -> None:
        """Reset GPIO configurations safely."""
        if not self.simulation_mode and self._gpio:
            try:
                self._gpio.cleanup()
                logger.info("RPi.GPIO pins cleaned up.")
            except Exception as exc:
                logger.debug("RPi.GPIO cleanup error: %s", exc)
