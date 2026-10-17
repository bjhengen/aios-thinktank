# Robotcar rebuild brief (hand-off to the Claude chat, 2026-10-17)

This brief is for designing the chassis rebuild in a Claude chat. It covers
what exists today, what the software expects from the hardware, and what the
rebuild has to fix. The repo is `~/dev/robotcar` on slmbeast. The Pi
(`thinktank`, Pi 4 2GB) is a thin client: it streams camera frames and sensor
readings to the server and drives the motors on command. All the
intelligence runs on the server's RTX 5090.

## What Brian wants from the rebuild

- **More power.** The car should move off a dead stop with authority and keep
  moving on carpet.
- **Traction on tile.** Most floors are tile, and the hard plastic mecanum
  rollers slip.
- **A LEGO Technic body,** using the parts list from the earlier chat.

## Findings so far

- **Drop the mecanum wheels.** The software never strafes. It only drives
  forward, reverses and rotates (skid-steer), so mecanum buys nothing, and
  its hard rollers are the cause of the tile slip. Rubber tires are the fix.
- **Size the motors for rotation, not just straight-line driving.** The car
  turns by spinning the left and right sides in opposite directions. Grippy
  tires scrub sideways during that turn and need more torque, and rotation is
  already where the current car stalls. Choose grippier wheels and stronger
  motors together. Upgrading the wheels alone would make turning worse.
- **The L298N drivers should go.** They lose about 2V and have no current
  sensing. The current motors are yellow TT hobby motors rated 3–6V. Today
  the software has to force a minimum speed of 200/255 (`MIN_MOVE_SPEED`),
  because below that the car buzzes without moving.
- **Encoders would pay off.** Rotation is open-loop today: a fixed duration,
  1050 ms for left and 1800 ms for right because the chassis is front-heavy,
  and the calibration drifted 2.4x between March and April. Motors with wheel
  encoders would let the car turn by measured angle.

## The software contract (what the new hardware has to fit)

The server sends a 6-byte command:

| Field | Range | Meaning |
|---|---|---|
| `left_speed`, `right_speed` | 0–255 | PWM duty per side |
| `left_dir`, `right_dir` | backward / forward / stop | Per-side direction |
| `duration_ms` | 0–65535 | How long to run (0 = until the next command) |

Both wheels on a side get the same command. Each wheel then has its own
compensation multiplier on the Pi (`comp_fl` and so on in `pi/config.py`).
A watchdog stops the motors if no command arrives within 1 s. Any motor
driver that takes direction + PWM per motor fits this with only Pi-side
changes. A driver that needs serial/I2C commands, or a different motor
layout (2 motors instead of 4), is also fine, but it means rewriting
`pi/motor_controller.py` and `pi-rs/src/motors.rs`. Nothing on the server
needs to change either way.

The server-side speed constants (`server/command_generator.py:98-136`)
were tuned for the old car and will be re-tuned after the rebuild: forward
cap 235, rotation cap 220, floor 200, backup 150, emergency stop at 15 cm
on the front sensors.

## Current wiring (for the teardown)

Photograph every connection and tape-label each wire before you pull
anything. Nothing records which physical motor plugs into which board
output, except the names in the code.

**Motors** (two L298N boards; board 1 = left side, board 2 = right side;
right-side forward/back are swapped in software):

| L298N pin | GPIO (Pi physical pin) | Drives |
|---|---|---|
| Board 1 IN1 / IN2 / ENA | 17 (11) / 27 (13) / 12 (32) | Front-left: forward / back / PWM |
| Board 1 IN3 / IN4 / ENB | 22 (15) / 23 (16) / 13 (33) | Rear-left: forward / back / PWM |
| Board 2 IN1 / IN2 / ENA | 5 (29) / 6 (31) / 18 (12) | Front-right: back / forward / PWM |
| Board 2 IN3 / IN4 / ENB | 16 (36) / 26 (37) / 19 (35) | Rear-right: back / forward / PWM |

**Ultrasonics** (HC-SR04 ×5; trigger direct to the Pi, echo through a
TXS0108E level shifter because the sensors output 5V):

| Sensor | Trigger GPIO (pin) | Echo GPIO (pin) | Status |
|---|---|---|---|
| Front-center | 4 (7) | 24 (18) | Disconnected. Causes the car to drive straight into obstacles directly ahead |
| Front-left (45°) | 7 (26) | 25 (22) | Working |
| Front-right (45°) | 8 (24) | 20 (38) | Working |
| Rear-left | 9 (21) | 14 (8) | Dead: 100% dropout, a wire, shifter or sensor fault |
| Rear-right | 10 (19) | 15 (10) | Working |

Rear-left's echo sits on GPIO 14, which is one of the serial-port pins.
That's probably not why it died, but moving it to a plain GPIO pin costs
nothing during the rewire.

**Power:** an Anker 10000 mAh power bank feeds the Pi over USB-C. The motor
battery (4×AA today; a 2S 18650 pack was ordered as the replacement) goes
to each L298N's 12V and GND terminals. Pi pins 6 and 9 carry ground to the
motor boards. The ENA/ENB jumpers are removed, and the 5V regulator jumper
is on. Keep the Pi and motor power separate.

**Camera:** Pi Camera Module 3 Wide on the CSI ribbon, 640×480 at 10 fps.
Today it hangs on a binder clip that sits too low: the model sees floor
strips instead of rooms and makes up room names. An acrylic tilt mount was
ordered. Mount it higher and angled so doorways and furniture are in frame.

**Spare:** GPIO 21 is reserved for an optional emergency-stop button.

## Worth considering while it's apart

- Side-facing sensors. The front sensors point forward and can't see a wall
  alongside the car, so it gets stuck pressed parallel to walls.
- A 9-axis IMU (ICM-20948 or MPU-9250): heading would tell the north and
  south hallways apart, and it gives closed-loop turns if the motors don't
  have encoders.
- Keep the weight centered. The current chassis is front-heavy, which is why
  left and right rotation need different durations.

## What to bring back to the Claude Code session

The final parts list (motors, driver, wheels, battery, sensors), the new pin
map, and any change to the motor layout. With those, Claude Code updates
`pi/config.py`, the Rust config, the motor controller, and the wiring docs,
then runs calibration and smoke tests before the first drive.
