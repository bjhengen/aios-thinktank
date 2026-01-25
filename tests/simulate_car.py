#!/usr/bin/env python3
"""
Simulate a car client for testing the server without real hardware.

This creates fake camera frames and connects to the server to test
the full pipeline without needing a Raspberry Pi.
"""

import sys
import os
import time
import socket
from PIL import Image, ImageDraw, ImageFont
import io

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.protocol import FrameProtocol, MotorCommand, COMMAND_SIZE
from shared.utils import setup_logging


logger = setup_logging(__name__)


class SimulatedCar:
    """Simulates a robot car for testing."""

    def __init__(self, server_host: str = "localhost", server_port: int = 5555):
        """
        Initialize simulated car.

        Args:
            server_host: Server hostname/IP
            server_port: Server port
        """
        self.server_host = server_host
        self.server_port = server_port
        self.socket = None
        self.frame_count = 0

    def connect(self) -> bool:
        """Connect to server."""
        try:
            logger.info(f"Connecting to {self.server_host}:{self.server_port}...")
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.server_host, self.server_port))
            logger.info("Connected successfully")
            return True
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False

    def generate_test_frame(self, width: int = 640, height: int = 480) -> bytes:
        """
        Generate a test frame with some visual content.

        Args:
            width: Frame width
            height: Frame height

        Returns:
            JPEG-encoded frame
        """
        # Create a colorful gradient
        image = Image.new('RGB', (width, height))
        draw = ImageDraw.Draw(image)

        # Draw gradient background
        for y in range(height):
            color_value = int(255 * (y / height))
            draw.line([(0, y), (width, y)], fill=(color_value, 100, 255 - color_value))

        # Draw some shapes to make it interesting
        draw.ellipse([100, 100, 200, 200], fill='yellow', outline='red')
        draw.rectangle([300, 200, 400, 350], fill='green', outline='white')

        # Add text overlay
        try:
            draw.text((10, 10), f"Frame {self.frame_count}", fill='white')
            draw.text((10, 30), time.strftime("%H:%M:%S"), fill='white')
            draw.text((10, 50), "Simulated Camera", fill='white')
        except Exception:
            pass  # Font rendering is optional

        # Encode as JPEG
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=85)
        return buffer.getvalue()

    def send_frame(self, jpeg_data: bytes) -> bool:
        """
        Send a frame to the server.

        Args:
            jpeg_data: JPEG-encoded frame

        Returns:
            True if sent successfully
        """
        try:
            frame_packet = FrameProtocol.encode_frame(jpeg_data)
            self.socket.sendall(frame_packet)
            self.frame_count += 1
            return True
        except Exception as e:
            logger.error(f"Failed to send frame: {e}")
            return False

    def receive_command(self, timeout: float = 0.1) -> MotorCommand:
        """
        Receive a command from the server.

        Args:
            timeout: Timeout in seconds

        Returns:
            MotorCommand or None
        """
        try:
            self.socket.settimeout(timeout)
            data = bytearray()
            while len(data) < COMMAND_SIZE:
                chunk = self.socket.recv(COMMAND_SIZE - len(data))
                if not chunk:
                    return None
                data.extend(chunk)

            command = MotorCommand.from_bytes(bytes(data))
            logger.info(f"Received command: {command}")
            return command

        except socket.timeout:
            return None
        except Exception as e:
            logger.error(f"Error receiving command: {e}")
            return None

    def run(self, fps: int = 10, duration: float = None):
        """
        Run simulation loop.

        Args:
            fps: Target frames per second
            duration: Run for this many seconds (None = forever)
        """
        logger.info(f"Starting simulation at {fps} FPS")

        frame_time = 1.0 / fps
        start_time = time.time()

        try:
            while True:
                loop_start = time.time()

                # Check duration
                if duration and (time.time() - start_time) > duration:
                    break

                # Generate and send frame
                frame = self.generate_test_frame()
                if not self.send_frame(frame):
                    logger.error("Failed to send frame, exiting")
                    break

                logger.debug(f"Sent frame {self.frame_count} ({len(frame)} bytes)")

                # Receive command
                command = self.receive_command(timeout=0.05)
                if command:
                    logger.info(f"  → Command: {command}")

                # Rate limiting
                elapsed = time.time() - loop_start
                if elapsed < frame_time:
                    time.sleep(frame_time - elapsed)

        except KeyboardInterrupt:
            logger.info("Simulation stopped by user")

        logger.info(f"Simulation complete. Sent {self.frame_count} frames")

    def close(self):
        """Close connection."""
        if self.socket:
            self.socket.close()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Simulate robot car for testing")
    parser.add_argument('--host', default='localhost', help='Server host')
    parser.add_argument('--port', type=int, default=5555, help='Server port')
    parser.add_argument('--fps', type=int, default=10, help='Target FPS')
    parser.add_argument('--duration', type=float, help='Run duration in seconds')

    args = parser.parse_args()

    car = SimulatedCar(args.host, args.port)

    try:
        if not car.connect():
            sys.exit(1)

        car.run(fps=args.fps, duration=args.duration)

    finally:
        car.close()


if __name__ == "__main__":
    main()
