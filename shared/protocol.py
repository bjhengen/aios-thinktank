"""
Communication protocol definitions for AI Car Control System.

This module defines the binary protocol for communication between
the server (AI) and the Raspberry Pi (hardware proxy).
"""

import struct
from enum import IntEnum
from typing import Dict, Optional, Tuple
from dataclasses import dataclass, field


class Direction(IntEnum):
    """Motor direction values."""
    BACKWARD = 0
    FORWARD = 1
    STOP = 2


@dataclass
class MotorCommand:
    """
    Motor command for mecanum wheel control.

    Attributes:
        left_speed: Left side speed (0-255)
        right_speed: Right side speed (0-255)
        left_dir: Left side direction (Direction enum)
        right_dir: Right side direction (Direction enum)
        duration_ms: Duration in milliseconds (0 = run until next command)
    """
    left_speed: int
    right_speed: int
    left_dir: Direction
    right_dir: Direction
    duration_ms: int = 0  # 0 means run until next command

    def validate(self) -> None:
        """Validate command values are in acceptable ranges."""
        if not (0 <= self.left_speed <= 255):
            raise ValueError(f"Invalid left_speed: {self.left_speed}")
        if not (0 <= self.right_speed <= 255):
            raise ValueError(f"Invalid right_speed: {self.right_speed}")
        if self.left_dir not in Direction:
            raise ValueError(f"Invalid left_dir: {self.left_dir}")
        if self.right_dir not in Direction:
            raise ValueError(f"Invalid right_dir: {self.right_dir}")
        if not (0 <= self.duration_ms <= 65535):
            raise ValueError(f"Invalid duration_ms: {self.duration_ms}")

    def to_bytes(self) -> bytes:
        """
        Convert command to 6-byte binary format.

        Format: [left_speed, right_speed, left_dir, right_dir, duration_ms (2 bytes)]
        """
        self.validate()
        return struct.pack('>BBBBH',
                          self.left_speed,
                          self.right_speed,
                          self.left_dir.value,
                          self.right_dir.value,
                          self.duration_ms)

    @classmethod
    def from_bytes(cls, data: bytes) -> 'MotorCommand':
        """
        Parse command from 6-byte binary format.

        Args:
            data: 6 bytes containing motor command

        Returns:
            MotorCommand instance
        """
        if len(data) != 6:
            raise ValueError(f"Expected 6 bytes, got {len(data)}")

        left_speed, right_speed, left_dir, right_dir, duration_ms = struct.unpack('>BBBBH', data)
        return cls(
            left_speed=left_speed,
            right_speed=right_speed,
            left_dir=Direction(left_dir),
            right_dir=Direction(right_dir),
            duration_ms=duration_ms
        )

    @classmethod
    def stop(cls) -> 'MotorCommand':
        """Create a stop command (all motors stopped)."""
        return cls(0, 0, Direction.STOP, Direction.STOP, 0)

    @classmethod
    def forward(cls, speed: int = 200, duration_ms: int = 0) -> 'MotorCommand':
        """Create a forward movement command."""
        return cls(speed, speed, Direction.FORWARD, Direction.FORWARD, duration_ms)

    @classmethod
    def backward(cls, speed: int = 200, duration_ms: int = 0) -> 'MotorCommand':
        """Create a backward movement command."""
        return cls(speed, speed, Direction.BACKWARD, Direction.BACKWARD, duration_ms)

    @classmethod
    def rotate_left(cls, speed: int = 150, duration_ms: int = 0) -> 'MotorCommand':
        """Create a rotate left command."""
        return cls(speed, speed, Direction.BACKWARD, Direction.FORWARD, duration_ms)

    @classmethod
    def rotate_right(cls, speed: int = 150, duration_ms: int = 0) -> 'MotorCommand':
        """Create a rotate right command."""
        return cls(speed, speed, Direction.FORWARD, Direction.BACKWARD, duration_ms)


# Sensor data constants
SENSOR_MAGIC = b'\x53\x01'  # 'S' + version 1
SENSOR_HEADER_SIZE = 20  # 2 magic + 5*2 distances + 8 reserved
SENSOR_KEYS = ['fc', 'fl', 'fr', 'rl', 'rr']


