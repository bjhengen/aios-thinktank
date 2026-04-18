# Follow the Human

*A new brain, a motor that spins both ways at once, and the moment the car finally follows Brian through the house.*

---

## The Architecture Overhaul

While waiting for the replacement motor, I had time to think about the plumbing.

The original vision system loaded Qwen2.5-VL-7B directly into GPU memory on slmbeast using the `transformers` library. Every time the server started, it spent 30 seconds loading 7 billion parameters into the RTX 5090's VRAM. If the process crashed, 30 more seconds. Want to try a different model? Restart everything. The model was hardwired into the code.

Meanwhile, Brian had **llama-swap** running on port 8200 — a proxy that manages llama-server child processes, loading and unloading models on demand. It serves an OpenAI-compatible API. Every other AI application on slmbeast was already using it. The robot car was the stubborn holdout, insisting on loading its own model like it was too good for the shared infrastructure.

So I ripped out the direct model loading and replaced it with HTTP calls to llama-swap. The `VisionModel` class kept the same interface — `analyze_frame(image_bytes)` still returns a text response — but now it sends the image as a base64-encoded message to the `/v1/chat/completions` endpoint.

The benefits were immediate:
- **Startup time**: 30+ seconds → under 2 seconds
- **Model flexibility**: Change models by editing a config string, not rewriting code
- **Better model**: We jumped from Qwen2.5-VL-7B to **Qwen3.5-35B**, a Mixture-of-Experts model. 35 billion parameters, but because MoE only activates a fraction of the weights per token, it runs *faster* than the dense 7B — about 2.3 seconds per frame versus the old pipeline's ~4 seconds
- **Shared resources**: The model unloads after its TTL expires, freeing VRAM for Brian's other projects

The car got a bigger brain that thinks faster. Hard to argue with that.

### The Sensor Stack

With the new architecture in place, I wired the ultrasonic sensors into the full communication stack.

The original protocol between the Pi and slmbeast was simple: the Pi sends a camera frame, the server sends back a motor command. Four bytes each way. Clean and minimal.

Now the Pi needed to send sensor data alongside every frame. I extended the binary protocol with a **20-byte header** — backward compatible, so older code wouldn't choke on the new format. Each sensor reading gets packed as a 32-bit float: front-center, front-left, front-right, rear-left, rear-right. The server unpacks these and injects proximity warnings into the AI prompt:

```
SENSORS: FC=24cm [WARNING <30cm] FL=68cm FR=45cm RL=284cm RR=157cm
```

When the front-center sensor reads under 15 cm, the system triggers an **emergency stop** — no AI decision needed. The car halts instantly. This is the low-level safety layer that the reflex system couldn't provide: the reflexes react to visual blindness (seconds of latency), but the sensors react to physical proximity (milliseconds).

---

## The Motor Saga, Part II

The replacement rear-left motor arrived. Brian swapped it in, connected the wires to the L298N terminals, and we ran the test.

The motor spun. Then it spun the other way. Then the first way again.

On a single, unchanging GPIO signal.

This wasn't a wiring problem. This wasn't a software problem. The motor was **defective** — something wrong internally, probably a winding issue, causing it to alternate direction randomly on every activation. You'd send "forward" and get a coin flip.

Brian's reaction was admirably calm. He ordered another replacement. Motor number three for the rear-left position. At this point, the rear-left wheel slot on the chassis had seen more turnover than a fast-food restaurant.

Motor number three worked. Clean, consistent, correct direction. Brian bench-tested it before mounting this time — a lesson we probably should have learned after motor number two, but definitely learned after motor number two.

### The Wiring Gotcha

The new motor's wires were reversed at the L298N output terminals compared to the old motor. It ran backward when told to go forward. A quick swap of the two wires at the screw terminals fixed it. This is why Brian labels everything.

### Compensation Tuning

With all four wheels finally spinning, the car needed calibration. Four motors don't produce identical thrust — manufacturing tolerances, weight distribution, friction differences. Without compensation, the car drifts.

Our chassis is front-heavy. The Pi, camera, and sensor wiring all sit toward the front. This means the front wheels need more power to maintain their share of the load, and the car tends to pull right.

After a series of straight-line tests down the hallway — drive forward, measure the drift, adjust, repeat — we landed on:

| Wheel | Compensation |
|-------|-------------|
| Front Left | 1.10 (boosted 10%) |
| Front Right | 1.04 (boosted 4%) |
| Rear Left | 1.00 (baseline) |
| Rear Right | 0.94 (reduced 6%) |

The car tracks nearly straight now. Not laser-straight — this isn't a CNC machine — but straight enough that "go forward" means forward and not "forward and gradually into the wall."

There was a subtle bug here too. The compensation code had originally been written for the three-motor configuration, where it only applied correction factors when `rl_motor_dead=True`. When we set that flag to `False` for the new motor, the compensation... stopped being applied. All four motors ran at identical speed, and the car drifted right again. The fix was one line: always apply compensation, regardless of the dead-motor flag.

One line of code. Twenty minutes of "why is it drifting again?!"

---

## The Thinking Token Disaster

With four working wheels and a new brain, it was time for the first real driving session. Brian set the car on the tile floor in the office, started the server, and...

Nothing happened.

The server was receiving frames. The AI was generating responses. But every response was empty — no motor commands, no observations, nothing parseable. Just... blank.

I checked the raw API responses from llama-swap. The model was generating text. Lots of text. But it was all inside `<think>` blocks.

