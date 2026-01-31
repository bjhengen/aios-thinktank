#!/usr/bin/env python3
"""
Main server control loop for AI Car Control System.

This is the main entry point for the server side. It:
1. Loads the vision model
2. Starts the network server
3. Receives camera frames
4. Generates motor commands using AI
5. Sends commands back to the car
"""

import sys
import time
import signal
from typing import Optional
import argparse

from server.vision_model import VisionModel
from server.network_server import NetworkServer
from server.command_generator import CommandGenerator, SimpleCommandParser
from server.config import config
from shared.protocol import MotorCommand
from shared.utils import setup_logging


logger = setup_logging(__name__)


class ServerController:
    """
    Main server controller that orchestrates all components.
    """

    def __init__(self, manual_mode: bool = False):
        """
        Initialize server controller.

        Args:
            manual_mode: If True, accept keyboard commands instead of AI
        """
        self.manual_mode = manual_mode
        self.vision_model = None if manual_mode else VisionModel()
        self.network_server = NetworkServer(config.host, config.port)
        self.command_generator = CommandGenerator()
        self.running = False

        logger.info(f"ServerController initialized (manual_mode={manual_mode})")

    def start(self) -> None:
        """Start the server and all components."""
        logger.info("Starting server...")

        # Load vision model if not in manual mode
        if not self.manual_mode:
            logger.info("Loading vision model (this may take a minute)...")
            self.vision_model.load()

        # Start network server
        self.network_server.start()

        self.running = True
        logger.info("Server started successfully")

    def stop(self) -> None:
        """Stop the server and cleanup."""
        logger.info("Stopping server...")
        self.running = False

        # Stop network server
        self.network_server.stop()

        # Unload model
        if self.vision_model:
            self.vision_model.unload()

        logger.info("Server stopped")

    def run_ai_control(self, goal: str) -> None:
        """
        Run AI-controlled mode.

        Args:
            goal: High-level goal for the AI (e.g., "explore forward")
        """
        if self.manual_mode:
            logger.error("Cannot run AI control in manual mode")
            return

        logger.info(f"Starting AI control with goal: '{goal}'")
        self.command_generator.set_goal(goal)

        frame_count = 0
        start_time = time.time()

        try:
            while self.running:
                # Get active connection
                conn = self.network_server.get_active_connection()
                if not conn:
                    logger.debug("Waiting for car connection...")
                    time.sleep(1.0)
                    continue

                # Get frame from car
                frame_data = conn.get_frame(timeout=0.5)
                if not frame_data:
                    continue

                frame_count += 1
                logger.info(f"Processing frame {frame_count} ({len(frame_data)} bytes)")

                # Build prompt
                prompt = self.command_generator.build_prompt(goal)

                # Process frame with AI
                try:
                    response = self.vision_model.process_with_history(
                        frame_data,
                        prompt,
                        max_history=3  # Keep last 3 exchanges for context
                    )
                    logger.info(f"AI Response: {response[:300]}...")  # Log first 300 chars

                    # Parse response to get structured output
                    parsed = self.command_generator.parse_response(response)

                    if parsed.command is None:
                        logger.warning("Failed to parse command, using fallback")
                        parsed.command = self.command_generator.get_safe_fallback_command()
                        parsed.reasoning = "Parse failed - emergency stop"

                    # Log the structured response
                    if parsed.observation:
                        logger.info(f"Observation: {parsed.observation[:100]}")
                    if parsed.assessment:
                        logger.info(f"Assessment: {parsed.assessment[:100]}")
                    logger.info(f"Command: {parsed.command}")
                    logger.info(f"Reasoning: {parsed.reasoning}")

                    # Send command to car
                    if conn.send_command(parsed.command):
                        self.command_generator.update_state(parsed)
                    else:
                        logger.error("Failed to send command")

                except Exception as e:
                    logger.error(f"Error processing frame: {e}")
                    # Send stop command on error
                    if config.emergency_stop_on_error:
                        conn.send_command(MotorCommand.stop())

                # Rate limiting
                elapsed = time.time() - start_time
                expected_frames = elapsed * config.target_fps
                if frame_count > expected_frames:
                    sleep_time = (frame_count - expected_frames) / config.target_fps
                    time.sleep(sleep_time)

        except KeyboardInterrupt:
            logger.info("AI control interrupted by user")
        finally:
            # Send final stop command
            conn = self.network_server.get_active_connection()
            if conn:
                conn.send_command(MotorCommand.stop())
                logger.info("Sent final stop command")

    def run_manual_control(self) -> None:
        """
        Run manual keyboard control mode.

        Accepts commands from stdin and sends them to the car.
        """
        logger.info("Starting manual control mode")
        logger.info("Commands: forward [speed], backward [speed], left [speed], right [speed], stop")
        logger.info("Or use numeric format: left_speed,right_speed,left_dir,right_dir")
        logger.info("Press Ctrl+C to exit")

        try:
            while self.running:
                # Get active connection
                conn = self.network_server.get_active_connection()
                if not conn:
                    logger.info("Waiting for car connection...")
                    time.sleep(1.0)
                    continue

                # Read command from stdin
                try:
                    print("\n> ", end='', flush=True)
                    command_str = input()

                    # Parse command
                    command = SimpleCommandParser.parse(command_str)
                    if command is None:
                        print("Invalid command. Try: forward 200, stop, left 150, etc.")
                        continue

                    # Send command
                    if conn.send_command(command):
                        print(f"Sent: {command}")
                    else:
                        print("Failed to send command")

                except EOFError:
                    break

        except KeyboardInterrupt:
            logger.info("Manual control interrupted by user")
        finally:
            # Send final stop command
            conn = self.network_server.get_active_connection()
            if conn:
                conn.send_command(MotorCommand.stop())
                logger.info("Sent final stop command")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="AI Car Control Server",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--manual',
        action='store_true',
        help='Run in manual control mode (keyboard input)'
    )

    parser.add_argument(
        '--goal',
        type=str,
        default='Explore the environment and avoid obstacles',
        help='Goal for AI control mode (default: explore)'
    )

    parser.add_argument(
        '--port',
        type=int,
        default=config.port,
        help=f'Server port (default: {config.port})'
    )

    parser.add_argument(
        '--host',
        type=str,
        default=config.host,
        help=f'Server host (default: {config.host})'
    )

    args = parser.parse_args()

    # Update config
    config.port = args.port
    config.host = args.host

    # Create controller
    controller = ServerController(manual_mode=args.manual)

    # Setup signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        logger.info("Received shutdown signal")
        controller.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Start server
        controller.start()

        # Run appropriate mode
        if args.manual:
            controller.run_manual_control()
        else:
            controller.run_ai_control(args.goal)

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        controller.stop()
        sys.exit(1)


if __name__ == "__main__":
    main()
