# Mapping Growth + Boredom Detector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the topological map grow from new locations (via seeded vocabulary + propose-new prompt) and add a server-side boredom-detector reflex that forces a 2-frame rotate+forward commit when the car is rut-running, so we can do a meaningful 30-minute explore-and-map drive.

**Architecture:** Two coordinated server-side changes in Python. (1) Mapping: seed `KNOWN_LOCATIONS` from `server/config.py`, allow the prompt to propose new names, validate names, and add a `--review-map` curation mode. (2) Boredom: composite signal (override-rate OR sensor-delta) tracked in a rolling window; trigger fires a 2-frame commit (rotate-90° → forward-2s) that wins over AI and other reflexes but yields to a <15cm emergency-stop. CLI-gated, default off.

**Tech Stack:** Python 3, dataclasses, `collections.deque`, plain-assert unit tests (no pytest), argparse.

**Spec:** [`docs/superpowers/specs/2026-05-24-mapping-growth-and-boredom-detector-design.md`](../specs/2026-05-24-mapping-growth-and-boredom-detector-design.md)

---

## File map

| File | Action | Responsibility |
|---|---|---|
| `server/config.py` | Modify | Add `SEED_LOCATIONS` list |
| `server/map_manager.py` | Modify | Merge seeds in `get_known_locations()`; add `rename_node()` + `delete_node()` helpers |
| `server/command_generator.py` | Modify | Add `BoredomState` dataclass + boredom constants + `check_and_override_if_bored()` + `_execute_commit_step()`; update prompt text; add location validator |
| `server/server_control.py` | Modify | Reorder override chain (emergency-stop / boredom / blind / stuck / sanitize); add `--boredom-detector` flag; add `--review-map` mode; wire location validator |
| `tests/test_map_manager.py` | Modify | Add tests for seed-merge, rename, delete |
| `tests/test_command_generator.py` | Modify | Add tests for new prompt text + location validator |
| `tests/test_boredom_detector.py` | Create | Unit tests for state machine, signals, commit sequence, cooldown, emergency abort |

---

## Task 1: Seed list + merge into `get_known_locations`

**Files:**
- Modify: `server/config.py`
- Modify: `server/map_manager.py:204-207`
- Modify: `tests/test_map_manager.py`

- [ ] **Step 1: Write failing test in `tests/test_map_manager.py`**

Append to the file before the `if __name__ == "__main__":` block:

```python
# ---------------------------------------------------------------------------
# Task 5: Seeded known_locations
# ---------------------------------------------------------------------------

def test_known_locations_includes_seeds_when_no_nodes():
    from server import config as server_config
    mm = MapManager()
    known = mm.get_known_locations()
    for seed in server_config.SEED_LOCATIONS:
        assert seed in known, f"seed '{seed}' missing from known_locations"


def test_known_locations_observed_first_then_seeds():
    from server import config as server_config
    mm = MapManager()
    mm.add_node("garage", "Garage", [], "concrete")
    known = mm.get_known_locations()
    # Observed nodes come first
    assert known[0] == "garage"
    # Seeds follow (any order among seeds is fine)
    seed_portion = known[1:]
    for seed in server_config.SEED_LOCATIONS:
        assert seed in seed_portion


def test_known_locations_deduplicates_observed_and_seeds():
    from server import config as server_config
    mm = MapManager()
    # 'office' is in SEED_LOCATIONS; if we observe it, it should appear once
    assert "office" in server_config.SEED_LOCATIONS
    mm.add_node("office", "Office", [], "tile")
    known = mm.get_known_locations()
    assert known.count("office") == 1
```

Also add three new function calls to the `__main__` runner so they execute:

```python
    test_known_locations_includes_seeds_when_no_nodes()
    test_known_locations_observed_first_then_seeds()
    test_known_locations_deduplicates_observed_and_seeds()
```

- [ ] **Step 2: Run tests to confirm failure**

Run: `python tests/test_map_manager.py`
Expected: FAIL with `AttributeError: module 'server.config' has no attribute 'SEED_LOCATIONS'` or similar.

- [ ] **Step 3: Add `SEED_LOCATIONS` to `server/config.py`**

Append after the `config = ServerConfig()` line at the bottom of the file:

```python
# Seed vocabulary for the map. These appear in the AI prompt's KNOWN LOCATIONS
# list so the model has plausible room names to choose from. They are NOT
# pre-created as MapNodes — nodes are created only when the model identifies
# a room during a drive.
SEED_LOCATIONS = [
    "office", "hallway", "living", "kitchen",
    "dining", "bedroom", "bathroom",
]
```

- [ ] **Step 4: Modify `get_known_locations()` in `server/map_manager.py`**

Replace the existing method (lines 204-207):

```python
    def get_known_locations(self) -> List[str]:
        """Observed node IDs first, then seed candidates not yet visited."""
        from server import config as server_config
        observed = list(self.nodes.keys())
        observed_set = set(observed)
        seeds = [s for s in server_config.SEED_LOCATIONS if s not in observed_set]
        return observed + seeds
```

- [ ] **Step 5: Run tests to confirm pass**

Run: `python tests/test_map_manager.py`
Expected: `All map manager tests passed!`

- [ ] **Step 6: Commit**

```bash
git add server/config.py server/map_manager.py tests/test_map_manager.py
git commit -m "Add SEED_LOCATIONS and merge into map known_locations

Seeds plausible room names into the prompt's KNOWN LOCATIONS list
without pre-creating MapNodes. Observed rooms still rank first."
```

---

## Task 2: Update the LOCATION prompt to allow propose-new

**Files:**
- Modify: `server/command_generator.py:386-389`
- Modify: `tests/test_command_generator.py`

- [ ] **Step 1: Update existing test in `tests/test_command_generator.py`**

Replace the `test_prompt_includes_known_locations` test with this expanded version and add a new test for propose-new instructions:

