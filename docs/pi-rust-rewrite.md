# Pi-side Rewrite in Rust — Design Sketch

Draft design document. The goal is to replace the Python car-side code (~1,200 lines across `pi/`) with a single Rust binary. This is the first concrete step toward the AIOS thesis: removing abstractions on the Pi that exist only to serve a human operator.

---

## Goals

- **Parity first.** Wire protocol to slmbeast remains byte-for-byte compatible. The server side is untouched. The Rust binary is a drop-in replacement for `python3 -m pi.car_hardware`.
- **Single static binary.** No runtime, no interpreter, no Python dependencies on the Pi.
- **Improved PWM jitter** via rppal's software PWM (lower jitter than Python's RPi.GPIO thanks to the absence of the GIL and fewer syscall layers). Note: Pi 4 has only 2 hardware PWM channels (PWM0 routed to GPIO 12 or 18, PWM1 routed to GPIO 13 or 19), so we cannot put all 4 wheels on hardware PWM. Software PWM for all 4 is the Phase-3 choice; hardware PWM for the 2 front wheels is an optional future optimization.
- **Reliable HC-SR04 timing** — reduce the `None` dropout rate on the RL/RR sensors, which is currently caused by Python GIL + syscall jitter during echo-pulse measurement.
- **Step toward Option 3** (strip the OS). The binary should be free of dependencies on systemd/journald/dbus so it can run as PID 1 under Buildroot later.

## Non-goals (for this phase)

- Replacing the slmbeast-side Python inference pipeline. That stays.
- Removing Raspberry Pi OS. That's Option 3, a later phase.
- Bare-metal or RTOS. We keep the Linux kernel for its drivers (camera, Wi-Fi, networking stack).
- Rewriting the wire protocol. The 6-byte motor command / 20-byte sensor header / `[size][payload]` frame format stays fixed.

---

## What we're replacing

| Python file | Lines | Responsibilities |
|---|---|---|
| `pi/car_hardware.py` | 364 | Main loop, orchestration, watchdog thread |
| `pi/motor_controller.py` | 299 | GPIO motor control, PWM, compensation, emergency stop |
| `pi/ultrasonic_sensors.py` | 291 | HC-SR04 trigger + echo timing, 5 sensors |
| `pi/camera_streamer.py` | 175 | picamera2 capture, JPEG encode |
| `pi/network_client.py` | 182 | TCP connect, frame send, command receive, reconnect |
| `pi/config.py` | 81 | GPIO pin assignments, speeds, thresholds |
| **Total** | **1,392** | |

Plus we re-implement (not reuse) the Pi-side slices of `shared/protocol.py` — the wire-format encode/decode — in Rust. The server still uses the Python version.

---

## Crate layout

```
pi-rs/
├── Cargo.toml
├── src/
│   ├── main.rs           # entry point, argument parsing, signal handling
│   ├── config.rs         # compile-time constants; matches pi/config.py
│   ├── protocol.rs       # MotorCommand, SensorData, FrameProtocol
│   ├── motors.rs         # MotorController, compensation, PWM
│   ├── sensors.rs        # UltrasonicSensors, 5x HC-SR04 poller
│   ├── camera.rs         # libcamera capture + JPEG encode
│   ├── network.rs        # TCP client, framing, reconnect
│   └── watchdog.rs       # shared state for the motor-kill watchdog
└── deploy/
    ├── cross.sh          # cross-compile wrapper for slmbeast → aarch64
    └── robotcar-pi.service  # systemd unit (until we move to PID 1)
```

## Dependencies

| Crate | Version | Purpose |
|---|---|---|
| `rppal` | 0.19 | BCM GPIO, hardware PWM, I²C/SPI if ever needed |
| `libcamera-rs` | 0.3 | **Risk — see below.** Bindings to libcamera for Pi Camera Module 3 |
| `turbojpeg` | 1 | Fast JPEG encode (vs. libjpeg ≈ 2× faster) |
| `crossbeam-channel` | 0.5 | bounded channels between threads |
| `byteorder` | 1 | big-endian wire-format encode/decode |
| `log` + `env_logger` | — | structured logging (removable if we target Buildroot) |
| `anyhow` + `thiserror` | — | error types |

