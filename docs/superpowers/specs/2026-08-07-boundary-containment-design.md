# Boundary Containment — Design

**Date:** 2026-08-07
**Status:** Spec
**Author:** Brian + Claude (brainstorming session)

## Background

Oracle AI World (Oct 25–28, 2026, Venetian Expo) may host a booth robot built on
this project's software. Venetian Expo rules require demonstrations to stay
within the confines of the booth space, so the robot must not leave a defined
area — and "must not" has to mean something stronger than a line in a prompt.

The show robot itself will be a **from-scratch build**: new chassis, new compute
(Linux), likely LiDAR. The current robotcar would not survive a busy trade show.
What carries over is software. So this work is a **portable policy testbed**:
build the containment *behaviour* on hardware we can crash safely, and design it
so the policy survives the hardware change while the sensing underneath it is
disposable.

### The constraint that shapes everything

Robotcar has **no position sense at all** — no wheel encoders, no IMU, no GPS.
The topological map design (`2026-03-21-topological-map-design.md`) explicitly
chose "no metric distances or occupancy grids" for exactly this reason. The
robot's entire spatial model is named rooms plus recorded command sequences.

A boundary therefore cannot be a coordinate fence. It has to be defined against
something the robot can directly perceive. The chosen answer: **mark the
boundary physically on the floor** (tape or reflective strip) and detect it in
the camera frame.

Two properties make floor marking the right call for a trade show specifically:

1. **A crowd cannot occlude it.** Anything at knee-to-eye height sits behind a
   wall of people for most of the day. The floor immediately ahead of the robot
   stays visible. (Eye-level fixtures are also unlikely to be permitted in the
   hall.)