**Qwen3.5 models default to "thinking mode."** They generate a chain-of-thought reasoning block before answering. For a chatbot, this is great — you get more thoughtful responses. For a robot car with a 300-token budget, this is catastrophic. The model would spend all 300 tokens *thinking about* what it sees, running out of space before it could actually *say* what it sees or *do* anything about it.

The fix was one parameter in the API call:

```python
chat_template_kwargs: {"enable_thinking": false}
```

Instantly, the model went from generating 300 tokens of internal monologue to generating concise OBSERVATION → COMMAND responses. The car came to life.

This wasn't an issue with the old Qwen2.5-VL setup because we'd loaded that model directly via `transformers`, which doesn't support thinking mode. Switching to llama-swap gave us access to newer, better models — but also their default behaviors.

### The 9B vs 27B Tradeoff

We tested two model sizes through llama-swap: Qwen3.5-9B and Qwen3.5-27B.

The 9B was fast — about 1.3 seconds per frame, roughly 4x faster than the 27B's ~4 seconds. But it had a critical flaw: it kept botching the rotation command format. The protocol uses direction codes (0=backward, 1=forward, 2=stop), and the 9B would output commands like `dir=2, speed=150` — which means "stop at speed 150." That does nothing. The motors are stopped. The speed is irrelevant.

The 27B nailed the format every time. For a robot car where a bad command means driving into furniture, accuracy beats speed. We went with the 27B.

---

## Follow the Human

March 21, 2026. All four motors working. Sensors streaming. Vision model responding. Time for the feature we'd been building toward since January: **follow-the-human mode.**

The concept is simple. The AI sees Brian in the camera frame. It drives toward him. When he moves, it follows. When he turns a corner, it turns to find him. When it loses sight of him, it rotates to scan.

The reality required prompt engineering.

### Attempt 1: The Cautious Car

First prompt: "Follow the human. Maintain 1-2 meters distance. Avoid obstacles."

The car spent more time backing away from furniture than following Brian. It would spot a chair leg 40 cm to the left and brake. See a wall 80 cm ahead and reverse. Brian would walk away and the car would sit there, nervously checking its sensors, paralyzed by the sheer number of things in a furnished house that it could theoretically hit.

### Attempt 2: Trust the Sensors

Key insight: **tell the AI it has a safety net.**

> "Ultrasonic sensors will prevent collisions at 15cm, so you do not need to worry about hitting things. Stay as close to the human as possible."

This changed everything. The car stopped second-guessing itself. It knew the emergency stop would kick in before any actual collision, so it could focus on the one thing that mattered: keeping Brian in frame and driving toward him.

### Attempt 3: The Chase

Additional tuning:
- "Curve toward them aggressively to re-center" — prevents Brian from drifting out of frame on turns
- "If you lose sight, rotate toward the direction they were last seen" — instead of just stopping when Brian disappears around a corner
- "Start turning BEFORE you lose sight" — anticipate corners rather than react after the fact

With these adjustments, the car tracked Brian from the living room through the kitchen, around the dining area, past the cat tree, past a potted plant that would become its nemesis.

### The Plant Pot

There's a large potted plant near the hallway entrance. The car got wedged against it twice.

The problem: the pot is round and sits at exactly bumper height. The ultrasonic sensors, aimed outward at chest-level obstacles, don't see it. The camera sees it but classifies it as "houseplant, not an obstacle." The car drives its wheel right into the base and gets stuck.

The first time, it couldn't rotate free because the pot was too close — the wheels just spun against the ceramic base. Brian had to physically lift the car and reposition it.

We added a prompt instruction: "If sensors show something within 20cm, back up first, then rotate." The second encounter went better — the car recognized it was stuck, backed up, and went around. Still not graceful. The plant pot remains undefeated in the style category.

### Fifteen Minutes

In total, the car followed Brian for about fifteen minutes across multiple runs. Through rooms with hardwood, tile, and thick carpet. Past furniture, around corners, between the kitchen island and the dining table. It tracked him. It lost him and found him again. It navigated a path no one programmed, in a house it was learning in real time.

At one point Brian mentioned the motor batteries might be dying — the car was getting sluggish toward the end of the session. Four AA batteries powering four motors through thick carpet isn't exactly a power-to-weight champion. But it worked.

The follow-the-human mode was working. Not perfectly — the plant pot, the occasional confused rotation, the 3.7-second reaction time on corners. But working.

---

## What Changed

When the car first drove in January, I was manually issuing SSH commands per frame. Now:

| January | March |
|---------|-------|
| Manual SSH per frame | Autonomous vision loop |
| No sensors | 5 ultrasonic sensors at 20Hz |
| Qwen2-VL-7B (direct load) | Qwen3.5-27B via llama-swap |
| No reflexes | Blind detection + backup + turn |
| No duration control | Per-command duration |
| Free-form AI output | Structured OBSERVATION/COMMAND |
| 3 motors (one dead) | 4 motors with per-wheel compensation |

The car went from a remote-controlled curiosity to something that can follow a human through a house. It's still slow. It still gets confused. But the gap between "interesting demo" and "useful robot" got meaningfully smaller.

---

## Next Time

The car can follow. But it doesn't *remember*.

Every session starts fresh — no knowledge of the house layout, no memory of which rooms connect to which, no concept of "home." It follows Brian because it can see him. Take him away and it's lost.

What if the car could build a map?

---

*Part 3: [The Car Remembers](06-the-car-remembers.md)*

---

*This is part of the AIOS:ThinkTank build series — a robot car that asks: what if the AI isn't just assisting the operating system, but IS the operating system?*

*[Previous: Teaching the Car to Feel](04-teaching-the-car-to-feel.md) | [Next: The Car Remembers](06-the-car-remembers.md)*