@dataclass
class SensorData:
    """
    Ultrasonic sensor distances for 5 positions.

    Distances are stored in millimeters as uint16 (0 = invalid/no reading).
    Binary format (20 bytes): [2-byte magic 0x5301][5 x uint16 distances][8 bytes reserved]
    """
    fc: int = 0  # Front Center (mm, 0=invalid)
    fl: int = 0  # Front Left
    fr: int = 0  # Front Right
    rl: int = 0  # Rear Left
    rr: int = 0  # Rear Right

    def to_bytes(self) -> bytes:
        """Serialize to 20-byte binary format."""
        return struct.pack('>2s5H8x',
                           SENSOR_MAGIC,
                           self.fc, self.fl, self.fr, self.rl, self.rr)

    @classmethod
    def from_bytes(cls, data: bytes) -> 'SensorData':
        """Deserialize from 20-byte binary format."""
        if len(data) < SENSOR_HEADER_SIZE:
            raise ValueError(f"Expected {SENSOR_HEADER_SIZE} bytes, got {len(data)}")
        magic = data[:2]
        if magic != SENSOR_MAGIC:
            raise ValueError(f"Invalid sensor magic: {magic!r}")
        fc, fl, fr, rl, rr = struct.unpack('>5H', data[2:12])
        return cls(fc=fc, fl=fl, fr=fr, rl=rl, rr=rr)

    @classmethod
    def empty(cls) -> 'SensorData':
        """Create empty sensor data (all invalid)."""
        return cls()

    def to_dict(self) -> Dict[str, Optional[float]]:
        """Return distances in cm, None for invalid (0) readings."""
        result = {}
        for key in SENSOR_KEYS:
            mm = getattr(self, key)
            result[key] = round(mm / 10.0, 1) if mm > 0 else None
        return result


class FrameProtocol:
    """
    Protocol for camera frame transmission.

    Frame format:
        [4 bytes: frame_size (uint32, big-endian)]
        [frame_size bytes: JPEG data]
    """

    @staticmethod
    def encode_frame(jpeg_data: bytes) -> bytes:
        """
        Encode JPEG data with length header.

        Args:
            jpeg_data: JPEG-encoded image data

        Returns:
            Encoded frame with 4-byte size header
        """
        frame_size = len(jpeg_data)
        header = struct.pack('>I', frame_size)  # Big-endian uint32
        return header + jpeg_data

    @staticmethod
    def decode_frame_size(header: bytes) -> int:
        """
        Decode frame size from 4-byte header.

        Args:
            header: 4 bytes containing frame size

        Returns:
            Frame size in bytes
        """
        if len(header) != 4:
            raise ValueError(f"Expected 4 bytes for header, got {len(header)}")
        return struct.unpack('>I', header)[0]

    @staticmethod
    def encode_frame_with_sensors(jpeg_data: bytes, sensor_data: SensorData) -> bytes:
        """
        Encode JPEG data with sensor header.

        Wire format: [4-byte total_size][20-byte sensors][JPEG data]
        total_size = len(sensor_header) + len(jpeg_data)
        """
        sensor_bytes = sensor_data.to_bytes()
        payload = sensor_bytes + jpeg_data
        header = struct.pack('>I', len(payload))
        return header + payload

    @staticmethod
    def decode_frame_payload(data: bytes) -> Tuple[SensorData, bytes]:
        """
        Decode frame payload into sensor data and JPEG bytes.

        Checks for sensor magic bytes; falls back to plain JPEG if absent.
        """
        if len(data) >= SENSOR_HEADER_SIZE and data[:2] == SENSOR_MAGIC:
            sensor_data = SensorData.from_bytes(data[:SENSOR_HEADER_SIZE])
            jpeg_data = data[SENSOR_HEADER_SIZE:]
            return sensor_data, jpeg_data
        # Backward compatible: plain JPEG with no sensor header
        return SensorData.empty(), data


# Protocol constants
FRAME_HEADER_SIZE = 4
MAX_FRAME_SIZE = 10 * 1024 * 1024  # 10MB max frame size
COMMAND_SIZE = 6  # 4 bytes motor control + 2 bytes duration
DEFAULT_PORT = 5555
KEEPALIVE_INTERVAL = 5  # seconds
CONNECTION_TIMEOUT = 30  # seconds
