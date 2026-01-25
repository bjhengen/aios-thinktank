# AIOS:ThinkTank

**An experiment to test whether AI can replace the traditional operating system.**

## The Thesis

Traditional operating systems exist as a human-computer interface. Shells, file systems, GUIs, multitasking—these are all affordances designed to translate human intent into machine action.

AI doesn't need these affordances.

This project tests a simple hypothesis: strip away everything that exists to serve humans, and let an AI interact with hardware more directly through a minimal "AI-native" interface.

## The Experiment

A mecanum-wheel robot car with the thinnest possible software layer. Llama 3.2 Vision running on an RTX 5090 serves as the "operating intelligence"—receiving camera frames and outputting motor commands. No ROS. No control loops in code. Just perception in, action out.

**The question:** Can an AI handle the control logic that traditionally lives in software—motion planning, obstacle avoidance, navigation—purely from vision, with minimal firmware beneath it?

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     RTX 5090 Server                         │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              Llama 3.2 Vision (11B)                   │  │
│  │                                                       │  │
│  │  Input: Camera frame + system prompt                  │  │
│  │  Output: JSON {fl, fr, rl, rr} motor values           │  │
│  └───────────────────────────────────────────────────────┘  │
│                         ▲ │                                 │
│                   frame │ │ command                         │
│                         │ ▼                                 │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              Python Control Server                    │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                          ▲ │
                     WiFi │ │ WiFi
                          │ ▼
┌─────────────────────────────────────────────────────────────┐
│                   Raspberry Pi 4 (2GB)                      │
│              Minimal Linux (Buildroot)                      │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                   C/Python Daemon                     │  │
│  │                                                       │  │
│  │  - Capture frame from Pi Camera                       │  │
│  │  - Stream to server                                   │  │
│  │  - Receive motor commands                             │  │
│  │  - Apply PWM to motor drivers                         │  │
│  │  - Watchdog: stop if no command in 200ms              │  │
│  └───────────────────────────────────────────────────────┘  │
│                         │                                   │
│                        GPIO                                 │
│                         ▼                                   │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              Motor Driver Board                       │  │
│  └───────────────────────────────────────────────────────┘  │
│                         │                                   │
│                         ▼                                   │
│                 4x Mecanum Wheel Motors                     │
└─────────────────────────────────────────────────────────────┘
```

## The Prompt is the Program

Instead of writing control logic in code, we write it in natural language:

```
You are controlling a mecanum-wheel robot car. You receive camera 
frames showing what the car sees.

Respond ONLY with a JSON object containing motor speeds:
{"fl": 0, "fr": 0, "rl": 0, "rr": 0}

Values range from -100 (full reverse) to 100 (full forward).

Your goal: [TASK GOES HERE]
```

## Hardware

See [hardware/PARTS.md](hardware/PARTS.md) for the complete parts list.

## Project Structure

```
aios-thinktank/
├── README.md           # You are here
├── docs/blog/          # Blog post drafts and content
├── pi/                 # Raspberry Pi daemon code
├── server/             # RTX 5090 control server + Llama integration
└── hardware/           # Wiring diagrams, parts list, GPIO mapping
```

## Blog Series

Follow along as we build and test this hypothesis:

1. [Unboxing: The Parts](docs/blog/01-unboxing.md) *(coming soon)*
2. First Boot
3. Closing the Loop
4. Experiments

## Author

**Brian Hengen** — VP of Database Platform Architects at Oracle, building AI applications and testing what's possible.

- Blog: [brianhengen.us](https://brianhengen.us)
- LinkedIn: [linkedin.com/in/brianhengen](https://linkedin.com/in/brianhengen)

## License

MIT
