//! test_motors — standalone hardware check for the 4-motor controller.
//!
//! Mirrors `python3 -m pi.car_hardware --test-motors`: cycles through
//! forward / backward / rotate-left / rotate-right for 1s each with a 0.5s
//! pause between, then emergency-stops.
//!
//! Usage on the Pi:  ~/bin/test_motors
//! Deploy from slmbeast:
//!   cross build --target aarch64-unknown-linux-gnu --release --bin test_motors
//!   scp target/aarch64-unknown-linux-gnu/release/test_motors thinktank:~/bin/

use std::thread;
use std::time::Duration;

use anyhow::Result;
use log::info;

use robotcar_pi::{config::MotorConfig, init_logging, motors::MotorController, protocol::MotorCommand};

const TEST_SPEED: u8 = 150;
const TEST_MS: u64 = 1000;
const PAUSE_MS: u64 = 500;

fn main() -> Result<()> {
    init_logging();
    info!("test_motors starting — batteries should be connected");

    let cfg = MotorConfig::from_env();
    let mut controller = MotorController::new(cfg)?;

    let tests: &[(&str, MotorCommand)] = &[
        ("Forward",       MotorCommand::forward(TEST_SPEED, 0)),
        ("Backward",      MotorCommand::backward(TEST_SPEED, 0)),
        ("Rotate Left",   MotorCommand::rotate_left(TEST_SPEED, 0)),
        ("Rotate Right",  MotorCommand::rotate_right(TEST_SPEED, 0)),
    ];

    for (name, cmd) in tests {
        info!("Testing: {}", name);
        controller.apply(cmd)?;
        thread::sleep(Duration::from_millis(TEST_MS));
        controller.emergency_stop()?;
        thread::sleep(Duration::from_millis(PAUSE_MS));
    }

    info!("Motor test complete");
    Ok(())
}
