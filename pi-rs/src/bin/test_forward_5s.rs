//! One-off: drive all 4 wheels forward at test speed for 5 seconds.

use std::thread;
use std::time::Duration;

use anyhow::Result;
use log::info;

use robotcar_pi::{config::MotorConfig, init_logging, motors::MotorController, protocol::MotorCommand};

fn main() -> Result<()> {
    init_logging();
    info!("test_forward_5s starting");

    let cfg = MotorConfig::from_env();
    let mut controller = MotorController::new(cfg)?;

    info!("Forward at speed 150 for 5 seconds...");
    controller.apply(&MotorCommand::forward(150, 0))?;
    thread::sleep(Duration::from_secs(5));
    controller.emergency_stop()?;

    info!("Done");
    Ok(())
}
