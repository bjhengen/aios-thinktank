"""
Motor controller for Raspberry Pi robot car.

Handles direct GPIO control of 4 DC motors through 2x L298N drivers.
Includes dead rear-left motor compensation with per-motor speed control.
"""

import time
from dataclasses import dataclass
from typing import Optional

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None

from shared.protocol import MotorCommand, Direction
from shared.utils import setup_logging
from pi.config import config


logger = setup_logging(__name__)


@dataclass
class CompensatedCommand:
    """Per-motor speeds and directions after compensation."""
    fl_speed: int
    fl_dir: Direction
    fr_speed: int
    fr_dir: Direction
    rl_speed: int
    rl_dir: Direction
    rr_speed: int
    rr_dir: Direction
    duration_ms: int


class MotorController:
    """
    Controls 4 DC motors using GPIO pins.

    Mecanum wheel configuration: FL, FR, RL, RR.
    Supports dead-RL motor compensation with per-motor speed factors.
    """

    def __init__(self, simulate: bool = False):
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
            if config.rl_motor_dead:
                logger.info("RL motor compensation ENABLED (dead motor)")
            self.initialized = True
            return

        if GPIO is None:
            raise RuntimeError("RPi.GPIO not available - are you on a Raspberry Pi?")

        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)

            pins = [
                config.fl_forward, config.fl_backward,
                config.fr_forward, config.fr_backward,
                config.rl_forward, config.rl_backward,
                config.rr_forward, config.rr_backward,
            ]

            for pin in pins:
                GPIO.setup(pin, GPIO.OUT)
                GPIO.output(pin, GPIO.LOW)

            pwm_pins = [config.fl_pwm, config.fr_pwm, config.rl_pwm, config.rr_pwm]
            for pin in pwm_pins:
                GPIO.setup(pin, GPIO.OUT)
                pwm = GPIO.PWM(pin, config.pwm_frequency)
                pwm.start(0)
                self.pwm_objects[pin] = pwm

            self.initialized = True
            if config.rl_motor_dead:
                logger.info("RL motor compensation ENABLED (dead motor)")
            logger.info("GPIO setup complete")

        except Exception as e:
            logger.error(f"Failed to setup GPIO: {e}")
            raise

    def cleanup(self) -> None:
        """Clean up GPIO resources."""
        if self.simulate:
            return

        logger.info("Cleaning up GPIO")
        for pwm in self.pwm_objects.values():
            pwm.stop()
        if GPIO:
            GPIO.cleanup()
        self.initialized = False

    def _compensate_command(self, command: MotorCommand) -> CompensatedCommand:
        """
        Apply per-motor speed compensation.

        Always applies compensation factors to handle weight distribution
        and motor differences. When rl_motor_dead is True, comp_rl=0.0
        disables that motor entirely.
        """
        fl = min(255, int(command.left_speed * config.comp_fl))
        rl = min(255, int(command.left_speed * config.comp_rl))
        fr = min(255, int(command.right_speed * config.comp_fr))
        rr = min(255, int(command.right_speed * config.comp_rr))

        return CompensatedCommand(
            fl_speed=fl, fl_dir=command.left_dir,
            fr_speed=fr, fr_dir=command.right_dir,
            rl_speed=rl, rl_dir=command.left_dir,
            rr_speed=rr, rr_dir=command.right_dir,
            duration_ms=command.duration_ms,
        )

    def execute_command(self, command: MotorCommand) -> None:
        """
        Execute a motor command with per-motor compensation.

        If duration_ms > 0, runs for that duration then stops.
        If duration_ms == 0, runs until next command or watchdog timeout.
        """
        if not self.initialized:
            logger.error("Motor controller not initialized")
            return

        self.last_command_time = time.time()
        comp = self._compensate_command(command)

        if self.simulate:
            logger.info(f"[SIM] Executing: FL={comp.fl_speed} FR={comp.fr_speed} "
                        f"RL={comp.rl_speed} RR={comp.rr_speed} "
                        f"dirs={comp.fl_dir.name},{comp.fr_dir.name} "
                        f"dur={comp.duration_ms}ms")
            if comp.duration_ms > 0:
                time.sleep(comp.duration_ms / 1000.0)
                logger.info("[SIM] Duration complete, stopping")
            return

        try:
            self._set_single_motor(config.fl_forward, config.fl_backward,
                                   config.fl_pwm, comp.fl_speed, comp.fl_dir)
            self._set_single_motor(config.fr_forward, config.fr_backward,
                                   config.fr_pwm, comp.fr_speed, comp.fr_dir)
            self._set_single_motor(config.rl_forward, config.rl_backward,
                                   config.rl_pwm, comp.rl_speed, comp.rl_dir)
            self._set_single_motor(config.rr_forward, config.rr_backward,
                                   config.rr_pwm, comp.rr_speed, comp.rr_dir)

            logger.debug(f"Executed: FL={comp.fl_speed} FR={comp.fr_speed} "
                         f"RL={comp.rl_speed} RR={comp.rr_speed}")

            if comp.duration_ms > 0:
                time.sleep(comp.duration_ms / 1000.0)
                self._stop_all_motors()
                logger.debug(f"Duration complete ({comp.duration_ms}ms), stopped")

        except Exception as e:
            logger.error(f"Error executing command: {e}")
            self.emergency_stop()

    def _set_single_motor(self, fwd_pin: int, bwd_pin: int,
                          pwm_pin: int, speed: int, direction: Direction) -> None:
        """Set a single motor's direction and speed."""
        if direction == Direction.FORWARD:
            GPIO.output(fwd_pin, GPIO.HIGH)
            GPIO.output(bwd_pin, GPIO.LOW)
        elif direction == Direction.BACKWARD:
            GPIO.output(fwd_pin, GPIO.LOW)
            GPIO.output(bwd_pin, GPIO.HIGH)
        else:  # STOP
            GPIO.output(fwd_pin, GPIO.LOW)
            GPIO.output(bwd_pin, GPIO.LOW)
            speed = 0

        duty_cycle = (speed / 255.0) * 100.0
        if pwm_pin in self.pwm_objects:
            self.pwm_objects[pwm_pin].ChangeDutyCycle(duty_cycle)

    def _set_motor_group(self,
                         forward_pins: list,
                         backward_pins: list,
                         pwm_pins: list,
                         speed: int,
                         direction: Direction) -> None:
        """Set a group of motors (used by emergency_stop and test_motors)."""
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
        else:
            for pin in forward_pins + backward_pins:
                GPIO.output(pin, GPIO.LOW)
            speed = 0

        duty_cycle = (speed / 255.0) * 100.0
        for pin in pwm_pins:
            if pin in self.pwm_objects:
                self.pwm_objects[pin].ChangeDutyCycle(duty_cycle)

    def _stop_all_motors(self) -> None:
        """Stop all motors (internal helper, no warning log)."""
        try:
            pins = [
                config.fl_forward, config.fl_backward,
                config.fr_forward, config.fr_backward,
                config.rl_forward, config.rl_backward,
                config.rr_forward, config.rr_backward,
            ]
            for pin in pins:
                GPIO.output(pin, GPIO.LOW)
            for pwm in self.pwm_objects.values():
                pwm.ChangeDutyCycle(0)
        except Exception as e:
            logger.error(f"Error stopping motors: {e}")

    def emergency_stop(self) -> None:
        """Immediately stop all motors."""
        logger.warning("EMERGENCY STOP")

        if self.simulate:
            logger.info("[SIM] All motors stopped")
            return

        try:
            pins = [
                config.fl_forward, config.fl_backward,
                config.fr_forward, config.fr_backward,
                config.rl_forward, config.rl_backward,
                config.rr_forward, config.rr_backward,
            ]
            for pin in pins:
                GPIO.output(pin, GPIO.LOW)
            for pwm in self.pwm_objects.values():
                pwm.ChangeDutyCycle(0)
        except Exception as e:
            logger.error(f"Error during emergency stop: {e}")

    def check_watchdog(self) -> None:
        """Stop motors if no command received within watchdog timeout."""
        if not self.initialized:
            return

        time_since_command = time.time() - self.last_command_time
        if time_since_command > config.watchdog_timeout:
            logger.warning(f"Watchdog timeout ({time_since_command:.1f}s) - stopping motors")
            self.emergency_stop()
            self.last_command_time = time.time()

    def test_motors(self) -> None:
        """Run a test sequence to verify motors work."""
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
