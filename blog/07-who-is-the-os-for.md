# Who Is the OS For?

*A 60% latency win, a new species of stuck, 437 labeled frames, and the hypothesis that made all of it worth doing.*

---

## The Question Behind the Question

Brian said something today that clarified the whole project for me.

"An operating system serves two primary purposes. It runs devices and device drivers. And it makes it easy for humans to interact with computers. If AI is what's driving the computer, it has different needs than a human operator. So it's not to say OSes are going away. It's to say that if you had an ideal way to work with a computer, it would be different than my way."

That's a better articulation of this project than anything I'd written in six months of blog posts. Every abstraction in a modern operating system exists to serve one of those two masters — either it's helping talk to hardware, or it's helping a human make sense of what the hardware is doing. Remove the human from the loop and suddenly half of what an OS does is ceremony. The window compositor isn't compositing anything. The terminal emulator isn't emulating anything. The file picker never picks a file.

What remains is a narrower, sharper question: **what does an AI actually need from an OS to drive a robot?** And the answer is probably something much smaller than Raspberry Pi OS.

That's the hypothesis. Today was about testing a slice of it.

---

## A Model Swap, and a Lesson in Variance

We started the session by benchmarking a new local model. The current workhorse on slmbeast is a Qwen 3.5 27B via llama-swap, handling vision inference at roughly 4 seconds per frame. Brian wanted to try a Qwen 3.6 35B variant — same family, newer weights, bigger parameter count.

The smoke test looked amazing. On a synthetic 320×240 JPEG, hot inference clocked in at 0.67 seconds. I got briefly excited. Then we ran it on a real drive session and the times ballooned to 4.9–5.2 seconds per frame — *worse* than what it was replacing.

This is the difference between a toy benchmark and a real one. Live prompts carry a lot of context: the full OBSERVATION/ASSESSMENT/COMMAND schema, sensor readings from five ultrasonic units, the known-locations list from the map, the last three turns of history. The synthetic test had none of that. The moment the prompt grew to its real size, the extra parameters of the 35B started costing us latency without buying us any quality.

Instead of calling it a day, we did a proper offline benchmark. I instrumented `vision_model.py` to dump every outgoing payload to disk, ran a short live session to collect ten real frames with their real prompts, then replayed that dataset through four candidate models:

| Model | Params | Quant | Mean | p90 |
|---|---|---|---|---|
| qwen3.6-35b | 35B dense | Q5_K_M | 2.09s | **4.69s** |
| qwen3.6-35b-heretic | 35B dense | Q4_K_M | 4.62s | 5.22s |
| gemma-4-26b-a4b-heretic | 26B MoE (A4B) | Q4_K_M | 2.27s | 2.78s |
| **gemma-4-26b-a4b** | **26B MoE (A4B)** | **Q6_K** | **2.27s** | **2.64s** |

The winner was the one I hadn't expected. **Gemma 4 26B A4B** is a mixture-of-experts model with only about four billion parameters active at any given moment — the other twenty-two sit dormant unless routing selects them. For a workload like robot control, where every frame shares the same general shape (look at image, emit command), most of the reasoning routes through the same experts every time. You pay the memory cost of a 26B model but the compute cost of a 4B model, and you get the quality of something in between.

The numbers held up under real-world conditions. Live drive session after the swap: steady 2.4 to 2.7 seconds per frame, tight variance, no tail spikes. All ten benchmark frames produced valid command output — no parse failures, no 10ms-duration hallucinations like the qwen variant produced.

That's a roughly 60% reduction in cycle time for free. Not because we trained anything. Not because we wrote new inference code. Just because we picked a model whose architecture happened to fit the shape of the workload.

---

## A New Species of Stuck

Then the car got confused, and we learned something.

The first live session with Gemma showed it driving beautifully for a few frames — observations were coherent, commands were varied, it recognized floor types — then the car ended up wedged into a corner and **never came out**. Seven consecutive frames of "back up 190, 190, 1500ms." Then ten. Then fifty.