```python
def test_prompt_includes_known_locations():
    cg = CommandGenerator()
    known = ["office", "hallway", "kitchen"]
    prompt = cg.build_prompt("Explore", known_locations=known)
    assert "KNOWN LOCATIONS:" in prompt
    assert "office" in prompt
    assert "hallway" in prompt
    assert "kitchen" in prompt


def test_prompt_allows_proposing_new_location_name():
    cg = CommandGenerator()
    prompt = cg.build_prompt("Explore", known_locations=["office"])
    # Prompt should explicitly invite proposing a new name when in a new area
    assert "propose" in prompt.lower()
    # And should keep 'unknown' as a fallback for genuine uncertainty
    assert "unknown" in prompt.lower()


def test_prompt_without_known_locations_omits_section():
    cg = CommandGenerator()
    prompt = cg.build_prompt("Explore")
    assert "KNOWN LOCATIONS" not in prompt
```

Add a `__main__` runner block if the file doesn't already have one. Check first:

```bash
grep -n "__main__" tests/test_command_generator.py
```

If missing, append to the file:

```python
if __name__ == "__main__":
    test_parse_location_from_response()
    test_parse_location_unknown()
    test_parse_no_location()
    test_prompt_includes_known_locations()
    test_prompt_allows_proposing_new_location_name()
    test_prompt_without_known_locations_omits_section()
    print("All command generator tests passed!")
```

If it already exists, just add the two new test calls inside it.

- [ ] **Step 2: Run tests to confirm failure**

Run: `python tests/test_command_generator.py`
Expected: FAIL on `test_prompt_allows_proposing_new_location_name` because the current prompt does not contain the word "propose".

- [ ] **Step 3: Modify the prompt in `server/command_generator.py`**

Replace lines 386-389 (`if known_locations:` block):

```python
        # Add map locations if available
        if known_locations:
            locs = ", ".join(known_locations)
            prompt += f"\nKNOWN LOCATIONS: {locs}"
            prompt += (
                "\nPick the best match from this list. If you're confident "
                "you're in a different area, propose a short one-word name "
                "(e.g. closet, garage). Say 'unknown' only if you genuinely "
                "cannot tell."
            )
```

- [ ] **Step 4: Run tests to confirm pass**

Run: `python tests/test_command_generator.py`
Expected: `All command generator tests passed!`

- [ ] **Step 5: Commit**

```bash
git add server/command_generator.py tests/test_command_generator.py
git commit -m "Allow vision model to propose new location names in prompt

Replaces 'pick from list or unknown' with 'pick from list, propose
new one-word name, or unknown'. Unblocks map growth from first-time
visits to rooms not in KNOWN LOCATIONS."
```

---

## Task 3: Location-name validator

**Files:**
- Modify: `server/command_generator.py` (add helper)
- Modify: `tests/test_command_generator.py` (add tests)

- [ ] **Step 1: Write failing tests in `tests/test_command_generator.py`**

Add these tests:

```python
def test_validate_location_accepts_simple_names():
    from server.command_generator import is_valid_location_name
    for name in ["office", "kitchen", "bedroom2", "guest_room", "a"]:
        assert is_valid_location_name(name), f"should accept {name!r}"


def test_validate_location_rejects_garbage():
    from server.command_generator import is_valid_location_name
    bad = [
        "",
        "Office",                # uppercase
        "1room",                 # starts with digit
        "room with spaces",
        "a-b",                   # hyphen
        "room!",                 # punctuation
        "x" * 20,                # too long (>16 chars)
    ]
    for name in bad:
        assert not is_valid_location_name(name), f"should reject {name!r}"
```

Add to the `__main__` runner:

```python
    test_validate_location_accepts_simple_names()
    test_validate_location_rejects_garbage()
```

- [ ] **Step 2: Run tests to confirm failure**

Run: `python tests/test_command_generator.py`
Expected: FAIL with `ImportError: cannot import name 'is_valid_location_name'`.

- [ ] **Step 3: Add `is_valid_location_name` to `server/command_generator.py`**

Add as a module-level function (after the imports, before the `BLIND_KEYWORDS` constant near line 40):

```python
_LOCATION_NAME_RE = re.compile(r'^[a-z][a-z0-9_]{0,15}$')


def is_valid_location_name(name: str) -> bool:
    """True iff `name` is a safe location identifier for the map.

    Rules: lowercase, starts with a letter, only [a-z0-9_], 1-16 chars total.
    Used to reject hallucinated multi-word or punctuated names before they
    pollute the map.
    """
    return bool(name) and bool(_LOCATION_NAME_RE.match(name))
```

- [ ] **Step 4: Run tests to confirm pass**

Run: `python tests/test_command_generator.py`
Expected: `All command generator tests passed!`

- [ ] **Step 5: Wire validator into `server/server_control.py`**

In the map-integration block around line 218, add validation before the `parsed.location != "unknown"` branch. Replace the existing block (lines 218-245) with:

```python
                    # Map integration
                    if self.map_manager and parsed.location:
                        # Reject malformed names — fall back to 'unknown'
                        if (parsed.location != "unknown"
                                and not is_valid_location_name(parsed.location)):
                            logger.warning(
                                f"Invalid location name '{parsed.location}' "
                                f"— treating as unknown"
                            )
                            parsed.location = "unknown"

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
```

Also add the import at the top of `server/server_control.py` next to the other command_generator import (line 21). Change:

```python
from server.command_generator import CommandGenerator, SimpleCommandParser
```

to:

```python
from server.command_generator import CommandGenerator, SimpleCommandParser, is_valid_location_name
```

- [ ] **Step 6: Smoke test — import works**

Run: `python -c "from server.server_control import ServerController; print('OK')"`
Expected: `OK`

- [ ] **Step 7: Commit**

```bash
git add server/command_generator.py server/server_control.py tests/test_command_generator.py
git commit -m "Add is_valid_location_name validator; reject garbage names

Names must be lowercase, start with a letter, contain only [a-z0-9_],
and be 1-16 chars. Invalid names from the vision model are demoted to
'unknown' instead of polluting the map."
```

