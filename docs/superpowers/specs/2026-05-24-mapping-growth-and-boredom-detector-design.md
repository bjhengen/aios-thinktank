# Mapping Growth + Boredom Detector — Design

**Date:** 2026-05-24
**Status:** Spec
**Author:** Brian + Claude (brainstorming session)

## Background

Two problems from the April 18-20 drive sessions block any meaningful exploration drive:

1. **The topological map never grows from new locations.** The `LOCATION:` slot of the prompt tells the model to "pick from the KNOWN LOCATIONS list or say 'unknown'." The April 18 office drive returned `unknown` for all 171 frames because the office wasn't in the list and the prompt offered no path for proposing a new name. Map currently holds 2 nodes (`living`, `hallway`).

2. **Explore mode rut-runs.** Same April 18 session: 5 minutes in the office, 171 frames of varied commands (FWD 50, BWD 48, ROT-L 43, ROT-R 21, STOP 9), reflexes firing appropriately — but the car never left the room. The AI has no concept of "I've been here too long" because reactive 3-frame history doesn't compose into exploration.

Goal: fix both before a planned ~30-minute explore-and-map drive that will also collect training data for the LoRA fine-tuning project.

## Non-goals

- Calibration regression diagnosis (rotation rate is 2.4× slower than March; separate session).
- Finishing the Pi-side Rust client (Phase 5+).
- RL ultrasonic sensor fix (chassis rebuild, ~1 month out).
- LoRA training pipeline (depends on dataset growing further).

## Architecture overview

Two coordinated changes in the server-side Python control path. No Pi-side changes. No protocol changes.

```
┌─────────────────────────┐
│  vision_model.process   │  AI inference (unchanged)
└────────────┬────────────┘
             │ raw response
             ▼
┌─────────────────────────┐
│  parse_response         │  (unchanged)
└────────────┬────────────┘
             │ ParsedResponse
             ▼
┌─────────────────────────┐
│  Override chain (NEW    │
│  ordering):             │
│   0. Emergency stop     │  <15cm front → STOP, abort commit
│   1. Boredom detector   │  NEW — owns next 2 frames when triggered
│      (if enabled)       │
│   2. Blind reflex       │  (suppressed during commit)
│   3. Stuck reflex       │  (suppressed during commit)
│   4. Sanitize           │  speed/duration caps + carpet boost
└────────────┬────────────┘
             │ final MotorCommand
             ▼
┌─────────────────────────┐
│  Map integration        │  NEW: seeded vocab + propose-new prompt
│  + send to Pi           │
└─────────────────────────┘
```

---

## Section 1 — Mapping growth (seed + propose-new)

### 1a. Seed list in `server/config.py`

Add a module-level constant:

```python
SEED_LOCATIONS = [
    "office", "hallway", "living", "kitchen",
    "dining", "bedroom", "bathroom",
]
```

No pre-created `MapNode` entries. Real nodes only get created when the model identifies a room (existing flow at `server_control.py:239`).

### 1b. Merge seeds into known_locations

Modify `MapManager.get_known_locations()` in `server/map_manager.py`:

```python
def get_known_locations(self) -> List[str]:
    """Get observed node IDs first, then seed candidates not yet visited."""
    from server import config
    observed = list(self.nodes.keys())
    observed_set = set(observed)
    seeds = [s for s in config.SEED_LOCATIONS if s not in observed_set]
    return observed + seeds
```

Order matters: observed nodes first (these are "real, you've been here before"), seeds second (these are "candidate names you may use if you recognize the space"). The model interprets order as priority.

### 1c. Prompt change in `command_generator.build_prompt()`

Replace the current location instruction (lines ~387-389):

```
KNOWN LOCATIONS: office, hallway, living, kitchen, dining, bedroom, bathroom
Pick the best match from this list. If you're confident you're in a
different area, propose a short one-word name (e.g. closet, garage).
Say "unknown" only if you genuinely cannot tell.
```

The `OBSERVATION:` block already exists in the prompt template and informs the location guess; no change needed there.

### 1d. Location validation in `server_control.py`

After parsing, validate any proposed location name before creating a node. In the map integration block (~line 218):

```python
# Reject malformed location names — fall back to 'unknown'
if parsed.location and parsed.location != "unknown":
    if not re.match(r'^[a-z][a-z0-9_]{0,15}$', parsed.location):
        logger.warning(f"Invalid location name '{parsed.location}' — treating as unknown")
        parsed.location = "unknown"
```

