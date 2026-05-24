#!/usr/bin/env python3
"""
Unit tests for the boredom detector state machine.

Pure unit tests — no network, no AI, no Pi. Construct a CommandGenerator,
feed it sequences of (parsed_response, sensor_data, override_applied_this_frame),
assert state transitions and commands.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from server.command_generator import CommandGenerator, ParsedResponse
from shared.protocol import MotorCommand, Direction, SensorData


def _ai_forward_response() -> ParsedResponse:
    """A generic 'AI said forward' response, no overrides applied.

    Note on the `override_applied_this_frame` parameter in these tests:
    per spec §2d, server_control passes the PREVIOUS frame's override
    outcome (via `self.last_frame_had_override`). In these unit tests we
    call the detector directly, so the parameter we pass simulates what
    the previous frame did. The asymmetry is intentional — the detector
    always works on a one-frame delay relative to the override chain.
    """
    return ParsedResponse(
        command=MotorCommand.forward(190, 1500),
        observation="Clear path ahead",
        assessment="Path clear",
        reasoning="Moving forward",
        location="office",
    )


def _sensors(fl=100, fr=100, rl=100, rr=100, fc=0) -> SensorData:
    """Build a SensorData with explicit per-channel readings.

    Values are in centimeters; they are converted to millimeters (the wire
    format) before being passed to SensorData. fc=0 means 'no reading'
    (the SensorData sentinel for invalid/absent readings).
    """
    return SensorData(fc=fc, fl=fl * 10, fr=fr * 10, rl=rl * 10, rr=rr * 10)


# ---------------------------------------------------------------------------
# Task 7: Detection
# ---------------------------------------------------------------------------

def test_no_trigger_when_buffer_not_full():
    cg = CommandGenerator()
    # Feed fewer frames than BOREDOM_WINDOW with all-override signal
    for _ in range(CommandGenerator.BOREDOM_WINDOW - 1):
        parsed = _ai_forward_response()
        result = cg.check_and_override_if_bored(
            parsed, _sensors(fl=100, fr=100),
            override_applied_this_frame=True,
        )
        # Buffer not full yet — no commit should have started
        assert cg.boredom_state.commit_state is None
        assert result.command == parsed.command


def test_trigger_on_high_override_rate():
    cg = CommandGenerator()
    # Fill the buffer with mostly-override frames AND high sensor variance
    # so we isolate the override-rate signal as the cause of the trigger.
    for i in range(CommandGenerator.BOREDOM_WINDOW):
        parsed = _ai_forward_response()
        # Alternate front distances so sensor_delta is large (won't trigger
        # sensor-delta branch on its own)
        fl = 200 if i % 2 == 0 else 50
        override_applied = (i % 2 == 0)  # 50% — at the threshold
        result = cg.check_and_override_if_bored(
            parsed, _sensors(fl=fl, fr=fl),
            override_applied_this_frame=override_applied,
        )
    # At end of fill, the next call should trigger (override_rate >= 0.5)
    parsed = _ai_forward_response()
    result = cg.check_and_override_if_bored(
        parsed, _sensors(fl=200, fr=200),
        override_applied_this_frame=True,
    )
    # Trigger fires immediately — state advances to 'forward' after the
    # rotate frame is dispatched
    assert cg.boredom_state.commit_state == 'forward'
    # Returned command must be a rotation
    rot = result.command
    assert rot.left_dir != rot.right_dir
    assert rot.left_dir != Direction.STOP and rot.right_dir != Direction.STOP


def test_trigger_on_low_sensor_delta():
    cg = CommandGenerator()
    # Fill the buffer with constant front distance (delta = 0) and NO overrides
    for _ in range(CommandGenerator.BOREDOM_WINDOW):
        parsed = _ai_forward_response()
        cg.check_and_override_if_bored(
            parsed, _sensors(fl=100, fr=100),
            override_applied_this_frame=False,
        )
    # Next call: sensor_delta_sum = 0 < threshold, should trigger
    parsed = _ai_forward_response()
    result = cg.check_and_override_if_bored(
        parsed, _sensors(fl=100, fr=100),
        override_applied_this_frame=False,
    )
    assert cg.boredom_state.commit_state == 'forward'
    rot = result.command
    assert rot.left_dir != rot.right_dir


def test_no_trigger_when_both_signals_quiet():
    cg = CommandGenerator()
    # Fill the buffer with high sensor variance and no overrides
    for i in range(CommandGenerator.BOREDOM_WINDOW):
        parsed = _ai_forward_response()
        fl = 200 if i % 2 == 0 else 50
        cg.check_and_override_if_bored(
            parsed, _sensors(fl=fl, fr=fl),
            override_applied_this_frame=False,
        )
    # Should be no trigger — variance is high, overrides are 0
    parsed = _ai_forward_response()
    result = cg.check_and_override_if_bored(
        parsed, _sensors(fl=300, fr=300),
        override_applied_this_frame=False,
    )
    assert cg.boredom_state.commit_state is None
    assert result.command == parsed.command


if __name__ == "__main__":
    test_no_trigger_when_buffer_not_full()
    test_trigger_on_high_override_rate()
    test_trigger_on_low_sensor_delta()
    test_no_trigger_when_both_signals_quiet()
    print("Boredom detector tests passed (Task 7)")
