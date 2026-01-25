"""
TCP server for receiving camera frames and sending motor commands.

Handles the network communication between the server (AI) and the
Raspberry Pi (hardware proxy).
"""

import socket
import threading
import time
from typing import Optional, Callable
from queue import Queue, Empty

from shared.protocol import (
    FrameProtocol, MotorCommand, FRAME_HEADER_SIZE,
    MAX_FRAME_SIZE, COMMAND_SIZE, DEFAULT_PORT
)
from shared.utils import setup_logging
from server.config import config


logger = setup_logging(__name__)


class CarConnection:
    """
    Manages a single connection to a robot car.

    Handles bidirectional communication:
    - Receiving camera frames from the car
    - Sending motor commands to the car
    """

    def __init__(self, conn: socket.socket, addr: tuple):
        """
        Initialize connection handler.

        Args:
            conn: Socket connection
            addr: Client address (ip, port)
        """
        self.conn = conn
        self.addr = addr
        self.running = False
        self.last_frame_time = time.time()
        self.frame_queue = Queue(maxsize=2)  # Buffer up to 2 frames
        self.receive_thread = None

        logger.info(f"New connection from {addr}")

    def start(self) -> None:
        """Start receiving frames in background thread."""
        self.running = True
        self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.receive_thread.start()
        logger.info(f"Started receive thread for {self.addr}")

    def stop(self) -> None:
        """Stop receiving and close connection."""
        self.running = False
        if self.receive_thread:
            self.receive_thread.join(timeout=2.0)
        try:
            self.conn.close()
        except Exception:
            pass
        logger.info(f"Connection closed for {self.addr}")

    def _receive_loop(self) -> None:
        """Background thread for receiving frames."""
        try:
            while self.running:
                # Receive frame header (4 bytes)
                header = self._recv_exact(FRAME_HEADER_SIZE)
                if not header:
                    logger.warning("Connection closed by client")
                    break

                # Decode frame size
                frame_size = FrameProtocol.decode_frame_size(header)

                # Validate frame size
                if frame_size > MAX_FRAME_SIZE:
                    logger.error(f"Frame size too large: {frame_size} bytes")
                    break

                # Receive frame data
                frame_data = self._recv_exact(frame_size)
                if not frame_data:
                    logger.warning("Connection closed while receiving frame")
                    break

                # Add to queue (drop oldest if full)
                try:
                    self.frame_queue.put_nowait(frame_data)
                except:
                    # Queue full, drop oldest and add new
                    try:
                        self.frame_queue.get_nowait()
                    except Empty:
                        pass
                    self.frame_queue.put_nowait(frame_data)

                self.last_frame_time = time.time()

        except Exception as e:
            logger.error(f"Error in receive loop: {e}")
        finally:
            self.running = False

    def _recv_exact(self, n: int) -> Optional[bytes]:
        """
        Receive exactly n bytes from socket.

        Args:
            n: Number of bytes to receive

        Returns:
            Received bytes, or None if connection closed
        """
        data = bytearray()
        while len(data) < n:
            try:
                chunk = self.conn.recv(n - len(data))
                if not chunk:
                    return None
                data.extend(chunk)
            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"Error receiving data: {e}")
                return None
        return bytes(data)

    def get_frame(self, timeout: float = 0.1) -> Optional[bytes]:
        """
        Get the next frame from the queue.

        Args:
            timeout: Maximum time to wait for a frame

        Returns:
            JPEG frame data, or None if no frame available
        """
        try:
            return self.frame_queue.get(timeout=timeout)
        except Empty:
            return None

    def send_command(self, command: MotorCommand) -> bool:
        """
        Send a motor command to the car.

        Args:
            command: MotorCommand to send

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            command_bytes = command.to_bytes()
            self.conn.sendall(command_bytes)

            if config.log_commands:
                logger.debug(f"Sent command: {command}")

            return True
        except Exception as e:
            logger.error(f"Error sending command: {e}")
            return False

    def is_alive(self) -> bool:
        """
        Check if connection is still alive.

        Returns:
            True if connection is active
        """
        return self.running


class NetworkServer:
    """
    TCP server that accepts connections from robot cars.

    Manages multiple car connections and provides a simple interface
    for frame reception and command transmission.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = DEFAULT_PORT):
        """
        Initialize network server.

        Args:
            host: Host address to bind to
            port: Port to listen on
        """
        self.host = host
        self.port = port
        self.server_socket = None
        self.running = False
        self.accept_thread = None
        self.connections = []
        self.lock = threading.Lock()

        logger.info(f"NetworkServer initialized on {host}:{port}")

    def start(self) -> None:
        """Start the server and begin accepting connections."""
        # Create server socket
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(config.max_connections)
        self.server_socket.settimeout(1.0)  # Timeout for accept()

        self.running = True

        # Start accept thread
        self.accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self.accept_thread.start()

        logger.info(f"Server listening on {self.host}:{self.port}")

    def stop(self) -> None:
        """Stop the server and close all connections."""
        logger.info("Stopping server...")
        self.running = False

        # Close all connections
        with self.lock:
            for conn in self.connections:
                conn.stop()
            self.connections.clear()

        # Close server socket
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass

        # Wait for accept thread
        if self.accept_thread:
            self.accept_thread.join(timeout=2.0)

        logger.info("Server stopped")

    def _accept_loop(self) -> None:
        """Background thread for accepting connections."""
        while self.running:
            try:
                conn, addr = self.server_socket.accept()
                conn.settimeout(10.0)  # 10s timeout for recv operations

                # Create and start connection handler
                car_conn = CarConnection(conn, addr)
                car_conn.start()

                with self.lock:
                    # Remove dead connections
                    self.connections = [c for c in self.connections if c.is_alive()]

                    # Add new connection
                    self.connections.append(car_conn)

                    logger.info(f"Active connections: {len(self.connections)}")

            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"Error accepting connection: {e}")

    def get_active_connection(self) -> Optional[CarConnection]:
        """
        Get the first active car connection.

        Returns:
            CarConnection instance, or None if no active connections
        """
        with self.lock:
            # Remove dead connections
            self.connections = [c for c in self.connections if c.is_alive()]

            if self.connections:
                return self.connections[0]
            return None

    def broadcast_command(self, command: MotorCommand) -> int:
        """
        Send a command to all connected cars.

        Args:
            command: MotorCommand to broadcast

        Returns:
            Number of cars that received the command
        """
        count = 0
        with self.lock:
            for conn in self.connections:
                if conn.send_command(command):
                    count += 1
        return count
