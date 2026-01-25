# AIOS:ThinkTank Build Day 2: First Movement

*The robot moves under its own power for the first time - after we fried two motor controllers learning an expensive lesson about polarity.*

---

## The Day's Objective

Wire up the motor controllers, connect everything to the Pi, and get the wheels spinning. The new pre-wired motors arrived, so no soldering required. Should be straightforward.

Spoiler: It wasn't.

---

## SSH Key Setup: AI-Ready Access

Before touching hardware, we set up passwordless SSH from the AI workstation (slmbeast) to the Pi. The whole point of this project is AI control - Claude needs to be able to run commands on the car without human intervention.

```bash
# Generated a fresh ed25519 key for the robotcar project
ssh-keygen -t ed25519 -C "slmbeast-robotcar" -f ~/.ssh/id_ed25519_robotcar

# Added to ~/.ssh/config
Host thinktank
    HostName 192.168.1.140
    User aios
    IdentityFile ~/.ssh/id_rsa
```

One gotcha: when pasting the public key to the Pi's `~/.ssh/authorized_keys`, line wrapping broke it. SSH keys must be on a single line. If you're getting "Permission denied (publickey)" after adding a key, check for accidental line breaks.

---

## L298N Wiring: The Expensive Lesson

The L298N H-Bridge motor driver has three power-related terminals:
- **12V** - Motor power INPUT
- **GND** - Common ground
- **5V** - Regulated power OUTPUT (from onboard regulator)

Read that again. The 5V terminal is an **OUTPUT**, not an input.

### What Happened

Connected the battery positive to the 5V terminal instead of 12V. Result:
- Spark
- Small shock
- LED blinked once and died
- Board permanently dead

The 5V terminal feeds from an onboard voltage regulator. Connecting external power there backfeeds the regulator and fries it instantly.

**Lesson learned:** On the L298N, battery positive goes to the 12V terminal. The 5V terminal is for powering other devices (like an Arduino) FROM the board, not for powering the board.

Fortunately, we had spare boards.

---

## The Wiring Plan

### Driver 1 - Front Wheels (FL + FR)

| L298N Pin | Function | Pi GPIO | Physical Pin |
|-----------|----------|---------|--------------|
| IN1 | FL Forward | GPIO 17 | Pin 11 |
| IN2 | FL Backward | GPIO 27 | Pin 13 |
| IN3 | FR Forward | GPIO 22 | Pin 15 |
| IN4 | FR Backward | GPIO 23 | Pin 16 |
| ENA | FL PWM | GPIO 12 | Pin 32 |
| ENB | FR PWM | GPIO 13 | Pin 33 |

### Driver 2 - Rear Wheels (RL + RR)

| L298N Pin | Function | Pi GPIO | Physical Pin |
|-----------|----------|---------|--------------|
| IN1 | RL Forward | GPIO 5 | Pin 29 |
| IN2 | RL Backward | GPIO 6 | Pin 31 |
| IN3 | RR Forward | GPIO 16 | Pin 36 |
| IN4 | RR Backward | GPIO 26 | Pin 37 |
| ENA | RL PWM | GPIO 18 | Pin 12 |
| ENB | RR PWM | GPIO 19 | Pin 35 |

### Power Connections

- Battery positive to L298N 12V terminals (both boards)
- Battery negative to L298N GND terminals
- **Critical:** Pi GND (Pin 6) connected to L298N GND for common reference

---

## Software Dependencies

Pi OS Lite doesn't include everything we need. Required packages:

```bash
sudo apt-get install -y python3-pip python3-pillow python3-rpi.gpio python3-picamera2
```

The `python3-picamera2` package is hefty - pulls in numpy, Qt5 libs, libcamera bindings. About 90MB of dependencies. But it gives us native access to the Pi Camera Module 3.

---

## First Movement

With fresh boards wired correctly and dependencies installed, we ran the motor test:

