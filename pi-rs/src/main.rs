//! robotcar-pi — Pi-side driver
//!
//! Phases in flight:
//!   1. ✓ scaffolding + cross-compile toolchain
//!   2. ✓ protocol port (Python-compatible wire format)
//!   3. ✓ motors (rppal software PWM, compensation)
//!   4. sensors (HC-SR04 timing)
//!   5. camera (libcamera)
//!   6. network (TCP client)
//!   7. integration
//!   8. cutover

use anyhow::Result;
use log::info;

use robotcar_pi::{hostname, init_logging, protocol::{MotorCommand, SensorData}};

fn main() -> Result<()> {
    init_logging();

    let version = env!("CARGO_PKG_VERSION");
    let arch = std::env::consts::ARCH;
    let host = hostname().unwrap_or_else(|| "unknown".into());

    info!("robotcar-pi v{version} ({arch}) starting on host {host}");
    info!("Phase 3 complete. Hardware access wired; no integration yet.");

    // Smoke-test the protocol module (no hardware needed).
    let cmd = MotorCommand::forward(190, 2000);
    info!("demo MotorCommand::forward(190,2000) = {:02x?}", cmd.to_bytes());

    let sensors = SensorData { fc: 0, fl: 627, fr: 537, rl: 0, rr: 90 };
    let cm = sensors.to_cm();
    info!(
        "demo SensorData FL/FR/RL/RR = {:?}/{:?}/{:?}/{:?} cm",
        cm.fl, cm.fr, cm.rl, cm.rr
    );

    info!("(motor init deferred to integration phase — run test_motors to exercise wheels)");
    Ok(())
}
