"""
Server configuration for AI Car Control System.
"""

import os
from dataclasses import dataclass


@dataclass
class ServerConfig:
    """Server configuration parameters."""

    # Network settings
    host: str = "0.0.0.0"  # Listen on all interfaces
    port: int = 5555
    max_connections: int = 1  # Only one car at a time for now

    # llama-swap settings
    llama_swap_url: str = "http://localhost:8200"
    model_name: str = "gemma-4-26b-a4b"
    temperature: float = 0.7
    max_new_tokens: int = 200  # Enough for proper command format
    inference_timeout: float = 30.0  # llama-swap needs time for cold load

    # Vision settings
    target_fps: int = 10  # Target frame processing rate
    frame_width: int = 640
    frame_height: int = 480

    # Control settings
    command_history_size: int = 100  # Number of past commands to keep
    emergency_stop_on_error: bool = True

    # Logging
    log_level: str = "INFO"
    log_commands: bool = True
    log_inference_time: bool = True
    save_debug_frames: bool = True
    debug_frame_dir: str = "./debug_frames"

    # Mapping settings
    map_file: str = "./map_data.json"
    enable_mapping: bool = True

    def __post_init__(self):
        """Validate configuration after initialization."""
        if self.save_debug_frames:
            os.makedirs(self.debug_frame_dir, exist_ok=True)


# Global config instance
config = ServerConfig()
