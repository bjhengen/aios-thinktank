//! Motor controller — 4 DC motors, 2x L298N drivers, software PWM via rppal.
//!
//! Port of `pi/motor_controller.py` with two intentional differences:
//!
//! 1. `apply()` is non-blocking — it only sets GPIO state. Duration timing
//!    happens at a higher layer (watchdog thread in integration phase), so
//!    the motor path never holds the call site.
//! 2. Shutdown safety is handled by rppal's `reset_on_drop`: when the
//!    `OutputPin`s in this struct are dropped, they revert to Input mode,
//!    floating the L298N inputs and safely coasting the motors to stop.
//!    This covers panic / SIGTERM / normal exit without an explicit handler.
//!    (Hard power loss is a chassis problem, not a software problem.)

use std::time::Instant;

use anyhow::{Context, Result};
use log::{info, warn};
use rppal::gpio::{Gpio, OutputPin};

use crate::config::{self, MotorConfig, PWM_FREQUENCY_HZ};
use crate::protocol::{Direction, MotorCommand};

const TARGET: &str = "robotcar_pi::motors";

// ═══════════════════════════════════════════════════════════════════════════
// Per-motor pins
// ═══════════════════════════════════════════════════════════════════════════

struct MotorPins {
    fwd: OutputPin,
    bwd: OutputPin,
    pwm: OutputPin,
    label: &'static str,
}

impl MotorPins {
    fn new(
        gpio: &Gpio,
        fwd_num: u8,
        bwd_num: u8,
        pwm_num: u8,
        label: &'static str,
    ) -> Result<Self> {
        let fwd = gpio
            .get(fwd_num)
            .with_context(|| format!("{label}: get fwd pin {fwd_num}"))?
            .into_output();
        let bwd = gpio
            .get(bwd_num)
            .with_context(|| format!("{label}: get bwd pin {bwd_num}"))?
            .into_output();
        let pwm = gpio
            .get(pwm_num)
            .with_context(|| format!("{label}: get pwm pin {pwm_num}"))?
            .into_output();
        Ok(Self { fwd, bwd, pwm, label })
    }

    fn apply(&mut self, speed: u8, dir: Direction) -> Result<()> {
        match dir {
            Direction::Forward => {
                self.fwd.set_high();
                self.bwd.set_low();
            }
            Direction::Backward => {
                self.fwd.set_low();
                self.bwd.set_high();
            }
            Direction::Stop => {
                self.fwd.set_low();
                self.bwd.set_low();
            }
        }
        let duty = if dir == Direction::Stop {
            0.0
        } else {
            speed as f64 / 255.0
        };
        self.pwm
            .set_pwm_frequency(PWM_FREQUENCY_HZ, duty)
            .with_context(|| format!("{}: set PWM duty={:.3}", self.label, duty))?;
        Ok(())
    }

