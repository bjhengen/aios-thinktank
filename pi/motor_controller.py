"""
Motor controller for Raspberry Pi robot car.

Handles direct GPIO control of 4 DC motors through 2x L298N drivers.
"""

import time
from typing import Optional

try:
    import RPi.GPIO as GPIO
except ImportError:
    # Allow imports on non-Pi systems for development
    GPIO = None

from shared.protocol import MotorCommand, Direction
from shared.utils import setup_logging
from pi.config import config


logger = setup_logging(__name__)


class MotorController:
    """
    Controls 4 DC motors using GPIO pins.

    This assumes mecanum wheel configuration:
    - Front Left (FL)
    - Front Right (FR)
    - Rear Left (RL)
    - Rear Right (RR)

    For simplicity, we group them as "left" (FL + RL) and "right" (FR + RR).
    """

    def __init__(self, simulate: bool = False):
        """
        Initialize motor controller.

        Args:
            simulate: If True, don't actually use GPIO (for testing)
        """
        self.simulate = simulate or (GPIO is None)
        self.pwm_objects = {}
        self.last_command_time = time.time()
        self.initialized = False

        if self.simulate:
            logger.warning("Running in SIMULATION mode - no actual GPIO control")
        else:
            logger.info("Initializing GPIO for motor control")

    def setup(self) -> None:
        """Set up GPIO pins for motor control."""
        if self.simulate:
            logger.info("Simulated GPIO setup complete")
            self.initialized = True
            return

        if GPIO is None:
            raise RuntimeError("RPi.GPIO not available - are you on a Raspberry Pi?")

        try:
            # Set GPIO mode
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)

            # Setup motor control pins
            pins = [
                config.fl_forward, config.fl_backward,
                config.fr_forward, config.fr_backward,
                config.rl_forward, config.rl_backward,
                config.rr_forward, config.rr_backward,
            ]

            for pin in pins:
                GPIO.setup(pin, GPIO.OUT)
                GPIO.output(pin, GPIO.LOW)

            # Setup PWM pins
            pwm_pins = [config.fl_pwm, config.fr_pwm, config.rl_pwm, config.rr_pwm]
            for pin in pwm_pins:
                GPIO.setup(pin, GPIO.OUT)
                pwm = GPIO.PWM(pin, config.pwm_frequency)
                pwm.start(0)
                self.pwm_objects[pin] = pwm

            self.initialized = True
            logger.info("GPIO setup complete")

        except Exception as e:
            logger.error(f"Failed to setup GPIO: {e}")
            raise

    def cleanup(self) -> None:
        """Clean up GPIO resources."""
        if self.simulate:
            return

        logger.info("Cleaning up GPIO")

        # Stop all PWM
        for pwm in self.pwm_objects.values():
            pwm.stop()

        # Cleanup GPIO
        if GPIO:
            GPIO.cleanup()

        self.initialized = False

    def execute_command(self, command: MotorCommand) -> None:
        """
        Execute a motor command.

        Args:
            command: MotorCommand to execute
        """
        if not self.initialized:
            logger.error("Motor controller not initialized")
            return

        self.last_command_time = time.time()

        if self.simulate:
            logger.info(f"[SIM] Executing: {command}")
            return

        try:
            # Control left side (FL + RL)
            self._set_motor_group(
                forward_pins=[config.fl_forward, config.rl_forward],
                backward_pins=[config.fl_backward, config.rl_backward],
                pwm_pins=[config.fl_pwm, config.rl_pwm],
                speed=command.left_speed,
                direction=command.left_dir
            )

            # Control right side (FR + RR)
            self._set_motor_group(
                forward_pins=[config.fr_forward, config.rr_forward],
                backward_pins=[config.fr_backward, config.rr_backward],
                pwm_pins=[config.fr_pwm, config.rr_pwm],
                speed=command.right_speed,
                direction=command.right_dir
            )

            logger.debug(f"Executed: {command}")

        except Exception as e:
            logger.error(f"Error executing command: {e}")
            self.emergency_stop()

    def _set_motor_group(self,
                        forward_pins: list,
                        backward_pins: list,
                        pwm_pins: list,
                        speed: int,
                        direction: Direction) -> None:
        """
        Set a group of motors (e.g., both left wheels).

        Args:
            forward_pins: GPIO pins for forward direction
            backward_pins: GPIO pins for backward direction
            pwm_pins: GPIO pins for PWM speed control
            speed: Speed value 0-255
            direction: Direction enum value
        """
        # Set direction pins
        if direction == Direction.FORWARD:
            for pin in forward_pins:
                GPIO.output(pin, GPIO.HIGH)
            for pin in backward_pins:
                GPIO.output(pin, GPIO.LOW)
        elif direction == Direction.BACKWARD:
            for pin in forward_pins:
                GPIO.output(pin, GPIO.LOW)
            for pin in backward_pins:
                GPIO.output(pin, GPIO.HIGH)
        else:  # STOP
            for pin in forward_pins + backward_pins:
                GPIO.output(pin, GPIO.LOW)
            speed = 0

        # Set speed via PWM (convert 0-255 to 0-100 duty cycle)
        duty_cycle = (speed / 255.0) * 100.0
        for pin in pwm_pins:
            if pin in self.pwm_objects:
                self.pwm_objects[pin].ChangeDutyCycle(duty_cycle)

    def emergency_stop(self) -> None:
        """Immediately stop all motors."""
        logger.warning("EMERGENCY STOP")

        if self.simulate:
            logger.info("[SIM] All motors stopped")
            return

        try:
            # Set all direction pins LOW
            pins = [
                config.fl_forward, config.fl_backward,
                config.fr_forward, config.fr_backward,
                config.rl_forward, config.rl_backward,
                config.rr_forward, config.rr_backward,
            ]
            for pin in pins:
                GPIO.output(pin, GPIO.LOW)

            # Set all PWM to 0
            for pwm in self.pwm_objects.values():
                pwm.ChangeDutyCycle(0)

        except Exception as e:
            logger.error(f"Error during emergency stop: {e}")

    def check_watchdog(self) -> None:
        """
        Check if we've received commands recently.

        If not, stop motors for safety.
        """
        if not self.initialized:
            return

        time_since_command = time.time() - self.last_command_time
        if time_since_command > config.watchdog_timeout:
            logger.warning(f"Watchdog timeout ({time_since_command:.1f}s) - stopping motors")
            self.emergency_stop()
            self.last_command_time = time.time()  # Reset to avoid spam

    def test_motors(self) -> None:
        """
        Run a test sequence to verify all motors work.

        Each motor group runs briefly in each direction.
        """
        logger.info("Starting motor test sequence...")

        if not self.initialized:
            logger.error("Cannot test - not initialized")
            return

        test_speed = 150
        test_duration = 1.0

        tests = [
            ("Forward", MotorCommand.forward(test_speed)),
            ("Backward", MotorCommand.backward(test_speed)),
            ("Rotate Left", MotorCommand.rotate_left(test_speed)),
            ("Rotate Right", MotorCommand.rotate_right(test_speed)),
        ]

        for name, command in tests:
            logger.info(f"Testing: {name}")
            self.execute_command(command)
            time.sleep(test_duration)
            self.emergency_stop()
            time.sleep(0.5)

        logger.info("Motor test complete")
