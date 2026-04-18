"""
Training data logger — persists per-frame records for future LoRA fine-tuning.

Each session writes one JSONL file plus a frames/ directory with the JPEG images.
Records capture the full decision context (prompt, raw model response, commands
before and after code overrides, sensor readings, outcome signals) so the dataset
can be filtered and relabeled offline.

Structured this way deliberately — keep logging cheap and inline, do the
filtering and labeling as a separate offline pass.
"""

import json
import os
import time
import uuid
from dataclasses import asdict
from typing import Optional

from shared.protocol import MotorCommand, SensorData
from shared.utils import setup_logging


logger = setup_logging(__name__)


def _cmd_to_dict(cmd: Optional[MotorCommand]) -> Optional[dict]:
    if cmd is None:
        return None
    return {
        "left_speed": cmd.left_speed,
        "right_speed": cmd.right_speed,
        "left_dir": int(cmd.left_dir),
        "right_dir": int(cmd.right_dir),
        "duration_ms": cmd.duration_ms,
    }


class TrainingLogger:
    """
    Writes one JSONL record per AI inference, plus frames/*.jpg alongside.

    Layout:
      <root>/sessions/<session_id>/
          session.jsonl
          frames/
              frame_000000.jpg
              frame_000001.jpg
              ...
    """

    def __init__(self, root: str = "./training_data", session_id: Optional[str] = None):
        self.session_id = session_id or time.strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
        self.session_dir = os.path.join(root, "sessions", self.session_id)
        self.frames_dir = os.path.join(self.session_dir, "frames")
        self.jsonl_path = os.path.join(self.session_dir, "session.jsonl")
        os.makedirs(self.frames_dir, exist_ok=True)
        self._fh = open(self.jsonl_path, "a", buffering=1)  # line-buffered
        self._frame_num = 0
        logger.info(f"TrainingLogger: session={self.session_id} → {self.session_dir}")

    def log_frame(self,
                  frame_bytes: bytes,
                  sensor_data: Optional[SensorData],
                  prompt: str,
                  raw_response: str,
                  parsed_command_before_overrides: Optional[MotorCommand],
                  final_command: Optional[MotorCommand],
                  observation: str = "",
                  assessment: str = "",
                  reasoning: str = "",
                  location: str = "",
                  overrides_applied: Optional[list] = None,
                  goal: str = "",
                  steps_taken: int = 0) -> str:
        """
        Write one training record and save the frame JPEG.

        Returns the relative frame path written (for debugging).
        """
        frame_name = f"frame_{self._frame_num:06d}.jpg"
        frame_path = os.path.join(self.frames_dir, frame_name)
        try:
            with open(frame_path, "wb") as f:
                f.write(frame_bytes)
        except OSError as e:
            logger.warning(f"Failed to save training frame: {e}")

        record = {
            "ts": time.time(),
            "session_id": self.session_id,
            "frame_num": self._frame_num,
            "frame_path": os.path.relpath(frame_path, start=self.session_dir),
            "goal": goal,
            "steps_taken": steps_taken,
            "sensors": sensor_data.to_dict() if sensor_data is not None else None,
            "prompt": prompt,
            "raw_response": raw_response,
            "parsed": {
                "observation": observation,
                "assessment": assessment,
                "reasoning": reasoning,
                "location": location,
            },
            "command_before_overrides": _cmd_to_dict(parsed_command_before_overrides),
            "command_final": _cmd_to_dict(final_command),
            "overrides_applied": overrides_applied or [],
        }

        try:
            self._fh.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.error(f"Failed to write training record: {e}")

        self._frame_num += 1
        return frame_path

    def close(self) -> None:
        try:
            self._fh.close()
            logger.info(f"TrainingLogger closed: {self._frame_num} frames → {self.jsonl_path}")
        except Exception:
            pass
