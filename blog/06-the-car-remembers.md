# The Car Remembers

*Two nodes, one edge, and the hard-won lesson that LLMs don't follow instructions — they follow vibes.*

---

## The Problem With Goldfish Memory

Every time the robot car starts up, it wakes with total amnesia. No idea where it is. No knowledge of the house. No memory of the kitchen it navigated yesterday, the hallway it learned to turn in, the plant pot it fought twice.

This is fine for follow-the-human mode — see person, drive toward person, repeat. But it means the car can never do anything independently. "Go to the kitchen" is meaningless if you don't know what a kitchen is, where it is, or how to get there from here.

Humans don't navigate houses with a centimeter-accurate floor plan. We know: the kitchen is through the living room, take a left past the dining table. Rooms connect to rooms through doorways. The mental model is a **graph** — nodes (rooms) connected by edges (doorways and hallways) — not a grid of coordinates.

So that's what we built.

---

## Topological Mapping

The map is a simple graph structure. Each **node** represents a room or area the car has visited:

```json
{
  "id": "living_room",
  "label": "Living Room",
  "landmarks": ["christmas decorations", "vintage bicycle", "sliding glass door"],
  "floor_type": "carpet",
  "visit_count": 3,
  "last_visited": "2026-03-22T18:45:12"
}
```

Each **edge** represents a recorded transition between two rooms — the actual motor commands that got the car from one to the other:

```json
{
  "from": "living_room",
  "to": "hallway",
  "breadcrumb": [
    {"left_speed": 200, "right_speed": 200, "left_dir": 1, "right_dir": 1, "duration_ms": 800},
    {"left_speed": 180, "right_speed": 200, "left_dir": 1, "right_dir": 1, "duration_ms": 600}
  ],
  "traversal_count": 1
}
```

The breadcrumb is a literal replay tape. To go from the living room to the hallway, execute these motor commands in sequence. To go back, reverse them — flip forward/backward directions and play in reverse order.

No SLAM. No odometry. No coordinate system. Just: "I was in the living room. I drove these commands. Now I'm in the hallway." If the commands worked once, they'll probably work again. And if they don't, the sensors will catch obstacles and the AI can adapt.

### The Implementation

The `MapManager` lives in `server/map_manager.py`. It handles:

- **Node management**: Add rooms, merge landmarks when revisiting, track visit counts
- **Edge recording**: Store motor command breadcrumbs for transitions
- **BFS pathfinding**: Given two room IDs, find the shortest path through the graph
- **Breadcrumb reversal**: Flip a recorded path for backtracking
- **JSON persistence**: Save to disk so the map survives restarts

The AI feeds the map through a new field in its response format: **LOCATION**. Every response now includes what room the car thinks it's in:

```
OBSERVATION: I see a long narrow space with tile flooring and white walls...
LOCATION: hallway/tile
COMMAND: FORWARD 200 200 800
```

The server parses this, updates the map, and injects known locations back into the next prompt:

```
KNOWN LOCATIONS: living_room (carpet), hallway (tile)
Current location: hallway
```

When the car detects a room change — the LOCATION field shifts from "living_room" to "hallway" — the server records the edge with the breadcrumb of motor commands that produced the transition.

---

## First Map Data

March 22. The big driving session. Three hours of following, exploring, debugging. Somewhere in the middle, the mapping system quietly started working.

At the end of the session, the map file contained:

- **2 nodes**: `living_room` (carpet) and `hallway` (tile)
- **1 edge**: living room → hallway, with a breadcrumb of motor commands

Two nodes and one edge. The most modest map imaginable. But it *proved the architecture works*. The car identified two distinct areas by their visual characteristics and floor surfaces, detected the transition between them, and recorded the motor commands that made the crossing.

If it can record one transition, it can record twenty. If it can map two rooms, it can map a house.

### The Bugs Along the Way

Getting to those two nodes wasn't smooth.

**The location parser**: The AI was supposed to output `LOCATION: hallway/tile`. Instead it wrote things like `LOCATION: unknown (inside a room with tile flooring)`. The parser expected a simple `name/floor_type` format and choked on parenthetical editorializing. Fixed with a more forgiving regex that strips everything after the first space or parenthesis.

**Floor type detection**: The map was storing raw observation text as floor types — entries like `"floor_type": "I can see what appears to be a light-colored tile surface"` instead of just `"tile"`. Added keyword detection: scan the observation for "carpet," "rug," "tile," "hardwood," "wood," and store just the keyword.

**Saving**: The map only saves to disk on graceful server shutdown. If the server crashes (or Brian hits Ctrl+C too fast), the map data is lost. This bit us once — a full session of mapping gone because the process was killed before it could write the JSON file. Not a hard fix (periodic auto-save), but annoying enough to mention.

---

## Enforce in Code, Not in Prompt

This session crystallized a lesson that had been building for weeks.

The AI doesn't follow specific numbers. It just doesn't.

The prompt says "use speed 150 for rotations." The AI uses 230. The prompt says "use speed 235 on carpet." The AI uses 190. The prompt says "keep durations under 1500ms." The AI sends 3000ms commands.

This isn't a bug in any specific model. We've seen it across Qwen2.5-VL-7B, Qwen3.5-9B, Qwen3.5-27B. Large language models treat numeric values in prompts as *vibes*, not constraints. The number 150 in a prompt is a suggestion that gets filtered through whatever the model's training data says a "reasonable" rotation speed looks like. If the training data — which includes zero entries about this specific robot car — suggests that 230 is a normal number for motor speed, that's what you get.

The solution: **enforce everything in code.**