```bash
ssh thinktank "cd ~/robotcar && python3 -m pi.car_hardware --test-motors"
```

Output:
```
2026-01-24 18:40:27 - pi.motor_controller - INFO - Starting motor test sequence...
2026-01-24 18:40:27 - pi.motor_controller - INFO - Testing: Forward
2026-01-24 18:40:28 - pi.motor_controller - WARNING - EMERGENCY STOP
2026-01-24 18:40:28 - pi.motor_controller - INFO - Testing: Backward
2026-01-24 18:40:29 - pi.motor_controller - WARNING - EMERGENCY STOP
2026-01-24 18:40:30 - pi.motor_controller - INFO - Testing: Rotate Left
2026-01-24 18:40:31 - pi.motor_controller - WARNING - EMERGENCY STOP
2026-01-24 18:40:31 - pi.motor_controller - INFO - Testing: Rotate Right
2026-01-24 18:40:32 - pi.motor_controller - WARNING - EMERGENCY STOP
2026-01-24 18:40:33 - pi.motor_controller - INFO - Motor test complete
```

All four wheels spinning. Forward, backward, rotate left, rotate right.

The robot moves.

[VIDEO: Motor test sequence - all four mecanum wheels spinning]

---

## Camera Verification

With motors working, we verified the camera:

```bash
ssh thinktank "cd ~/robotcar && python3 -m pi.car_hardware --test-camera"
```

```
2026-01-24 18:42:44 - pi.camera_streamer - INFO - Camera initialized: 640x480 @ 10 FPS
2026-01-24 18:42:44 - __main__ - INFO - Captured frame 1: 28970 bytes
2026-01-24 18:42:45 - __main__ - INFO - Captured frame 2: 21915 bytes
...
2026-01-24 18:42:49 - __main__ - INFO - Captured frame 10: 17572 bytes
```

Frame sizes vary between 12-29KB - real JPEG captures, not simulation frames. The AI will have eyes.

---

## Hardware Status

| Component | Status |
|-----------|--------|
| Front Left Motor | Working |
| Front Right Motor | Working |
| Rear Left Motor | Working |
| Rear Right Motor | Working |
| Pi Camera Module 3 | Working (640x480 @ 10 FPS) |
| L298N Driver #1 | Working (replacement) |
| L298N Driver #2 | Working (replacement) |
| SSH from AI Workstation | Working (passwordless) |

**Casualties:** Two L298N boards (user error - wrong power terminal)

---

## What's Next

The hardware layer is complete. The Pi can:
- Capture camera frames
- Control all four motors
- Accept SSH commands from the AI workstation

Next session: Connect the Pi to the server and test the full AI control loop. The vision model (Qwen2-VL-7B) on the RTX 5090 will receive camera frames and generate motor commands. The question we've been building toward: can an AI actually drive this thing?

---

## Lessons Learned

1. **L298N 5V is an OUTPUT.** Battery positive goes to 12V. Backfeeding the 5V terminal kills the board instantly.

2. **Keep spare components.** Hardware debugging goes faster when you can swap parts to isolate problems.

3. **Check power first.** "Nothing happening" is almost always a power issue - disconnected, dead batteries, or wrong polarity.

4. **SSH keys must be single-line.** Line breaks in authorized_keys will silently fail authentication.

5. **picamera2 replaces picamera.** The old Python camera library doesn't work on newer Pi OS. Use `python3-picamera2` from apt.

---

## The Moment

There's something satisfying about watching wheels spin for the first time. It's just motors responding to GPIO signals - nothing fancy. But it means the wiring is right, the code works, and the path to AI control is clear.

Next time, we find out if an AI can actually navigate with this thing.

---

*This is part of the AIOS:ThinkTank build series. The robot car that asks: what if the AI isn't just assisting the operating system - what if the AI IS the operating system?*

*[Previous: First Boot](02-build-day-1.md) | [Next: AI Control](04-ai-control.md)*
