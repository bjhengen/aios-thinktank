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
from server.map_manager import MapManager
from server.training_logger import TrainingLogger
from server.config import config
from shared.protocol import MotorCommand, Direction
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

        self.map_manager = None
        if not manual_mode and config.enable_mapping:
            self.map_manager = MapManager(config.map_file)

        self.training_logger = None if manual_mode else TrainingLogger()

        logger.info(f"ServerController initialized (manual_mode={manual_mode})")

    def start(self) -> None:
        """Start the server and all components."""
        logger.info("Starting server...")

        # Load vision model if not in manual mode
        if not self.manual_mode:
            logger.info("Loading vision model (this may take a minute)...")
            self.vision_model.load()

        if self.map_manager:
            self.map_manager.load()
            logger.info(f"Map loaded: {len(self.map_manager.nodes)} nodes, "
                        f"{len(self.map_manager.edges)} edges")

        # Start network server
        self.network_server.start()

        self.running = True
        logger.info("Server started successfully")

    def stop(self) -> None:
        """Stop the server and cleanup."""
        logger.info("Stopping server...")
        self.running = False

        if self.map_manager:
            self.map_manager.save()
            logger.info("Map saved")

        if self.training_logger:
            self.training_logger.close()

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
        current_location = ""
        pending_breadcrumb = []
        discovering_room = False

        try:
            while self.running:
                # Get active connection
                conn = self.network_server.get_active_connection()
                if not conn:
                    logger.debug("Waiting for car connection...")
                    time.sleep(1.0)
                    continue

                # Get frame from car (now returns tuple with sensor data)
                result = conn.get_frame(timeout=0.5)
                if not result:
                    continue

                sensor_data, frame_data = result
                frame_count += 1
                logger.info(f"Processing frame {frame_count} ({len(frame_data)} bytes)")

                # Log sensor readings if present
                distances = sensor_data.to_dict()
                if any(v is not None for v in distances.values()):
                    logger.debug(f"Sensors: {distances}")

                # Build prompt with sensor data and known locations
                known_locs = self.map_manager.get_known_locations() if self.map_manager else None
                prompt = self.command_generator.build_prompt(
                    goal, sensor_data=sensor_data,
                    known_locations=known_locs
                )

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

                    # Snapshot the raw model command for training-data provenance
                    command_before_overrides = parsed.command
                    overrides_applied = []

                    # Check for blind/collision reflex override
                    parsed = self.command_generator.check_and_override_if_blind(parsed)
                    if parsed.command is not command_before_overrides:
                        overrides_applied.append("blind_reflex")

                    # Stuck-streak escape: force rotate when model fixates on BWD/STOP
                    before_stuck = parsed.command
                    parsed = self.command_generator.check_and_override_if_stuck(parsed, sensor_data)
                    if parsed.command is not before_stuck:
                        overrides_applied.append("stuck_escape")

                    # Enforce speed/duration limits (catches reflex overrides too)
                    if parsed.command:
                        before_sanitize = parsed.command
                        parsed.command = self.command_generator._sanitize_command(parsed.command)
                        if parsed.command != before_sanitize:
                            overrides_applied.append("sanitize")

                    # Persist training record (fire-and-forget, never blocks control loop)
                    if self.training_logger:
                        try:
                            self.training_logger.log_frame(
                                frame_bytes=frame_data,
                                sensor_data=sensor_data,
                                prompt=prompt,
                                raw_response=response,
                                parsed_command_before_overrides=command_before_overrides,
                                final_command=parsed.command,
                                observation=parsed.observation,
                                assessment=parsed.assessment,
                                reasoning=parsed.reasoning,
                                location=parsed.location,
                                overrides_applied=overrides_applied,
                                goal=goal,
                                steps_taken=self.command_generator.state.steps_taken,
                            )
                        except Exception as e:
                            logger.warning(f"Training log failed (non-fatal): {e}")

                    # Log the structured response
                    if parsed.observation:
                        logger.info(f"Observation: {parsed.observation[:100]}")
                    if parsed.assessment:
                        logger.info(f"Assessment: {parsed.assessment[:100]}")
                    logger.info(f"Command: {parsed.command}")
                    logger.info(f"Reasoning: {parsed.reasoning}")

                    # Map integration
                    if self.map_manager and parsed.location:
                        if parsed.location == "unknown" and not discovering_room:
                            discovering_room = True
                            logger.info("Unknown location — will ask for room details")
                        elif parsed.location != "unknown":
                            discovering_room = False
                            if parsed.location != current_location:
                                # Transition detected
                                if current_location and pending_breadcrumb:
                                    self.map_manager.add_edge(
                                        current_location, parsed.location,
                                        pending_breadcrumb)
                                    logger.info(f"Map edge: {current_location} → {parsed.location}")
                                # Detect floor type from observation
                                obs_lower = (parsed.observation or "").lower()
                                if any(kw in obs_lower for kw in ["carpet", "rug"]):
                                    floor = "carpet"
                                elif any(kw in obs_lower for kw in ["tile", "laminate", "wood"]):
                                    floor = "tile"
                                else:
                                    floor = "unknown"
                                self.map_manager.add_node(
                                    parsed.location,
                                    parsed.location.replace("_", " ").title(),
                                    floor_type=floor)
                                current_location = parsed.location
                                pending_breadcrumb = []
                                logger.info(f"Location: {current_location}")

                    # Send command to car
                    if conn.send_command(parsed.command):
                        self.command_generator.update_state(parsed)
                        # Record breadcrumb for map traversal
                        if self.map_manager and parsed.command:
                            pending_breadcrumb.append({
                                "left_speed": parsed.command.left_speed,
                                "right_speed": parsed.command.right_speed,
                                "left_dir": parsed.command.left_dir.value,
                                "right_dir": parsed.command.right_dir.value,
                                "duration_ms": parsed.command.duration_ms,
                            })
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

    def run_goto(self, target: str) -> None:
        """Navigate to a named location using the map."""
        if not self.map_manager:
            logger.error("Mapping not enabled")
            return

        logger.info(f"Navigating to: {target}")

        # First, need to know where we are — run one AI frame
        # to get current location, then plan path
        path = None
        current = None
        conn = None

        try:
            while self.running:
                conn = self.network_server.get_active_connection()
                if not conn:
                    time.sleep(1.0)
                    continue

                result = conn.get_frame(timeout=0.5)
                if not result:
                    continue

                sensor_data, frame_data = result
                known_locs = self.map_manager.get_known_locations()
                prompt = self.command_generator.build_prompt(
                    f"Identify your current location",
                    sensor_data=sensor_data,
                    known_locations=known_locs)

                response = self.vision_model.process_frame(frame_data, prompt)
                parsed = self.command_generator.parse_response(response)

                if not parsed.location or parsed.location == "unknown":
                    logger.warning("Cannot determine current location, retrying...")
                    continue

                current = parsed.location
                logger.info(f"Current location: {current}")

                path = self.map_manager.get_path(current, target)
                if path is None:
                    logger.error(f"No route from {current} to {target}")
                    return

                logger.info(f"Route: {' → '.join(e.from_id for e in path)} → {target}")
                break

            # Execute breadcrumb trail for each edge
            if path is not None:
                for edge in path:
                    logger.info(f"Traversing: {edge.from_id} → {edge.to_id}")
                    for cmd_dict in edge.breadcrumb:
                        command = MotorCommand(
                            left_speed=cmd_dict["left_speed"],
                            right_speed=cmd_dict["right_speed"],
                            left_dir=Direction(cmd_dict["left_dir"]),
                            right_dir=Direction(cmd_dict["right_dir"]),
                            duration_ms=cmd_dict["duration_ms"],
                        )
                        conn = self.network_server.get_active_connection()
                        if conn:
                            conn.send_command(command)
                        if command.duration_ms > 0:
                            time.sleep(command.duration_ms / 1000.0 + 0.2)

                    logger.info(f"Arrived at: {edge.to_id}")

                logger.info(f"Navigation complete — arrived at {target}")

        except KeyboardInterrupt:
            logger.info("Navigation interrupted")
        finally:
            conn = self.network_server.get_active_connection()
            if conn:
                conn.send_command(MotorCommand.stop())


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

    parser.add_argument(
        '--goto',
        type=str,
        default=None,
        help='Navigate to a named location on the map'
    )

    parser.add_argument(
        '--home',
        action='store_true',
        help='Navigate back to starting location (alias for --goto office)'
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
        if args.goto:
            controller.run_goto(args.goto)
        elif args.home:
            controller.run_goto("office")
        elif args.manual:
            controller.run_manual_control()
        else:
            controller.run_ai_control(args.goal)

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        controller.stop()
        sys.exit(1)


if __name__ == "__main__":
    main()
