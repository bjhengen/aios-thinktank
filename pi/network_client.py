"""
Network client for Raspberry Pi.

Handles TCP connection to server, sending camera frames and receiving commands.
"""

import socket
import time
from typing import Optional, Callable

from shared.protocol import (
    FrameProtocol, MotorCommand, COMMAND_SIZE
)
from shared.utils import setup_logging
from pi.config import config


logger = setup_logging(__name__)


class NetworkClient:
    """
    TCP client that connects to the server.

    Sends camera frames and receives motor commands.
    """

    def __init__(self, host: str = None, port: int = None):
        """
        Initialize network client.

        Args:
            host: Server hostname/IP (default: from config)
            port: Server port (default: from config)
        """
        self.host = host or config.server_host
        self.port = port or config.server_port
        self.socket = None
        self.connected = False

        logger.info(f"NetworkClient initialized for {self.host}:{self.port}")

    def connect(self) -> bool:
        """
        Connect to the server.

        Returns:
            True if connected successfully
        """
        try:
            logger.info(f"Connecting to server at {self.host}:{self.port}...")

            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(config.connection_timeout)
            self.socket.connect((self.host, self.port))

            self.connected = True
            logger.info("Connected to server successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            self.connected = False
            if self.socket:
                try:
                    self.socket.close()
                except Exception:
                    pass
                self.socket = None
            return False

    def disconnect(self) -> None:
        """Disconnect from server."""
        logger.info("Disconnecting from server")
        self.connected = False

        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None

    def send_frame(self, jpeg_data: bytes) -> bool:
        """
        Send a camera frame to the server.

        Args:
            jpeg_data: JPEG-encoded image data

        Returns:
            True if sent successfully
        """
        if not self.connected or not self.socket:
            logger.error("Not connected to server")
            return False

        try:
            # Encode frame with protocol
            frame_packet = FrameProtocol.encode_frame(jpeg_data)

            # Send to server
            self.socket.sendall(frame_packet)

            logger.debug(f"Sent frame: {len(jpeg_data)} bytes")
            return True

        except Exception as e:
            logger.error(f"Error sending frame: {e}")
            self.connected = False
            return False

    def receive_command(self, timeout: float = 0.1) -> Optional[MotorCommand]:
        """
        Receive a motor command from the server.

        Args:
            timeout: Timeout in seconds (None = blocking)

        Returns:
            MotorCommand if received, None otherwise
        """
        if not self.connected or not self.socket:
            return None

        try:
            # Set timeout
            self.socket.settimeout(timeout)

            # Receive 4 bytes
            data = bytearray()
            while len(data) < COMMAND_SIZE:
                chunk = self.socket.recv(COMMAND_SIZE - len(data))
                if not chunk:
                    logger.warning("Server closed connection")
                    self.connected = False
                    return None
                data.extend(chunk)

            # Parse command
            command = MotorCommand.from_bytes(bytes(data))
            logger.debug(f"Received command: {command}")
            return command

        except socket.timeout:
            # This is normal - no command available
            return None
        except Exception as e:
            logger.error(f"Error receiving command: {e}")
            self.connected = False
            return None

    def is_connected(self) -> bool:
        """
        Check if connected to server.

        Returns:
            True if connected
        """
        return self.connected

    def reconnect_loop(self, retry_delay: float = None) -> None:
        """
        Keep trying to reconnect until successful.

        Args:
            retry_delay: Seconds between retry attempts (default: from config)
        """
        retry_delay = retry_delay or config.reconnect_delay

        while not self.connected:
            logger.info("Attempting to reconnect...")
            if self.connect():
                return
            logger.info(f"Reconnect failed, retrying in {retry_delay}s...")
            time.sleep(retry_delay)