Deliberately **not** using `tokio` — the concurrency is modest (3 threads) and blocking I/O is simpler and more predictable than async for this workload. If we later add more parallel tasks (IMU, encoders, etc.) we reconsider.

---

## Concurrency model

Three threads + one short-lived timer, all coordinated by channels and an `Arc<RwLock<SensorData>>`:

```
  ┌───────────────────┐
  │ camera thread     │  10 Hz
  │ libcamera capture │───┐
  │ → JPEG encode     │   │ (jpeg bytes)
  └───────────────────┘   │
                          ▼
  ┌───────────────────┐   Channel<FrameWithSensors>
  │ sensors thread    │   │
  │ 20 Hz HC-SR04     │───┤
  │ polling loop      │   │ (updates shared SensorData)
  └───────────────────┘   │
                          ▼
                 ┌────────────────────┐
                 │ network thread     │
                 │ TCP send/recv      │────→ slmbeast (frames, sensors)
                 │ incoming commands  │←──── slmbeast (MotorCommand)
                 └─────────┬──────────┘
                           │ (command)
                           ▼
                 ┌────────────────────┐
                 │ main thread        │
                 │ motor exec + wdog  │───→ GPIO PWM
                 └────────────────────┘
```

- **Camera thread**: blocking `libcamera::capture()` → encode → push to bounded channel. Drops frames if channel is full (network slow) rather than growing unbounded memory.
- **Sensor thread**: infinite loop, 50ms cadence. Trigger each of 5 HC-SR04s, measure echo pulse width with nanosecond `Instant`, update shared `SensorData` under a `RwLock`. Reads are lock-free for the consumer (clone-on-read).
- **Network thread**: on connect, splits into read-half and write-half tasks internally. Writes are `frame_with_sensors` reads from the camera channel + latest sensor snapshot. Reads are incoming `MotorCommand`s pushed to the main thread's channel.
- **Main thread**: receives commands, applies compensation, issues `rppal::Pwm` updates, starts a watchdog timer that emergency-stops if no new command arrives within 1 second.

This matches the current Python structure almost exactly — the mapping is 1:1, which keeps the migration mentally simple.

---

## Module sketches

### `protocol.rs`

Direct port of `shared/protocol.py`. Big-endian everywhere, tested against Python-generated fixtures.

```rust
#[repr(u8)]
#[derive(Copy, Clone, Debug)]
pub enum Direction { Backward = 0, Forward = 1, Stop = 2 }

#[derive(Copy, Clone, Debug)]
pub struct MotorCommand {
    pub left_speed: u8,
    pub right_speed: u8,
    pub left_dir: Direction,
    pub right_dir: Direction,
    pub duration_ms: u16,
}

impl MotorCommand {
    pub fn from_bytes(b: &[u8; 6]) -> Result<Self> { ... }
    pub fn to_bytes(&self) -> [u8; 6] { ... }
    pub fn stop() -> Self { ... }
}

pub struct SensorData { pub fc: u16, pub fl: u16, pub fr: u16, pub rl: u16, pub rr: u16 }

pub const SENSOR_MAGIC: [u8; 2] = [0x53, 0x01];
pub const FRAME_HEADER_SIZE: usize = 4;
// ... encode_frame_with_sensors(), decode_frame_payload(), etc.
```

Unit tests: round-trip against byte vectors from the Python version.

### `motors.rs`

