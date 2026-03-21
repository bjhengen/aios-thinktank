# Topological Map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent topological map so the robot car learns the house layout across driving sessions and can navigate to named locations.

**Architecture:** Server-side only. A new `MapManager` class stores a JSON graph of rooms (nodes) connected by recorded motor command sequences (edges). The vision model identifies rooms by landmarks each frame, and transitions are recorded as breadcrumb trails. The command generator's prompt is extended with a `LOCATION:` output field and map context.

**Tech Stack:** Python dataclasses, JSON for persistence, BFS for pathfinding. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-03-21-topological-map-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `server/map_manager.py` | Create | Graph data model, persistence, BFS pathfinding |
| `tests/test_map_manager.py` | Create | Unit tests for map manager |
| `server/config.py` | Modify | Add `map_file` and `enable_mapping` settings |
| `server/command_generator.py` | Modify | Add `LOCATION:` to prompt/parser, map context injection |
| `tests/test_command_generator.py` | Create | Tests for location parsing and prompt building |
| `server/server_control.py` | Modify | Integrate map into control loop, add `--goto`/`--home` modes |

---

### Task 1: Map Manager — Data Model and Persistence

**Files:**
- Create: `server/map_manager.py`
- Create: `tests/test_map_manager.py`

- [ ] **Step 1: Write failing test for MapNode and MapEdge dataclasses**

```python
# tests/test_map_manager.py
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from server.map_manager import MapManager, MapNode, MapEdge


def test_map_node_creation():
    node = MapNode(id="kitchen", label="Kitchen",
                   landmarks=["white cabinets", "island"],
                   floor_type="tile")
    assert node.id == "kitchen"
    assert node.visit_count == 0
    assert "island" in node.landmarks


def test_map_edge_creation():
    breadcrumb = [
        {"left_speed": 190, "right_speed": 190, "left_dir": 1,
         "right_dir": 1, "duration_ms": 2000}
    ]
    edge = MapEdge(from_id="kitchen", to_id="hallway",
                   breadcrumb=breadcrumb)
    assert edge.from_id == "kitchen"
    assert edge.traversal_count == 0
    assert len(edge.breadcrumb) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/dev/robotcar && PYTHONPATH=. python -m pytest tests/test_map_manager.py::test_map_node_creation -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server.map_manager'`

- [ ] **Step 3: Implement MapNode, MapEdge, and empty MapManager**

```python
# server/map_manager.py
"""
Topological map manager for robot car navigation.

Stores a graph of rooms (nodes) connected by recorded motor command
sequences (edges). Persists to JSON for cross-session learning.
"""

import json
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from collections import deque

from shared.utils import setup_logging

logger = setup_logging(__name__)


@dataclass
class MapNode:
    """A room or area the car has visited."""
    id: str
    label: str
    landmarks: List[str] = field(default_factory=list)
    floor_type: str = "unknown"
    visit_count: int = 0
    last_visited: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id, "label": self.label,
            "landmarks": self.landmarks, "floor_type": self.floor_type,
            "visit_count": self.visit_count, "last_visited": self.last_visited,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MapNode":
        return cls(**d)


@dataclass
class MapEdge:
    """A recorded transition between two rooms."""
    from_id: str
    to_id: str
    breadcrumb: List[dict] = field(default_factory=list)
    traversal_count: int = 0

    def to_dict(self) -> dict:
        return {
            "from": self.from_id, "to": self.to_id,
            "breadcrumb": self.breadcrumb,
            "traversal_count": self.traversal_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MapEdge":
        return cls(
            from_id=d["from"], to_id=d["to"],
            breadcrumb=d.get("breadcrumb", []),
            traversal_count=d.get("traversal_count", 0),
        )


class MapManager:
    """Manages the topological map graph."""

    def __init__(self, map_file: str = "./map_data.json"):
        self.map_file = map_file
        self.nodes: Dict[str, MapNode] = {}
        self.edges: List[MapEdge] = []

    def load(self) -> None:
        """Load map from JSON file. No-op if file doesn't exist."""
        pass

    def save(self) -> None:
        """Save map to JSON file."""
        pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/dev/robotcar && PYTHONPATH=. python -m pytest tests/test_map_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/map_manager.py tests/test_map_manager.py
git commit -m "feat: add MapNode, MapEdge, and MapManager skeleton"
```