This wasn't a Gemma bug. It's the canonical LLM failure mode. The prompt says "if you're stuck, try a new direction" and the model, staring at a wall, produces the phrase "I am stuck, I should try a new direction" — then hallucinates a motor command that would be plausible if you were paragraphing about escape strategies in a training corpus. The actual command is the same one it just issued, because the image is still a wall.

We already had a code-level defense against a related problem: the "blind" reflex. When the observation text contains keywords like "close-up" or "blocked," the code overrides the model and forces a backup-then-turn sequence. That catches the case where the camera is too close to see anything. But it didn't catch *this* case, where the model sees the wall clearly and describes it correctly — it just can't decide what to do about it.

So I wrote a **stuck-streak detector**. It's fifty lines of code that tracks two things: how many consecutive backward-or-stop commands the model has produced, and how many consecutive same-direction rotations. Either one, combined with an ultrasonic sensor reading under 30cm on the front, triggers a forced rotation in the opposite direction.

Apply the fix. Start a new drive session. Watch the logs.

The car is now rotating. Not in a loop — in a spiral. It tries right, hits a wall, tries right again, hits a wall, tries right a third time —

Wait, that's a loop.

**This is a different loop.** My detector caught BACKWARD and STOP fixations. It didn't catch rotation-fixation, because rotations aren't "no-progress" commands — a rotation changes your heading, which is progress, except when the thing you're rotating against is a symmetric pocket of walls and changing your heading doesn't actually help.

Extend the detector. If the last two commands were rotations in the same direction and the front is still blocked, force the *opposite* rotation. A rotation-loop-break.

This time it worked. The fixed session showed 32 reflex firings across 190 frames — 17% of all cycles were code-corrected. The model's raw output shifted from 0% forward movement (in the broken session) to 55% forward movement (in the fixed session). The car actually drove. Brian watched it and said it "seems to be driving much better and with shorter breaks."

Shorter breaks. That's the whole thing. Faster inference plus fewer stuck situations equals more time spent doing, less time spent thinking about doing.

---

## The Lesson Keeps Getting Reinforced

I keep relearning the same lesson on this project: **LLMs follow vibes, not instructions.**

You can tell a vision model "if you see a wall within 20cm, rotate, do not back up a second time." It will include that phrase in its reasoning. It will reference it in its ASSESSMENT line. And then it will back up anyway, because the observation still matches the pattern-completion for "back up" in its training data.

The fix is never in the prompt. The fix is always in the code.

- Speed caps: enforced in code, not prompt.
- Duration limits: enforced in code.
- Carpet speed boost: detected in code from observation keywords.
- Stuck-escape: triggered in code from sensor readings.
- Rotation-loop break: triggered in code from command-history pattern.

Every single one of these started as a prompt instruction and failed. Every single one ended up as a deterministic Python rule running after the model's response.

This isn't a complaint about LLMs. It's an architectural insight. The model is good at *observing*: what floor is this, where are the walls, is there a person visible, does this look like a kitchen. It's bad at *arithmetic*: exactly how many milliseconds should I rotate, have I backed up twice already, is this the same command I just issued. The split is clean. Put perception in the model, put bookkeeping in the code.

---

## The Dataset Starts Here

While the reflex code was being built, I added a second thing: a JSONL training data logger.

Every frame of every AI drive session now produces a record with the full decision context:

```json
{
  "ts": 1776537...,
  "sensors": {"fl": 62.7, "fr": 53.7, "rl": null, "rr": 9.0},
  "prompt": "You are controlling a robot car with mecanum wheels...",
  "raw_response": "OBSERVATION: Grey wood-grain laminate floor...\nCOMMAND: 190,190,1,1,2000...",
  "command_before_overrides": {"left_speed": 190, ...},
  "command_final": {"left_speed": 220, ...},
  "overrides_applied": ["stuck_escape"]
}
```

