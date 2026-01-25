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
    # Motor Driver #1 (Front Left + Rear Left)
    fl_forward: int = 17
    fl_backward: int = 27
    fl_pwm: int = 12
    rl_forward: int = 22
    rl_backward: int = 23
    rl_pwm: int = 13

    # Motor Driver #2 (Front Right + Rear Right)
    fr_forward: int = 6   # swapped fwd/bwd for correct direction
    fr_backward: int = 5
    fr_pwm: int = 18
    rr_forward: int = 26  # swapped fwd/bwd for correct direction
    rr_backward: int = 16
    rr_pwm: int = 19

    # PWM frequency for motor control
    pwm_frequency: int = 1000  # 1kHz

    # Ultrasonic sensors (HC-SR04)
    # ECHO pins go through TXS0108E level shifter (5V → 3.3V)
    # Sensor positions: FC=Front Center, FL/FR=Front corners, RL/RR=Rear corners
    ultrasonic_fc_trig: int = 4
    ultrasonic_fc_echo: int = 24
    ultrasonic_fl_trig: int = 7
    ultrasonic_fl_echo: int = 25
    ultrasonic_fr_trig: int = 8
    ultrasonic_fr_echo: int = 20
    ultrasonic_rl_trig: int = 9
    ultrasonic_rl_echo: int = 14
    ultrasonic_rr_trig: int = 10
    ultrasonic_rr_echo: int = 15

    # Ultrasonic settings
    ultrasonic_timeout: float = 0.04  # 40ms timeout (~7m max range)
    ultrasonic_min_distance: float = 2.0  # cm - closer readings are unreliable
    ultrasonic_max_distance: float = 400.0  # cm - max rated range

    # Safety settings
    watchdog_timeout: float = 1.0  # Stop motors if no command for this long
    emergency_stop_gpio: int = 21  # GPIO pin for emergency stop button (optional)
    collision_stop_distance: float = 15.0  # cm - emergency stop if obstacle closer

    # Logging
    log_level: str = "INFO"


# Global config instance
config = PiConfig()
