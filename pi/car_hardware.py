#!/usr/bin/env python3
"""
Main Raspberry Pi hardware control script.

This is the main entry point for the Pi side. It:
1. Connects to the server
2. Captures camera frames
3. Streams frames to server
4. Receives motor commands
5. Executes motor commands
"""

import sys
import time
import signal
import argparse

from pi.camera_streamer import CameraStreamer
from pi.motor_controller import MotorController
from pi.network_client import NetworkClient
from pi.config import config
from shared.utils import setup_logging


logger = setup_logging(__name__)


class CarHardware:
    """
    Main hardware controller for the robot car.

    Orchestrates camera, motors, and network communication.
    """

    def __init__(self, simulate: bool = False):
        """
        Initialize car hardware.

        Args:
            simulate: If True, run in simulation mode (no GPIO/camera)
        """
        self.simulate = simulate
        self.camera = CameraStreamer(simulate=simulate)
        self.motors = MotorController(simulate=simulate)
        self.network = NetworkClient()
        self.running = False

        logger.info(f"CarHardware initialized (simulate={simulate})")

    def setup(self) -> None:
        """Set up all hardware components."""
        logger.info("Setting up hardware...")

        try:
            # Setup camera
            self.camera.setup()

            # Setup motors
            self.motors.setup()

            # Test motors briefly
            if not self.simulate:
                logger.info("Running motor test (you should hear/see motors activate)")
                # Don't run full test, just verify setup worked
                # self.motors.test_motors()

            logger.info("Hardware setup complete")

        except Exception as e:
            logger.error(f"Hardware setup failed: {e}")
            raise

    def cleanup(self) -> None:
        """Clean up all hardware resources."""
        logger.info("Cleaning up hardware...")

        # Stop motors
        try:
            self.motors.emergency_stop()
            self.motors.cleanup()
        except Exception as e:
            logger.error(f"Error cleaning up motors: {e}")

        # Stop camera
        try:
            self.camera.cleanup()
        except Exception as e:
            logger.error(f"Error cleaning up camera: {e}")

        # Disconnect network
        try:
            self.network.disconnect()
        except Exception as e:
            logger.error(f"Error disconnecting network: {e}")

        logger.info("Cleanup complete")

    def run(self) -> None:
        """
        Main control loop.

        Continuously:
        1. Capture frame
        2. Send to server
        3. Receive command
        4. Execute command
        """
        logger.info("Starting main control loop")
        self.running = True

        # Connect to server
        logger.info("Connecting to server...")
        self.network.reconnect_loop()

        frame_count = 0
        last_fps_log = time.time()

        try:
            while self.running:
                # Check connection
                if not self.network.is_connected():
                    logger.warning("Lost connection to server, reconnecting...")
                    self.motors.emergency_stop()
                    self.network.reconnect_loop()

                # Capture frame
                frame_data = self.camera.capture_frame()
                if frame_data is None:
                    logger.warning("Failed to capture frame")
                    time.sleep(0.1)
                    continue

                # Send frame to server
                if not self.network.send_frame(frame_data):
                    logger.error("Failed to send frame")
                    continue

                frame_count += 1

                # Receive command(s) from server
                # Non-blocking receive with short timeout
                command = self.network.receive_command(timeout=0.05)
                if command:
                    self.motors.execute_command(command)

                # Check motor watchdog
                self.motors.check_watchdog()

                # Log FPS periodically
                if time.time() - last_fps_log > 10.0:
                    fps = self.camera.get_fps()
                    logger.info(f"Camera FPS: {fps:.1f}, Frames sent: {frame_count}")
                    last_fps_log = time.time()

                # Rate limiting to target FPS
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

    args = parser.parse_args()

    # Update config
    config.server_host = args.server
    config.server_port = args.port

    # Create car hardware
    car = CarHardware(simulate=args.simulate)

    # Setup signal handlers
    def signal_handler(sig, frame):
        logger.info("Received shutdown signal")
        car.running = False
        car.cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Setup hardware
        car.setup()

        # Run test modes if requested
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

        # Run main control loop
        car.run()

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        car.cleanup()


if __name__ == "__main__":
    main()
