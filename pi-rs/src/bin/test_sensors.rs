//! test_sensors — exercise all 5 ultrasonic sensors and report dropout rates.
//!
//! Runs for 10 seconds, logs each read cycle, then summarizes which channels
//! are returning real values and which are timing out. The Phase 4 success
//! criterion is RL dropout dropping significantly from Python's ~100%.

use std::time::{Duration, Instant};

use anyhow::Result;
use log::info;

use robotcar_pi::{init_logging, protocol::SensorData, sensors::UltrasonicArray};

const RUN_DURATION: Duration = Duration::from_secs(10);

#[derive(Default)]
struct ChannelStats {
    total: u32,
    valid: u32,
    sum_cm: f32,
    min_cm: f32,
    max_cm: f32,
}

impl ChannelStats {
    fn record(&mut self, mm: u16) {
        self.total += 1;
        if mm > 0 {
            self.valid += 1;
            let cm = mm as f32 / 10.0;
            self.sum_cm += cm;
            if self.min_cm == 0.0 || cm < self.min_cm {
                self.min_cm = cm;
            }
            if cm > self.max_cm {
                self.max_cm = cm;
            }
        }
    }

    fn report(&self, name: &str) {
        let pct = if self.total == 0 { 0.0 } else {
            100.0 * self.valid as f32 / self.total as f32
        };
        if self.valid == 0 {
            info!("  {name}: 0/{} valid (100% dropout)", self.total);
        } else {
            let avg = self.sum_cm / self.valid as f32;
            info!(
                "  {name}: {}/{} valid ({:.1}%), range {:.1}-{:.1}cm, avg {:.1}cm",
                self.valid, self.total, pct, self.min_cm, self.max_cm, avg
            );
        }
    }
}

fn main() -> Result<()> {
    init_logging();
    info!("test_sensors — sampling all 5 channels for 10 seconds");

    let mut array = UltrasonicArray::new()?;

    let mut fc = ChannelStats::default();
    let mut fl = ChannelStats::default();
    let mut fr = ChannelStats::default();
    let mut rl = ChannelStats::default();
    let mut rr = ChannelStats::default();

    let deadline = Instant::now() + RUN_DURATION;
    let mut cycle = 0u32;
    while Instant::now() < deadline {
        let SensorData { fc: a, fl: b, fr: c, rl: d, rr: e } = array.read_all();
        fc.record(a);
        fl.record(b);
        fr.record(c);
        rl.record(d);
        rr.record(e);
        cycle += 1;

        let fmt = |mm: u16| -> String {
            if mm == 0 { "---".into() } else { format!("{:6.1}cm", mm as f32 / 10.0) }
        };
        info!(
            "cycle {:3}: FC={} FL={} FR={} RL={} RR={}",
            cycle, fmt(a), fmt(b), fmt(c), fmt(d), fmt(e)
        );
    }

    info!("");
    info!("=== Summary ({} cycles) ===", cycle);
    fc.report("FC");
    fl.report("FL");
    fr.report("FR");
    rl.report("RL");
    rr.report("RR");
    info!("");
    info!("Phase 4 target: RL valid-rate > 0%. Python baseline: ~0%.");

    Ok(())
}