---

## Task 4: `rename_node` and `delete_node` helpers on MapManager

**Files:**
- Modify: `server/map_manager.py`
- Modify: `tests/test_map_manager.py`

- [ ] **Step 1: Write failing tests in `tests/test_map_manager.py`**

Append before the `__main__` runner:

```python
# ---------------------------------------------------------------------------
# Task 6: rename_node / delete_node — used by --review-map curation
# ---------------------------------------------------------------------------

def test_rename_node_updates_node_id():
    mm = MapManager()
    mm.add_node("unknown_x1", "Unknown X1", [], "tile")
    mm.rename_node("unknown_x1", "garage")
    assert mm.get_node("unknown_x1") is None
    node = mm.get_node("garage")
    assert node is not None
    assert node.id == "garage"


def test_rename_node_updates_edges():
    mm = MapManager()
    mm.add_node("unknown_x1", "Unknown X1", [], "tile")
    mm.add_node("hallway", "Hallway", [], "tile")
    crumbs = [{"left_speed": 190, "right_speed": 190,
               "left_dir": 1, "right_dir": 1, "duration_ms": 2000}]
    mm.add_edge("unknown_x1", "hallway", crumbs)
    mm.add_edge("hallway", "unknown_x1", crumbs)

    mm.rename_node("unknown_x1", "garage")

    # Edges should now reference 'garage', not 'unknown_x1'
    from_ids = {e.from_id for e in mm.edges}
    to_ids = {e.to_id for e in mm.edges}
    assert "unknown_x1" not in from_ids
    assert "unknown_x1" not in to_ids
    assert "garage" in from_ids
    assert "garage" in to_ids


def test_rename_node_missing_is_noop():
    mm = MapManager()
    mm.rename_node("nonexistent", "garage")  # should not raise
    assert mm.get_node("garage") is None


def test_delete_node_removes_node_and_edges():
    mm = MapManager()
    mm.add_node("kitchen", "Kitchen", [], "tile")
    mm.add_node("hallway", "Hallway", [], "tile")
    crumbs = [{"left_speed": 190, "right_speed": 190,
               "left_dir": 1, "right_dir": 1, "duration_ms": 2000}]
    mm.add_edge("kitchen", "hallway", crumbs)
    mm.add_edge("hallway", "kitchen", crumbs)

    mm.delete_node("kitchen")

    assert mm.get_node("kitchen") is None
    assert all(e.from_id != "kitchen" and e.to_id != "kitchen"
               for e in mm.edges)


def test_delete_node_missing_is_noop():
    mm = MapManager()
    mm.delete_node("nonexistent")  # should not raise
```

Add to `__main__` runner:

```python
    test_rename_node_updates_node_id()
    test_rename_node_updates_edges()
    test_rename_node_missing_is_noop()
    test_delete_node_removes_node_and_edges()
    test_delete_node_missing_is_noop()
```

- [ ] **Step 2: Run tests to confirm failure**

Run: `python tests/test_map_manager.py`
Expected: FAIL on `AttributeError: 'MapManager' object has no attribute 'rename_node'`.

- [ ] **Step 3: Add `rename_node` and `delete_node` to `server/map_manager.py`**

Add as methods of `MapManager`, just before `get_known_locations` (around line 204):

```python
    def rename_node(self, old_id: str, new_id: str) -> None:
        """Rename a node and rewrite any edges that reference it.

        No-op if `old_id` is not present.
        """
        if old_id not in self.nodes:
            return
        node = self.nodes.pop(old_id)
        node.id = new_id
        self.nodes[new_id] = node
        for edge in self.edges:
            if edge.from_id == old_id:
                edge.from_id = new_id
            if edge.to_id == old_id:
                edge.to_id = new_id
        logger.info(f"Renamed map node: {old_id} → {new_id}")

    def delete_node(self, node_id: str) -> None:
        """Delete a node and all edges that reference it.

        No-op if `node_id` is not present.
        """
        if node_id not in self.nodes:
            return
        del self.nodes[node_id]
        self.edges = [e for e in self.edges
                      if e.from_id != node_id and e.to_id != node_id]
        logger.info(f"Deleted map node: {node_id}")
```

- [ ] **Step 4: Run tests to confirm pass**

Run: `python tests/test_map_manager.py`
Expected: `All map manager tests passed!`

- [ ] **Step 5: Commit**

```bash
git add server/map_manager.py tests/test_map_manager.py
git commit -m "Add rename_node and delete_node to MapManager

Both update edge references and are no-ops for missing IDs. Will be
used by the --review-map curation mode."
```

---

## Task 5: `--review-map` interactive curation mode

**Files:**
- Modify: `server/server_control.py`

This task has no automated tests — it's an interactive stdin-driven utility. We verify by running it manually against a temporary map.

- [ ] **Step 1: Add `run_review_map` method to `ServerController`**

Insert this method just before `def main()` at the bottom of `server/server_control.py` (around line 410):

