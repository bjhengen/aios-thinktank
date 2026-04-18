# Robotcar TODO

Running list of deferred items that came up during sessions. Not a hard
backlog — just captured so we don't lose them.

---

## Behavioral

### Boredom detector (server-side reflex)
**Goal:** make "explore" mode actually explore instead of rut-running in one
corner of a room.

**Observation (Apr 18 session `20260418_164359_9d59c4`):** car was placed in
office, ran 5 minutes, produced 171 frames of varied commands (FWD 50, BWD 48,
ROT-L 43, ROT-R 21, STOP 9), stuck-escape + blind-reflex fired appropriately —
but never left the office. Rut-ran in one corner, escaped, rut-ran elsewhere.

**Proposed fix (in `server/command_generator.py`):** track a rolling position-
proxy — e.g., cumulative absolute delta of front sensor readings over the last
N frames. If the signal stays below some threshold, the car isn't meaningfully
moving. When boredom triggers, override the next command with a forced
"commit" sequence: 90° rotate + 2–3s sustained FWD at carpet-speed, ignoring
all overrides except the strict emergency-stop watchdog (<15 cm).

**Tradeoff:** forced commitment will occasionally knock the car into
obstacles. Acceptable for explore mode, must be disabled for follow-the-human
mode.

**Open design choices:**
- Rolling window size (probably 20–30 frames)
- Delta threshold (needs empirical tuning — probably cm of sensor change summed over window)
- Interaction with existing stuck_escape / rotation_loop_break reflexes
  (boredom should fire *before* those chain, not after)

---

### Map growth from new locations
**Bug:** The `LOCATION:` slot of the prompt tells gemma to "pick from the
KNOWN LOCATIONS list or say 'unknown'." That means new rooms never get a
name proposed, which means the map never grows from first-time visits.
Observed in two drives today: the car visited the office (new) and returned
`unknown` for all 171 frames.

**Options:**
1. Prompt fix: "If this is a new area NOT in the list, propose a short
   one-word name (office, kitchen, bedroom, etc.)" — quick, maybe 60–80%
   effective given gemma's instruction-following track record.
2. Structured handshake: when "unknown" is detected, follow up with a
   dedicated "what room is this?" prompt and use the answer. More reliable,
   adds a round-trip.
3. Seed `known_locations` from a config file of expected rooms (office,
   hallway, kitchen, bedroom, living_room, etc.). Deterministic, works
   immediately for this house.

Recommendation: do (3) as the immediate fix + (1) as secondary.

---

## Rust rewrite (per `docs/pi-rust-rewrite.md`)

### Phase 5 — Camera
Next big phase. Plan: try `libcamera-rs` first; fall back to spawning
`rpicam-still` as subprocess if the bindings aren't ready. `turbojpeg` for
encode, or hardware JPEG via V4L2 M2M if we want to chase the last ~10ms.

### Phase 6 — Network
Plain blocking `std::net::TcpStream`, split into reader/writer, reconnect
loop. No TLS. No complications.

### Phase 7 — Integration
Wire camera + sensors + motors + network into the threading model laid out
in the design doc. Includes the watchdog thread that emergency-stops when
no command arrives within `ROBOTCAR_WATCHDOG_MS` (default 1000).

### Phase 8 — Cutover
Disable Python systemd unit, enable Rust unit. Roll back by swapping units.

### Post-cutover

- **Hardware PWM for 2 motors** (optional). PWM0 → GPIO 12, PWM1 → GPIO 13
  via `dtoverlay=pwm-2chan`. Cleaner timing for front wheels; other two
  stay software PWM. Only worth doing if we see PWM-related motor issues
  under CPU load in the integrated build.
- **Single-thread PWM scheduler** (alternative to above). One thread, one
  loop, toggles all 4 pins according to per-pin duty cycles. Avoids
  thread-contention risk entirely. More code but simpler mental model.
- **JSON structured logs** as an opt-in via `--log-format=json`. Enables
  structured correlation between Pi-side and server-side events in future
  training-pipeline work.
- **Hardware JPEG encoder** via V4L2 M2M. Saves ~10ms/frame vs software
  turbojpeg. Only valuable after we verify total cycle-time is bottlenecked
  on the Pi (currently it's bottlenecked on inference).

---

## Hardware (month-out)

When Brian does the chassis rebuild (LEGO Technic body + re-wire):

- **Fix RL ultrasonic wiring.** Currently 100% dropout in both Python and
  Rust (lesson #804). Hardware problem, not software. Re-crimp/re-seat the
  RL echo line.
- **Reconnect FC ultrasonic** if the center-front sensor is desired. It's
  been disconnected since the original wiring.
- **Mount the acrylic tilt camera mount** (already ordered). The current
  binder-clip mount gives too-low a camera angle; half the observations are
  "close-up of floor" rather than useful room context. Higher camera angle
  directly helps doorway detection, which helps exploration.
- **Switch to 2S 18650 battery pack** (parts ordered; Brian's first
  soldering project). Replaces the 4xAA holder. Steadier motor voltage,
  way more capacity, and USB-C charging instead of AA-swap.

---

## Dataset / LoRA

- **608 labeled training frames** as of the April 18 sessions. Three source
  sessions: stuck-ROT-R, fixed-drive, office-rut.
- **Preference-pair candidates:** every frame with `overrides_applied: ["…"]`
  is a natural preference pair — "here's what gemma did, here's what the
  code said was correct." Preserve these with labels.
- **Target session counts:** 5–10 more drive sessions of varying scenarios
  (follow-human, explore, goto-named-location) before we have enough data
  to try a small LoRA on gemma-4-26b-a4b. Probably a few hundred to low
  thousands of good examples.
- **Ideal next sessions:** (a) teleoperation via `--manual` mode to capture
  human-policy demonstrations, (b) deliberate drives through multiple rooms
  for cross-room context, (c) drives with the tilt-mount camera after the
  chassis rebuild.
