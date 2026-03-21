#!/usr/bin/env python3
"""
Main Raspberry Pi hardware control script.

This is the main entry point for the Pi side. It:
1. Connects to the server
2. Captures camera frames
3. Reads ultrasonic sensors
4. Streams frames + sensor data to server
5. Receives motor commands
6. Executes motor commands with dead-RL compensation
"""

import sys
import time
import signal
import argparse

from pi.camera_streamer import CameraStreamer
from pi.motor_controller import MotorController
from pi.ultrasonic_sensors import UltrasonicSensors
from pi.network_client import NetworkClient
from pi.config import config
from shared.protocol import SensorData, Direction
from shared.utils import setup_logging


logger = setup_logging(__name__)


class CarHardware:
    """
    Main hardware controller for the robot car.

    Orchestrates camera, motors, sensors, and network communication.
    """

    def __init__(self, simulate: bool = False):
        self.simulate = simulate
        self.camera = CameraStreamer(simulate=simulate)
        self.motors = MotorController(simulate=simulate)
        self.sensors = UltrasonicSensors(simulate=simulate)
        self.network = NetworkClient()
        self.running = False

        logger.info(f"CarHardware initialized (simulate={simulate})")

    def setup(self) -> None:
        """Set up all hardware components."""
        logger.info("Setting up hardware...")

        try:
            self.camera.setup()
            self.motors.setup()
            self.sensors.setup()
            logger.info("Hardware setup complete")

        except Exception as e:
            logger.error(f"Hardware setup failed: {e}")
            raise

    def cleanup(self) -> None:
        """Clean up all hardware resources."""
        logger.info("Cleaning up hardware...")

        try:
            self.motors.emergency_stop()
            self.motors.cleanup()
        except Exception as e:
            logger.error(f"Error cleaning up motors: {e}")

        try:
            self.sensors.cleanup()
        except Exception as e:
            logger.error(f"Error cleaning up sensors: {e}")

        try:
            self.camera.cleanup()
        except Exception as e:
            logger.error(f"Error cleaning up camera: {e}")

        try:
            self.network.disconnect()
        except Exception as e:
            logger.error(f"Error disconnecting network: {e}")

        logger.info("Cleanup complete")

    def _read_sensors(self) -> SensorData:
        """Read all connected sensors and return SensorData."""
        readings = {}
        # Read FL, FR, RL, RR (skip FC — disconnected)
        for key in ['fl', 'fr', 'rl', 'rr']:
            reading = self.sensors.read_sensor(key.upper())
            if reading and reading.valid:
                readings[key] = int(reading.distance_cm * 10)  # cm → mm
            else:
                readings[key] = 0

        return SensorData(
            fc=0,  # FC disconnected
            fl=readings.get('fl', 0),
            fr=readings.get('fr', 0),
            rl=readings.get('rl', 0),
            rr=readings.get('rr', 0),
        )

    def _check_emergency_stop(self, sensor_data: SensorData, command) -> bool:
        """
        Check if we need to emergency-block a command based on sensor data.

        Returns True if the command should be blocked.
        """
        if command is None:
            return False

        stop_dist_mm = int(config.collision_stop_distance * 10)

        is_moving = (command.left_dir != Direction.STOP or
                     command.right_dir != Direction.STOP)

        if not is_moving:
            return False

        # Check front sensors for any command with forward component
        if command.left_dir == Direction.FORWARD or command.right_dir == Direction.FORWARD:
            front_readings = [sensor_data.fl, sensor_data.fr]
            for dist_mm in front_readings:
                if 0 < dist_mm < stop_dist_mm:
                    logger.warning(f"SENSOR BLOCK: Front obstacle at {dist_mm/10:.1f}cm — blocking movement")
                    self.motors.emergency_stop()
                    return True

        # Check rear sensors for any command with backward component
        if command.left_dir == Direction.BACKWARD or command.right_dir == Direction.BACKWARD:
            rear_readings = [sensor_data.rl, sensor_data.rr]
            for dist_mm in rear_readings:
                if 0 < dist_mm < stop_dist_mm:
                    logger.warning(f"SENSOR BLOCK: Rear obstacle at {dist_mm/10:.1f}cm — blocking movement")
                    self.motors.emergency_stop()
                    return True

        # For rotations (opposite directions), check ALL sensors
        is_rotation = (command.left_dir != command.right_dir and
                       command.left_dir != Direction.STOP and
                       command.right_dir != Direction.STOP)
        if is_rotation:
            all_readings = [sensor_data.fl, sensor_data.fr,
                            sensor_data.rl, sensor_data.rr]
            for dist_mm in all_readings:
                if 0 < dist_mm < stop_dist_mm:
                    logger.warning(f"SENSOR BLOCK: Obstacle at {dist_mm/10:.1f}cm — blocking rotation")
                    self.motors.emergency_stop()
                    return True

        return False

    def run(self) -> None:
        """
        Main control loop.

        Continuously:
        1. Read sensors
        2. Capture frame
        3. Send frame + sensor data to server
        4. Receive command
        5. Check emergency stop
        6. Execute command
        """
        logger.info("Starting main control loop")
        self.running = True

        logger.info("Connecting to server...")
        self.network.reconnect_loop()

        frame_count = 0
        last_fps_log = time.time()

        try:
            while self.running:
                if not self.network.is_connected():
                    logger.warning("Lost connection to server, reconnecting...")
                    self.motors.emergency_stop()
                    self.network.reconnect_loop()

                # Read sensors
                sensor_data = self._read_sensors()

                # Capture frame
                frame_data = self.camera.capture_frame()
                if frame_data is None:
                    logger.warning("Failed to capture frame")
                    time.sleep(0.1)
                    continue

                # Send frame with sensor data
                if not self.network.send_frame(frame_data, sensor_data=sensor_data):
                    logger.error("Failed to send frame")
                    continue

                frame_count += 1

                # Receive command from server
                command = self.network.receive_command(timeout=0.05)
                if command:
                    # Check sensor-based emergency stop before executing
                    if not self._check_emergency_stop(sensor_data, command):
                        self.motors.execute_command(command)

                # Check motor watchdog
                self.motors.check_watchdog()

                # Log FPS periodically
                if time.time() - last_fps_log > 10.0:
                    fps = self.camera.get_fps()
                    distances = sensor_data.to_dict()
                    active = {k: v for k, v in distances.items() if v is not None}
                    logger.info(f"FPS: {fps:.1f}, Frames: {frame_count}, Sensors: {active}")
                    last_fps_log = time.time()

                # Rate limiting
                time.sleep(1.0 / config.camera_fps)

        except KeyboardInterrupt:
            logger.info("Control loop interrupted by user")
        except Exception as e:
            logger.error(f"Error in control loop: {e}", exc_info=True)
        finally:
            self.running = False
            self.motors.emergency_stop()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="AI Car Hardware Control (Raspberry Pi)"
    )

    parser.add_argument(
        '--simulate',
        action='store_true',
        help='Run in simulation mode (no GPIO/camera)'
    )

    parser.add_argument(
        '--server',
        type=str,
        default=config.server_host,
        help=f'Server host (default: {config.server_host})'
    )

    parser.add_argument(
        '--port',
        type=int,
        default=config.server_port,
        help=f'Server port (default: {config.server_port})'
    )

    parser.add_argument(
        '--test-motors',
        action='store_true',
        help='Run motor test sequence and exit'
    )

    parser.add_argument(
        '--test-camera',
        action='store_true',
        help='Test camera capture and exit'
    )

    parser.add_argument(
        '--test-sensors',
        action='store_true',
        help='Test ultrasonic sensors and exit'
    )

    args = parser.parse_args()

    config.server_host = args.server
    config.server_port = args.port

    car = CarHardware(simulate=args.simulate)

    def signal_handler(sig, frame):
        logger.info("Received shutdown signal")
        car.running = False
        car.cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        car.setup()

        if args.test_motors:
            logger.info("Running motor test...")
            car.motors.test_motors()
            logger.info("Motor test complete")
            return

        if args.test_camera:
            logger.info("Testing camera capture...")
            for i in range(10):
                frame = car.camera.capture_frame()
                if frame:
                    logger.info(f"Captured frame {i+1}: {len(frame)} bytes")
                time.sleep(0.5)
            logger.info("Camera test complete")
            return

        if args.test_sensors:
            logger.info("Testing ultrasonic sensors...")
            for i in range(10):
                for key in ['FL', 'FR', 'RL', 'RR']:
                    reading = car.sensors.read_sensor(key)
                    if reading and reading.valid:
                        logger.info(f"  {key}: {reading.distance_cm:.1f} cm")
                    else:
                        logger.info(f"  {key}: no reading")
                logger.info(f"--- Reading {i+1}/10 ---")
                time.sleep(1.0)
            logger.info("Sensor test complete")
            return

        car.run()

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        car.cleanup()


if __name__ == "__main__":
    main()
