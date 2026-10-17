"""Build a clean DPO preference dataset from logged drive frames.

WHY THIS EXISTS
---------------
Each logged frame stored the model's raw command (`command_before_overrides`)
and the command the enforce-in-code layer actually executed (`command_final`).
That pair is the DPO signal: rejected = raw model command, chosen = corrected.

But `command_final` was computed by whatever code was live *at collection time* —
including the escape-reflex bug fixed in 61bf0d9, where blind/stuck reflexes could
rotate INTO a wall. Training on those stale `chosen` labels would distill the bug
back into the weights.

So instead of trusting the logged `command_final`, this tool RE-DERIVES the chosen
command by replaying the CURRENT override chain over each frame's logged inputs
(raw model command + sensors + observation). No GPU and no robot: the vision model
is not re-run — its logged output is the fixed `rejected`, and only the
deterministic override/sanitize code is recomputed to produce a fresh `chosen`.

CHAIN REPLAYED (mirrors server_control.run_ai_control, minus boredom):
    emergency-stop (forward veto) -> blind reflex -> stuck escape -> sanitize
Reflexes are stateful (blind_frames, stuck_streak, last_escape_rotate_dir), so
frames are replayed IN ORDER with a fresh CommandGenerator per session.

SCOPE NOTES:
  * Boredom-commit frames are excluded (exploration heuristic, off by default,
    unrelated to the fix; live it preempted the reflexes so counters didn't
    advance on those frames either — skipping matches that).
  * Carpet boost reads state.last_observation; we set it to THIS frame's
    observation so the label reflects the surface actually in view.
  * A pair is emitted only when regenerated chosen != raw (a real correction).

OUTPUT: training_data/dpo_pairs.jsonl — one JSON object per line:
  { image, prompt, rejected_command, chosen_command,
    rejected_response, chosen_response,   # minimal pair: same text, swapped COMMAND: line
    corrections, observation, sensors, session, frame }

Run from repo root:  python3 -m scripts.build_dpo_dataset
"""
import sys, os, re, json, glob
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from server.command_generator import CommandGenerator, ParsedResponse
from shared.protocol import MotorCommand, Direction

SESSIONS_GLOB = "training_data/sessions/*/"
OUT_PATH = "training_data/dpo_pairs.jsonl"
EMERGENCY_CM = CommandGenerator.EMERGENCY_STOP_CM


class _Sensors:
    """Stub matching the .to_dict() contract the reflex/emergency code consumes.
    The logged 'sensors' field is already SensorData.to_dict() output (cm)."""
    def __init__(self, d):
        self._d = d or {}
    def to_dict(self):
        return self._d


def to_cmd(d):
    if not d:
        return None
    return MotorCommand(
        int(d["left_speed"]), int(d["right_speed"]),
        Direction(int(d["left_dir"])), Direction(int(d["right_dir"])),
        int(d["duration_ms"]),
    )


def cmd_str(c):
    """Render a command in the model's 'COMMAND:' 5-field format."""
    return f"{c.left_speed},{c.right_speed},{int(c.left_dir)},{int(c.right_dir)},{c.duration_ms}"


def same(a, b):
    return (a.left_speed == b.left_speed and a.right_speed == b.right_speed
            and a.left_dir == b.left_dir and a.right_dir == b.right_dir
            and a.duration_ms == b.duration_ms)


_CMD_LINE = re.compile(r"(?im)^[ \t]*COMMAND:.*$")


def swap_command(resp, cmd):
    """Return the model response with its COMMAND: line rewritten to `cmd`,
    yielding a minimal contrastive pair (identical prose, corrected command)."""
    line = f"COMMAND: {cmd_str(cmd)}"
    if _CMD_LINE.search(resp or ""):
        return _CMD_LINE.sub(line, resp, count=1)
    return (resp + ("\n" if resp and not resp.endswith("\n") else "")) + line