Prevents the model from polluting the map with garbage like `room1234567890extra_long_name` or punctuation.

### 1e. Parser — no change needed

The existing regex `r'LOCATION:\s*(\w+)'` in `parse_response()` already extracts any word. The bug was purely the prompt instruction.

### 1f. Post-drive map review (`--review-map` mode)

Add a new CLI mode in `server_control.py`. No network, no AI, no Pi. Pure local file curation:

```python
def run_review_map(self) -> None:
    """Interactive map review: rename, delete, keep nodes after a drive."""
    self.map_manager.load()
    for node_id in list(self.map_manager.nodes.keys()):
        node = self.map_manager.nodes[node_id]
        print(f"\n{node_id}: visits={node.visit_count} "
              f"floor={node.floor_type} last={node.last_visited} "
              f"landmarks={node.landmarks}")
        choice = input("(k)eep / (r)ename / (d)elete: ").strip().lower()
        if choice == 'r':
            new_id = input("New name: ").strip().lower()
            if re.match(r'^[a-z][a-z0-9_]{0,15}$', new_id):
                self._rename_node(node_id, new_id)
        elif choice == 'd':
            self._delete_node(node_id)
    self.map_manager.save()
```

Helpers `_rename_node` and `_delete_node` must also update edges:
- Rename: walk `self.map_manager.edges` and replace `from_id` / `to_id` references.
- Delete: remove all edges that reference the node, then pop the node.

CLI flag: `--review-map`. Mutually exclusive with `--manual`, `--goto`, `--home`.

---

## Section 2 — Boredom detector state and signal

### 2a. State

Add a new sibling dataclass `BoredomState` (kept separate from `ControlState`, which is already crowded with stuck_streak / rotate_streak / etc.):

```python
@dataclass
class BoredomState:
    recent_overrides: deque         # last N booleans (any override applied?)
    recent_front_distances: deque   # last N (FL+FR)/2 sensor readings
    commit_state: Optional[str] = None   # None | 'rotate' | 'forward'
    commit_direction: Optional[str] = None  # 'left' | 'right'
    cooldown_frames: int = 0
```

`deque(maxlen=BOREDOM_WINDOW)` for both buffers. The `CommandGenerator` instance owns one as `self.boredom_state`; `server_control.py` reads/writes via that path (e.g. `self.command_generator.boredom_state.commit_state`).

### 2b. Constants on `CommandGenerator`

Added as class attributes alongside the existing `STUCK_FRONT_CM`, `MAX_ROTATION_SPEED`, etc., so both modules can reference them via `CommandGenerator.NAME`:

```python
BOREDOM_WINDOW = 20                # ~1 min at ~3s/frame
OVERRIDE_RATE_THRESHOLD = 0.5      # >=50% of window had any reflex override
SENSOR_DELTA_THRESHOLD = 30        # total |FL+FR avg| change in cm over window
BOREDOM_COOLDOWN_FRAMES = 10       # ~30s suppression after a commit completes
BOREDOM_COMMIT_FORWARD_MS = 2000
EMERGENCY_STOP_CM = 15             # front sensor threshold for absolute STOP
```

### 2c. Per-frame update + detection

New method `check_and_override_if_bored(parsed, sensor_data, override_applied_this_frame: bool)` called from `server_control.py` after parse but before blind/stuck reflexes. Returns possibly-mutated `parsed`.

Algorithm:

```
Append override_applied_this_frame to recent_overrides
Append (fl + fr) / 2 (treating None as 999) to recent_front_distances

If commit_state is not None:
    return _execute_commit_step(parsed, sensor_data)

If cooldown_frames > 0:
    cooldown_frames -= 1
    return parsed   # unchanged

If len(recent_overrides) < BOREDOM_WINDOW:
    return parsed   # not enough data yet

override_rate = sum(recent_overrides) / BOREDOM_WINDOW
sensor_delta_sum = sum(abs(d[i] - d[i-1]) for i in 1..N-1)

if override_rate >= OVERRIDE_RATE_THRESHOLD OR sensor_delta_sum < SENSOR_DELTA_THRESHOLD:
    commit_state = 'rotate'
    commit_direction = _pick_escape_dir(sensor_data)  # least-blocked rear
    recent_overrides.clear()
    recent_front_distances.clear()
    logger.warning(f"BOREDOM TRIGGERED: override_rate={override_rate:.2f} "
                   f"sensor_delta={sensor_delta_sum}cm → commit rotate-{commit_direction}")
    return _execute_commit_step(parsed, sensor_data)

return parsed
```