```python
    def run_review_map(self) -> None:
        """Interactive map curation: rename, delete, or keep each node.

        No network, no AI, no Pi connection. Operates purely on the
        local map_data.json file.
        """
        if not self.map_manager:
            logger.error("Mapping not enabled")
            return

        self.map_manager.load()
        if not self.map_manager.nodes:
            print("Map is empty — nothing to review.")
            return

        print(f"\n{len(self.map_manager.nodes)} node(s), "
              f"{len(self.map_manager.edges)} edge(s)\n")

        for node_id in list(self.map_manager.nodes.keys()):
            node = self.map_manager.nodes[node_id]
            print(f"--- {node_id} ---")
            print(f"  label:        {node.label}")
            print(f"  visit_count:  {node.visit_count}")
            print(f"  floor_type:   {node.floor_type}")
            print(f"  last_visited: {node.last_visited}")
            print(f"  landmarks:    {node.landmarks}")
            neighbors = self.map_manager.get_neighbors(node_id)
            print(f"  neighbors:    {neighbors}")

            while True:
                choice = input("(k)eep / (r)ename / (d)elete: ").strip().lower()
                if choice in ("k", "keep", ""):
                    break
                if choice in ("r", "rename"):
                    new_id = input("  new name: ").strip().lower()
                    if not is_valid_location_name(new_id):
                        print(f"  '{new_id}' is not a valid name. Try again.")
                        continue
                    if new_id in self.map_manager.nodes:
                        print(f"  '{new_id}' already exists. Try again.")
                        continue
                    self.map_manager.rename_node(node_id, new_id)
                    print(f"  renamed → {new_id}")
                    break
                if choice in ("d", "delete"):
                    confirm = input(f"  delete '{node_id}'? (y/N): ").strip().lower()
                    if confirm == "y":
                        self.map_manager.delete_node(node_id)
                        print(f"  deleted {node_id}")
                    break
                print("  Choose k, r, or d.")
            print()

        self.map_manager.save()
        print(f"Saved: {len(self.map_manager.nodes)} node(s), "
              f"{len(self.map_manager.edges)} edge(s)")
```

- [ ] **Step 2: Add `--review-map` CLI flag**

In the `main()` function in `server/server_control.py`, add a new argument near the other `add_argument` blocks (after `--home`, around line 459):

```python
    parser.add_argument(
        '--review-map',
        action='store_true',
        help='Interactive map review: rename, delete, or keep each node'
    )
```

- [ ] **Step 3: Wire the flag into the dispatch in `main()`**

In the `try:` block (around line 478), add a `--review-map` branch BEFORE `controller.start()` so we don't spin up the network/model for a pure file operation. Replace the existing try block:

```python
    try:
        # --review-map is a pure file op — skip network/model startup
        if args.review_map:
            controller.run_review_map()
            return

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
```

Also: `--review-map` needs `self.map_manager` to exist, but `ServerController.__init__` only creates one when `not manual_mode and config.enable_mapping`. Update the controller construction (around line 467):

```python
    # Create controller (skip model load for --review-map)
    if args.review_map:
        controller = ServerController(manual_mode=True)
        # Force-enable map_manager even though manual_mode is True
        controller.map_manager = MapManager(config.map_file)
    else:
        controller = ServerController(manual_mode=args.manual)
```

Add the import at the top of `server_control.py` if it's not already there (check line 22 — `MapManager` is already imported).

- [ ] **Step 4: Manual smoke test**

Use the current `map_data.json` (2 nodes, 1 edge). Test rename, then test delete, then verify the file roundtrips.

```bash
# First, back up the real map
cp map_data.json map_data.json.backup

# Run review and rename 'living' → 'living_room' (keep the other)
echo -e "r\nliving_room\nk" | python -m server.server_control --review-map

# Verify
cat map_data.json
```

Expected: `living_room` appears as a key in `nodes`, and the edge's `"from"` field is now `living_room`.

Restore the real map after testing:

```bash
mv map_data.json.backup map_data.json
```

- [ ] **Step 5: Commit**

```bash
git add server/server_control.py
git commit -m "Add --review-map mode for interactive map curation

Loads map_data.json, walks each node, allows (k)eep / (r)ename /
(d)elete with validation. Rename rewrites edge references. Pure
file operation — no network, no AI, no Pi."
```

---

## Task 6: `BoredomState` dataclass + constants

**Files:**
- Modify: `server/command_generator.py`

- [ ] **Step 1: Add the dataclass and constants near the top of `server/command_generator.py`**

Add immediately after `from dataclasses import dataclass` (around line 12), import `field` and `deque`, and add the new class. Replace line 12:

```python
from dataclasses import dataclass, field
from collections import deque
```

Then add a new dataclass definition right after `ControlState` (around line 38):

```python
@dataclass
class BoredomState:
    """Rolling-window state for the boredom detector + commit state machine."""
    recent_overrides: deque = field(default_factory=lambda: deque(maxlen=20))
    recent_front_distances: deque = field(default_factory=lambda: deque(maxlen=20))
    commit_state: Optional[str] = None       # None | 'rotate' | 'forward'
    commit_direction: Optional[str] = None   # 'left' | 'right'
    cooldown_frames: int = 0
```

- [ ] **Step 2: Add boredom constants to `CommandGenerator` class**

Add as class attributes immediately after the existing `CARPET_KEYWORDS = ...` line (around line 91):

```python
    # Boredom detector
    BOREDOM_WINDOW = 20                # ~1 min at ~3s/frame
    OVERRIDE_RATE_THRESHOLD = 0.5      # >=50% of window had any reflex override
    SENSOR_DELTA_THRESHOLD = 30        # total |FL+FR avg| change in cm over window
    BOREDOM_COOLDOWN_FRAMES = 10       # suppression after a commit completes
    BOREDOM_COMMIT_FORWARD_MS = 2000
    EMERGENCY_STOP_CM = 15             # front sensor threshold for absolute STOP
```

- [ ] **Step 3: Instantiate `self.boredom_state` in `CommandGenerator.__init__`**

Modify `__init__` (around line 80-83):

```python
    def __init__(self):
        """Initialize command generator."""
        self.state = ControlState()
        self.boredom_state = BoredomState(
            recent_overrides=deque(maxlen=self.BOREDOM_WINDOW),
            recent_front_distances=deque(maxlen=self.BOREDOM_WINDOW),
        )
        logger.info("CommandGenerator initialized")
```

- [ ] **Step 4: Smoke test — import + instantiate**

Run:

```bash
python -c "
from server.command_generator import CommandGenerator, BoredomState
cg = CommandGenerator()
assert cg.boredom_state.commit_state is None
assert cg.boredom_state.recent_overrides.maxlen == 20
assert CommandGenerator.EMERGENCY_STOP_CM == 15
print('OK')
"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add server/command_generator.py
git commit -m "Add BoredomState dataclass and boredom constants

State and constants only — detection logic and commit sequence land
in subsequent commits. Each CommandGenerator now owns one
BoredomState with the deque buffers pre-sized."
```

