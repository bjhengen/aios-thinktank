#!/usr/bin/env python3
"""
Test the communication protocol.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.protocol import MotorCommand, Direction, FrameProtocol


def test_motor_command():
    """Test motor command encoding/decoding."""
    print("Testing MotorCommand...")

    # Test basic command
    cmd = MotorCommand(200, 200, Direction.FORWARD, Direction.FORWARD)
    data = cmd.to_bytes()
    assert len(data) == 4, f"Expected 4 bytes, got {len(data)}"

    cmd2 = MotorCommand.from_bytes(data)
    assert cmd.left_speed == cmd2.left_speed
    assert cmd.right_speed == cmd2.right_speed
    assert cmd.left_dir == cmd2.left_dir
    assert cmd.right_dir == cmd2.right_dir

    print("  ✓ Basic encoding/decoding works")

    # Test helper methods
    forward = MotorCommand.forward(180)
    assert forward.left_speed == 180
    assert forward.right_speed == 180
    assert forward.left_dir == Direction.FORWARD
    assert forward.right_dir == Direction.FORWARD

    print("  ✓ Helper methods work")

    # Test validation
    try:
        bad_cmd = MotorCommand(300, 200, Direction.FORWARD, Direction.FORWARD)
        bad_cmd.validate()
        assert False, "Should have raised ValueError"
    except ValueError:
        print("  ✓ Validation works")

    print("MotorCommand tests passed!\n")


def test_frame_protocol():
    """Test frame encoding/decoding."""
    print("Testing FrameProtocol...")

    # Create fake JPEG data
    fake_jpeg = b'\xff\xd8\xff\xe0' + b'\x00' * 100 + b'\xff\xd9'

    # Encode
    encoded = FrameProtocol.encode_frame(fake_jpeg)
    assert len(encoded) == len(fake_jpeg) + 4

    # Decode size
    header = encoded[:4]
    size = FrameProtocol.decode_frame_size(header)
    assert size == len(fake_jpeg)

    # Extract data
    data = encoded[4:]
    assert data == fake_jpeg

    print("  ✓ Frame encoding/decoding works")
    print("FrameProtocol tests passed!\n")


if __name__ == "__main__":
    test_motor_command()
    test_frame_protocol()
    print("All protocol tests passed!")