---

### Task 2: Map Manager — Add/Get Nodes and Edges

**Files:**
- Modify: `server/map_manager.py`
- Modify: `tests/test_map_manager.py`

- [ ] **Step 1: Write failing tests for add_node, get_node, add_edge, get_neighbors**

```python
def test_add_and_get_node():
    mm = MapManager()
    mm.add_node("kitchen", "Kitchen", ["white cabinets"], "tile")
    node = mm.get_node("kitchen")
    assert node is not None
    assert node.label == "Kitchen"
    assert node.visit_count == 1


def test_get_node_missing():
    mm = MapManager()
    assert mm.get_node("nonexistent") is None


def test_add_node_increments_visit():
    mm = MapManager()
    mm.add_node("kitchen", "Kitchen", ["cabinets"], "tile")
    mm.add_node("kitchen", "Kitchen", ["cabinets"], "tile")
    assert mm.get_node("kitchen").visit_count == 2


def test_add_edge():
    mm = MapManager()
    mm.add_node("kitchen", "Kitchen", [], "tile")
    mm.add_node("hallway", "Hallway", [], "tile")
    crumbs = [{"left_speed": 190, "right_speed": 190,
               "left_dir": 1, "right_dir": 1, "duration_ms": 2000}]
    mm.add_edge("kitchen", "hallway", crumbs)
    neighbors = mm.get_neighbors("kitchen")
    assert "hallway" in neighbors


def test_get_neighbors_empty():
    mm = MapManager()
    mm.add_node("kitchen", "Kitchen", [], "tile")
    assert mm.get_neighbors("kitchen") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/dev/robotcar && PYTHONPATH=. python -m pytest tests/test_map_manager.py -v`
Expected: FAIL — `AttributeError: 'MapManager' object has no attribute 'add_node'`

- [ ] **Step 3: Implement add_node, get_node, add_edge, get_neighbors**

Add to `MapManager` class in `server/map_manager.py`:

```python
    def add_node(self, id: str, label: str,
                 landmarks: List[str] = None,
                 floor_type: str = "unknown") -> MapNode:
        """Add or update a node. Increments visit_count if it exists."""
        if id in self.nodes:
            self.nodes[id].visit_count += 1
            self.nodes[id].last_visited = time.strftime("%Y-%m-%dT%H:%M:%S")
            if landmarks:
                # Merge new landmarks
                existing = set(self.nodes[id].landmarks)
                for lm in landmarks:
                    existing.add(lm)
                self.nodes[id].landmarks = list(existing)
            return self.nodes[id]

        node = MapNode(
            id=id, label=label,
            landmarks=landmarks or [],
            floor_type=floor_type,
            visit_count=1,
            last_visited=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        self.nodes[id] = node
        logger.info(f"New map node: {id} ({label})")
        return node

    def get_node(self, id: str) -> Optional[MapNode]:
        """Get a node by ID, or None if not found."""
        return self.nodes.get(id)

    def add_edge(self, from_id: str, to_id: str,
                 breadcrumb: List[dict]) -> MapEdge:
        """Record a transition between two nodes."""
        # Check if edge already exists, update breadcrumb
        for edge in self.edges:
            if edge.from_id == from_id and edge.to_id == to_id:
                edge.breadcrumb = breadcrumb  # Use latest recording
                edge.traversal_count += 1
                return edge

        edge = MapEdge(
            from_id=from_id, to_id=to_id,
            breadcrumb=breadcrumb, traversal_count=1,
        )
        self.edges.append(edge)
        logger.info(f"New map edge: {from_id} → {to_id} ({len(breadcrumb)} commands)")
        return edge

    def get_neighbors(self, node_id: str) -> List[str]:
        """Get IDs of nodes reachable from this node."""
        return [e.to_id for e in self.edges if e.from_id == node_id]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/dev/robotcar && PYTHONPATH=. python -m pytest tests/test_map_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/map_manager.py tests/test_map_manager.py
git commit -m "feat: add node/edge CRUD and neighbor lookup to MapManager"
```

---

