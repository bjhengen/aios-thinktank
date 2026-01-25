# AIOS:ThinkTank Build Day 1: First Boot and Chassis Assembly

*The robot takes shape — Pi is alive, wheels are on, and we hit our first real-world snag.*

---

## The Day's Objective

Get the foundational pieces in place: a working Raspberry Pi with camera, an assembled chassis, and a clear path to wiring. One hour of build time. Let's see how far we get.

---

## Naming the Project

Before touching hardware, we needed a name. After some back and forth, we landed on **AIOS:ThinkTank**.

- **AIOS** — AI Operating System. The thesis we're testing.
- **ThinkTank** — The vehicle itself. It thinks. It's vaguely tank-like with its mecanum wheels.
- **The colon** — Gives it a namespace feel. If this works, maybe there's an AIOS:Drone or AIOS:Arm in the future.

The GitHub repo is live at [github.com/bjhengen/aios-thinktank](https://github.com/bjhengen/aios-thinktank). Public from day one — if we're going to test a thesis, we might as well do it in the open.

---

## Raspberry Pi: First Boot

The Pi 4 is the "peripheral nervous system" of this build — it handles camera input and motor output, but all the thinking happens on the RTX 5090 server running Llama 3.2 Vision. The Pi just needs to be lean and reliable.

### The Setup

Flashed **Raspberry Pi OS Lite (64-bit)** using Raspberry Pi Imager. No desktop environment — just command line. Every GUI element is overhead we don't need.

A small philosophical decision during setup: what should the login credentials be? The whole point of this project is that the AI controls the system, not a human. So I let Claude pick:

- **Username:** `aios`
- **Password:** `IAmTheOperatingSystem`

A small thing, but it felt right. Every time I log in, I'm reminded that this machine isn't meant for me.

**Hostname:** `thinktank` — so we can reach it at `thinktank.local` on the network.

### First Boot Checklist

- ✅ Boots to login prompt
- ✅ Login works
- ✅ WiFi connected (configured in Imager)
- ✅ SSH working — confirmed from my laptop with `ssh aios@thinktank.local`

From here on out, no monitor or keyboard needed. The Pi runs headless.

[PHOTO: Pi connected to monitor showing login prompt]

---

## Camera: The AI's Eyes

Connected the **Raspberry Pi Camera Module 3** to the CSI port. The ribbon cable is always a bit fiddly — lift the black plastic tab, slide the cable in with the blue side facing the Ethernet port, push the tab back down.

### A Minor Gotcha

Went into `raspi-config` to enable the camera... and there's no camera option. Turns out, on newer Pi OS (Bookworm), the camera is enabled by default. The old menu option is gone because it's no longer needed. The new `libcamera` stack is always on.

### Another Minor Gotcha

Tried to test with `libcamera-hello` — command not found. Pi OS Lite doesn't include camera tools by default.

```bash
sudo apt update
sudo apt install -y libcamera-apps
```

Tried again — still not found. Turns out on Bookworm, the commands were renamed from `libcamera-*` to `rpicam-*`.

```bash
rpicam-hello --timeout 5000
```

**Success.** Five seconds of live video from the camera. The AI will have eyes.

[PHOTO: Camera module connected to Pi]
[VIDEO: rpicam-hello test output]

---

## Chassis Assembly

The **MC100 Mecanum Wheel Chassis Kit** is straightforward — metal frame, four TT motors, four mecanum wheels, mounting hardware.

### Mecanum Wheel Orientation

This matters. The angled rollers on mecanum wheels need to form an **X pattern** when viewed from above. Front wheels point inward, rear wheels point inward. Get this wrong and the car will strafe the opposite direction from what you intend.

```
    Front
     ╲   ╱
      ╲ ╱
      ╱ ╲
     ╱   ╲
    Back
```

Motors mounted, wheels attached. The mechanical assembly is complete.

[PHOTO: Assembled chassis, top view showing X pattern]
[PHOTO: Side view showing motors]

---

## Motor Drivers: L298N Prep

The **L298N H-Bridge** boards will translate Pi GPIO signals into motor power. Each board handles two motors, so we need two boards for four-wheel drive.

### Prep Work

Removed the **ENA and ENB jumpers** from both boards. These jumpers bypass the speed control pins — with them in place, motors run at full speed whenever enabled. We need those pins free so the Pi can send PWM signals for variable speed control.

Left the 5V regulator jumper in place.

[PHOTO: L298N board with jumpers removed]

---

## The First Real Problem: Motor Voltage

While documenting the parts, I noticed something concerning.

- **Battery pack:** 6x AA = 9V nominal
- **TT motors in the MC100 kit:** Rated 3V-6V

That's a problem. 9V into a 6V motor will burn it out.

### The Solutions

**Immediate fix:** The L298N has about a 1.5-2V drop, so 9V in means ~7-7.5V to the motors. Still too high, but we can cap the PWM duty cycle at 80% in software, effectively limiting voltage to ~6V. This actually gives us headroom as batteries discharge.

**Cleaner fix:** Ordered a **4x AA battery holder** ($5). Four AAs = 6V nominal, matching the motor specs exactly. Swap it in when it arrives.

Funny thing — the 6x AA holder came bundled with the chassis kit that includes 3-6V motors. Someone didn't think that through.

---

## The Second Problem: No Motor Wires

Got ready to wire the motors to the L298N boards and realized... the motors have bare solder tabs. No wires attached. The chassis kit apparently assumes you'll solder your own.

I don't have a soldering iron. The dupont jumper wires I have are designed for pin headers, not flat tabs.

### The Solution

Rather than buy specialty connectors or a soldering kit for this one task, I ordered **replacement TT motors with wires pre-attached** — same form factor, $7 for a 4-pack. Minor annoyance to swap them out, but it skips the problem entirely.

[PHOTO: Bare motor tabs — no wires]

---

## End of Day Status

**Completed:**
- ✅ GitHub repo live and public
- ✅ Pi OS Lite installed, booted, SSH working
- ✅ Camera Module 3 connected and tested
- ✅ Chassis assembled (motors + mecanum wheels)
- ✅ L298N boards prepped (jumpers removed)
- ✅ Identified and solved motor voltage mismatch

**Waiting on:**
- ⏸️ Pre-wired TT motors (arriving soon)
- ⏸️ 4x AA battery holder (arriving soon)

**Next session:**
- Swap motors
- Wire L298N boards to Pi GPIO
- Test individual motors
- First movement

---

## Lessons Learned

1. **Check your voltages before you build.** The kit came with incompatible parts — 9V battery holder + 6V motors. Always verify specs match.

2. **Pi OS keeps changing.** Commands get renamed (`libcamera` → `rpicam`), menu options disappear, defaults change. When something doesn't work, check if the OS version changed the interface.

3. **Pre-wired beats soldering for prototypes.** For $7, I skipped a tooling purchase and saved time. Production hardware can be optimized later.

4. **Mecanum wheel orientation matters.** Easy to get wrong, annoying to debug later. The X pattern, viewed from above.

---

## The Bigger Picture

None of this is the interesting part yet. The interesting part is whether an AI can actually control this thing — whether Llama 3.2 Vision can look at camera frames and output motor commands that result in coherent movement.

But you can't test the interesting part until the boring parts work. Today was about the boring parts.

Next time: wires, electrons, and hopefully spinning wheels.

---

*This is part of the AIOS:ThinkTank build series. Follow along on [GitHub](https://github.com/bjhengen/aios-thinktank) or connect on [LinkedIn](https://linkedin.com/in/brianhengen).*

*[← Previous: Unboxing](01-unboxing.md) | [Next: First Movement →](03-first-movement.md)*
