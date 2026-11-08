# Robotcar rebuild parts catalog (2026-11-08)

This catalog records the parts on hand for the chassis rebuild. It is built from Brian's
34 photos of 2026-11-08 (`/u02/share/media/robotcar-build2/build_components_8Nov26.zip`;
file names below are the photo timestamps, `20261108_HHMMSS.jpg`). The order list itself
lives in the claude.ai design chat, so anything not readable on a label is marked
**confirm** rather than guessed.

Read with [`2026-10-17-rebuild-brief.md`](2026-10-17-rebuild-brief.md), which holds the
software contract and the old wiring tables.

## What the parts say about the design

The parts point to a two-wheel differential drive on ball casters rather than the old
four-wheel skid-steer. The RoboClaw has two motor channels, the Pololu wheels came as one
pair, and there are 16 ball-transfer casters. A two-wheel layout with casters also removes
the problem the brief worried about most: grippy tires scrubbing sideways in a skid-steer
turn. With casters, the drive wheels only roll. **Confirm the layout with Brian before any
code changes**, because the motor count was not visible in the photos.

The parts also point to aluminium rather than LEGO for the structure: two goBILDA grid
plates, standoffs and M4 screws, and a clamping motor mount. The LEGO Technic parts from
the earlier plan are still on hand and suit lighter jobs such as sensor brackets, the
camera mast and covers.

## Drive train

| Part | Seen on label | Qty seen | Photo | Notes |
|---|---|---|---|---|
| Gear motors | CQRobot "Metal DC Gear Motor" | 2 boxes (**confirm** count) | 163613 | The model, voltage, gear ratio and encoder were not visible. The motor in the open box is a long cylindrical gearmotor with a bracket, consistent with a 37 mm motor with an encoder. **Confirm** from the motor label. |
| Motor controller | Pololu #3682, RoboClaw 2x7A (V6B/V6F) | 1 | 164111 | Two channels, 7.5 A continuous and 15 A peak per channel, up to 34 V. It is driven over USB, TTL serial, RC or analog, not direction + PWM pins. It has quadrature encoder inputs for closed-loop speed and position. |
| Wheels | Pololu #1438, 90×10 mm wheel pair, blue | 1 pair | 164111 | Silicone tires. The hub bore is a 3 mm D, so a larger motor needs a Pololu universal mounting hub (six #4-40/M3 holes). |
| Wheel hubs | Packing slip line reads "...Mounting Hub for 6...", "2-Pa..." | **not seen** | 164111 | The slip appears to list a 6 mm universal aluminium hub 2-pack, which is what a 37D motor's 6 mm shaft needs. **Confirm** the hubs are in the box. |
| Hub screws | #4-40 × 1/4" pan head machine screws | pack of 25 | 163704 | These match the #4-40 holes of the Pololu universal hubs. |
| Ball casters | 1/2" roller ball transfer units, 22 lb rating | 16 | 163836 | Two-hole flange mount. |

## Structure

| Part | Seen on label | Qty seen | Photo | Notes |
|---|---|---|---|---|
| Grid plates | goBILDA 1116-0136-0232, 1116 Series Grid Plate, 17×29 hole, 136×232 mm | 2 | 163912 | Aluminium chassis decks. |
| Socket head screws | goBILDA/Robotzone 2800-0004-0012, M4×0.7 × 12 mm | pack of 25 plus loose | 163753 | |
| Standoffs/rods | aluminium, unmarked | 4 | 163753 | **Confirm** whether these are threaded standoffs. |
| Motor clamp | aluminium clamping mount with a round bore, unmarked | 1 seen | 163753 | Probably sized for a 37 mm motor. **Confirm** the count; two motors need two. |
| Camera mount | Poolside Factory tilt-adjustable Raspberry Pi camera mount (fits camera module v1/v2/v3/AI) | 1 | 163635 | The tilt mount the brief called for. It fixes the low camera angle behind the room-name hallucinations. |
| Washers | flat washer assortment | 1 box | 163623 | |
| Hot glue gun | Boswell BS778, 150 W | 1 | 163807 | |

## Power