Software PWM on GPIO 12, 13, 18, 19 via `rppal::gpio::OutputPin::set_pwm_frequency()`. Direction pins via `rppal::gpio::OutputPin`. (Hardware PWM on Pi 4 is limited to 2 channels — we'd need to give up per-wheel PWM on 2 motors to use it. Not worth it for Phase 3.)

```rust
pub struct MotorController {
    fl_fwd: OutputPin, fl_bwd: OutputPin, fl_pwm: Pwm,
    fr_fwd: OutputPin, fr_bwd: OutputPin, fr_pwm: Pwm,
    rl_fwd: OutputPin, rl_bwd: OutputPin, rl_pwm: Pwm,
    rr_fwd: OutputPin, rr_bwd: OutputPin, rr_pwm: Pwm,
}

impl MotorController {
    pub fn apply(&mut self, cmd: MotorCommand) -> Result<()> {
        let c = compensate(cmd); // per-wheel speed tweaks
        self.set_wheel(Wheel::FL, c.fl_speed, c.fl_dir)?;
        // ... etc
    }
    pub fn emergency_stop(&mut self) -> Result<()> { ... }
}
```

Compensation logic is line-for-line translated from `pi/motor_controller.py` — same factors (FL=1.10, FR=1.04, RL=1.0, RR=0.94), same dead-RL fallback.

### `sensors.rs`

The most interesting module. HC-SR04 pulse-width measurement is where Rust earns its keep.

```rust
pub struct UltrasonicArray {
    sensors: [SensorChannel; 5],  // FC, FL, FR, RL, RR
    shared: Arc<RwLock<SensorData>>,
}

struct SensorChannel {
    trig: OutputPin,
    echo: InputPin,
    last: Option<SensorReading>,
}

impl SensorChannel {
    fn measure(&mut self) -> Option<f32> {
        // 10μs HIGH pulse on trigger
        self.trig.set_high();
        spin_wait(Duration::from_micros(10));
        self.trig.set_low();

        // wait for echo rise, up to 40ms
        let start = wait_for_edge(&self.echo, Level::High, Duration::from_millis(40))?;
        // measure echo width, up to 40ms
        let end = wait_for_edge(&self.echo, Level::Low, Duration::from_millis(40))?;
        let us = (end - start).as_micros() as f32;
        Some(us * SPEED_OF_SOUND_CM_PER_US / 2.0)
    }
}
```

Open question: do we use `rppal`'s `poll_interrupt()` which parks the thread via `/sys/class/gpio/gpioN/value`, or do we busy-loop with `Instant::now()` in a tight loop? The former is cheap on CPU, the latter is more precise. For 5 sensors at 20Hz, busy-loop is fine (~1% CPU) and the precision wins. We'll benchmark both.

Fallback path if this still isn't reliable: use the **pigpio daemon** (which does DMA-based timing at the kernel level) via its C/IPC interface. Rust bindings exist (`rpi-pigpio`). Keeps Rust in userspace but offloads the timing-critical work to a DMA engine. Worth prototyping if the direct approach has the same dropout rate as Python.

### `camera.rs`

Biggest risk in the project.

**Primary plan:** `libcamera-rs` for direct bindings to libcamera, which is what the Pi Camera Module 3 actually uses. Configure 640×480 @ 10fps, receive NV12 frames, encode to JPEG with `turbojpeg` on the CPU (the Pi 4's quad-core at 640×480 handles this in ~15ms per frame).

**Fallback plan (if libcamera-rs is too immature):** spawn `rpicam-still --output - --timeout 0 --nopreview --continuous 1 ...` as a subprocess and read JPEG frames from its stdout. Ugly, requires a process boundary, but it works today and has zero binding risk. We'd resort to this only if libcamera-rs blocks for more than a day of effort.

**Stretch plan:** use the Pi's hardware JPEG encoder through V4L2 `M2M` — saves 10ms per frame vs. software JPEG. Worth pursuing only after the binary is otherwise working.

### `network.rs`

Plain blocking `std::net::TcpStream`. Split into reader and writer with `try_clone()`. No TLS (we're on 192.168.x trusted LAN). Reconnect loop handles server restarts cleanly.

```rust
pub struct NetworkClient {
    stream: Option<TcpStream>,
    frame_rx: Receiver<(SensorData, Vec<u8>)>,   // from camera+sensors
    cmd_tx: Sender<MotorCommand>,                // to main
}

impl NetworkClient {
    pub fn run(&mut self) -> Result<()> {
        loop {
            self.connect_with_backoff()?;
            // spawn read half, run write half in this function
            // on disconnect: fall through, reconnect
        }
    }
}
```

### `main.rs`

Sets up GPIO, camera, and network. Spawns the three worker threads. Main thread receives commands and applies them to motors, with a `SystemTime`-based watchdog that emergency-stops if no command arrives within 1s.

Signal handling: `SIGTERM`/`SIGINT` set a shared `AtomicBool`, all threads check it between cycles, then main thread calls `emergency_stop()` on its way out. Clean shutdown even when killed by systemd or by the Python server pushing a stop.

---

## Build & deploy

### Cross-compilation

Install `cross` (Docker-based cross-compile toolchain):

```bash
cargo install cross
# on slmbeast:
cross build --target aarch64-unknown-linux-gnu --release
# produces: target/aarch64-unknown-linux-gnu/release/robotcar-pi
```

Why `cross` over native-on-Pi build: the Pi 4 (4GB RAM) compiles rust slowly and swaps on anything nontrivial. Cross-compile from slmbeast (32 cores, RTX 5090 idle) takes seconds.

### Deploy

```bash
./deploy/cross.sh  # builds + scps binary to thinktank
ssh thinktank "sudo systemctl restart robotcar-pi"
```

### Systemd unit (interim)

```ini
[Unit]
Description=Robotcar Pi driver
After=network-online.target

[Service]
Type=simple
User=aios
ExecStart=/home/aios/bin/robotcar-pi
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

This unit file is temporary scaffolding — it disappears in Option 3 when we move to a Buildroot image where the binary is PID 1.

---

## Testing strategy

### Unit tests (host, no hardware)

- `protocol.rs`: fixtures generated by the Python version → round-trip decode/encode in Rust
- `motors.rs`: `compensate()` is pure arithmetic — table-driven tests
- `sensors.rs`: `distance_from_pulse_us()` is pure arithmetic — table-driven tests

### Hardware-in-loop tests (on the Pi)

- `cargo run --bin test_motors` — spin each wheel for 500ms, log encoder-less "did it move?" confirmation
- `cargo run --bin test_sensors` — read all 5 sensors for 10 seconds, report dropout rate per channel
- `cargo run --bin test_camera` — capture 10 frames, save JPEGs, confirm nonzero sizes
- `cargo run --bin test_network` — connect to slmbeast, exchange one ping frame, confirm wire-format parity

### Integration test

Run the full binary against the real slmbeast server for one drive session. Compare JSONL logs (from slmbeast's training_logger) against a baseline Python session: same distribution of commands received, same frame rates, same sensor-reading densities.

**Acceptance criterion for parity:** median inference cycle time ≤ current Python version, sensor dropout rate ≤ current Python version, no regression in any override firing rate.

**Acceptance criterion for win:** HC-SR04 dropout rate meaningfully down on RL/RR (current Python version: RL is `None` ~100% of the time, RR ~20% of the time).

---

## Risks & open questions

| Risk | Likelihood | Mitigation |
|---|---|---|
| `libcamera-rs` immature / broken | **Medium** | Subprocess fallback to `rpicam-still` |
| rppal GPIO interrupts slow under load | Low | Busy-loop alternative; `pigpiod` fallback |
| Cross-compile fails on some dep (e.g. turbojpeg linking) | Low | Compile natively on Pi once, ship binary |
| PWM conflicts (hw PWM requires sysfs enabled at boot) | Low | Document `dtoverlay=pwm-2chan` in boot config |
| systemd unit conflicts with existing Python process | Low | Interim only; we'll kill the Python systemd unit before enabling the Rust one |
| Different compensation behavior (float arithmetic subtleties) | Low | Snapshot tests against Python-generated expected values |

Resolved decisions:

1. **Test affordances** — separate binaries in the same crate (`cargo run --bin test_motors`, `test_sensors`, `test_camera`, `test_network`). Only `robotcar-pi` ships to the Pi; test binaries stay on slmbeast as dev tools. Cargo's multi-binary support makes this trivial.
2. **Log format** — match Python's format byte-for-byte during migration via a custom `env_logger` formatter. After cutover, add `--log-format=json` as an opt-in so the Pi's logs can flow into the same training-data pipeline the server uses.
3. **Config** — compile-time constants in `config.rs` for hardware truth (GPIO pins, PWM frequency, ultrasonic timing), with a short list of environment-variable overrides for tunables. No TOML file, no writable filesystem dependency. Overrides:

```
ROBOTCAR_SERVER=192.168.1.234:5555
ROBOTCAR_COMP_FL=1.10
ROBOTCAR_COMP_FR=1.04
ROBOTCAR_COMP_RL=1.00
ROBOTCAR_COMP_RR=0.94
ROBOTCAR_RL_DEAD=false
ROBOTCAR_WATCHDOG_MS=1000
```

All three choices are Buildroot-friendly — nothing here depends on a read-write filesystem, systemd-specific features, or an installed Python runtime.

---

## Sequence of work

Concrete phases, each merge-able independently. Target: ~1 week of focused work, checkpoints daily.

1. **Scaffolding (half day)**
   - `cargo new`, `Cargo.toml` with deps, `cross` build working, skeleton `main.rs` that prints "hello from the Pi" over SSH deploy.
2. **Protocol (half day)**
   - Port `shared/protocol.py` → `protocol.rs`, with Python-fixture round-trip tests passing.
3. **Motors (1 day)**
   - `motors.rs` using rppal PWM + direction pins. Compensation logic. `test_motors` binary confirms all 4 wheels spin correctly with Python-equivalent behavior.
4. **Sensors (1–2 days)**
   - `sensors.rs` HC-SR04 timing loop. `test_sensors` binary logs 10s of readings per channel. Measure dropout rate; decide interrupt-poll vs. busy-loop based on data. **Success criterion: RL reads something other than `None`.**
5. **Camera (1–3 days, risk-adjusted)**
   - Prototype `libcamera-rs` capture + JPEG encode. If blocked within a day, fall back to `rpicam-still` subprocess. `test_camera` binary saves 10 frames.
6. **Network (half day)**
   - TCP client with reconnect loop. `test_network` binary confirms wire parity against slmbeast.
7. **Integration (1 day)**
   - Wire all threads together in `main.rs`. Run full drive session against the live slmbeast server. Compare training logs to a Python baseline.
8. **Cutover (half day)**
   - Disable Python systemd unit, enable Rust systemd unit. Verify auto-restart on power cycle. Document rollback path (single-line systemd swap).

At the cutover point, the Python code under `pi/` can be retired from the active deployment but kept in the repo as reference during the Buildroot phase.

---

## After this is done

Once we have a single binary doing the car-side work reliably, Option 3 becomes concrete:

- Build a Buildroot image with kernel + rppal-compatible sysfs + the Rust binary as PID 1 (no init system, no userland except our binary and a `/bin/sh` for emergency debug).
- Boot time drops from ~25 seconds (Raspberry Pi OS) to sub-3 seconds.
- Writable root filesystem disappears — SD card is immutable, eliminating SD-card-wear as a failure mode.
- SSH access becomes an opt-in emergency path, not a background service.

That's where the AIOS thesis gets tangible: a Pi that exists to be the robot's body, with no abstractions left that aren't serving that purpose.