---

## Task 7: Boredom detection — trigger logic

**Files:**
- Create: `tests/test_boredom_detector.py`
- Modify: `server/command_generator.py`

- [ ] **Step 1: Create `tests/test_boredom_detector.py` with detection tests**

```python
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
    """A generic 'AI said forward' response, no overrides applied."""
    return ParsedResponse(
        command=MotorCommand.forward(190, 1500),
        observation="Clear path ahead",
        assessment="Path clear",
        reasoning="Moving forward",
        location="office",
    )


def _sensors(fl=100, fr=100, rl=100, rr=100, fc=None) -> SensorData:
    """Build a SensorData with explicit per-channel readings."""
    return SensorData(fc=fc, fl=fl, fr=fr, rl=rl, rr=rr)


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
```

- [ ] **Step 2: Run tests to confirm failure**

Run: `python tests/test_boredom_detector.py`
Expected: FAIL with `AttributeError: 'CommandGenerator' object has no attribute 'check_and_override_if_bored'`.

- [ ] **Step 3: Implement `check_and_override_if_bored` in `server/command_generator.py`**

Add this method to the `CommandGenerator` class, right after `check_and_override_if_stuck` (around line 290):

```python
    def _least_blocked_rear_dir(self, sensor_data: SensorData) -> str:
        """Pick rotation direction so the rear swings toward the more open side.

        Identical heuristic to _pick_escape_dir but stays robust if that
        method is later removed.
        """
        d = sensor_data.to_dict() if sensor_data else {}
        rl = d.get('rl') or 999
        rr = d.get('rr') or 999
        return 'right' if rl < rr else 'left'

    def _front_avg(self, sensor_data: SensorData) -> float:
        """Average of FL and FR, treating None as 999 (sensor 'sees nothing')."""
        if sensor_data is None:
            return 999.0
        d = sensor_data.to_dict()
        fl = d.get('fl') if d.get('fl') is not None else 999
        fr = d.get('fr') if d.get('fr') is not None else 999
        return (fl + fr) / 2.0

    def check_and_override_if_bored(self, parsed: ParsedResponse,
                                     sensor_data: SensorData,
                                     override_applied_this_frame: bool) -> ParsedResponse:
        """Detect rut-running over a rolling window; force a 2-frame commit.

        Composite signal:
          - override_rate >= OVERRIDE_RATE_THRESHOLD (reflexes thrashing), OR
          - sensor_delta_sum < SENSOR_DELTA_THRESHOLD (car not moving).

        When in mid-commit (commit_state != None), advance the state machine
        and return the forced command for the current phase.
        """
        bs = self.boredom_state

        # Update rolling buffers with the PREVIOUS frame's outcome.
        bs.recent_overrides.append(bool(override_applied_this_frame))
        bs.recent_front_distances.append(self._front_avg(sensor_data))

        # If we're mid-commit, advance the state machine and return forced cmd.
        if bs.commit_state is not None:
            return self._execute_commit_step(parsed, sensor_data)

        # Cooldown blocks re-trigger.
        if bs.cooldown_frames > 0:
            bs.cooldown_frames -= 1
            return parsed

        # Need a full window before evaluating signals.
        if len(bs.recent_overrides) < self.BOREDOM_WINDOW:
            return parsed

        # Compute signals.
        override_rate = sum(bs.recent_overrides) / float(self.BOREDOM_WINDOW)
        d = list(bs.recent_front_distances)
        sensor_delta_sum = sum(abs(d[i] - d[i - 1]) for i in range(1, len(d)))

        bored = (override_rate >= self.OVERRIDE_RATE_THRESHOLD
                 or sensor_delta_sum < self.SENSOR_DELTA_THRESHOLD)

        if not bored:
            return parsed

        # Trigger: start the commit sequence.
        bs.commit_state = 'rotate'
        bs.commit_direction = self._least_blocked_rear_dir(sensor_data)
        bs.recent_overrides.clear()
        bs.recent_front_distances.clear()
        logger.warning(
            f"BOREDOM TRIGGERED: override_rate={override_rate:.2f} "
            f"sensor_delta={sensor_delta_sum:.0f}cm window={self.BOREDOM_WINDOW} "
            f"→ commit rotate-{bs.commit_direction}"
        )
        return self._execute_commit_step(parsed, sensor_data)
```

Also add a stub for `_execute_commit_step` immediately after — full implementation comes in Task 8:

```python
    def _execute_commit_step(self, parsed: ParsedResponse,
                              sensor_data: SensorData) -> ParsedResponse:
        """Stub — replaced with state machine in Task 8."""
        bs = self.boredom_state
        if bs.commit_state == 'rotate':
            direction = bs.commit_direction or 'left'
            if direction == 'left':
                parsed.command = MotorCommand.rotate_left(self.MAX_ROTATION_SPEED, 1050)
            else:
                parsed.command = MotorCommand.rotate_right(self.MAX_ROTATION_SPEED, 1800)
            parsed.reasoning = f"BOREDOM COMMIT 1/2: rotate-{direction}"
            bs.commit_state = 'forward'
            return parsed
        # 'forward' or any other state — full handling in Task 8
        bs.commit_state = None
        bs.cooldown_frames = self.BOREDOM_COOLDOWN_FRAMES
        return parsed
```

- [ ] **Step 4: Run tests to confirm pass**

Run: `python tests/test_boredom_detector.py`
Expected: `Boredom detector tests passed (Task 7)`

- [ ] **Step 5: Commit**

```bash
git add server/command_generator.py tests/test_boredom_detector.py
git commit -m "Boredom detector: trigger logic on composite signal

Tracks override-rate and sensor-delta in a 20-frame rolling window.
Triggers when EITHER signal crosses threshold. Sets commit_state to
'rotate' on trigger. Full commit state machine lands in next commit."
```

