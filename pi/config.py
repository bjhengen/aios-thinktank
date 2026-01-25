"""
Raspberry Pi configuration for AI Car Control System.
"""

from dataclasses import dataclass


@dataclass
class PiConfig:
    """Raspberry Pi configuration parameters."""

    # Server connection
    server_host: str = "192.168.1.100"  # UPDATE THIS to your server's IP
    server_port: int = 5555
    reconnect_delay: float = 5.0  # seconds between reconnection attempts
    connection_timeout: float = 10.0

    # Camera settings
    camera_width: int = 640
    camera_height: int = 480
    camera_fps: int = 10
    jpeg_quality: int = 80  # 0-100, lower = smaller files but worse quality

    # Motor settings (GPIO pins)
    # Motor Driver #1 (Front Left + Front Right)
    fl_forward: int = 17
    fl_backward: int = 27
    fr_forward: int = 22
    fr_backward: int = 23
    fl_pwm: int = 12
    fr_pwm: int = 13

    # Motor Driver #2 (Rear Left + Rear Right)
    rl_forward: int = 5
    rl_backward: int = 6
    rr_forward: int = 16
    rr_backward: int = 26
    rl_pwm: int = 18
    rr_pwm: int = 19

    # PWM frequency for motor control
    pwm_frequency: int = 1000  # 1kHz

    # Safety settings
    watchdog_timeout: float = 1.0  # Stop motors if no command for this long
    emergency_stop_gpio: int = 21  # GPIO pin for emergency stop button (optional)

    # Logging
    log_level: str = "INFO"


# Global config instance
config = PiConfig()