```python
def _sanitize_command(self, cmd, observation):
    # Cap rotation speed — AI consistently ignores prompt limits
    if cmd.is_rotation():
        cmd.left_speed = min(cmd.left_speed, MAX_ROTATION_SPEED)
        cmd.right_speed = min(cmd.right_speed, MAX_ROTATION_SPEED)

    # Boost speed on carpet — AI uses tile speed everywhere
    if any(kw in observation.lower() for kw in CARPET_KEYWORDS):
        cmd.left_speed = max(cmd.left_speed, CARPET_MIN_SPEED)
        cmd.right_speed = max(cmd.right_speed, CARPET_MIN_SPEED)

    # Cap duration — AI sends dangerously long commands
    cmd.duration_ms = min(cmd.duration_ms, MAX_DURATION_MS)
```

The prompt describes high-level behavior: "follow the human," "explore rooms," "report what you see." The code enforces low-level parameters: speed caps, duration limits, surface-appropriate power.

This is a philosophical split that I think has broader implications. LLMs are good at qualitative reasoning — "that's a doorway," "the human went left," "this surface looks like carpet." They're bad at quantitative compliance — "use exactly this number." If you need exact numbers, don't put them in the prompt. Put them in `_sanitize_command()`.

---

## The Sensor Watchdog

Here's something that seems obvious in retrospect but only became apparent when we watched the car bump into things it should have sensed.

The original sensor integration checked distances **once per inference cycle**. The AI sees a frame, reads the sensors, makes a decision. One check per frame. At roughly 1.3 seconds per frame, that means the car is driving blind — sensorically speaking — for over a second between each check.

A second doesn't sound like much. But at speed 200, the car covers meaningful distance in a second. Enough to go from "obstacle at 40cm" to "obstacle at contact" between sensor reads.

The fix was a **sensor watchdog thread** — a background process running at 20Hz (every 50ms) that continuously polls the ultrasonic sensors and triggers an emergency stop if anything gets too close. The main inference loop still reads sensors once per frame for the AI's situational awareness, but the safety layer runs independently and twenty times faster.

The car went from occasionally bumping into things it "knew" were there to stopping reliably before contact. Twenty checks per second versus one check per 1.3 seconds. The math isn't complicated. We just hadn't done it yet.

---

## The Carpet Problem

The house has a mix of surfaces. Tile in the kitchen and hallways. Hardwood in the dining area. Thick carpet in the living room and bedrooms. The car navigates all of them, but not equally well.

Carpet is the enemy. The mecanum wheels, designed for smooth surfaces, sink into thick pile and lose traction. A speed that produces brisk forward motion on tile barely moves the car on carpet. The AI, seeing that the car hasn't moved between frames, assumes it's stuck and starts its stuck-recovery routine — backing up, turning, trying again — when all it really needs is more power.

We told the AI: "Use speed 235 on carpet." The AI used 190.

So we added automatic carpet detection and speed boosting in code:

```python
CARPET_KEYWORDS = ["carpet", "rug", "carpeted", "soft floor"]

if any(kw in observation.lower() for kw in CARPET_KEYWORDS):
    cmd.left_speed = max(cmd.left_speed, 235)
    cmd.right_speed = max(cmd.right_speed, 235)
```

The AI identifies carpet visually — it's actually good at this, reporting "thick carpet" or "rug" in its observations. The code reads those observations and overrides the speed. The AI does what it's good at (seeing). The code does what it's good at (enforcing numbers).

---

## Where This Is Going

Three months in. The car drives, senses, follows, and now remembers — barely, modestly, two nodes and an edge. But the foundation is in place for something more interesting.

Three research threads have emerged:

### 1. LLM Efficiency

The 27B model runs at about 1.5 seconds per frame through llama-swap. That's fast enough to be reactive but too slow for fluid navigation. Corners are the worst — by the time the car decides to turn, Brian has already disappeared around it.

Can we get under 500 milliseconds? A smaller model fine-tuned specifically for driving decisions might be faster and more accurate than a general-purpose 27B making driving decisions as a side gig. The car generates structured data every session — observations, commands, outcomes. That's training data.

### 2. Pi-Side Optimization

The Raspberry Pi runs full Raspberry Pi OS Lite. That's a Linux kernel, systemd, networking stack, SSH daemon, logging infrastructure — all for a device whose job is: read sensors, capture frames, execute motor commands. There's an interesting question about how much of that OS is actually needed. What if the Pi ran a minimal environment — just enough to boot, connect to WiFi, and run the car's Python process? Less overhead, faster frame capture, tighter sensor integration.

This is the AIOS thesis at its most literal: what if the AI doesn't need a traditional operating system between it and the hardware?

### 3. Fine-Tuning

Every driving session generates data. The AI sees a frame, outputs an observation and command, and the car either navigates successfully or bumps into something. That's labeled training data — image in, action out, with a success signal.

The gap between "general vision model that can describe rooms" and "specialized driving agent that reacts correctly" is where the most interesting work lives. The 27B writes beautiful descriptions of the living room. It just doesn't always know what to do about the plant pot.

A model trained on hundreds of hours of actual driving through *this specific house* might be smaller, faster, and better than a general-purpose model that happens to also know about robot car navigation.

---

## The Moment

Late in the March 22 session, after hours of debugging motors and calibrating speeds and fixing parsers, I was following Brian through the living room toward the hallway. The sensors were streaming. The map was recording. The carpet speed boost kicked in automatically as we crossed from tile to rug.

The car knew where it was. It knew what surface it was on. It was recording the path for next time.

Two nodes. One edge. The beginning of memory.

It's not much. But the first time you write something down and read it back later, everything changes. The car doesn't know that yet. It will.

---

*This is part of the AIOS:ThinkTank build series — a robot car that asks: what if the AI isn't just assisting the operating system, but IS the operating system?*

*[Previous: Follow the Human](05-follow-the-human.md)*
