"""
Command generator - converts AI vision responses to motor commands.

This module handles:
1. Prompt engineering for the vision model
2. Parsing AI responses to extract motor commands
3. Validating and sanitizing commands
"""

import re
from typing import Optional, Tuple
from dataclasses import dataclass

from shared.protocol import MotorCommand, Direction
from shared.utils import setup_logging


logger = setup_logging(__name__)


@dataclass
class ControlState:
    """Current control state and context."""
    current_goal: str = ""
    last_command: Optional[MotorCommand] = None
    last_reasoning: str = ""
    steps_taken: int = 0
    obstacles_detected: int = 0


class CommandGenerator:
    """
    Generates motor commands from vision model responses.

    Handles prompt construction and response parsing.
    """

    def __init__(self):
        """Initialize command generator."""
        self.state = ControlState()
        logger.info("CommandGenerator initialized")

    def build_prompt(self, goal: str, include_examples: bool = True) -> str:
        """
        Build a prompt for the vision model.

        Args:
            goal: High-level goal (e.g., "find the kitchen")
            include_examples: Whether to include example commands

        Returns:
            Formatted prompt string
        """
        prompt = f"""You are controlling a robot car with mecanum wheels via camera vision.

CURRENT GOAL: {goal}

You can see through the camera. Analyze the image and decide what motor action to take next.

MOTOR CONTROL:
You control 4 wheels using left/right motor groups:
- left_speed: 0-255 (0=stop, 255=max)
- right_speed: 0-255 (0=stop, 255=max)
- left_dir: 0=backward, 1=forward, 2=stop
- right_dir: 0=backward, 1=forward, 2=stop

OUTPUT FORMAT (REQUIRED):
COMMAND: <left_speed>,<right_speed>,<left_dir>,<right_dir>
REASONING: <brief explanation of why you chose this action>
"""

        if include_examples:
            prompt += """
EXAMPLE COMMANDS:
- Forward: COMMAND: 200,200,1,1
- Backward: COMMAND: 200,200,0,0
- Rotate left (turn in place): COMMAND: 150,150,0,1
- Rotate right (turn in place): COMMAND: 150,150,1,0
- Stop: COMMAND: 0,0,2,2
- Gentle left turn while moving: COMMAND: 100,180,1,1
- Gentle right turn while moving: COMMAND: 180,100,1,1

MECANUM WHEEL NOTES:
- This car has mecanum wheels (omnidirectional movement capable)
- You can experiment with different motor patterns
- The wheels can enable diagonal movement and strafing
- Try different speed combinations to discover new movement patterns
"""

        if self.state.last_command:
            prompt += f"\nPREVIOUS COMMAND: {self._command_to_string(self.state.last_command)}"
            if self.state.last_reasoning:
                prompt += f"\nPREVIOUS REASONING: {self.state.last_reasoning}"

        prompt += f"\n\nSTEPS TAKEN: {self.state.steps_taken}"

        prompt += "\n\nAnalyze the image and provide your decision in the required format."

        return prompt

    def parse_response(self, response: str) -> Tuple[Optional[MotorCommand], str]:
        """
        Parse AI response to extract motor command and reasoning.

        Args:
            response: Raw text response from vision model

        Returns:
            Tuple of (MotorCommand or None, reasoning string)
        """
        command = None
        reasoning = ""

        # Extract command line
        command_match = re.search(r'COMMAND:\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)', response)
        if command_match:
            try:
                left_speed = int(command_match.group(1))
                right_speed = int(command_match.group(2))
                left_dir = int(command_match.group(3))
                right_dir = int(command_match.group(4))

                # Clamp values to valid ranges
                left_speed = max(0, min(255, left_speed))
                right_speed = max(0, min(255, right_speed))
                left_dir = max(0, min(2, left_dir))
                right_dir = max(0, min(2, right_dir))

                command = MotorCommand(
                    left_speed=left_speed,
                    right_speed=right_speed,
                    left_dir=Direction(left_dir),
                    right_dir=Direction(right_dir)
                )
                logger.debug(f"Parsed command: {command}")

            except Exception as e:
                logger.error(f"Error parsing command: {e}")

        # Extract reasoning
        reasoning_match = re.search(r'REASONING:\s*(.+?)(?:\n|$)', response, re.IGNORECASE)
        if reasoning_match:
            reasoning = reasoning_match.group(1).strip()

        # If no structured response found, try to extract any numbers
        if command is None:
            logger.warning("No COMMAND: format found, attempting fallback parsing")
            numbers = re.findall(r'\b(\d+)\b', response)
            if len(numbers) >= 4:
                try:
                    command = MotorCommand(
                        left_speed=max(0, min(255, int(numbers[0]))),
                        right_speed=max(0, min(255, int(numbers[1]))),
                        left_dir=Direction(max(0, min(2, int(numbers[2])))),
                        right_dir=Direction(max(0, min(2, int(numbers[3]))))
                    )
                    logger.info(f"Fallback parsing succeeded: {command}")
                except Exception as e:
                    logger.error(f"Fallback parsing failed: {e}")

        return command, reasoning

    def update_state(self, command: MotorCommand, reasoning: str) -> None:
        """
        Update control state with latest command.

        Args:
            command: The executed motor command
            reasoning: AI's reasoning for the command
        """
        self.state.last_command = command
        self.state.last_reasoning = reasoning
        self.state.steps_taken += 1

    def set_goal(self, goal: str) -> None:
        """
        Set a new goal and reset state.

        Args:
            goal: New goal description
        """
        logger.info(f"New goal set: {goal}")
        self.state.current_goal = goal
        self.state.last_command = None
        self.state.last_reasoning = ""
        self.state.steps_taken = 0
        self.state.obstacles_detected = 0

    def get_safe_fallback_command(self) -> MotorCommand:
        """
        Get a safe fallback command when parsing fails.

        Returns:
            Safe stop command
        """
        logger.warning("Using safe fallback command (STOP)")
        return MotorCommand.stop()

    def _command_to_string(self, command: MotorCommand) -> str:
        """
        Convert MotorCommand to readable string.

        Args:
            command: MotorCommand to convert

        Returns:
            Human-readable string
        """
        return f"{command.left_speed},{command.right_speed},{command.left_dir.value},{command.right_dir.value}"