---

## Task 8: Commit state machine — rotate → forward → cooldown

**Files:**
- Modify: `server/command_generator.py`
- Modify: `tests/test_boredom_detector.py`

- [ ] **Step 1: Add failing tests in `tests/test_boredom_detector.py`**

Insert before the `__main__` runner, after the Task 7 tests:

```python
# ---------------------------------------------------------------------------
# Task 8: Commit sequence — rotate → forward → cooldown
# ---------------------------------------------------------------------------

def _fill_buffer_until_trigger(cg):
    """Helper: fill buffer with quiet+stationary signal to force a trigger
    on the next call. Returns the trigger-frame result."""
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
    # Frame 1 (trigger frame): rotate
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
    # During cooldown, fill the buffer again with a triggering signal
    for _ in range(CommandGenerator.BOREDOM_COOLDOWN_FRAMES):
        result = cg.check_and_override_if_bored(
            _ai_forward_response(),
            _sensors(fl=100, fr=100),
            override_applied_this_frame=True,
        )
        # No commit should fire while cooldown is active
        assert cg.boredom_state.commit_state is None
    # After cooldown expires AND buffer is full, a fresh trigger should fire
    assert cg.boredom_state.cooldown_frames == 0
```

Add to `__main__`:

```python
    test_commit_frame1_is_rotate()
    test_commit_frame2_is_forward()
    test_commit_frame3_is_ai_command()
    test_cooldown_blocks_retrigger()
```

- [ ] **Step 2: Run tests to confirm partial failure**

Run: `python tests/test_boredom_detector.py`
Expected: PASS on `test_commit_frame1_is_rotate` (stub handles it), but FAIL on `test_commit_frame2_is_forward` because the stub doesn't emit a forward command — it just transitions out of the commit state.

- [ ] **Step 3: Replace the stub `_execute_commit_step` with the real implementation**

In `server/command_generator.py`, replace the stub from Task 7 with:

```python
    def _execute_commit_step(self, parsed: ParsedResponse,
                              sensor_data: SensorData) -> ParsedResponse:
        """Advance the commit state machine and emit the forced command.

        rotate (frame N) → forward (frame N+1) → None + cooldown engaged
        """
        bs = self.boredom_state

        if bs.commit_state == 'rotate':
            direction = bs.commit_direction or 'left'
            if direction == 'left':
                parsed.command = MotorCommand.rotate_left(self.MAX_ROTATION_SPEED, 1050)
            else:
                parsed.command = MotorCommand.rotate_right(self.MAX_ROTATION_SPEED, 1800)
            parsed.reasoning = f"BOREDOM COMMIT 1/2: rotate-{direction} {self.MAX_ROTATION_SPEED}"
            logger.warning(parsed.reasoning)
            bs.commit_state = 'forward'
            return parsed

        if bs.commit_state == 'forward':
            parsed.command = MotorCommand.forward(self.CARPET_SPEED,
                                                   self.BOREDOM_COMMIT_FORWARD_MS)
            parsed.reasoning = (f"BOREDOM COMMIT 2/2: forward {self.CARPET_SPEED} "
                                f"{self.BOREDOM_COMMIT_FORWARD_MS}ms")
            logger.warning(parsed.reasoning)
            bs.commit_state = None
            bs.commit_direction = None
            bs.cooldown_frames = self.BOREDOM_COOLDOWN_FRAMES
            return parsed

        # Unexpected state — clear and yield back to AI
        bs.commit_state = None
        bs.commit_direction = None
        return parsed
```

- [ ] **Step 4: Run tests to confirm pass**

Run: `python tests/test_boredom_detector.py`
Expected: `Boredom detector tests passed (Task 7)` (the print line still says Task 7 — that's fine; we'll update later if it bothers us. The point is all assertions pass.)

Update the print line in the `__main__` block to be more accurate:

```python
    print("All boredom detector tests passed!")
```

Re-run to confirm:

Run: `python tests/test_boredom_detector.py`
Expected: `All boredom detector tests passed!`

- [ ] **Step 5: Commit**

```bash
git add server/command_generator.py tests/test_boredom_detector.py
git commit -m "Boredom detector: 2-frame commit state machine + cooldown

Rotate-90° → forward-2s @ carpet-speed → cooldown for 10 frames.
Cooldown blocks re-trigger even if signal stays bad. After cooldown,
buffer must refill before next evaluation."
```

---

## Task 9: Emergency-stop abort + integration into `server_control.py`

**Files:**
- Modify: `server/server_control.py`
- Modify: `tests/test_boredom_detector.py`

- [ ] **Step 1: Add failing tests for emergency-stop abort**

Append before the `__main__` runner in `tests/test_boredom_detector.py`:

```python
# ---------------------------------------------------------------------------
# Task 9: Emergency-stop abort
# ---------------------------------------------------------------------------

def test_emergency_stop_during_commit_clears_state():
    """Simulate the server_control.py contract: when front sensors read
    below EMERGENCY_STOP_CM, the caller is responsible for clearing the
    commit state and engaging cooldown."""
    cg = CommandGenerator()
    _fill_buffer_until_trigger(cg)
    # Mid-commit (state is now 'forward'). Caller detects emergency.
    cg.boredom_state.commit_state = None
    cg.boredom_state.commit_direction = None
    cg.boredom_state.cooldown_frames = CommandGenerator.BOREDOM_COOLDOWN_FRAMES
    # Subsequent boredom call should NOT execute the forward step;
    # buffer-update happens and cooldown decrements
    parsed = _ai_forward_response()
    result = cg.check_and_override_if_bored(
        parsed, _sensors(fl=10, fr=10),
        override_applied_this_frame=True,
    )
    # Command unchanged (AI command passes through), cooldown decremented
    assert result.command == parsed.command
    assert cg.boredom_state.cooldown_frames == CommandGenerator.BOREDOM_COOLDOWN_FRAMES - 1
```