| Part | Seen on label | Qty seen | Photo | Notes |
|---|---|---|---|---|
| Cells | Samsung-type INR18650-30Q, 3000 mAh | ~4 visible (**confirm**) | 164027 | 15 A continuous cells. Use cells from the same batch in a series pack. |
| 3S charger | 12.6 V 1 A Li-ion charger for 3S 11.1 V packs, US plug | 1 | 164042 | |
| 3S BMS | 3S 20A BMS (12.6 V / 8.4 V / 4.2 V taps) | 6 | 163730, 163734 | |
| 18650 holders | 18650 battery holder, 4 pcs, "3 Sl...or Series" (likely 3-slot) | 4 | 164006 | Open frame. |
| 2S holders | 2× 18650 enclosed holder with switch and leads, 7.4 V | 2 | 164001 | |
| 2S protection | Anmbest 2S protection board | 5 | 163718, 163722 | |
| 2S USB-C charger board | Adeept Type-C BMS, "USB C to 8.4V", 18650 | 1 | 163534 | Charges a 2S pack from USB-C. |
| Inline fuse holders | ATO blade fuse holders with red leads | ~8 | 163925 | |
| Blade fuses | 120 pc ATO set: 5, 7.5, 10, 15, 20, 25 and 30 A | 1 box | 163938, 163943 | |
| Power connectors | LEDVillage kit: XT60, EC3, Deans/T, Traxxas-style, bullets, silicone leads, heat shrink | 1 box | 163858, 163902 | |
| Rocker switches | DaierTek KCD1-5-101, 2-pin, with leads | 5 | 163742 | Main power switches. |
| Push button | APIELE 16 mm metal push button, momentary, blue LED ring (12 V) | 1 | 163815, 163818 | Momentary, so it cannot latch power off. It suits the GPIO 21 stop button the brief reserved, not a hard motor-power cut. |

## Sensors and wiring

| Part | Seen on label | Qty seen | Photo | Notes |
|---|---|---|---|---|
| Ultrasonic sensors | Elegoo HC-SR04, set of 5 | 2 sets (10) | 163955 | 5 V parts. Their echo still needs level shifting to the Pi; the old TXS0108E is on the old car. |
| Hook-up wire | TUOFENG spool box, 6 colours | 1 | 163847 | **Confirm** the gauge. |
| ESD ground cord | Kaisi grounding cord for the bench mat | 1 | 164015 | |

## Carried over from the earlier plan

| Part | Qty seen | Photo | Notes |
|---|---|---|---|
| LEGO Technic: blue panel, orange beams and liftarms, dark grey frames | 1 bag | 163647 | Useful for sensor brackets, the camera mast and covers. |
| LEGO Technic: black beams and liftarms; black and blue pins | 2 bags | 163827 | Blue pins are friction axle-pins. |
| LEGO Technic: dark grey pins | ~12 | 163655 | |
| YEEWANKE rechargeable AA cells with charging case | 8 | 164132 | Leftover from the 4×AA motor supply; not needed once the 18650 pack is in. |
| The old car, wires tape-labelled for teardown | 1 | 163934 | The labelling the brief asked for is already done. Donor parts: the Pi 4, the Pi Camera Module 3 Wide, the TXS0108E level shifter, the 5 working HC-SR04s, the Anker power bank. |

## Not seen in the photos

- **A 5 V supply for the Pi.** There is no buck converter, so the Pi presumably stays on the
  Anker power bank. That also keeps Pi and motor power separate, as the brief recommends.
- **An IMU.** The brief suggested one, but encoder motors make it optional for turning.
- **A RoboClaw-to-Pi cable** (micro-B USB, or jumper leads for TTL serial).

## Open questions for Brian

1. **The motor label.** What are the model, rated voltage, gear ratio and encoder? A photo
   of the label and the shaft settles all four.
2. **The layout.** Is it two drive wheels on the RoboClaw plus ball casters? That changes
   `pi/config.py` (per-wheel compensation `comp_fl` etc. collapses to two motors, or goes
   away under encoder speed control) and the per-wheel test tooling. The server-side
   `MotorCommand` (left/right speed, direction, duration) still fits unchanged.
3. **The pack.** The parts cover both a 3S pack (charger, BMS, holders) and a 2S pack
   (enclosed holders, protection boards, USB-C charger). Which one drives the motors, and
   is the other one spare from the earlier plan? A 12 V motor wants 3S.
4. **The hubs.** Are the 6 mm Pololu hubs on the packing slip in the box?
5. **The RoboClaw link.** USB or TTL serial? I recommend USB. The Pi's UART pins are GPIO 14
   and 15, which today carry the rear-left and rear-right echo lines, so TTL serial would
   force those two sensors to move. Either way the RoboClaw replaces the direction + PWM
   interface, so `pi/motor_controller.py` and `pi-rs/src/motors.rs` get rewritten (the
   brief foresaw this).
