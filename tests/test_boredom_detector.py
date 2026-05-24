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


# ---------------------------------------------------------------------------
# Task 8: Commit sequence — rotate → forward → cooldown
# ---------------------------------------------------------------------------

def _fill_buffer_until_trigger(cg):
    """Helper: fill buffer with quiet+stationary signal to force a trigger.
    Returns the trigger-frame result.

    With pre-append window-full semantics, the buffer needs WINDOW+1 calls
    total: the first WINDOW fills it, then the (WINDOW+1)th sees a full
    buffer and evaluates → triggers.
    """
    for _ in range(CommandGenerator.BOREDOM_WINDOW):
        cg.check_and_override_if_bored(
            _ai_forward_response(),
            _sensors(fl=100, fr=100),
            override_applied_this_frame=False,
        )
    return cg.check_and_override_if_bored(
        _ai_forward_response(),
        _sensors(fl=100, fr=100),
        override_applied_this_frame=False,
    )


def test_commit_frame1_is_rotate():
    cg = CommandGenerator()
    result = _fill_buffer_until_trigger(cg)
    # Frame 1 (trigger frame): rotate command emitted, state advances
    assert cg.boredom_state.commit_state == 'forward'  # advanced past 'rotate'
    cmd = result.command
    assert cmd.left_dir != cmd.right_dir
    assert cmd.left_dir != Direction.STOP and cmd.right_dir != Direction.STOP
    assert cmd.left_speed == CommandGenerator.MAX_ROTATION_SPEED


def test_commit_frame2_is_forward():
    cg = CommandGenerator()
    _fill_buffer_until_trigger(cg)
    # Frame 2: forward
    result = cg.check_and_override_if_bored(
        _ai_forward_response(),
        _sensors(fl=100, fr=100),
        override_applied_this_frame=False,
    )
    cmd = result.command
    assert cmd.left_dir == Direction.FORWARD
    assert cmd.right_dir == Direction.FORWARD
    assert cmd.left_speed == CommandGenerator.CARPET_SPEED
    assert cmd.duration_ms == CommandGenerator.BOREDOM_COMMIT_FORWARD_MS
    assert cg.boredom_state.commit_state is None
    # Cooldown engaged
    assert cg.boredom_state.cooldown_frames == CommandGenerator.BOREDOM_COOLDOWN_FRAMES


def test_commit_frame3_is_ai_command():
    cg = CommandGenerator()
    _fill_buffer_until_trigger(cg)
    # Drain rotate + forward frames
    cg.check_and_override_if_bored(_ai_forward_response(),
                                    _sensors(fl=100, fr=100),
                                    override_applied_this_frame=False)
    # Frame 3: should pass through AI command (cooldown active but commit done)
    ai = _ai_forward_response()
    result = cg.check_and_override_if_bored(
        ai, _sensors(fl=100, fr=100),
        override_applied_this_frame=False,
    )
    assert result.command == ai.command
    assert cg.boredom_state.cooldown_frames == CommandGenerator.BOREDOM_COOLDOWN_FRAMES - 1


def test_cooldown_blocks_retrigger():
    cg = CommandGenerator()
    _fill_buffer_until_trigger(cg)
    # Drain rotate + forward
    cg.check_and_override_if_bored(_ai_forward_response(),
                                    _sensors(fl=100, fr=100),
                                    override_applied_this_frame=False)
    # During cooldown, AI commands pass through and cooldown decrements.
    # (The buffers were cleared on trigger, so they're also refilling.)
    for _ in range(CommandGenerator.BOREDOM_COOLDOWN_FRAMES):
        result = cg.check_and_override_if_bored(
            _ai_forward_response(),
            _sensors(fl=100, fr=100),
            override_applied_this_frame=True,
        )
        # No commit should fire while cooldown is active
        assert cg.boredom_state.commit_state is None
    # Cooldown is now exhausted
    assert cg.boredom_state.cooldown_frames == 0

    # Feed triggering signal until the detector re-triggers. Robust to
    # off-by-one in exact buffer state — we just want to prove that
    # cooldown doesn't permanently disable the detector.
    triggered = False
    for _ in range(CommandGenerator.BOREDOM_WINDOW + 5):
        cg.check_and_override_if_bored(
            _ai_forward_response(),
            _sensors(fl=100, fr=100),
            override_applied_this_frame=False,
        )
        if cg.boredom_state.commit_state is not None:
            triggered = True
            break
    assert triggered, (
        "After cooldown expires and buffer refills with quiet+stationary "
        "signal, the detector should re-trigger"
    )


if __name__ == "__main__":
    test_no_trigger_when_buffer_not_full()
    test_trigger_on_high_override_rate()
    test_trigger_on_low_sensor_delta()
    test_no_trigger_when_both_signals_quiet()
    test_commit_frame1_is_rotate()
    test_commit_frame2_is_forward()
    test_commit_frame3_is_ai_command()
    test_cooldown_blocks_retrigger()
    print("All boredom detector tests passed!")
