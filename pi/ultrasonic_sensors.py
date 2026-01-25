"""
Ultrasonic sensor array for obstacle detection.

Uses 5x HC-SR04 sensors via TXS0108E level shifter:
- FC: Front Center
- FL: Front Left (angled 45°)
- FR: Front Right (angled 45°)
- RL: Rear Left
- RR: Rear Right
"""

import time
from typing import Dict, Optional
from dataclasses import dataclass

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None

from pi.config import config
from shared.utils import setup_logging


logger = setup_logging(__name__)


@dataclass
class SensorReading:
    """A single sensor reading."""
    distance_cm: float
    valid: bool
    timestamp: float


class UltrasonicSensors:
    """
    Manages 5 HC-SR04 ultrasonic sensors for obstacle detection.

    ECHO pins must go through a level shifter (5V → 3.3V).
    TRIG pins can connect directly to Pi GPIO (3.3V triggers the sensor fine).
    """

    SENSORS = {
        "FC": {"trig": config.ultrasonic_fc_trig, "echo": config.ultrasonic_fc_echo, "name": "Front Center"},
        "FL": {"trig": config.ultrasonic_fl_trig, "echo": config.ultrasonic_fl_echo, "name": "Front Left"},
        "FR": {"trig": config.ultrasonic_fr_trig, "echo": config.ultrasonic_fr_echo, "name": "Front Right"},
        "RL": {"trig": config.ultrasonic_rl_trig, "echo": config.ultrasonic_rl_echo, "name": "Rear Left"},
        "RR": {"trig": config.ultrasonic_rr_trig, "echo": config.ultrasonic_rr_echo, "name": "Rear Right"},
    }

    # Speed of sound at ~20°C in cm/μs
    SPEED_OF_SOUND_CM_US = 0.0343

    def __init__(self, simulate: bool = False):
        """
        Initialize ultrasonic sensor array.

        Args:
            simulate: If True, return fake readings (for testing without hardware)
        """
        self.simulate = simulate or (GPIO is None)
        self.initialized = False
        self.last_readings: Dict[str, SensorReading] = {}

        if self.simulate:
            logger.warning("Ultrasonic sensors in SIMULATION mode")
        else:
            logger.info("Initializing ultrasonic sensor array")

    def setup(self) -> None:
        """Set up GPIO pins for all sensors."""
        if self.simulate:
            logger.info("Simulated ultrasonic setup complete")
            self.initialized = True
            return

        if GPIO is None:
            raise RuntimeError("RPi.GPIO not available")

        try:
            # GPIO mode should already be set by motor controller
            # but set it just in case we're running standalone
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)

            for key, sensor in self.SENSORS.items():
                # TRIG is output
                GPIO.setup(sensor["trig"], GPIO.OUT)
                GPIO.output(sensor["trig"], GPIO.LOW)

                # ECHO is input (through level shifter)
                GPIO.setup(sensor["echo"], GPIO.IN)

                logger.debug(f"Configured {sensor['name']}: TRIG={sensor['trig']}, ECHO={sensor['echo']}")

            # Let sensors settle
            time.sleep(0.1)

            self.initialized = True
            logger.info("Ultrasonic sensors initialized")

        except Exception as e:
            logger.error(f"Failed to setup ultrasonic sensors: {e}")
            raise

    def cleanup(self) -> None:
        """Clean up GPIO resources."""
        if self.simulate:
            return

        # Note: Don't call GPIO.cleanup() here as motors may still be using GPIO
        # Just ensure TRIG pins are LOW
        for sensor in self.SENSORS.values():
            try:
                GPIO.output(sensor["trig"], GPIO.LOW)
            except Exception:
                pass

        self.initialized = False
        logger.info("Ultrasonic sensors cleaned up")

    def read_sensor(self, key: str) -> SensorReading:
        """
        Read distance from a single sensor.

        Args:
            key: Sensor key (FC, FL, FR, RL, RR)

        Returns:
            SensorReading with distance in cm
        """
        timestamp = time.time()

        if self.simulate:
            # Return simulated reading (random-ish based on sensor)
            import random
            fake_distance = 50.0 + random.uniform(-20, 100)
            return SensorReading(
                distance_cm=max(config.ultrasonic_min_distance,
                               min(fake_distance, config.ultrasonic_max_distance)),
                valid=True,
                timestamp=timestamp
            )

        if not self.initialized:
            return SensorReading(distance_cm=0, valid=False, timestamp=timestamp)

        sensor = self.SENSORS.get(key)
        if not sensor:
            logger.error(f"Unknown sensor: {key}")
            return SensorReading(distance_cm=0, valid=False, timestamp=timestamp)

        trig_pin = sensor["trig"]
        echo_pin = sensor["echo"]

        try:
            # Send 10μs trigger pulse
            GPIO.output(trig_pin, GPIO.HIGH)
            time.sleep(0.00001)  # 10μs
            GPIO.output(trig_pin, GPIO.LOW)

            # Wait for echo to start (with timeout)
            pulse_start = time.time()
            timeout_start = pulse_start

            while GPIO.input(echo_pin) == GPIO.LOW:
                pulse_start = time.time()
                if pulse_start - timeout_start > config.ultrasonic_timeout:
                    return SensorReading(distance_cm=0, valid=False, timestamp=timestamp)

            # Wait for echo to end (with timeout)
            pulse_end = pulse_start
            while GPIO.input(echo_pin) == GPIO.HIGH:
                pulse_end = time.time()
                if pulse_end - pulse_start > config.ultrasonic_timeout:
                    return SensorReading(distance_cm=0, valid=False, timestamp=timestamp)

            # Calculate distance
            pulse_duration = pulse_end - pulse_start
            distance_cm = (pulse_duration * 1_000_000 * self.SPEED_OF_SOUND_CM_US) / 2

            # Validate range
            if distance_cm < config.ultrasonic_min_distance:
                return SensorReading(distance_cm=distance_cm, valid=False, timestamp=timestamp)
            if distance_cm > config.ultrasonic_max_distance:
                return SensorReading(distance_cm=config.ultrasonic_max_distance, valid=False, timestamp=timestamp)

            return SensorReading(distance_cm=distance_cm, valid=True, timestamp=timestamp)

        except Exception as e:
            logger.error(f"Error reading sensor {key}: {e}")
            return SensorReading(distance_cm=0, valid=False, timestamp=timestamp)

    def read_all(self) -> Dict[str, SensorReading]:
        """
        Read all sensors sequentially.

        Returns:
            Dict mapping sensor key to SensorReading
        """
        readings = {}
        for key in self.SENSORS:
            readings[key] = self.read_sensor(key)
            # Small delay between readings to avoid interference
            time.sleep(0.01)

        self.last_readings = readings
        return readings

    def read_front(self) -> Dict[str, SensorReading]:
        """Read only front-facing sensors (FC, FL, FR)."""
        readings = {}
        for key in ["FC", "FL", "FR"]:
            readings[key] = self.read_sensor(key)
            time.sleep(0.01)
        return readings

    def read_rear(self) -> Dict[str, SensorReading]:
        """Read only rear-facing sensors (RL, RR)."""
        readings = {}
        for key in ["RL", "RR"]:
            readings[key] = self.read_sensor(key)
            time.sleep(0.01)
        return readings

    def get_min_front_distance(self) -> float:
        """Get minimum distance from front sensors."""
        readings = self.read_front()
        valid_distances = [r.distance_cm for r in readings.values() if r.valid]
        if valid_distances:
            return min(valid_distances)
        return config.ultrasonic_max_distance

    def get_min_rear_distance(self) -> float:
        """Get minimum distance from rear sensors."""
        readings = self.read_rear()
        valid_distances = [r.distance_cm for r in readings.values() if r.valid]
        if valid_distances:
            return min(valid_distances)
        return config.ultrasonic_max_distance

    def check_collision_risk(self, direction: str = "forward") -> bool:
        """
        Check if there's a collision risk in the given direction.

        Args:
            direction: "forward" or "backward"

        Returns:
            True if obstacle is closer than collision_stop_distance
        """
        if direction == "forward":
            min_dist = self.get_min_front_distance()
        else:
            min_dist = self.get_min_rear_distance()

        return min_dist < config.collision_stop_distance

    def get_readings_summary(self) -> str:
        """Get a formatted summary of all sensor readings."""
        readings = self.read_all()
        lines = []
        for key, reading in readings.items():
            name = self.SENSORS[key]["name"]
            if reading.valid:
                lines.append(f"{name}: {reading.distance_cm:.1f} cm")
            else:
                lines.append(f"{name}: --")
        return " | ".join(lines)


def test_sensors():
    """Test all ultrasonic sensors."""
    print("Ultrasonic Sensor Test")
    print("=" * 50)

    sensors = UltrasonicSensors()
    sensors.setup()

    try:
        for i in range(10):
            print(f"\nReading {i+1}:")
            print(sensors.get_readings_summary())
            time.sleep(0.5)
    finally:
        sensors.cleanup()


if __name__ == "__main__":
    test_sensors()
