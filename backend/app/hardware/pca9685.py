"""
Sortyx 2.0 — PCA9685 I2C PWM Controller Wrapper.

Manages I2C communication with the PCA9685 16-channel PWM servo driver.
On Raspberry Pi with hardware present, uses Adafruit CircuitPython libraries.
Gracefully handles absent hardware, simulation mode, and unconfigured channels.

Hardware Architecture & Safety:
1. Standard I2C Bus 1 (SDA GPIO 2, SCL GPIO 3), Default Address 0x40, 50 Hz PWM.
2. Open = 50°, Close = 0°, Hold = 3.0s, Settle = 0.5s.
3. Channels: Bin 1 (Organic) = 0, Bin 2 (Bio) = 1, Bin 3 (Non-Bio) = 2.
4. Mutex lock (asyncio.Lock) prevents concurrent movements across channels.
5. Emergency stop method to immediately close and de-energize all servos.
6. Servos MUST NEVER be powered directly from Raspberry Pi 5V header.
   External 5V supply connected to PCA9685 screw terminals is mandatory.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional

from app.core.logging_config import get_logger
from app.core.exceptions import HardwareError, ServoError

logger = get_logger(__name__)


class PCA9685Controller:
    """Low-level controller for PCA9685 16-channel servo driver."""

    def __init__(
        self,
        i2c_address: int = 0x40,
        i2c_bus: int = 1,
        pwm_frequency: int = 50,
        simulation_mode: bool = True,
    ) -> None:
        self.i2c_address = i2c_address
        self.i2c_bus = i2c_bus
        self.pwm_frequency = pwm_frequency
        self.simulation_mode = simulation_mode
        self._kit = None
        self._is_connected = False
        self._current_angles: Dict[int, int] = {}
        self._lock: Optional[asyncio.Lock] = None

        if not self.simulation_mode:
            self._init_hardware()
        else:
            logger.info("PCA9685 running in SIMULATION mode — physical actuation strictly disabled.")

    def _init_hardware(self) -> None:
        """Attempt to initialize Adafruit ServoKit on Raspberry Pi."""
        try:
            from adafruit_servokit import ServoKit  # type: ignore

            self._kit = ServoKit(channels=16, address=self.i2c_address)
            self._is_connected = True
            logger.info(
                "PCA9685 hardware connected at address 0x%02X on bus %d (PWM=%dHz)",
                self.i2c_address,
                self.i2c_bus,
                self.pwm_frequency,
            )
        except ImportError:
            logger.warning(
                "adafruit-circuitpython-servokit is not installed. Falling back to simulation."
            )
            self.simulation_mode = True
            self._is_connected = False
        except Exception as exc:
            logger.error("Failed to connect to PCA9685 at 0x%02X: %s", self.i2c_address, exc)
            self.simulation_mode = True
            self._is_connected = False

    @property
    def is_connected(self) -> bool:
        """Return True if physical hardware is confirmed connected."""
        return not self.simulation_mode and self._is_connected

    def set_servo_angle(
        self,
        channel: int,
        angle: int,
        pulse_min: Optional[int] = None,
        pulse_max: Optional[int] = None,
    ) -> bool:
        """Set servo on given channel to target angle (0-180 degrees).

        Returns True on success, False if unconfigured or hardware failed.
        """
        if channel < 0 or channel > 15:
            logger.warning("Channel %s is NOT_CONFIGURED or invalid. No movement.", channel)
            return False

        clamped_angle = max(0, min(180, int(angle)))

        if self.simulation_mode or not self._kit:
            logger.info(
                "[SIMULATION] PCA9685 Channel %d set to %d°",
                channel,
                clamped_angle,
            )
            self._current_angles[channel] = clamped_angle
            return True

        try:
            servo = self._kit.servo[channel]
            if pulse_min is not None and pulse_max is not None:
                servo.set_pulse_width_range(pulse_min, pulse_max)
            servo.angle = clamped_angle
            self._current_angles[channel] = clamped_angle
            logger.debug("PCA9685 Channel %d set to %d°", channel, clamped_angle)
            return True
        except Exception as exc:
            logger.error("Hardware error setting servo on channel %d: %s", channel, exc)
            return False

    async def move_smooth(
        self,
        channel: int,
        start_angle: int,
        target_angle: int,
        step_deg: int = 2,
        step_delay_s: float = 0.02,
        pulse_min: Optional[int] = None,
        pulse_max: Optional[int] = None,
    ) -> bool:
        """Smoothly actuate servo between start and target angle to avoid mechanical slamming."""
        if channel < 0 or channel > 15:
            logger.warning("Channel %s is NOT_CONFIGURED. Smooth movement aborted.", channel)
            return False

        start = max(0, min(180, int(start_angle)))
        target = max(0, min(180, int(target_angle)))

        if self.simulation_mode or not self._kit:
            logger.info(
                "[SIMULATION] PCA9685 Channel %d smoothly transitioning from %d° to %d° (step=%d°, delay=%.3fs)",
                channel,
                start,
                target,
                step_deg,
                step_delay_s,
            )
            self._current_angles[channel] = target
            return True

        step = step_deg if target > start else -step_deg
        current = start

        while (step > 0 and current < target) or (step < 0 and current > target):
            current += step
            if (step > 0 and current > target) or (step < 0 and current < target):
                current = target
            success = self.set_servo_angle(channel, current, pulse_min, pulse_max)
            if not success:
                return False
            await asyncio.sleep(step_delay_s)

        return True

    async def actuate_cycle(
        self,
        channel: int,
        open_deg: int = 50,
        close_deg: int = 0,
        hold_s: float = 3.0,
        settle_s: float = 0.5,
        pulse_min: Optional[int] = None,
        pulse_max: Optional[int] = None,
    ) -> bool:
        """Execute a full door/chute actuation cycle: Open -> Hold -> Close -> Settle.

        Uses an internal asyncio mutex lock to ensure no concurrent servo actions.
        """
        if channel < 0 or channel > 15:
            logger.warning("Cannot cycle invalid channel: %d", channel)
            return False

        if self._lock is None:
            self._lock = asyncio.Lock()

        async with self._lock:
            logger.info(
                "Starting actuation cycle on Channel %d (open=%d°, close=%d°, hold=%.1fs, settle=%.1fs)",
                channel,
                open_deg,
                close_deg,
                hold_s,
                settle_s,
            )

            # 1. Smoothly open to open_deg
            current = self._current_angles.get(channel, close_deg)
            open_ok = await self.move_smooth(
                channel=channel,
                start_angle=current,
                target_angle=open_deg,
                pulse_min=pulse_min,
                pulse_max=pulse_max,
            )
            if not open_ok:
                logger.error("Failed to open channel %d", channel)
                return False

            # 2. Hold in open position
            await asyncio.sleep(hold_s)

            # 3. Smoothly close back to close_deg
            close_ok = await self.move_smooth(
                channel=channel,
                start_angle=open_deg,
                target_angle=close_deg,
                pulse_min=pulse_min,
                pulse_max=pulse_max,
            )

            # 4. Settle delay
            await asyncio.sleep(settle_s)

            # 5. Disable PWM signal to prevent coil heating and buzz
            self.disable_channel(channel)

            return close_ok

    def disable_channel(self, channel: int) -> None:
        """Release servo signal to stop jitter, holding torque, and coil overheating."""
        if channel < 0 or channel > 15:
            return

        if self.simulation_mode or not self._kit:
            logger.debug("[SIMULATION] PCA9685 Channel %d PWM signal released.", channel)
            return

        try:
            self._kit.servo[channel].angle = None
            logger.debug("PCA9685 Channel %d PWM signal released.", channel)
        except Exception as exc:
            logger.debug("Could not release servo channel %d: %s", channel, exc)

    def emergency_stop(self) -> None:
        """Immediately command all 16 servo channels to 0° and disable PWM signals."""
        logger.warning("PCA9685 EMERGENCY STOP triggered — resetting all channels.")
        for ch in range(16):
            try:
                if self.simulation_mode or not self._kit:
                    self._current_angles[ch] = 0
                else:
                    self._kit.servo[ch].angle = 0
                    self.disable_channel(ch)
            except Exception as exc:
                logger.debug("Emergency stop error on channel %d: %s", ch, exc)

    def diagnose_i2c(self) -> Dict[str, Any]:
        """Test I2C bus connectivity and probe for PCA9685."""
        if self.simulation_mode:
            return {
                "status": "simulation",
                "bus": self.i2c_bus,
                "address": hex(self.i2c_address),
                "connected": False,
                "message": "PCA9685 controller is running in SIMULATION mode.",
            }

        try:
            import smbus2  # type: ignore

            with smbus2.SMBus(self.i2c_bus) as bus:
                # Attempt to read MODE1 register (0x00)
                mode1 = bus.read_byte_data(self.i2c_address, 0x00)
                return {
                    "status": "online",
                    "bus": self.i2c_bus,
                    "address": hex(self.i2c_address),
                    "connected": True,
                    "mode1_register": hex(mode1),
                    "message": "PCA9685 successfully acknowledged I2C communication.",
                }
        except ImportError:
            return {
                "status": "warning",
                "bus": self.i2c_bus,
                "address": hex(self.i2c_address),
                "connected": self._is_connected,
                "message": "smbus2 module not installed for direct I2C register probe.",
            }
        except Exception as exc:
            return {
                "status": "error",
                "bus": self.i2c_bus,
                "address": hex(self.i2c_address),
                "connected": False,
                "error": str(exc),
                "message": f"Failed to communicate with PCA9685 at {hex(self.i2c_address)}.",
            }