Add to `__main__`:

```python
    test_emergency_stop_during_commit_clears_state()
```

- [ ] **Step 2: Run tests to confirm pass (this validates the contract — no code change yet)**

Run: `python tests/test_boredom_detector.py`
Expected: `All boredom detector tests passed!`

This passes because the abort behavior is enforced by the caller, not by `check_and_override_if_bored`. The test documents the contract.

- [ ] **Step 3: Modify `server/server_control.py` override chain**

In `run_ai_control` (around line 99), find the existing block from line 161 to ~186. Replace it with the new ordered chain. The full replacement starts at `if parsed.command is None:` and goes through the `_sanitize_command` call (currently lines 161-186):

```python
                    if parsed.command is None:
                        logger.warning("Failed to parse command, using fallback")
                        parsed.command = self.command_generator.get_safe_fallback_command()
                        parsed.reasoning = "Parse failed - emergency stop"

                    # Snapshot the raw model command for training-data provenance
                    command_before_overrides = parsed.command
                    overrides_applied = []

                    # ---- New override chain ----

                    # 0. Emergency-stop watchdog — always wins
                    d = sensor_data.to_dict() if sensor_data else {}
                    fl = d.get('fl') if d.get('fl') is not None else 999
                    fr = d.get('fr') if d.get('fr') is not None else 999
                    if min(fl, fr) < CommandGenerator.EMERGENCY_STOP_CM:
                        parsed.command = MotorCommand.stop()
                        parsed.reasoning = (
                            f"EMERGENCY: front <{CommandGenerator.EMERGENCY_STOP_CM}cm "
                            f"(fl={fl} fr={fr})"
                        )
                        overrides_applied.append("emergency_stop")
                        # Abort any in-progress commit
                        bs = self.command_generator.boredom_state
                        if bs.commit_state is not None:
                            logger.warning(
                                f"BOREDOM ABORTED: emergency stop fl={fl}cm fr={fr}cm"
                            )
                            bs.commit_state = None
                            bs.commit_direction = None
                            bs.cooldown_frames = CommandGenerator.BOREDOM_COOLDOWN_FRAMES

                    # 1. Boredom — wins over AI + other reflexes when enabled
                    elif self.boredom_enabled:
                        before_bored = parsed.command
                        # commit_state BEFORE the call tells us what phase fires
                        phase_before = self.command_generator.boredom_state.commit_state
                        parsed = self.command_generator.check_and_override_if_bored(
                            parsed, sensor_data, self.last_frame_had_override
                        )
                        if parsed.command is not before_bored:
                            # Tag with the phase that JUST executed
                            tag = phase_before if phase_before else 'trigger'
                            overrides_applied.append(f"boredom_commit_{tag}")

                    # 2 & 3. Blind / stuck reflexes — only if boredom didn't override
                    boredom_fired = any(t.startswith("boredom_commit_")
                                         for t in overrides_applied)
                    if not boredom_fired and "emergency_stop" not in overrides_applied:
                        before_blind = parsed.command
                        parsed = self.command_generator.check_and_override_if_blind(parsed)
                        if parsed.command is not before_blind:
                            overrides_applied.append("blind_reflex")

                        before_stuck = parsed.command
                        parsed = self.command_generator.check_and_override_if_stuck(parsed, sensor_data)
                        if parsed.command is not before_stuck:
                            overrides_applied.append("stuck_escape")

                    # 4. Sanitize (caps speed/duration, applies carpet boost)
                    if parsed.command:
                        before_sanitize = parsed.command
                        parsed.command = self.command_generator._sanitize_command(parsed.command)
                        if parsed.command != before_sanitize:
                            overrides_applied.append("sanitize")

                    # Track for next frame's boredom calculation
                    self.last_frame_had_override = bool(overrides_applied)
```

- [ ] **Step 4: Initialize the new instance attributes in `ServerController.__init__`**

Modify `__init__` (around lines 37-56):

```python
    def __init__(self, manual_mode: bool = False, boredom_enabled: bool = False):
        """
        Initialize server controller.

        Args:
            manual_mode: If True, accept keyboard commands instead of AI
            boredom_enabled: If True, run the boredom detector in AI mode
        """
        self.manual_mode = manual_mode
        self.boredom_enabled = boredom_enabled
        self.last_frame_had_override = False
        self.vision_model = None if manual_mode else VisionModel()
        self.network_server = NetworkServer(config.host, config.port)
        self.command_generator = CommandGenerator()
        self.running = False

        self.map_manager = None
        if not manual_mode and config.enable_mapping:
            self.map_manager = MapManager(config.map_file)

        self.training_logger = None if manual_mode else TrainingLogger()

        logger.info(f"ServerController initialized "
                    f"(manual_mode={manual_mode}, boredom_enabled={boredom_enabled})")
```

- [ ] **Step 5: Smoke test — import + instantiate**

Run:

```bash
python -c "
from server.server_control import ServerController
from server.command_generator import CommandGenerator
c = ServerController(manual_mode=True, boredom_enabled=True)
assert c.boredom_enabled is True
assert c.last_frame_had_override is False
print('OK')
"
```

Expected: `OK`

- [ ] **Step 6: Re-run boredom unit tests to confirm they still pass**

Run: `python tests/test_boredom_detector.py`
Expected: `All boredom detector tests passed!`

- [ ] **Step 7: Commit**

```bash
git add server/server_control.py tests/test_boredom_detector.py
git commit -m "Wire boredom detector into server_control override chain

New priority: emergency-stop (<15cm) > boredom commit > blind/stuck
reflexes > sanitize. Emergency stop aborts in-progress commits and
engages cooldown. Boredom suppresses blind/stuck while active."
```

---

## Task 10: `--boredom-detector` CLI flag

**Files:**
- Modify: `server/server_control.py`

