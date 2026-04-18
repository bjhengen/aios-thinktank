//! HC-SR04 ultrasonic sensor array.
//!
//! Port of `pi/ultrasonic_sensors.py`. The algorithm is straightforward —
//! pulse-trigger, busy-wait for rising edge on echo, time the pulse width
//! to falling edge — but the actual *value* of this port over Python is that
//! Rust's busy-wait doesn't sit under the GIL. Python's reads suffer from the
//! interpreter parking the measuring thread for many milliseconds at a
//! time, mid-pulse, corrupting the pulse-width measurement. The RL sensor
//! has been returning `None` roughly 100% of the time in Python — the
//! success criterion for Phase 4 is making that number drop.
//!
//! Sequential firing, not parallel. All five sensors are triggered one at
//! a time with a short inter-read delay, same as Python. Parallel firing
//! risks acoustic crosstalk (FL's burst picked up by FR) which is a worse
//! class of failure than an occasional timeout.

use std::thread;
use std::time::{Duration, Instant};

use anyhow::{Context, Result};
use log::{info, trace};
use rppal::gpio::{Gpio, InputPin, Level, OutputPin};

use crate::config::{
    self, US_INTER_READ_MS, US_MAX_CM, US_MIN_CM, US_SPEED_OF_SOUND_CM_PER_US, US_TIMEOUT_US,
};
use crate::protocol::SensorData;

const TARGET: &str = "robotcar_pi::sensors";

// ═══════════════════════════════════════════════════════════════════════════
// Single sensor
// ═══════════════════════════════════════════════════════════════════════════

pub struct Sensor {
    pub name: &'static str,
    trig: OutputPin,
    echo: InputPin,
}

impl Sensor {
    fn new(gpio: &Gpio, name: &'static str, trig_num: u8, echo_num: u8) -> Result<Self> {
        let mut trig = gpio
            .get(trig_num)
            .with_context(|| format!("{name}: get trig pin {trig_num}"))?
            .into_output();
        trig.set_low();
        let echo = gpio
            .get(echo_num)
            .with_context(|| format!("{name}: get echo pin {echo_num}"))?
            .into_input();
        Ok(Self { name, trig, echo })
    }

