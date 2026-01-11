# AIOS:ThinkTank Part 1: Unboxing

*Can AI replace the operating system? Let's find out.*

---

## The Hypothesis

Traditional operating systems exist to serve humans. Shells, file systems, GUIs, permissions, multitasking—these are all interfaces designed to translate human intent into machine action.

But AI doesn't need a shell. It doesn't need a file browser. It doesn't need a desktop metaphor.

What if we stripped away everything that exists to serve humans and let AI interact with hardware more directly?

That's what I'm testing with **AIOS:ThinkTank**—a mecanum-wheel robot car with the thinnest possible software layer. An AI vision model (Llama 3.2 Vision) running on my RTX 5090 server will serve as the "operating intelligence," receiving camera frames and outputting motor commands. No ROS. No coded control loops. Just perception in, action out.

If the AI can handle motion planning, obstacle avoidance, and navigation purely from vision—with minimal firmware beneath it—it suggests something interesting about the future of operating systems.

---

## The Architecture

[ARCHITECTURE DIAGRAM - TODO: Create visual version]

The system has two parts:

**On the car (Raspberry Pi 4):**
- Captures camera frames
- Streams to the server over WiFi
- Receives motor commands
- Applies PWM signals to motors
- Stops if connection is lost (safety watchdog)

That's it. Maybe 400 lines of code. No logic, no decisions—just I/O.

**On the server (RTX 5090):**
- Receives camera frames
- Runs Llama 3.2 Vision
- Decides what the car should do
- Sends motor commands back

All the intelligence lives here. The prompt *is* the program.

---

## The Parts

Here's what we're working with:

### Compute

**Raspberry Pi 4 Model B (2GB)**

[PHOTO: Pi 4]

The brain on the vehicle—though in this experiment, it's really just the peripheral nervous system. We chose the 2GB model because we don't need memory for AI inference; all the thinking happens on the server. The Pi just needs enough to handle camera streaming and motor control.

---

### Chassis & Mobility

**[CHASSIS NAME]**

[PHOTO: Chassis with mecanum wheels]

Mecanum wheels are the key to this build. Those angled rollers let the car move in any direction—forward, backward, strafe left/right, rotate—without needing a steering mechanism. This gives the AI full freedom of movement with a simple control interface: just four motor speed values.

---

### Electronics

**[MOTOR DRIVER NAME]**

[PHOTO: Motor driver board]

Bridges the gap between the Pi's GPIO pins and the motors. Takes low-power control signals and translates them into the higher current the motors need.

---

**[CAMERA NAME]**

[PHOTO: Camera module]

The AI's eyes. Every frame from this camera goes to the server, where Llama 3.2 Vision decides what to do next.

---

**Power Supply**

[PHOTO: Battery pack or power supply]

[DESCRIPTION TBD]

---

## What's Next

Next up: **First Boot**. We'll flash a minimal Linux image to the Pi, prove the camera and motors work independently, and prepare for the moment of truth—closing the loop with AI control.

Follow along on [GitHub](https://github.com/bjhengen/aios-thinktank) or connect with me on [LinkedIn](https://linkedin.com/in/brianhengen).

---

*Part of the AIOS:ThinkTank series. [Back to project overview](https://github.com/bjhengen/aios-thinktank)*
