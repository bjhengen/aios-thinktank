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

    # AI Model settings
    model_name: str = "Qwen/Qwen2-VL-7B-Instruct"  # Or Qwen3-VL-8B when available
    model_device: str = "cuda"  # Use GPU
    max_context_length: int = 128000  # 128k context window
    temperature: float = 0.7
    max_new_tokens: int = 100  # Short responses for motor commands

    # Vision settings
    target_fps: int = 10  # Target frame processing rate
    frame_width: int = 640
    frame_height: int = 480

    # Control settings
    inference_timeout: float = 2.0  # Max time for AI inference
    command_history_size: int = 100  # Number of past commands to keep
    emergency_stop_on_error: bool = True

    # Logging
    log_level: str = "INFO"
    log_commands: bool = True
    log_inference_time: bool = True
    save_debug_frames: bool = False
    debug_frame_dir: str = "./debug_frames"

    def __post_init__(self):
        """Validate configuration after initialization."""
        if self.save_debug_frames:
            os.makedirs(self.debug_frame_dir, exist_ok=True)


# Global config instance
config = ServerConfig()