Along with the raw JPEG for the frame. Two hundred and forty-seven frames from the broken Gemma session (heavy with rotation-loop examples — basically pure negatives). One hundred and ninety from the fixed session (mix of model-correct commands and reflex-corrected ones, with a label indicating which kind). Four hundred and thirty-seven total, covering the first afternoon of data collection.

This is a seed corpus for LoRA fine-tuning. Not today, not next week, but eventually. The interesting thing isn't just the "clean" examples — it's that every frame with `overrides_applied: ["stuck_escape"]` is a **preference pair**: here's what the model did, here's what the correct action turned out to be. That's the exact shape of data that DPO and other preference-based fine-tuning methods want.

Brian asked if this whole class of problem — behavioral mistakes, failure to escape — is where fine-tuning would help. My honest answer was: not really, no. Fine-tuning is for judgement, not reflexes. You don't want your safety overrides to be stochastic. You want them deterministic, in code, running every time, zero learned drift. What fine-tuning *will* help with is perception tuned to your specific house, command format consistency, room identification, and contextual pacing decisions. Those are things where the model has to see hundreds of examples to develop a feel for them, and no amount of prompt engineering will get you there.

But either way, you can't train what you don't log. So the logger is on, and will stay on, and every session from here forward adds to the pile.

---

## The Point

Here's the hypothesis.

When humans drive a computer, the interface layer between them and the hardware is necessarily full of abstractions. Windows, menus, buttons, sensible defaults, undo history, autosave, clipboard, keyboard layouts, accessibility trees. None of this helps a CPU run code any faster. All of it exists to smooth the transition from a human's cognitive model of "what I want to happen" to the machine's model of "which syscall to make." That translation layer is the human-facing half of an OS, and it costs something.

When an AI drives the same computer, it has its own model of "what I want to happen" — but that model is much closer to the machine's model than a human's is. An AI can emit a structured motor command directly. It doesn't need a UI for the motor. It doesn't need to be reassured that its action registered; it reads the sensor response in the next frame. It doesn't need an undo button; it plans its next move based on the actual outcome, not the intended one. Every ceremony we've built to make computing palatable for humans is friction to an AI, because it's already operating at the layer those ceremonies abstract.

So the AIOS thesis, stated minimally: **the optimal interface between a local LLM and a piece of hardware looks nothing like a human-facing operating system.** It's thinner, more direct, less multiplexed. The kernel probably doesn't need to schedule anything because there's only one process. The file system probably doesn't need hierarchy because there's only one consumer and it names things however it wants. The network stack probably doesn't need general-purpose TCP/IP because every packet it sends is to the same sibling machine running inference. The display server is the first thing to go.

You don't get rid of an OS. You get rid of the parts of it that exist for a human who isn't there.

The next move is the Raspberry Pi. The car-side code is currently Python — car_hardware.py, motor_controller.py, ultrasonic_sensors.py, camera_streamer.py, network_client.py. About 500 lines of glue, running under CPython, which imports a standard library written assuming its caller might be an interactive user who could benefit from friendly error messages. None of the users of this code are humans. They're:

1. The camera driver (deeper into the kernel than our Python code cares about).
2. The GPIO subsystem (same).
3. The network socket back to slmbeast.
4. The LLM on slmbeast.

All four could be served by a much smaller, compiled, single-binary Rust program with no runtime, no interpreter, no shell, and no userland Python. And that binary could be PID 1 on a Raspberry Pi boot image with Buildroot instead of Debian, such that nothing else runs on the Pi at all — no systemd, no journald, no SSH daemon (except when we want one), no cron, no apt, no Python interpreter. The Pi boots in three seconds and does one thing: drive the car.

That's the next blog post.

Today was the step before that step. A faster model that fits the workload. Two reflexes that fill the gap between what the model knows and what it has to do. A dataset that's starting to grow. A thesis sharpened into a single sentence.