2. **The low camera mount finally helps.** The binder-clip mount's downward
   angle has been a liability for months — it is the root of the room-label
   hallucinations (lesson #1076), because the model sees floor strips instead of
   rooms. For detecting a line on the ground it is the correct camera.

## Non-goals

- Localization, odometry, coordinate frames, or SLAM of any kind.
- A polygon/region model of the allowed area. "Line ahead, in this sector" is
  sufficient.
- A return-to-anchor routine. Breadcrumb backtracking already exists in
  `MapManager.get_reverse_breadcrumb` if we want it later.
- ArUco fiducial detection. The estimator interface stays open for it; we do not
  write it. (Verified available in the installed OpenCV 4.11 — noted for later.)
- Any Pi-side or protocol change. This is server-side only.
- Fixing the dead `fc` / dead `rl` ultrasonics or the camera mount. Those belong
  to the chassis rebuild.

## Architecture overview

Two new server-side modules and a wiring change. No Pi changes, no protocol
changes.

```
┌────────────────────────────────────────────┐
│  Pi → (SensorData, jpeg bytes)             │
└───────────────────┬────────────────────────┘
                    │
                    ▼
┌────────────────────────────────────────────┐
│  [UNCONDITIONAL OBSERVE]            NEW    │
│    estimator.read(jpeg)  → BoundaryReading │
│    policy.observe(reading)                 │
│  Runs every frame, before any override.    │
└───────────────────┬────────────────────────┘
                    │
                    ▼
┌────────────────────────────────────────────┐
│  build_prompt(..., boundary=reading) NEW   │
│  vision_model.process_frame                │
│  parse_response                            │
└───────────────────┬────────────────────────┘
                    │ ParsedResponse
                    ▼
┌────────────────────────────────────────────┐
│  Override chain:                           │
│   0. Boredom detector      (existing)      │
│   1. Containment veto            NEW       │
│   2. Emergency stop        (existing)      │
│   3. Blind / stuck reflex  (existing)      │
│   4. Sanitize              (existing)      │
└───────────────────┬────────────────────────┘
                    │ final MotorCommand
                    ▼
                 send to Pi
```

### Why the split into two modules

`server/boundary.py` is the **disposable** half — it knows about JPEGs, pixels
and colour thresholds. `server/containment.py` is the **portable** half — a pure
function with no I/O that decides what a reading means. Only the disposable half
gets rewritten when the new build swaps a camera-and-tape estimator for a
LiDAR-and-virtual-walls one.

New files rather than extensions: `command_generator.py` is already 833 lines
and `server_control.py` 692. Containment belongs in neither.

---

## Section 1 — `server/boundary.py` (the disposable half)

### 1a. The reading

```python
@dataclass
class BoundaryReading:
    valid: bool          # detector ran; False = sensing failure
    detected: bool       # a boundary marker is visible
    proximity: float     # 0.0 = far/none … 1.0 = at the line
    sectors: dict        # {"left": float, "center": float, "right": float}
    confidence: float    # 0.0–1.0; degrades with poor lighting
```

`sectors` is the load-bearing field. It reports **where the line runs relative
to the robot** without the estimator making any decision about what to do. Each
value is the proximity contribution from that third of the frame band. A future
LiDAR estimator populates the identical structure from virtual-wall geometry,
which is precisely what makes the policy portable.

`valid` and `detected` are deliberately distinct: `valid=True, detected=False`
means "the detector looked and there is no boundary in view" (normal, robot is
mid-area). `valid=False` means "the detector could not form an opinion" — a
failure, handled as described in Section 4.

### 1b. `BoundaryEstimator` interface

```python
class BoundaryEstimator(ABC):
    @abstractmethod
    def read(self, jpeg_data: bytes, sensor_data) -> BoundaryReading: ...
```

`sensor_data` is unused by the floor-line implementation but present in the
signature so later estimators (LiDAR, fused) need no interface change.

### 1c. `FloorLineEstimator`

Pipeline, all OpenCV, all on the frame the server already holds:

1. Decode JPEG to BGR (`cv2.imdecode`).
2. Crop to the lower band of the frame — the floor region. Band bounds are
   config, since they depend on camera mount angle.
3. Convert to HSV and threshold against the configured marker colour range.
   (A brightness threshold is used instead for retroreflective tape; selected by
   config, same code path.)
4. Morphological open/close to remove speckle.
5. Split the band into left/centre/right thirds. For each, compute the marker
   pixel mass and the **vertical position** of its centroid — lower in the frame
   means physically closer to the robot. Map to a 0–1 proximity per sector.
6. `proximity` = max of the three sectors. `confidence` = total marker pixel
   fraction, clamped, used to spot degraded lighting.
7. `detected` = `proximity` exceeds a configured floor.

Latency budget: this is a few milliseconds of OpenCV on a 640×480 frame, against
a ~1.1s inference call. It is free at this scale.

**Attach point:** `server_control.py` already holds the raw JPEG as `frame_data`
(around line 141) before passing it to the vision model. No extra capture, no
extra round trip.

---

## Section 2 — `server/containment.py` (the portable half)

### 2a. `ContainmentPolicy`

A pure decision unit. No I/O, no frames, no network, no clock. Everything it
knows arrives through its two methods:

```python
class ContainmentPolicy:
    def observe(self, reading: BoundaryReading) -> None: ...
    def evaluate(self, command: MotorCommand) -> ContainmentDecision: ...
    def prompt_annotation(self) -> str | None: ...
```

`observe` updates internal state (rolling confidence, degraded-mode counter,
hysteresis). `evaluate` is a pure function of that state plus the proposed
command. `prompt_annotation` renders the current state as a short natural-
language phrase for the prompt, e.g. `"The boundary of your area is close on
your left."`

### 2b. `ContainmentDecision`

```python
@dataclass
class ContainmentDecision:
    allowed: bool
    substitute: Optional[MotorCommand]  # what to do instead
    reason: str                         # for logging + training records
```

### 2c. Decision rules

A command is vetoed when it would **translate the robot toward a sector whose
proximity exceeds the veto threshold.** Concretely:

- Forward motion is vetoed when `sectors["center"]` is over threshold, or when
  either side sector is over threshold and the command curves that way.
- **Backward motion is never vetoed by this estimator**, because a
  forward-facing camera cannot see a boundary behind the robot. This is an
  accepted limitation, not an oversight: the policy interface supports rear
  sectors, and a LiDAR estimator on the new build will populate them, at which
  point the same rule that governs forward motion applies to reverse with no
  policy change. Until then the never-cross invariant (Section 2d) covers it —
  the robot only ever reverses *away* from a line it is facing.
- **Rotation in place is never vetoed.** A rotation does not translate the
  robot, so it cannot cross a line. This is the escape valve — see Section 3.

Hysteresis: once vetoing, the policy keeps vetoing until proximity falls below a
lower release threshold. Without this the robot chatters at the line.

### 2d. The never-cross invariant

The design rests on a single assumption: **the robot starts inside the area and
is never permitted to cross the line.** Given that, a detected line always means
"edge ahead, do not proceed," and we never have to answer the much harder
question of which side of the line we are on.

This is enforced by the startup assertion in Section 4, and it is the same
reasoning temi's virtual walls use.

---

## Section 3 — Deadlock avoidance

Adding a third veto to the chain makes pinning *more* likely. Emergency-stop can
forbid forward while containment forbids turning outward, leaving the robot
buzzing with no legal move. This is precisely the May 2026 failure (lesson
#1075), where the car wedged at 13.1 cm and looped on emergency-stop for 60+
seconds, unrescuable.

**The fix is cheap: rotation in place is always containment-legal.** When
containment vetoes, the substitute is a rotation toward the interior — away from
the highest-proximity sector, using the existing `_rotate_toward` helper in
`command_generator.py` so the tuned per-direction durations are preserved
(rotate_left 1050 ms vs rotate_right 1800 ms; the front-heavy chassis rotates
left faster).

No arbiter refactor of the override chain is required. The guarantee is encoded
as a property test rather than trusted (Section 6).

---

## Section 4 — Failure handling

Every failure resolves the same way, matching the rule already used for network
loss: **stop, do not coast.**

| Condition | Response |
|---|---|
| Detector raises | Caught, converted to `valid=False`. Never propagates into the control loop. |
| `valid=False` | Treated as *at the boundary*: translation blocked, rotation allowed, logged at WARNING. |
| `confidence` below threshold for N consecutive frames | Degraded mode — same response as `valid=False`. |
| Startup: no valid reading in first N frames | **Refuse to enter AI mode.** |

The startup assertion is deliberately strict. The whole design rests on "starts
inside and never crosses"; if we cannot confirm we are inside, we do not drive.
It applies only when containment is enabled.

---

## Section 5 — Integration into `server_control.py`

### 5a. Observe phase

The estimator and `policy.observe()` run **before the override chain**, ahead of
even the boredom detector, and unconditionally. This is lesson #1075 encoded
structurally: state-maintaining observers must see every frame, never gated
inside the override `if/elif`. The boredom detector went blind to exactly the
ruts it was built for because it was gated that way.

### 5b. Veto position — after boredom, before emergency stop

Containment sits at **position 1**, between the boredom detector and the
emergency-stop watchdog. The ordering is not arbitrary:

- **After boredom**, because the boredom detector emits a forced "commit"
  sequence (90° rotate + sustained forward) that deliberately ignores lower
  overrides. That commit must be vetoable by containment, or the rescue
  mechanism will drive the robot straight out of the booth.
- **Before emergency stop**, so that a containment substitute (a rotation) is
  still subject to the emergency watchdog.

### 5c. Aborting an in-progress boredom commit

When containment vetoes a boredom commit it must also **clear
`boredom_state.commit_state` and set the cooldown**, mirroring what the
emergency-stop branch already does. Otherwise the commit resumes on the next
frame and drives across the line anyway.

### 5d. Override accounting

Append `"containment_veto"` to `overrides_applied` so it lands in the training
records.

It must **not** count toward `last_frame_had_override`. That flag feeds the
boredom detector's override-rate signal, and containment vetoes fire
continuously while the robot works along a boundary — counting them would
inflate the rate and cause boredom to self-trigger. Same reasoning that already
excludes `sanitize`.

### 5e. Prompt annotation

`build_prompt()` gains a `boundary=` keyword carrying
`policy.prompt_annotation()`. The model is *told* where the edge is so it tends
to choose inward moves on its own — but per the project's most-repeated lesson
(enforce in code, not in prompt), nothing depends on it complying.

### 5f. CLI flag

`--boundary` enables containment, defaulting **off**, matching the precedent set
by `--boredom-detector`. Off by default means existing drives are unaffected.

---

## Section 6 — Testing

### 6a. Detector fixtures (no hardware)

Every drive already logs frames to `training_data/sessions/`. Lay tape in the
house, run one short drive, and that becomes a labelled corpus. Detector tests
then run offline against real frames — including the degraded-lighting and
no-marker-visible cases.

### 6b. Policy unit tests (no hardware)

`ContainmentPolicy` is pure, so tests are table-driven over
`(reading, command) → expected decision`. Cases: each sector over threshold,
hysteresis enter/release, degraded mode, `valid=False`, rotation always allowed.

**These are the tests that move to the new platform unchanged.**

### 6c. Deadlock property test

Across the cross-product of containment state × emergency-stop state × sensor
readings, assert **at least one action is always permitted**. This converts
lesson #1075 from something we remember into something that breaks the build.

### 6d. Live validation

Tape a box on the floor, drive with `--boundary`, count breaches. Success: zero
crossings over a 10-minute drive, and no pinning episodes longer than a few
seconds.

---

## Section 7 — Configuration

Added to `server/config.py`:

| Setting | Purpose |
|---|---|
| `boundary_marker_mode` | `"color"` or `"reflective"` — selects threshold strategy |
| `boundary_hsv_low` / `boundary_hsv_high` | HSV range for colour mode |
| `boundary_brightness_min` | Threshold for reflective mode |
| `boundary_band_top` / `boundary_band_bottom` | Frame crop bounds (fractions of height) |
| `boundary_veto_threshold` | Proximity at which vetoing starts |
| `boundary_release_threshold` | Proximity below which vetoing stops (hysteresis) |
| `boundary_min_confidence` | Below this, degraded mode |
| `boundary_degraded_frames` | Consecutive low-confidence frames before degrading |
| `boundary_startup_frames` | Valid readings required before AI mode starts |

### On-site calibration utility

`scripts/calibrate_boundary.py` — grabs a frame, and either reports the HSV
range of a user-specified region or sweeps candidate thresholds and prints the
resulting detection mask as ASCII.

**This is not optional polish.** Carpet colour and lighting at the Venetian are
unknown until load-in, and a hardcoded HSV range will not survive the trip. A
ten-minute calibration on-site beats debugging on the show floor.

---

## What carries to the AI World build

| Component | Fate |
|---|---|
| `ContainmentPolicy` + its tests | **Carries unchanged** |
| `BoundaryReading` / `BoundaryEstimator` interface | **Carries unchanged** |
| Override-chain wiring pattern + deadlock property test | **Carries as a pattern** |
| `FloorLineEstimator` | Disposable — replaced by a LiDAR/virtual-wall estimator |
| HSV config + calibration utility | Disposable |

## Open questions

- **Marker colour** is unknown until we see the booth carpet. Config-driven, so
  this does not block implementation.
- **Rear boundary detection** is out of reach for a forward-facing camera. The
  never-cross invariant covers it in practice; the LiDAR estimator closes it
  properly. Flagged rather than solved.