    /// Take a single measurement. Returns `None` if the sensor times out
    /// waiting for either edge, or if the computed distance is outside the
    /// physical valid range.
    ///
    /// Blocks the current thread for up to 2×`US_TIMEOUT_US` microseconds.
    pub fn measure(&mut self) -> Option<f32> {
        // Send a 10μs HIGH pulse on TRIG.
        self.trig.set_high();
        busy_wait_us(10);
        self.trig.set_low();

        // Wait for the echo to go HIGH. Bail if it never does.
        let deadline = Instant::now() + Duration::from_micros(US_TIMEOUT_US);
        while self.echo.read() == Level::Low {
            if Instant::now() >= deadline {
                trace!(target: TARGET, "{}: timeout waiting for rising edge", self.name);
                return None;
            }
        }
        let pulse_start = Instant::now();

        // Now time the HIGH portion.
        let fall_deadline = pulse_start + Duration::from_micros(US_TIMEOUT_US);
        while self.echo.read() == Level::High {
            if Instant::now() >= fall_deadline {
                trace!(target: TARGET, "{}: timeout waiting for falling edge", self.name);
                return None;
            }
        }
        let pulse_us = pulse_start.elapsed().as_micros() as f32;

        // Distance = (pulse_us × 0.0343) / 2  →  one-way speed-of-sound
        let cm = pulse_us * US_SPEED_OF_SOUND_CM_PER_US / 2.0;
        if (US_MIN_CM..=US_MAX_CM).contains(&cm) {
            Some(cm)
        } else {
            trace!(
                target: TARGET,
                "{}: distance {:.1}cm out of range [{}, {}]",
                self.name, cm, US_MIN_CM, US_MAX_CM
            );
            None
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Array of 5 sensors, fired sequentially
// ═══════════════════════════════════════════════════════════════════════════

pub struct UltrasonicArray {
    pub fc: Sensor,
    pub fl: Sensor,
    pub fr: Sensor,
    pub rl: Sensor,
    pub rr: Sensor,
    fc_alive: bool,
    fl_alive: bool,
    fr_alive: bool,
    rl_alive: bool,
    rr_alive: bool,
}

impl UltrasonicArray {
    pub fn new() -> Result<Self> {
        let gpio = Gpio::new().context("opening /dev/gpiomem for ultrasonic sensors")?;
        let fc = Sensor::new(&gpio, "FC", config::US_FC_TRIG, config::US_FC_ECHO)?;
        let fl = Sensor::new(&gpio, "FL", config::US_FL_TRIG, config::US_FL_ECHO)?;
        let fr = Sensor::new(&gpio, "FR", config::US_FR_TRIG, config::US_FR_ECHO)?;
        let rl = Sensor::new(&gpio, "RL", config::US_RL_TRIG, config::US_RL_ECHO)?;
        let rr = Sensor::new(&gpio, "RR", config::US_RR_TRIG, config::US_RR_ECHO)?;

        let dead = config::dead_sensors();
        let is_alive = |name: &str| -> bool { !dead.iter().any(|d| d == name) };
        let fc_alive = is_alive("fc");
        let fl_alive = is_alive("fl");
        let fr_alive = is_alive("fr");
        let rl_alive = is_alive("rl");
        let rr_alive = is_alive("rr");

        // Let pins settle before the first trigger pulse. Matches Python.
        thread::sleep(Duration::from_millis(100));

        let alive_count = [fc_alive, fl_alive, fr_alive, rl_alive, rr_alive]
            .iter()
            .filter(|&&a| a)
            .count();
        info!(
            target: TARGET,
            "UltrasonicArray ready: {}/5 channels active, skipping [{}], {}ms inter-read",
            alive_count,
            dead.join(","),
            US_INTER_READ_MS
        );

        Ok(Self { fc, fl, fr, rl, rr, fc_alive, fl_alive, fr_alive, rl_alive, rr_alive })
    }

    /// Read each active sensor sequentially and return the protocol SensorData.
    /// Dead sensors are skipped (report 0 = invalid) to avoid their 40ms timeouts.
    pub fn read_all(&mut self) -> SensorData {
        let mut first = true;
        let mut read_one = |alive: bool, sensor: &mut Sensor| -> u16 {
            if !alive {
                return 0;
            }
            if !first {
                sleep_between();
            }
            first = false;
            measure_to_mm(sensor.measure())
        };

        let fc = read_one(self.fc_alive, &mut self.fc);
        let fl = read_one(self.fl_alive, &mut self.fl);
        let fr = read_one(self.fr_alive, &mut self.fr);
        let rl = read_one(self.rl_alive, &mut self.rl);
        let rr = read_one(self.rr_alive, &mut self.rr);
        SensorData { fc, fl, fr, rl, rr }
    }
}

fn sleep_between() {
    thread::sleep(Duration::from_millis(US_INTER_READ_MS));
}

fn measure_to_mm(cm: Option<f32>) -> u16 {
    match cm {
        Some(c) if c > 0.0 => (c * 10.0).round() as u16,
        _ => 0,
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Busy-wait with microsecond precision.
// ═══════════════════════════════════════════════════════════════════════════

/// Busy-wait for `us` microseconds. Used for the HC-SR04's 10μs trigger pulse,
/// where `thread::sleep` would oversleep by 50-200μs on Linux (the minimum
/// scheduler grain) and corrupt the pulse timing.
fn busy_wait_us(us: u64) {
    let target = Instant::now() + Duration::from_micros(us);
    while Instant::now() < target {
        std::hint::spin_loop();
    }
}

