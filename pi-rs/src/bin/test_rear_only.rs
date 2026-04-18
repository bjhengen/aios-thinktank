//! Diagnostic: spin ONLY the rear two wheels at the same time. If they spin
//! here (but not when all 4 are active), the failure mode is "4 concurrent
//! software-PWM threads starve each other" rather than anything wiring-specific.

use std::thread;
use std::time::Duration;

use anyhow::{Context, Result};
use log::info;
use rppal::gpio::{Gpio, OutputPin};

use robotcar_pi::{config::{self, PWM_FREQUENCY_HZ}, init_logging};

fn main() -> Result<()> {
    init_logging();
    info!("test_rear_only — spin RL+RR together at duty 0.78 for 3s");

    let gpio = Gpio::new().context("open /dev/gpiomem")?;

    let mut rl_fwd: OutputPin = gpio.get(config::RL_FORWARD)?.into_output();
    let mut rl_bwd: OutputPin = gpio.get(config::RL_BACKWARD)?.into_output();
    let mut rl_pwm: OutputPin = gpio.get(config::RL_PWM)?.into_output();

    let mut rr_fwd: OutputPin = gpio.get(config::RR_FORWARD)?.into_output();
    let mut rr_bwd: OutputPin = gpio.get(config::RR_BACKWARD)?.into_output();
    let mut rr_pwm: OutputPin = gpio.get(config::RR_PWM)?.into_output();

    // Direction: forward on both
    rl_fwd.set_high();
    rl_bwd.set_low();
    rr_fwd.set_high();
    rr_bwd.set_low();

    // Start PWM on both rears
    rl_pwm.set_pwm_frequency(PWM_FREQUENCY_HZ, 200.0 / 255.0)?;
    rr_pwm.set_pwm_frequency(PWM_FREQUENCY_HZ, 200.0 / 255.0)?;

    thread::sleep(Duration::from_secs(3));

    // Stop
    rl_fwd.set_low();
    rr_fwd.set_low();
    rl_pwm.set_pwm_frequency(PWM_FREQUENCY_HZ, 0.0)?;
    rr_pwm.set_pwm_frequency(PWM_FREQUENCY_HZ, 0.0)?;

    info!("Done");
    Ok(())
}