    fn stop(&mut self) -> Result<()> {
        self.fwd.set_low();
        self.bwd.set_low();
        self.pwm
            .set_pwm_frequency(PWM_FREQUENCY_HZ, 0.0)
            .with_context(|| format!("{}: clear PWM", self.label))?;
        Ok(())
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Compensation — pure function, fully unit-testable without hardware
// ═══════════════════════════════════════════════════════════════════════════

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub struct CompensatedCommand {
    pub fl: (u8, Direction),
    pub fr: (u8, Direction),
    pub rl: (u8, Direction),
    pub rr: (u8, Direction),
    pub duration_ms: u16,
}

/// Apply per-motor compensation factors to a MotorCommand.
/// Mirrors `pi/motor_controller.py::_compensate_command` byte-for-byte, including
/// Python's `int()`-toward-zero truncation (which matches `f32 as u8` in Rust).
pub fn compensate(cmd: &MotorCommand, cfg: &MotorConfig) -> CompensatedCommand {
    let clamp = |scaled: f32| -> u8 {
        let v = scaled.max(0.0).min(255.0);
        v as u8
    };
    CompensatedCommand {
        fl: (clamp(cmd.left_speed as f32 * cfg.comp_fl), cmd.left_dir),
        fr: (clamp(cmd.right_speed as f32 * cfg.comp_fr), cmd.right_dir),
        rl: (clamp(cmd.left_speed as f32 * cfg.comp_rl), cmd.left_dir),
        rr: (clamp(cmd.right_speed as f32 * cfg.comp_rr), cmd.right_dir),
        duration_ms: cmd.duration_ms,
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// MotorController — the live hardware interface
// ═══════════════════════════════════════════════════════════════════════════

pub struct MotorController {
    fl: MotorPins,
    fr: MotorPins,
    rl: MotorPins,
    rr: MotorPins,
    cfg: MotorConfig,
    last_command: Instant,
}

impl MotorController {
    pub fn new(cfg: MotorConfig) -> Result<Self> {
        let gpio = Gpio::new().context("opening /dev/gpiomem (is the user in the 'gpio' group?)")?;

        let mut fl = MotorPins::new(&gpio, config::FL_FORWARD, config::FL_BACKWARD, config::FL_PWM, "FL")?;
        let mut fr = MotorPins::new(&gpio, config::FR_FORWARD, config::FR_BACKWARD, config::FR_PWM, "FR")?;
        let mut rl = MotorPins::new(&gpio, config::RL_FORWARD, config::RL_BACKWARD, config::RL_PWM, "RL")?;
        let mut rr = MotorPins::new(&gpio, config::RR_FORWARD, config::RR_BACKWARD, config::RR_PWM, "RR")?;

        // Start with all motors stopped — direction pins LOW, PWM duty 0.
        fl.stop()?;
        fr.stop()?;
        rl.stop()?;
        rr.stop()?;

        if cfg.rl_dead {
            warn!(target: TARGET, "RL motor compensation ENABLED (dead-motor flag set)");
        }
        info!(
            target: TARGET,
            "MotorController ready: comp FL={:.2} FR={:.2} RL={:.2} RR={:.2}, PWM={} Hz",
            cfg.comp_fl, cfg.comp_fr, cfg.comp_rl, cfg.comp_rr, PWM_FREQUENCY_HZ as u32,
        );

        Ok(Self { fl, fr, rl, rr, cfg, last_command: Instant::now() })
    }

    /// Apply a motor command. Non-blocking — duration is metadata only; the
    /// integration-layer watchdog decides when to auto-stop.
    pub fn apply(&mut self, cmd: &MotorCommand) -> Result<()> {
        let c = compensate(cmd, &self.cfg);
        self.fl.apply(c.fl.0, c.fl.1)?;
        self.fr.apply(c.fr.0, c.fr.1)?;
        self.rl.apply(c.rl.0, c.rl.1)?;
        self.rr.apply(c.rr.0, c.rr.1)?;
        self.last_command = Instant::now();
        Ok(())
    }

    pub fn emergency_stop(&mut self) -> Result<()> {
        warn!(target: TARGET, "EMERGENCY STOP");
        self.fl.stop()?;
        self.fr.stop()?;
        self.rl.stop()?;
        self.rr.stop()?;
        Ok(())
    }

    pub fn time_since_last_command(&self) -> std::time::Duration {
        self.last_command.elapsed()
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Tests — pure-function compensation against Python-generated fixtures
// ═══════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    fn default_cfg() -> MotorConfig {
        MotorConfig::default()
    }

    #[test]
    fn compensate_forward_190_matches_python() {
        // Python: MotorCommand(190, 190, FORWARD, FORWARD) with default comps
        //   fl = min(255, int(190 * 1.10)) = 209
        //   fr = min(255, int(190 * 1.04)) = 197
        //   rl = min(255, int(190 * 1.00)) = 190
        //   rr = min(255, int(190 * 0.94)) = 178
        let c = compensate(&MotorCommand::forward(190, 0), &default_cfg());
        assert_eq!(c.fl, (209, Direction::Forward));
        assert_eq!(c.fr, (197, Direction::Forward));
        assert_eq!(c.rl, (190, Direction::Forward));
        assert_eq!(c.rr, (178, Direction::Forward));
    }

    #[test]
    fn compensate_stop_produces_zero_speed() {
        let c = compensate(&MotorCommand::stop(), &default_cfg());
        assert_eq!(c.fl, (0, Direction::Stop));
        assert_eq!(c.fr, (0, Direction::Stop));
        assert_eq!(c.rl, (0, Direction::Stop));
        assert_eq!(c.rr, (0, Direction::Stop));
    }

    #[test]
    fn compensate_clamps_above_255() {
        // left_speed=240 * fl_comp 1.10 = 264, must clamp to 255
        let cmd = MotorCommand::forward(240, 0);
        let c = compensate(&cmd, &default_cfg());
        assert_eq!(c.fl.0, 255);
    }

    #[test]
    fn compensate_preserves_direction_per_side() {
        // Rotate-right: left=FORWARD, right=BACKWARD
        //   FL and RL should be FORWARD; FR and RR should be BACKWARD.
        let c = compensate(&MotorCommand::rotate_right(220, 0), &default_cfg());
        assert_eq!(c.fl.1, Direction::Forward);
        assert_eq!(c.rl.1, Direction::Forward);
        assert_eq!(c.fr.1, Direction::Backward);
        assert_eq!(c.rr.1, Direction::Backward);
    }

    #[test]
    fn compensate_dead_rl_zeros_rear_left_speed() {
        // When comp_rl=0.0 is set (via ROBOTCAR_COMP_RL env), RL motor gets zero speed.
        let cfg = MotorConfig { comp_rl: 0.0, ..MotorConfig::default() };
        let c = compensate(&MotorCommand::forward(255, 0), &cfg);
        assert_eq!(c.rl.0, 0);
        assert!(c.fl.0 > 0);
    }
}