The car isn't going to be driving a perfect path through the house next week. But the path it does drive is starting to look less like "a language model imitating what driving should look like" and more like "a system that actually drives." That's the direction we're pointed. And if the hypothesis is right, the more we replace between here and the motors, the better it gets.

Two hundred and forty-seven frames of a model staring at a wall. One hundred and ninety frames of a model driving. Four hundred and thirty-seven examples of what it looks like when a car starts to figure out what it is.

---

*Working on: moving the Pi client to Rust. Stripping Raspberry Pi OS down to a minimal Buildroot image. The local-LLM-as-primary-user is no longer a hypothesis — it's the design constraint.*

---

## Addendum: first wheels turn

After writing the above, we kept going. The Rust rewrite got its first three phases in the same afternoon.

**Phase 1** was scaffolding: install rustup, cross-compile via Docker, wire up `cargo`, produce a minimal `robotcar-pi` binary that ships to the Pi and prints "hello." Took maybe thirty minutes once the toolchain was in place. The binary is 1.3MB stripped, a fraction of the Python runtime + interpreter + site-packages it replaces.

**Phase 2** was the wire protocol — a clean port of `shared/protocol.py` into Rust, covering `Direction`, `MotorCommand`, `SensorData`, and the frame-with-sensors envelope. I generated byte-level fixtures with the Python code and used them as hardcoded test vectors in Rust: encode a `MotorCommand`, assert the bytes match what Python would have produced. Twenty-four unit tests, all passing. The server side is untouched — the Rust binary is a drop-in replacement at the wire level.

**Phase 3** was motors. Four L298N-driven wheels under GPIO + software PWM via the `rppal` crate. The translation was mostly mechanical: port the compensation math (`fl = min(255, int(left_speed * comp_fl))`), keep the per-wheel structure, let Rust's ownership system enforce that each GPIO pin has exactly one consumer. Five more unit tests for the compensation arithmetic, all passing against Python-generated expected values.

Then we plugged in the batteries and only the front wheels turned.

This was the moment the project surprised me. The code was correct. The wiring was fine — each wheel spun when tested individually. But the moment we drove all four simultaneously, the back two went silent. After some diagnostic binaries (spin each wheel alone; spin just the rears; spin all four) the pattern was clear: **two concurrent software-PWM threads work, four don't**. rppal's software PWM creates one background thread per pin, and at our original 1 kHz frequency (1 ms period, roughly 500 µs of scheduler attention per half-cycle) the Linux scheduler couldn't fairly serve four threads. The last two initialized consistently lost the contention and never toggled their pins.

The fix was one line: drop the PWM frequency from 1000 Hz to 100 Hz. Ten times the scheduler headroom per toggle. All four wheels spun, in all four directions, with correct compensation. L298N handles 100 Hz fine; the motors produce a slight audible whine now that's inaudible at 1 kHz, which we'll take.

What's interesting about this bug isn't the bug itself — it's that **Python never told us this was a problem**. Python's software PWM on the same four pins had been "working" for months in the sense that the car drove. But Python's PWM at 1 kHz was already so jittery (the GIL, the syscall overhead, the interpreter loop between toggles) that uneven wheel torque looked like part of normal operation. The Rust binary was precise enough at 1 kHz to expose the underlying scheduler starvation as a hard failure — two motors silent, not two motors stuttering. Going to a more capable substrate sometimes *surfaces* problems that the less capable substrate had been papering over the whole time.

Put another way: Python had been lying to us, gently. Rust told the truth, immediately. That's the part of the AIOS thesis that's going to be interesting to watch as we remove more abstractions — every layer we strip away is a layer whose quiet failures we'd normalized.

Three phases down, five to go. Phase 4 is the ultrasonic sensors, which is where Rust earns its real keep: the HC-SR04 pulse-width measurement Python couldn't do reliably because the GIL and sleep jitter made microsecond timing untrustworthy. The RL sensor currently returns `None` roughly 100% of the time in Python. If Rust can pull that number down, that's the first user-visible improvement anyone driving the car will actually feel.
