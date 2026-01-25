"""
Camera streamer for Raspberry Pi.

Captures frames from Pi Camera Module 3 and streams them to the server.
"""

import io
import time
from typing import Optional

try:
    from picamera2 import Picamera2
except ImportError:
    # Allow imports on non-Pi systems for development
    Picamera2 = None

from PIL import Image

from shared.protocol import FrameProtocol
from shared.utils import setup_logging
from pi.config import config


logger = setup_logging(__name__)


class CameraStreamer:
    """
    Handles camera capture and frame encoding.

    Uses Picamera2 for Pi Camera Module 3.
    """

    def __init__(self, simulate: bool = False):
        """
        Initialize camera streamer.

        Args:
            simulate: If True, generate test images instead of using camera
        """
        self.simulate = simulate or (Picamera2 is None)
        self.camera = None
        self.frame_count = 0
        self.start_time = time.time()

        if self.simulate:
            logger.warning("Running in SIMULATION mode - generating test images")
        else:
            logger.info("Initializing Pi Camera")

    def setup(self) -> None:
        """Set up camera for capture."""
        if self.simulate:
            logger.info("Simulated camera setup complete")
            return

        if Picamera2 is None:
            raise RuntimeError("picamera2 not available - are you on a Raspberry Pi?")

        try:
            self.camera = Picamera2()

            # Configure camera
            camera_config = self.camera.create_still_configuration(
                main={
                    "size": (config.camera_width, config.camera_height),
                    "format": "RGB888"
                }
            )
            self.camera.configure(camera_config)

            # Start camera
            self.camera.start()

            # Let camera warm up
            time.sleep(2)

            logger.info(f"Camera initialized: {config.camera_width}x{config.camera_height} @ {config.camera_fps} FPS")

        except Exception as e:
            logger.error(f"Failed to setup camera: {e}")
            raise

    def cleanup(self) -> None:
        """Clean up camera resources."""
        if self.simulate:
            return

        if self.camera:
            logger.info("Stopping camera")
            self.camera.stop()
            self.camera.close()
            self.camera = None

    def capture_frame(self) -> Optional[bytes]:
        """
        Capture a frame and encode as JPEG.

        Returns:
            JPEG-encoded frame data, or None on error
        """
        try:
            if self.simulate:
                return self._generate_test_frame()

            # Capture frame as numpy array
            frame = self.camera.capture_array()

            # Convert to PIL Image
            image = Image.fromarray(frame)

            # Encode as JPEG
            buffer = io.BytesIO()
            image.save(buffer, format='JPEG', quality=config.jpeg_quality)
            jpeg_data = buffer.getvalue()

            self.frame_count += 1

            if self.frame_count % 100 == 0:
                elapsed = time.time() - self.start_time
                fps = self.frame_count / elapsed
                logger.info(f"Captured {self.frame_count} frames ({fps:.1f} FPS avg)")

            return jpeg_data

        except Exception as e:
            logger.error(f"Error capturing frame: {e}")
            return None

    def _generate_test_frame(self) -> bytes:
        """
        Generate a test frame for simulation.

        Returns:
            JPEG-encoded test image
        """
        # Create a simple test pattern
        image = Image.new('RGB', (config.camera_width, config.camera_height), color='blue')

        # Add some text
        try:
            from PIL import ImageDraw, ImageFont
            draw = ImageDraw.Draw(image)

            # Draw frame counter
            text = f"Test Frame {self.frame_count}"
            draw.text((10, 10), text, fill='white')

            # Draw timestamp
            timestamp = time.strftime("%H:%M:%S")
            draw.text((10, 30), timestamp, fill='white')

        except Exception:
            pass  # Text drawing is optional

        # Encode as JPEG
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=config.jpeg_quality)
        jpeg_data = buffer.getvalue()

        self.frame_count += 1

        return jpeg_data

    def get_fps(self) -> float:
        """
        Get current average FPS.

        Returns:
            Average frames per second
        """
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            return self.frame_count / elapsed
        return 0.0