### Task 3: Map Manager — Persistence (load/save)

**Files:**
- Modify: `server/map_manager.py`
- Modify: `tests/test_map_manager.py`

- [ ] **Step 1: Write failing tests for save and load**

```python
def test_save_and_load():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name

    try:
        mm = MapManager(map_file=path)
        mm.add_node("kitchen", "Kitchen", ["cabinets"], "tile")
        mm.add_node("hallway", "Hallway", ["mirror"], "tile")
        mm.add_edge("kitchen", "hallway",
                     [{"left_speed": 190, "right_speed": 190,
                       "left_dir": 1, "right_dir": 1, "duration_ms": 2000}])
        mm.save()

        # Load into fresh instance
        mm2 = MapManager(map_file=path)
        mm2.load()
        assert mm2.get_node("kitchen") is not None
        assert mm2.get_node("kitchen").label == "Kitchen"
        assert mm2.get_neighbors("kitchen") == ["hallway"]
    finally:
        os.unlink(path)


def test_load_missing_file():
    mm = MapManager(map_file="/tmp/nonexistent_robotcar_map.json")
    mm.load()  # Should not raise
    assert len(mm.nodes) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/dev/robotcar && PYTHONPATH=. python -m pytest tests/test_map_manager.py::test_save_and_load -v`
Expected: FAIL — save/load are no-ops

- [ ] **Step 3: Implement load and save**

Replace the stub `load()` and `save()` in `MapManager`:

```python
    def load(self) -> None:
        """Load map from JSON file. No-op if file doesn't exist."""
        try:
            with open(self.map_file, 'r') as f:
                data = json.load(f)
            self.nodes = {
                k: MapNode.from_dict(v)
                for k, v in data.get("nodes", {}).items()
            }
            self.edges = [
                MapEdge.from_dict(e)
                for e in data.get("edges", [])
            ]
            logger.info(f"Loaded map: {len(self.nodes)} nodes, {len(self.edges)} edges")
        except FileNotFoundError:
            logger.info(f"No map file found at {self.map_file}, starting fresh")
        except Exception as e:
            logger.error(f"Error loading map: {e}")

    def save(self) -> None:
        """Save map to JSON file."""
        data = {
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
        }
        try:
            with open(self.map_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved map: {len(self.nodes)} nodes, {len(self.edges)} edges")
        except Exception as e:
            logger.error(f"Error saving map: {e}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/dev/robotcar && PYTHONPATH=. python -m pytest tests/test_map_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/map_manager.py tests/test_map_manager.py
git commit -m "feat: add JSON persistence to MapManager"
```

---

### Task 4: Map Manager — BFS Pathfinding and Breadcrumb Reversal

**Files:**
- Modify: `server/map_manager.py`
- Modify: `tests/test_map_manager.py`

- [ ] **Step 1: Write failing tests for get_path and get_reverse_breadcrumb**

```python
def test_get_path_direct():
    mm = MapManager()
    mm.add_node("a", "A", [], "tile")
    mm.add_node("b", "B", [], "tile")
    crumbs = [{"left_speed": 190, "right_speed": 190,
               "left_dir": 1, "right_dir": 1, "duration_ms": 2000}]
    mm.add_edge("a", "b", crumbs)
    path = mm.get_path("a", "b")
    assert len(path) == 1
    assert path[0].from_id == "a"
    assert path[0].to_id == "b"


def test_get_path_multi_hop():
    mm = MapManager()
    for n in ["a", "b", "c"]:
        mm.add_node(n, n.upper(), [], "tile")
    mm.add_edge("a", "b", [{"left_speed": 190, "right_speed": 190,
                             "left_dir": 1, "right_dir": 1, "duration_ms": 1000}])
    mm.add_edge("b", "c", [{"left_speed": 190, "right_speed": 190,
                             "left_dir": 1, "right_dir": 1, "duration_ms": 1000}])
    path = mm.get_path("a", "c")
    assert len(path) == 2
    assert path[0].to_id == "b"
    assert path[1].to_id == "c"


def test_get_path_no_route():
    mm = MapManager()
    mm.add_node("a", "A", [], "tile")
    mm.add_node("b", "B", [], "tile")
    path = mm.get_path("a", "b")
    assert path is None


def test_reverse_breadcrumb():
    mm = MapManager()
    crumbs = [
        {"left_speed": 190, "right_speed": 190,
         "left_dir": 1, "right_dir": 1, "duration_ms": 2000},
        {"left_speed": 230, "right_speed": 230,
         "left_dir": 0, "right_dir": 1, "duration_ms": 1250},
    ]
    reversed_crumbs = mm.get_reverse_breadcrumb(crumbs)
    # Reversed order, directions flipped (1→0, 0→1, 2→2)
    assert len(reversed_crumbs) == 2
    # Second original command becomes first reversed
    assert reversed_crumbs[0]["left_dir"] == 1  # was 0
    assert reversed_crumbs[0]["right_dir"] == 0  # was 1
    # First original command becomes second reversed
    assert reversed_crumbs[1]["left_dir"] == 0  # was 1
    assert reversed_crumbs[1]["right_dir"] == 0  # was 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/dev/robotcar && PYTHONPATH=. python -m pytest tests/test_map_manager.py::test_get_path_direct -v`