def main():
    sessions = sorted(glob.glob(SESSIONS_GLOB))
    n_frames = n_usable = n_boredom = n_emit = n_missing_img = 0
    kind = Counter()
    corr_combo = Counter()

    with open(OUT_PATH, "w") as out:
        for s in sessions:
            jf = glob.glob(os.path.join(s, "*.jsonl"))
            if not jf:
                continue
            cg = CommandGenerator()  # fresh reflex state per session
            for raw_line in open(jf[0]):
                try:
                    r = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                n_frames += 1
                raw = to_cmd(r.get("command_before_overrides"))
                if raw is None:
                    continue  # error/timeout frame — no model command
                if any(str(o).startswith("boredom") for o in (r.get("overrides_applied") or [])):
                    n_boredom += 1
                    continue  # exclude exploration-heuristic frames
                n_usable += 1

                sensors = _Sensors(r.get("sensors") or {})
                obs = (r.get("parsed") or {}).get("observation", "") or ""
                cg.state.last_observation = obs  # carpet detection in sanitize
                parsed = ParsedResponse(command=to_cmd(r["command_before_overrides"]),
                                        observation=obs)
                applied = []

                # 1. emergency-stop — vetoes FORWARD only
                d = sensors.to_dict()
                fc = d.get("fc") if d.get("fc") is not None else 999
                fl = d.get("fl") if d.get("fl") is not None else 999
                fr = d.get("fr") if d.get("fr") is not None else 999
                is_fwd = (parsed.command.left_dir == Direction.FORWARD
                          and parsed.command.right_dir == Direction.FORWARD)
                if min(fc, fl, fr) < EMERGENCY_CM and is_fwd:
                    parsed.command = MotorCommand.stop()
                    applied.append("emergency_stop")
                else:
                    # 2 & 3. blind / stuck reflexes (skipped under emergency, as live)
                    b = parsed.command
                    parsed = cg.check_and_override_if_blind(parsed, sensors)
                    if parsed.command is not b:
                        applied.append("blind_reflex")
                    b = parsed.command
                    parsed = cg.check_and_override_if_stuck(parsed, sensors)
                    if parsed.command is not b:
                        applied.append("stuck_escape")

                # 4. sanitize (speed/duration caps, carpet boost, min-move floor)
                before_san = parsed.command
                parsed.command = cg._sanitize_command(parsed.command)
                if not same(parsed.command, before_san):
                    applied.append("sanitize")

                chosen = parsed.command
                if same(chosen, raw):
                    continue  # no correction -> not a preference pair

                img = os.path.abspath(os.path.join(s, r.get("frame_path", "")))
                if not os.path.exists(img):
                    n_missing_img += 1

                for a in applied:
                    kind[a] += 1
                corr_combo["+".join(applied) or "none"] += 1
                n_emit += 1
                out.write(json.dumps({
                    "image": img,
                    "prompt": r.get("prompt", ""),
                    "rejected_command": cmd_str(raw),
                    "chosen_command": cmd_str(chosen),
                    "rejected_response": r.get("raw_response", ""),
                    "chosen_response": swap_command(r.get("raw_response", ""), chosen),
                    "corrections": applied,
                    "observation": obs,
                    "sensors": d,
                    "session": os.path.basename(s.rstrip("/")),
                    "frame": r.get("frame_num"),
                }) + "\n")

    print(f"sessions scanned          : {len(sessions)}")
    print(f"frames seen               : {n_frames}")
    print(f"  boredom frames excluded : {n_boredom}")
    print(f"  usable (had model cmd)  : {n_usable}")
    print(f"DPO PAIRS WRITTEN         : {n_emit}   -> {OUT_PATH}")
    if n_missing_img:
        print(f"  (warning: {n_missing_img} pairs reference a missing frame JPEG)")
    print("\ncorrection type (a pair may have several):")
    for k, v in kind.most_common():
        print(f"  {k:16s} {v}")
    print("\ncorrection combos:")
    for k, v in corr_combo.most_common(10):
        print(f"  {k:28s} {v}")


if __name__ == "__main__":
    main()