### 2d. `override_applied_this_frame` derivation

`server_control.py` already tracks `overrides_applied` as a list per frame for training data. Pass `bool(overrides_applied)` into the boredom check. The check runs *before* blind/stuck reflexes are evaluated, so it sees the override state from the previous control loop's tracking. We update the buffer with the *previous* frame's outcome — slightly delayed but accurate for rolling-window purposes.

Concretely: server_control.py keeps a `last_frame_had_override: bool` variable, passes it on the next iteration, then sets it from the current iteration's outcome.

---

## Section 3 — Commit sequence + override priority

### 3a. Commit state machine

```
Frame N (trigger):
    commit_state = 'rotate'
    command = rotate_left(220, 1050) if direction=='left' else rotate_right(220, 1800)
    advance commit_state to 'forward'
    log: "BOREDOM COMMIT 1/2: rotate-{direction} 220 {duration}ms"

Frame N+1:
    commit_state = 'forward'
    command = forward(CARPET_SPEED=235, 2000ms)
    advance commit_state to None
    cooldown_frames = BOREDOM_COOLDOWN_FRAMES
    log: "BOREDOM COMMIT 2/2: forward 235 2000ms"

Frame N+2 onward:
    commit_state is None — normal AI control resumes
    cooldown counts down on each frame
```

Implemented in `_execute_commit_step(parsed, sensor_data)`.

### 3b. Override priority in `server_control.py`

Replace the current chain at `server_control.py:167-186`:

```python
parsed = self.command_generator.parse_response(response)
if parsed.command is None:
    parsed.command = self.command_generator.get_safe_fallback_command()
    parsed.reasoning = "Parse failed - emergency stop"

command_before_overrides = parsed.command
overrides_applied = []

# 0. Emergency-stop watchdog — always wins
fl_fr_min = min(
    (sensor_data.to_dict().get('fl') or 999),
    (sensor_data.to_dict().get('fr') or 999),
)
if fl_fr_min < CommandGenerator.EMERGENCY_STOP_CM:
    parsed.command = MotorCommand.stop()
    parsed.reasoning = f"EMERGENCY: front <{CommandGenerator.EMERGENCY_STOP_CM}cm"
    overrides_applied.append("emergency_stop")
    # Abort any in-progress commit
    if self.command_generator.boredom_state.commit_state is not None:
        self.command_generator.boredom_state.commit_state = None
        self.command_generator.boredom_state.cooldown_frames = BOREDOM_COOLDOWN_FRAMES

# 1. Boredom (commit-in-progress OR new trigger) — wins over AI + other reflexes
elif self.boredom_enabled:
    before_bored = parsed.command
    parsed = self.command_generator.check_and_override_if_bored(
        parsed, sensor_data, self.last_frame_had_override
    )
    if parsed.command is not before_bored:
        # Tag with phase so training data is clear
        phase = self.command_generator.boredom_state.commit_state or "trigger"
        overrides_applied.append(f"boredom_commit_{phase}")

# 2 & 3. Blind / stuck reflexes ONLY if boredom didn't override
if "boredom_commit_rotate" not in overrides_applied \
   and "boredom_commit_forward" not in overrides_applied \
   and "emergency_stop" not in overrides_applied:
    before_blind = parsed.command
    parsed = self.command_generator.check_and_override_if_blind(parsed)
    if parsed.command is not before_blind:
        overrides_applied.append("blind_reflex")

    before_stuck = parsed.command
    parsed = self.command_generator.check_and_override_if_stuck(parsed, sensor_data)
    if parsed.command is not before_stuck:
        overrides_applied.append("stuck_escape")

# 4. Sanitize (defensive on commit commands; they should already be within caps)
if parsed.command:
    before_sanitize = parsed.command
    parsed.command = self.command_generator._sanitize_command(parsed.command)
    if parsed.command != before_sanitize:
        overrides_applied.append("sanitize")

self.last_frame_had_override = bool(overrides_applied)
```

### 3c. Mode gating

- New CLI flag `--boredom-detector` in `server_control.py`, default `False`.
- `AIController.__init__` accepts `boredom_enabled: bool`.
- Boredom block in step 1 above is gated on `self.boredom_enabled`. With the flag off, the buffer isn't even updated and the existing override chain runs as today.

### 3d. Per-tick logging

WARN-level structured logs from boredom code:

```
BOREDOM TRIGGERED: override_rate=0.65 sensor_delta=12cm window=20 → commit rotate-left
BOREDOM COMMIT 1/2: rotate-left 220 1050ms
BOREDOM COMMIT 2/2: forward 235 2000ms
BOREDOM ABORTED: emergency stop fl=12cm fr=999cm
BOREDOM COOLDOWN: 7 frames remaining
```

Visible in stdout and the training-data record (`overrides_applied`).

---

## Section 4 — Testing and the drive

### 4a. Unit tests (`tests/test_boredom_detector.py`)

Pure unit tests on `CommandGenerator`, no network/AI/Pi. Construct a `CommandGenerator`, manually feed sequences of `(parsed_response, sensor_data, override_applied_this_frame)`, assert:

1. Buffer fills correctly over N frames; no trigger before window is full.
2. High override-rate (≥0.5) triggers commit; signal values logged.
3. Low sensor-delta (< threshold) triggers commit even with no overrides.
4. Cooldown blocks re-trigger for exactly BOREDOM_COOLDOWN_FRAMES frames.
5. Commit progresses rotate (frame N) → forward (frame N+1) → None (frame N+2).
6. Emergency stop (< 15cm) aborts in-progress commit and starts cooldown.
7. Blind/stuck reflexes are suppressed while commit_state != None (verified via override tag inspection).
8. With `boredom_enabled=False`, no commits ever happen regardless of inputs.

### 4b. Mapping tests (`tests/test_map_manager.py` — add to existing if present, else new)

1. `get_known_locations()` returns observed nodes first, seeds second, deduplicated.
2. `--review-map` rename: rewrites edges to use new ID.
3. `--review-map` delete: removes edges referencing the deleted node.

### 4c. The 30-minute drive

1. Run unit tests; confirm green.
2. Launch Pi client (`pi/car_hardware.py`) — confirms protocol still works.
3. Launch server: `python -m server.server_control --boredom-detector --goal "explore the house, identify rooms, drive into spaces you haven't visited"`
4. Drive 30 minutes. Stop briefly between rooms to observe what `LOCATION:` the model is producing.
5. After: `python -m server.server_control --review-map` to curate `map_data.json`.
6. Inspect `training_data/<session>/` — training records should now include `boredom_commit_rotate` / `boredom_commit_forward` override labels for frames where the detector fired.

### 4d. Success criteria

- Map grows beyond `living` + `hallway` (at least 2 additional nodes from a 30-min drive).
- At least one `BOREDOM TRIGGERED` event fires during the drive AND the car visibly moves out of the rut it was in.
- No new training-data corruption (override tags well-formed, frames still log correctly).

---

## Open questions deferred to implementation

- Exact value of `BOREDOM_WINDOW`: starting at 20, may tune up/down empirically during drive.
- Whether `SENSOR_DELTA_THRESHOLD=30cm` is appropriate when fl/fr report None (open space). Current plan: treat None as 999, which means open-space frames count as "very large reading" and produce a tiny delta when nothing changes. Worst case: open-space stationary triggers boredom — which is actually correct.
- `BOREDOM_COOLDOWN_FRAMES=10` may be too low if the car gets into an exit corridor that still has high reflex activity. Tune during drive.
- Rotation calibration is currently regressed (~2.4× slower than the March 1050ms-for-90° baseline, per journal entry 226 / lesson #811). The commit's rotate phase uses the same 1050ms / 1800ms values the existing reflex code uses. Real rotation may only be ~40° instead of 90° until calibration is diagnosed. This degrades the commit but doesn't break it — the point is "do something different," not "achieve an exact angle." Calibration is out of scope for this work.

These are empirical tuning questions, not architectural ones. Defaults are reasonable starting points.

## Files touched

| File | Change |
|---|---|
| `server/config.py` | Add `SEED_LOCATIONS` constant |
| `server/map_manager.py` | Modify `get_known_locations()` to merge seeds |
| `server/command_generator.py` | Add `BoredomState`, constants, `check_and_override_if_bored()`, `_execute_commit_step()`, helpers; update prompt |
| `server/server_control.py` | New override chain order, `--boredom-detector` flag, `--review-map` mode, location validation |
| `tests/test_boredom_detector.py` | New file — unit tests for boredom state machine |
| `tests/test_map_manager.py` | New file (or add to existing) — `get_known_locations`, `--review-map` helpers |

## Estimated change size

~250 lines added, ~30 modified across 4 source files. Tests: ~150 lines.