Expected: FAIL — `AttributeError`

- [ ] **Step 3: Implement get_path and get_reverse_breadcrumb**

Add to `MapManager`:

```python
    def get_path(self, from_id: str, to_id: str) -> Optional[List[MapEdge]]:
        """BFS to find a route between two nodes. Returns list of edges or None."""
        if from_id not in self.nodes or to_id not in self.nodes:
            return None
        if from_id == to_id:
            return []

        visited = {from_id}
        queue = deque([(from_id, [])])

        while queue:
            current, path = queue.popleft()
            for edge in self.edges:
                if edge.from_id == current and edge.to_id not in visited:
                    new_path = path + [edge]
                    if edge.to_id == to_id:
                        return new_path
                    visited.add(edge.to_id)
                    queue.append((edge.to_id, new_path))

        return None  # No route found

    @staticmethod
    def get_reverse_breadcrumb(breadcrumb: List[dict]) -> List[dict]:
        """Reverse a breadcrumb trail for backtracking.

        Reverses order and flips forward/backward directions.
        Direction mapping: 0 (BACKWARD) ↔ 1 (FORWARD), 2 (STOP) stays 2.
        """
        def flip_dir(d: int) -> int:
            if d == 0:
                return 1
            if d == 1:
                return 0
            return 2  # STOP stays STOP

        reversed_crumbs = []
        for cmd in reversed(breadcrumb):
            reversed_crumbs.append({
                "left_speed": cmd["left_speed"],
                "right_speed": cmd["right_speed"],
                "left_dir": flip_dir(cmd["left_dir"]),
                "right_dir": flip_dir(cmd["right_dir"]),
                "duration_ms": cmd["duration_ms"],
            })
        return reversed_crumbs

    def get_known_locations(self) -> List[str]:
        """Get list of all known node IDs."""
        return list(self.nodes.keys())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/dev/robotcar && PYTHONPATH=. python -m pytest tests/test_map_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/map_manager.py tests/test_map_manager.py
git commit -m "feat: add BFS pathfinding and breadcrumb reversal to MapManager"
```

---

### Task 5: Config — Add Map Settings

**Files:**
- Modify: `server/config.py`

- [ ] **Step 1: Add map settings to ServerConfig**

Add after the `debug_frame_dir` line in `server/config.py`:

```python
    # Mapping settings
    map_file: str = "./map_data.json"
    enable_mapping: bool = True
```

- [ ] **Step 2: Verify server still starts**

Run: `cd ~/dev/robotcar && PYTHONPATH=. python -c "from server.config import config; print(f'map_file={config.map_file}, enable_mapping={config.enable_mapping}')"`
Expected: `map_file=./map_data.json, enable_mapping=True`

- [ ] **Step 3: Commit**

```bash
git add server/config.py
git commit -m "feat: add map_file and enable_mapping to server config"
```

---

### Task 6: Command Generator — LOCATION Parsing

**Files:**
- Modify: `server/command_generator.py`
- Create: `tests/test_command_generator.py`

- [ ] **Step 1: Write failing tests for LOCATION parsing**

