# Topological Map for Robot Car Navigation

**Date:** 2026-03-21
**Status:** Approved
**Project:** robotcar

## Overview

Add a persistent topological map that lets the robot car learn the layout of the house over multiple driving sessions. The map is a graph of named rooms/areas connected by recorded command sequences, enabling "go to" navigation and smarter exploration.

## Approach

Pure topological graph — no metric distances or occupancy grids. The vision model identifies rooms by landmarks, and motor command sequences are recorded as breadcrumb trails between rooms. This plays to the system's strengths (good vision model) and avoids its weaknesses (no wheel encoders or IMU for odometry).

## Data Model

The map persists as a JSON file at `server/map_data.json`.

### Nodes (Rooms/Areas)

```json
{
  "id": "kitchen",
  "label": "Kitchen",
  "landmarks": ["white cabinets", "island", "bar stools"],
  "floor_type": "tile",
  "visit_count": 12,
  "last_visited": "2026-03-21T15:00:00"
}
```

### Edges (Transitions)

```json
{
  "from": "kitchen",
  "to": "living_room",
  "breadcrumb": [
    {"left_speed": 230, "right_speed": 230, "left_dir": 0, "right_dir": 1, "duration_ms": 1250},
    {"left_speed": 190, "right_speed": 190, "left_dir": 1, "right_dir": 1, "duration_ms": 2000}
  ],
  "traversal_count": 5
}
```

The breadcrumb is the recorded sequence of motor commands that successfully moved between two nodes. Reverse paths are computed by flipping directions and reversing command order.

## New Module: `server/map_manager.py`

A pure data layer that stores and queries the graph. No vision model or motor interaction.

### API

- `load()` / `save()` — read/write `map_data.json`
- `add_node(id, label, landmarks, floor_type)` — register a new room
- `add_edge(from_id, to_id, breadcrumb)` — record a transition
- `get_node(id)` — look up a room
- `get_neighbors(id)` — rooms connected to this one
- `get_path(from_id, to_id)` — BFS to find a route (returns list of edges)
- `get_reverse_breadcrumb(edge)` — flip a breadcrumb trail for backtracking

## Localization: "Where Am I?"

Each inference cycle, the AI identifies its current location on the map.

### Active Localization

The AI prompt includes a condensed list of known rooms. The AI adds a `LOCATION:` line to its structured output:

```
OBSERVATION: White cabinets, island with bar stools, tile floor...
ASSESSMENT: Path clear...
LOCATION: kitchen
COMMAND: 190,190,1,1,2000
REASONING: ...
```

The prompt addition is small:

```
KNOWN LOCATIONS: office, short_hallway, long_hallway, living_room, kitchen, bedroom
Pick the best match or say "unknown" if this is a new area.
```

### Transition Detection

When `LOCATION:` changes between frames (e.g., "kitchen" → "hallway"), the map manager records the breadcrumb of commands issued since the last location change as a new edge.

### New Room Discovery

If the AI reports "unknown," the server asks a follow-up on the next frame: "Describe this room in 3-5 words and list its key landmarks." This creates a new node.

## Integration Points

### Modified Files

**`server/server_control.py`** — main loop changes:
- Load map on startup
- Track `current_location` and `pending_breadcrumb` (commands since last location change)
- On location change: save breadcrumb as edge, start new breadcrumb
- On "unknown": trigger room-naming query
- Save map on shutdown

**`server/command_generator.py`** — prompt changes:
- Add `LOCATION:` to output format
- Inject known locations list into prompt
- Add room-naming follow-up prompt for new areas

**`server/config.py`** — new settings:
- `map_file: str = "./map_data.json"`
- `enable_mapping: bool = True`

### New Files

- `server/map_manager.py` — map data layer

### Unchanged

Pi side is completely unchanged. Mapping is entirely server-side logic.

## Using the Map: New Modes

### "Go To" Mode (`--goto <location>`)

1. Map manager runs BFS from current location to target
2. Returns list of edges with breadcrumb commands
3. Server executes each breadcrumb sequence in order
4. Between edges, AI verifies arrival at expected intermediate node
5. If lost (location mismatch), falls back to explore mode

### "Home" Mode (`--home`)

Shortcut for `--goto office` (or wherever the session started).

### Enhanced Explore Mode

When exploring with a map, the AI prompt includes visited/unvisited information:

```
You have visited: kitchen, living_room.
Unexplored exits from living_room: 2 directions not yet mapped.
```

This biases exploration toward unmapped areas rather than wandering randomly.

## Design Decisions

- **Server-side only**: No Pi changes needed. The Pi is a hardware proxy; navigation intelligence lives on the server.
- **Persistent to disk**: The house layout is static. The map builds up across sessions and survives reboots.
- **AI-driven localization**: Rather than visual fingerprinting or image embeddings, the vision model identifies rooms by their landmarks. Simpler and uses existing infrastructure.
- **Breadcrumb recording**: Motor commands are recorded as-is. Reverse paths are computed by flipping forward/backward directions and reversing command order.
- **Graceful degradation**: If mapping is disabled or the map is empty, the system operates exactly as before.