class SimpleCommandParser:
    """
    Simple command parser for manual control and testing.

    Allows human-readable commands like "forward 200", "rotate left 150", etc.
    """

    @staticmethod
    def parse(command_str: str) -> Optional[MotorCommand]:
        """
        Parse a simple text command.

        Args:
            command_str: Command string (e.g., "forward 200", "stop")

        Returns:
            MotorCommand or None if parsing fails
        """
        command_str = command_str.lower().strip()

        # Handle direct numeric format: "200,200,1,1"
        if ',' in command_str:
            parts = command_str.split(',')
            if len(parts) == 4:
                try:
                    return MotorCommand(
                        left_speed=int(parts[0].strip()),
                        right_speed=int(parts[1].strip()),
                        left_dir=Direction(int(parts[2].strip())),
                        right_dir=Direction(int(parts[3].strip()))
                    )
                except Exception:
                    pass

        # Handle named commands
        parts = command_str.split()
        cmd = parts[0] if parts else ""
        speed = int(parts[1]) if len(parts) > 1 else 200

        if cmd in ["stop", "s"]:
            return MotorCommand.stop()
        elif cmd in ["forward", "f", "fwd"]:
            return MotorCommand.forward(speed)
        elif cmd in ["backward", "b", "back"]:
            return MotorCommand.backward(speed)
        elif cmd in ["left", "l", "rotate_left"]:
            return MotorCommand.rotate_left(speed)
        elif cmd in ["right", "r", "rotate_right"]:
            return MotorCommand.rotate_right(speed)

        return None