```python
# tests/test_command_generator.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from server.command_generator import CommandGenerator


def test_parse_location_from_response():
    cg = CommandGenerator()
    response = """OBSERVATION: White cabinets, island, tile floor
ASSESSMENT: Clear path
LOCATION: kitchen
COMMAND: 190,190,1,1,2000
REASONING: Moving forward"""
    parsed = cg.parse_response(response)
    assert parsed.location == "kitchen"
    assert parsed.command is not None


def test_parse_location_unknown():
    cg = CommandGenerator()
    response = """OBSERVATION: Unfamiliar room
ASSESSMENT: New area
LOCATION: unknown
COMMAND: 0,0,2,2,0
REASONING: Stopping to identify"""
    parsed = cg.parse_response(response)
    assert parsed.location == "unknown"


def test_parse_no_location():
    cg = CommandGenerator()
    response = """OBSERVATION: Floor ahead
ASSESSMENT: Clear
COMMAND: 190,190,1,1,2000
REASONING: Forward"""
    parsed = cg.parse_response(response)
    assert parsed.location == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/dev/robotcar && PYTHONPATH=. python -m pytest tests/test_command_generator.py -v`
Expected: FAIL — `ParsedResponse` has no `location` field

- [ ] **Step 3: Add location field to ParsedResponse and parsing logic**

In `server/command_generator.py`:

Add `location: str = ""` to the `ParsedResponse` dataclass.

Add location extraction to `parse_response()`, after the assessment extraction:

```python
        # Extract location
        location = ""
        loc_match = re.search(r'LOCATION:\s*(\S+)', response, re.IGNORECASE)
        if loc_match:
            location = loc_match.group(1).strip().lower()
```

Include `location=location` in the returned `ParsedResponse`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/dev/robotcar && PYTHONPATH=. python -m pytest tests/test_command_generator.py tests/test_map_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/command_generator.py tests/test_command_generator.py
git commit -m "feat: parse LOCATION field from AI responses"
```

---

### Task 7: Command Generator — Map-Aware Prompt Building

**Files:**
- Modify: `server/command_generator.py`
- Modify: `tests/test_command_generator.py`

- [ ] **Step 1: Write failing tests for map-aware prompt**

```python
def test_prompt_includes_known_locations():
    cg = CommandGenerator()
    known = ["office", "hallway", "kitchen"]
    prompt = cg.build_prompt("Explore", known_locations=known)
    assert "LOCATION:" in prompt
    assert "office" in prompt
    assert "hallway" in prompt
    assert "kitchen" in prompt
    assert "unknown" in prompt.lower()


def test_prompt_without_locations():
    cg = CommandGenerator()
    prompt = cg.build_prompt("Explore")
    # Should not include LOCATION section when no locations known
    assert "KNOWN LOCATIONS:" not in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/dev/robotcar && PYTHONPATH=. python -m pytest tests/test_command_generator.py::test_prompt_includes_known_locations -v`
Expected: FAIL — `build_prompt()` doesn't accept `known_locations`

- [ ] **Step 3: Add known_locations parameter to build_prompt**

In `server/command_generator.py`, modify `build_prompt()` signature:

```python
    def build_prompt(self, goal: str, include_examples: bool = True,
                     sensor_data: SensorData = None,
                     known_locations: List[str] = None) -> str:
```

Add `LOCATION:` to the OUTPUT FORMAT section (between ASSESSMENT and COMMAND):

```python
LOCATION: <which room/area are you in from the KNOWN LOCATIONS list, or "unknown" if new>
```

After the sensor section, add:

```python
        # Add map locations if available
        if known_locations:
            locs = ", ".join(known_locations)
            prompt += f"\nKNOWN LOCATIONS: {locs}"
            prompt += "\nIdentify your current location from this list, or say 'unknown' if this is a new area."
```

- [ ] **Step 4: Run all tests**

Run: `cd ~/dev/robotcar && PYTHONPATH=. python -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/command_generator.py tests/test_command_generator.py
git commit -m "feat: inject map locations into AI prompt with LOCATION output"
```

---

### Task 8: Server Control — Map Integration into Control Loop

**Files:**
- Modify: `server/server_control.py`
- Modify: `server/config.py` (already done in Task 5)

- [ ] **Step 1: Import and initialize MapManager in ServerController**

In `server/server_control.py`, add import:

```python
from server.map_manager import MapManager
```

In `__init__`, add:

```python
        self.map_manager = None
        if not manual_mode:
            from server.config import config as srv_config
            if srv_config.enable_mapping:
                self.map_manager = MapManager(srv_config.map_file)