- [ ] **Step 1: Add the flag in `main()`**

Add to the argparse block (after `--review-map`, around line 462):

```python
    parser.add_argument(
        '--boredom-detector',
        action='store_true',
        help='Enable boredom-detector reflex (off by default; use for explore drives)'
    )
```

- [ ] **Step 2: Pass it through to `ServerController`**

Update the controller construction (around line 467, modified in Task 5). Replace:

```python
    if args.review_map:
        controller = ServerController(manual_mode=True)
        controller.map_manager = MapManager(config.map_file)
    else:
        controller = ServerController(manual_mode=args.manual)
```

with:

```python
    if args.review_map:
        controller = ServerController(manual_mode=True)
        controller.map_manager = MapManager(config.map_file)
    else:
        controller = ServerController(
            manual_mode=args.manual,
            boredom_enabled=args.boredom_detector,
        )
```

- [ ] **Step 3: Smoke test the CLI**

```bash
python -m server.server_control --help 2>&1 | grep -A1 boredom
```

Expected: `--boredom-detector` flag and its help text are listed.

- [ ] **Step 4: Verify the flag plumbs to the controller**

```bash
python -c "
import sys
sys.argv = ['server_control', '--boredom-detector', '--manual']
from server.server_control import main
# Don't actually run main — just import and parse
import argparse
from server.config import config
parser = argparse.ArgumentParser()
parser.add_argument('--manual', action='store_true')
parser.add_argument('--boredom-detector', action='store_true')
args = parser.parse_args(['--boredom-detector', '--manual'])
assert args.boredom_detector is True
print('OK')
"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add server/server_control.py
git commit -m "Add --boredom-detector CLI flag (off by default)

Enable for explore drives, skip for follow-the-human drives so the
forced commit sequence doesn't push the car past a stationary human."
```

---

## Task 11: Full integration smoke test

**Files:** None modified — verification only.

- [ ] **Step 1: Run all unit tests**

```bash
python tests/test_protocol.py
python tests/test_map_manager.py
python tests/test_command_generator.py
python tests/test_boredom_detector.py
```

Expected: each prints its "All ... tests passed!" message.

- [ ] **Step 2: Verify simulated-car path still works (no Pi needed)**

This is the existing simulate_car.py harness — confirm we haven't broken the manual-control path.

Terminal 1:
```bash
python -m server.server_control --manual
```

Terminal 2:
```bash
python tests/simulate_car.py
```

In Terminal 1, type `stop` and press Enter. Expected: command echoes, no errors.

Press Ctrl+C in both terminals.

- [ ] **Step 3: Verify `--boredom-detector` boots cleanly (without Pi)**

```bash
timeout 5 python -m server.server_control --boredom-detector --goal "explore" 2>&1 | tail -20
```

Expected output should include:
- `ServerController initialized (manual_mode=False, boredom_enabled=True)`
- `Map loaded: 2 nodes, 1 edges` (or whatever the current state is)
- `Loading vision model...` (then it times out at 5s — fine)
- No tracebacks.

- [ ] **Step 4: Verify `--review-map` still boots cleanly**

```bash
cp map_data.json map_data.json.backup
echo "k" | python -m server.server_control --review-map
mv map_data.json.backup map_data.json
```

Expected: prints the 2 nodes, accepts "k" (keep) for each, saves, no errors.

- [ ] **Step 5: Commit (only if any tweaks were needed during smoke test)**

Only commit if Steps 1-4 surfaced fixes. Otherwise skip — no changes to commit.

---

## Task 12: Drive day checklist

**Files:** None — this is a runbook for the actual 30-minute drive after the code is implemented and merged.

- [ ] Start Pi client: `ssh thinktank "cd ~/dev/robotcar && python3 -m pi.car_hardware"` (or current equivalent — verify with `ssh thinktank pgrep -f car_hardware` that nothing is already running)
- [ ] Confirm Pi connects: server log should show `Client connected`
- [ ] Start server: `python -m server.server_control --boredom-detector --goal "explore the house, identify rooms by their KNOWN LOCATIONS list, and drive into spaces you haven't visited"`
- [ ] During drive, watch for log lines:
  - `BOREDOM TRIGGERED: ...` (detector working)
  - `BOREDOM COMMIT 1/2: ...` / `BOREDOM COMMIT 2/2: ...` (commit firing)
  - `BOREDOM ABORTED: ...` (emergency stop kicked in mid-commit — note location for diagnosis)
  - `Map edge: <X> → <Y>` (map growing)
  - `New map node: <name>` (proposed-new working)
- [ ] After drive, stop the server (Ctrl+C — triggers map save via existing shutdown path).
- [ ] Curate the map: `python -m server.server_control --review-map`
- [ ] Inspect the training data directory for the session — confirm `overrides_applied` includes `boredom_commit_rotate` and `boredom_commit_forward` labels on appropriate frames.
- [ ] Log a lesson to claude-memory summarizing what worked and what needs tuning.

---

## Self-review notes

- **Spec coverage:** Section 1 (mapping growth) → Tasks 1-4. Section 1f (review-map) → Task 5. Section 2 (boredom state/signal) → Tasks 6-7. Section 3 (commit sequence + override priority) → Tasks 8-9. Section 4 (testing + drive) → Tasks 11-12. CLI flag → Task 10.
- **Placeholders:** None. Every code step has the full code; every test step has the full assertion.
- **Type consistency:** `BoredomState` defined once in Task 6 with field names that match references in Tasks 7, 8, 9. `is_valid_location_name` defined in Task 3 and reused in Task 5. `EMERGENCY_STOP_CM` defined as class attribute in Task 6, referenced as `CommandGenerator.EMERGENCY_STOP_CM` in Task 9.
- **One known gap:** The drive day checklist (Task 12) assumes the Pi-side Python client (`pi/car_hardware.py`) is launchable as today. The Rust client is incomplete and not part of this work. Pi-side is unchanged.
