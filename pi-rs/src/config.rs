//! Compile-time hardware configuration + runtime-tunable parameters.
//!
//! GPIO pins are hardware truth — they only change when the Pi is physically
//! rewired, so they're compile-time `const`s. Everything tunable during a
//! driving session (server IP, compensation factors, watchdog timeout) comes
//! from environment variables with sensible defaults.
//!
//! This matches the design doc's Q3c decision: single binary, no config files,
//! no read-write filesystem dependency.

// ═══════════════════════════════════════════════════════════════════════════
// GPIO pin assignments (BCM numbering) — mirrors pi/config.py
// ═══════════════════════════════════════════════════════════════════════════

// Motor driver #1 — Front-Left + Rear-Left (shares one L298N)
pub const FL_FORWARD: u8 = 17;
pub const FL_BACKWARD: u8 = 27;
pub const FL_PWM: u8 = 12;
pub const RL_FORWARD: u8 = 22;
pub const RL_BACKWARD: u8 = 23;
pub const RL_PWM: u8 = 13;

// Motor driver #2 — Front-Right + Rear-Right
// fwd/bwd are swapped in hardware wiring; the Python config does the same.
pub const FR_FORWARD: u8 = 6;
pub const FR_BACKWARD: u8 = 5;
pub const FR_PWM: u8 = 18;
pub const RR_FORWARD: u8 = 26;
pub const RR_BACKWARD: u8 = 16;
pub const RR_PWM: u8 = 19;

// Dropped from 1 kHz to 100 Hz because rppal's software PWM starves when 4
// threads run at 1 kHz simultaneously — with ~1 ms periods, the scheduler
// can't keep 4 threads toggling reliably. 100 Hz (10 ms period) gives each
// thread an order of magnitude more scheduler headroom. L298N handles this
// fine; the only cost is a faint audible whine from the motors.
pub const PWM_FREQUENCY_HZ: f64 = 100.0;

// ═══════════════════════════════════════════════════════════════════════════
// Runtime-tunable: motor compensation + watchdog
// ═══════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Copy)]
pub struct MotorConfig {
    /// Speed multiplier per wheel, applied as `speed * comp` and clamped to [0, 255].
    /// Default values match pi/config.py after the March motor compensation pass:
    ///   FL=1.10 (front-heavy boost), FR=1.04, RL=1.00, RR=0.94 (right-pull trim).
    pub comp_fl: f32,
    pub comp_fr: f32,
    pub comp_rl: f32,
    pub comp_rr: f32,

    /// Informational flag only — when true, we log "RL motor dead" at startup.
    /// Actual motor muting is achieved by setting `ROBOTCAR_COMP_RL=0` on a
    /// separate env var. Matches Python's `rl_motor_dead` semantics.
    pub rl_dead: bool,

    /// Emergency-stop motors if no command received within this window.
    pub watchdog_ms: u64,
}

impl Default for MotorConfig {
    fn default() -> Self {
        Self {
            comp_fl: 1.10,
            comp_fr: 1.04,
            comp_rl: 1.00,
            comp_rr: 0.94,
            rl_dead: false,
            watchdog_ms: 1000,
        }
    }
}

impl MotorConfig {
    /// Read env vars and fall back to defaults. Called once at startup.
    pub fn from_env() -> Self {
        let d = Self::default();
        Self {
            comp_fl: env_f32("ROBOTCAR_COMP_FL", d.comp_fl),
            comp_fr: env_f32("ROBOTCAR_COMP_FR", d.comp_fr),
            comp_rl: env_f32("ROBOTCAR_COMP_RL", d.comp_rl),
            comp_rr: env_f32("ROBOTCAR_COMP_RR", d.comp_rr),
            rl_dead: env_bool("ROBOTCAR_RL_DEAD", d.rl_dead),
            watchdog_ms: env_u64("ROBOTCAR_WATCHDOG_MS", d.watchdog_ms),
        }
    }
}

fn env_f32(key: &str, default: f32) -> f32 {
    std::env::var(key).ok().and_then(|s| s.parse().ok()).unwrap_or(default)
}
fn env_bool(key: &str, default: bool) -> bool {
    std::env::var(key)
        .ok()
        .map(|s| matches!(s.to_lowercase().as_str(), "1" | "true" | "yes" | "on"))
        .unwrap_or(default)
}
fn env_u64(key: &str, default: u64) -> u64 {
    std::env::var(key).ok().and_then(|s| s.parse().ok()).unwrap_or(default)
}

// ═══════════════════════════════════════════════════════════════════════════
// Network
// ═══════════════════════════════════════════════════════════════════════════

pub fn server_address() -> String {
    std::env::var("ROBOTCAR_SERVER").unwrap_or_else(|_| "192.168.1.234:5555".into())
}
