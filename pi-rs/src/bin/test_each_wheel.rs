//! Diagnostic: spin each wheel individually at a clearly-audible duty cycle.
//! Runs at speed 200 on one motor at a time, holds for 2s, stops, pauses 1s, next.
//! Isolates concurrent-PWM issues from per-motor wiring/code issues.

use std::thread;
use std::time::Duration;

use anyhow::{Context, Result};
use log::info;
use rppal::gpio::{Gpio, OutputPin};

use robotcar_pi::{config::{self, PWM_FREQUENCY_HZ}, init_logging};

const SPEED: u8 = 200;
const HOLD_MS: u64 = 2000;
const PAUSE_MS: u64 = 1000;

struct Wheel<'a> {
    name: &'a str,
    fwd: OutputPin,
    bwd: OutputPin,
    pwm: OutputPin,
}

impl<'a> Wheel<'a> {
    fn forward_on(&mut self) -> Result<()> {
        self.fwd.set_high();
        self.bwd.set_low();
        self.pwm.set_pwm_frequency(PWM_FREQUENCY_HZ, SPEED as f64 / 255.0)?;
        Ok(())
    }
    fn stop(&mut self) -> Result<()> {
        self.fwd.set_low();
        self.bwd.set_low();
        self.pwm.set_pwm_frequency(PWM_FREQUENCY_HZ, 0.0)?;
        Ok(())
    }
}

fn main() -> Result<()> {
    init_logging();
    info!("test_each_wheel starting — expect 4 wheels to spin in isolation");

    let gpio = Gpio::new().context("open /dev/gpiomem")?;
    let mut wheels: Vec<Wheel> = vec![
        Wheel {
            name: "FL",
            fwd: gpio.get(config::FL_FORWARD)?.into_output(),
            bwd: gpio.get(config::FL_BACKWARD)?.into_output(),
            pwm: gpio.get(config::FL_PWM)?.into_output(),
        },
        Wheel {
            name: "FR",
            fwd: gpio.get(config::FR_FORWARD)?.into_output(),
            bwd: gpio.get(config::FR_BACKWARD)?.into_output(),
            pwm: gpio.get(config::FR_PWM)?.into_output(),
        },
        Wheel {
            name: "RL",
            fwd: gpio.get(config::RL_FORWARD)?.into_output(),
            bwd: gpio.get(config::RL_BACKWARD)?.into_output(),
            pwm: gpio.get(config::RL_PWM)?.into_output(),
        },
        Wheel {
            name: "RR",
            fwd: gpio.get(config::RR_FORWARD)?.into_output(),
            bwd: gpio.get(config::RR_BACKWARD)?.into_output(),
            pwm: gpio.get(config::RR_PWM)?.into_output(),
        },
    ];

    // Ensure all stopped to start.
    for w in wheels.iter_mut() {
        w.stop()?;
    }
    thread::sleep(Duration::from_millis(500));

    for w in wheels.iter_mut() {
        info!(
            "{} forward @ duty={:.2} (pins fwd/bwd/pwm = {:?}/{:?}/{:?})",
            w.name,
            SPEED as f64 / 255.0,
            w.fwd.pin(),
            w.bwd.pin(),
            w.pwm.pin(),
        );
        w.forward_on()?;
        thread::sleep(Duration::from_millis(HOLD_MS));
        w.stop()?;
        thread::sleep(Duration::from_millis(PAUSE_MS));
    }

    info!("Done");
    Ok(())
}