```

In `start()`, after model loading:

```python
        if self.map_manager:
            self.map_manager.load()
            logger.info(f"Map loaded: {len(self.map_manager.nodes)} nodes, "
                        f"{len(self.map_manager.edges)} edges")
```

In `stop()`, before network stop:

```python
        if self.map_manager:
            self.map_manager.save()
            logger.info("Map saved")
```

- [ ] **Step 2: Add location tracking to run_ai_control**

Add tracking variables at the start of `run_ai_control()`:

```python
        current_location = ""
        pending_breadcrumb = []
        discovering_room = False
```

After `parsed = self.command_generator.parse_response(response)`, add map logic:

```python
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
                                self.map_manager.add_node(
                                    parsed.location, parsed.location.replace("_", " ").title(),
                                    floor_type=parsed.observation[:50] if parsed.observation else "unknown")
                                current_location = parsed.location
                                pending_breadcrumb = []
                                logger.info(f"Location: {current_location}")
```

After `conn.send_command(parsed.command)`, record the breadcrumb:

```python
                    if self.map_manager and parsed.command:
                        pending_breadcrumb.append({
                            "left_speed": parsed.command.left_speed,
                            "right_speed": parsed.command.right_speed,
                            "left_dir": parsed.command.left_dir.value,
                            "right_dir": parsed.command.right_dir.value,
                            "duration_ms": parsed.command.duration_ms,
                        })
```

Modify the `build_prompt` call to pass known locations:

```python
                known_locs = self.map_manager.get_known_locations() if self.map_manager else None
                prompt = self.command_generator.build_prompt(
                    goal, sensor_data=sensor_data,
                    known_locations=known_locs
                )
```

- [ ] **Step 3: Test manually**

Run: `cd ~/dev/robotcar && PYTHONPATH=. python server/server_control.py --goal "Explore" &`
Check log for "Map loaded" message, then Ctrl+C.
Verify `map_data.json` is created (even if empty).

- [ ] **Step 4: Commit**

```bash
git add server/server_control.py
git commit -m "feat: integrate topological map into server control loop"
```

---

### Task 9: Server Control — GoTo and Home Modes

**Files:**
- Modify: `server/server_control.py`

- [ ] **Step 1: Add --goto and --home CLI arguments**

In `main()`, add to the argument parser:

```python
    parser.add_argument(
        '--goto',
        type=str,
        default=None,
        help='Navigate to a named location on the map'
    )

    parser.add_argument(
        '--home',
        action='store_true',
        help='Navigate back to starting location'
    )
```

- [ ] **Step 2: Add run_goto method to ServerController**

```python
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
```

- [ ] **Step 3: Wire up in main()**

In `main()`, after the manual mode check and before `controller.run_ai_control()`:

```python
        if args.goto:
            controller.run_goto(args.goto)
        elif args.home:
            controller.run_goto("office")
        elif args.manual:
            controller.run_manual_control()
        else:
            controller.run_ai_control(args.goal)
```

- [ ] **Step 4: Commit**

```bash
git add server/server_control.py
git commit -m "feat: add --goto and --home navigation modes"
```

---

### Task 10: Final Integration Test and Cleanup

**Files:**
- All test files

- [ ] **Step 1: Run full test suite**

Run: `cd ~/dev/robotcar && PYTHONPATH=. python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Verify server starts with mapping enabled**

Run: `cd ~/dev/robotcar && PYTHONPATH=. timeout 5 python server/server_control.py --goal "Explore" 2>&1 | head -20`
Expected: "Map loaded" in output, no errors

- [ ] **Step 3: Rsync to Pi**

```bash
rsync -av --exclude='__pycache__' --exclude='.git' ~/dev/robotcar/ thinktank:~/robotcar/
```

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: topological map complete — persistent room graph with goto navigation"
```
